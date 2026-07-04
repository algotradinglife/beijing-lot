#!/usr/bin/env python3
"""Evaluate the unified N=7 leg selector / depth gate.

The current production candidate is intentionally split into two arms:

* balanced: o4 + market_top_linegap_soft + 5 singles / 2 protected legs;
* tail: o8 + q_top + 5 singles / 2 protected legs.

Issue-level K-line state is emitted as monitoring data only. It does not
mechanically reduce stake or switch arms in this script.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_high_sp_anchor_protection import (
    annual_rows,
    build_anchor_candidates,
    compact_summary,
    issue_regime_rows,
    load_line_gaps,
    make_composition_tickets,
    o_fmt,
    option_stats,
    regime_summary_rows,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import (
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    group_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


@dataclass(frozen=True)
class ArmConfig:
    key: str
    strategy: str
    min_proxy_odds: float
    protection_policy: str


def parse_allocations(raw: str) -> list[tuple[str, dict[str, float]]]:
    out = []
    for item in raw.split(";"):
        item = item.strip()
        if not item:
            continue
        name, vals = item.split("=", 1)
        balanced_raw, tail_raw = vals.split(",", 1)
        weights = {
            "balanced": float(balanced_raw),
            "tail": float(tail_raw),
        }
        total = sum(weights.values())
        if total <= 0:
            raise ValueError(f"allocation must be positive: {item}")
        weights = {key: value / total for key, value in weights.items()}
        out.append((name.strip(), weights))
    return out


def allocate_rows_for_budget(
    rows: list[dict[str, object]],
    *,
    budget_units: float,
    strategy_name: str,
    portfolio_arm: str,
) -> list[dict[str, object]]:
    if budget_units <= 1e-9 or not rows:
        return []

    ranked = sorted(
        rows,
        key=lambda row: (
            float(row.get("pred_ev_per_stake", 0.0)),
            float(row.get("pred_hit_prob", 0.0)),
            -float(row.get("stake_units", 0.0)),
        ),
        reverse=True,
    )
    remaining = budget_units
    selected: list[tuple[dict[str, object], float]] = []
    for row in ranked:
        raw_stake = float(row["stake_units"])
        if raw_stake <= 0 or remaining <= 1e-9:
            break
        scale = 1.0 if raw_stake <= remaining + 1e-9 else remaining / raw_stake
        selected.append((row, scale))
        remaining -= raw_stake * scale

    spent = sum(float(row["stake_units"]) * scale for row, scale in selected)
    fill_scale = budget_units / spent if 0 < spent < budget_units else 1.0
    out = []
    for row, scale in selected:
        raw_stake = float(row["stake_units"])
        final_scale = scale * fill_scale
        converted = dict(row)
        converted["strategy"] = strategy_name
        converted["original_strategy"] = str(row["strategy"])
        converted["portfolio_arm"] = portfolio_arm
        converted["arm_budget_units"] = budget_units
        converted["raw_stake_units"] = raw_stake
        converted["stake_scale"] = final_scale
        converted["stake_units"] = raw_stake * final_scale
        converted["payout_units"] = float(row["payout_units"]) * final_scale
        converted["profit_units"] = float(row["profit_units"]) * final_scale
        converted["roi"] = (
            float(converted["profit_units"]) / float(converted["stake_units"])
            if float(converted["stake_units"]) > 0
            else float("nan")
        )
        converted["issue_budget_units"] = budget_units
        out.append(converted)
    return out


def build_portfolio_rows(
    raw_rows: list[dict[str, object]],
    *,
    allocations: list[tuple[str, dict[str, float]]],
    issue_budget_units: float,
    strategy_by_arm: dict[str, str],
    reallocate_unused_to_balanced: bool,
) -> list[dict[str, object]]:
    rows_by_arm_issue: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    issues: set[str] = set()
    for row in raw_rows:
        strategy = str(row["strategy"])
        issue = str(row["issue"])
        issues.add(issue)
        for arm, arm_strategy in strategy_by_arm.items():
            if strategy == arm_strategy:
                rows_by_arm_issue[(arm, issue)].append(row)
                break

    out: list[dict[str, object]] = []
    suffix = "_balFallback" if reallocate_unused_to_balanced else "_noFallback"
    for portfolio_name, weights in allocations:
        strategy_name = f"{portfolio_name}{suffix}"
        for issue in sorted(issues):
            budgets = {arm: issue_budget_units * weights.get(arm, 0.0) for arm in strategy_by_arm}
            missing_budget = 0.0
            for arm, budget in list(budgets.items()):
                if budget > 1e-9 and not rows_by_arm_issue.get((arm, issue)):
                    missing_budget += budget
                    budgets[arm] = 0.0

            if missing_budget > 1e-9 and reallocate_unused_to_balanced:
                if reallocate_unused_to_balanced and rows_by_arm_issue.get(("balanced", issue)):
                    budgets["balanced"] = budgets.get("balanced", 0.0) + missing_budget
                else:
                    available = [
                        arm
                        for arm in strategy_by_arm
                        if rows_by_arm_issue.get((arm, issue)) and budgets.get(arm, 0.0) > 1e-9
                    ]
                    total_available = sum(budgets[arm] for arm in available)
                    if total_available > 1e-9:
                        for arm in available:
                            budgets[arm] += missing_budget * budgets[arm] / total_available

            for arm, budget in budgets.items():
                out.extend(
                    allocate_rows_for_budget(
                        rows_by_arm_issue.get((arm, issue), []),
                        budget_units=budget,
                        strategy_name=strategy_name,
                        portfolio_arm=arm,
                    )
                )
    return out


def ex_best_issue_rows(issue_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        grouped[str(row["strategy"])].append(row)

    out = []
    for strategy, rows in sorted(grouped.items()):
        stake = sum(float(row["stake_units"]) for row in rows)
        profit = sum(float(row["profit_units"]) for row in rows)
        best = max((float(row["profit_units"]) for row in rows), default=0.0)
        out.append(
            {
                "strategy": strategy,
                "n_issues": len(rows),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else float("nan"),
                "best_issue_profit_units": best,
                "profit_ex_best_issue": profit - best,
                "roi_ex_best_issue": (profit - best) / stake if stake else float("nan"),
                "best_issue_profit_share": best / profit if profit > 0 and best > 0 else "",
            }
        )
    return out


def recent_subset(rows: list[dict[str, object]], min_year: int, max_year: int) -> list[dict[str, object]]:
    out = []
    for row in rows:
        issue = str(row["issue"])
        year = 2000 + int(issue[:2])
        if min_year <= year <= max_year:
            out.append(row)
    return out


def run(args: argparse.Namespace) -> None:
    arm_configs = [
        ArmConfig(
            key="balanced",
            strategy=f"selector_balanced_o4_market_top_linegap_soft_5s{args.target_protected_per_ticket}p_full{o_fmt(args.full_cover_min_proxy_odds)}",
            min_proxy_odds=4.0,
            protection_policy="market_top_linegap_soft",
        ),
        ArmConfig(
            key="tail",
            strategy=f"selector_tail_o8_q_top_5s{args.target_protected_per_ticket}p_full{o_fmt(args.full_cover_min_proxy_odds)}",
            min_proxy_odds=8.0,
            protection_policy="q_top",
        ),
    ]
    strategy_by_arm = {arm.key: arm.strategy for arm in arm_configs}
    allocations = parse_allocations(args.allocations)

    rows = load_action_rows(args.db, args.min_year)
    by_issue = group_by_issue(rows)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    min_anchor_score = threshold * args.min_anchor_score_ratio
    min_protected_score = threshold * args.min_protected_score_ratio
    line_gaps = load_line_gaps(args.db, args.snapshot)

    arm_ticket_rows: list[dict[str, object]] = []
    baseline_ticket_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        if any(issue >= test_issue for issue in train_issues):
            raise RuntimeError(f"leakage guard failed: train={train_issues}, test={test_issue}")
        train_rows = [row for issue in train_issues for row in by_issue[issue]]
        test_rows = by_issue[test_issue]
        train_start, train_end = train_issues[0], train_issues[-1]
        q_model, global_q = train_q_model(train_rows, snapshot=args.snapshot, prior_n=args.q_prior_n)
        stats_by_match = option_stats(test_rows, q_model, global_q, snapshot=args.snapshot)

        q_legs = build_q_baseline_legs(
            test_rows,
            q_model,
            global_q,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        q_tickets = make_tickets(
            q_legs,
            strategy="baseline_q_high_sp",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_start,
            train_end_issue=train_end,
            full_rows={},
            action_model={},
        )
        baseline_ticket_rows.extend(settle_ticket(ticket) for ticket in q_tickets)

        for arm in arm_configs:
            candidates, decisions = build_anchor_candidates(
                test_rows,
                stats_by_match,
                strategy=arm.strategy,
                line_gaps=line_gaps,
                min_proxy_odds=arm.min_proxy_odds,
                max_proxy_odds=args.max_proxy_odds,
                protection_policy=arm.protection_policy,
                min_anchor_score=min_anchor_score,
                min_protected_score=min_protected_score,
                protect_score_floor_ratio=args.protect_score_floor_ratio,
                full_cover_min_proxy_odds=args.full_cover_min_proxy_odds,
                full_protect_score_floor_ratio=args.full_protect_score_floor_ratio,
                line_gap_threshold=args.line_gap_threshold,
                draw_stability_max_abs_log_move=args.draw_stability_max_abs_log_move,
                line_gap_soft_boost=args.line_gap_soft_boost,
                line_gap_soft_haircut=args.line_gap_soft_haircut,
            )
            tickets = make_composition_tickets(
                candidates,
                strategy=arm.strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_start,
                train_end_issue=train_end,
                target_protected_per_ticket=args.target_protected_per_ticket,
                max_full_cover_per_ticket=args.max_full_cover_per_ticket,
                require_target_protection=True,
                max_leg_uses=args.max_composition_leg_uses,
            )
            for decision in decisions:
                decision["selector_arm"] = arm.key
                decision["selector_stage"] = "single_double_full_depth_gate"
            settled = [settle_ticket(ticket) for ticket in tickets]
            arm_ticket_rows.extend(settled)
            decision_rows.extend(decisions)
            coverage_rows.append(
                {
                    "strategy": arm.strategy,
                    "issue": test_issue,
                    "selector_arm": arm.key,
                    "n_candidate_rows": len(candidates),
                    "n_tickets": len(tickets),
                    "n_settled_rows": len(settled),
                    "min_proxy_odds": arm.min_proxy_odds,
                    "protection_policy": arm.protection_policy,
                }
            )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_start,
                "train_end_issue": train_end,
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "n_train_rows": len(train_rows),
                "n_test_rows": len(test_rows),
                "n_baseline_tickets": len(q_tickets),
            }
        )

    portfolio_rows = build_portfolio_rows(
        arm_ticket_rows,
        allocations=allocations,
        issue_budget_units=args.issue_budget_units,
        strategy_by_arm=strategy_by_arm,
        reallocate_unused_to_balanced=args.reallocate_unused_to_balanced,
    )
    baseline_budget_rows = budgeted_ticket_rows(
        baseline_ticket_rows,
        issue_budget_units=args.issue_budget_units,
        fractional=True,
    )
    budget_rows = portfolio_rows + baseline_budget_rows

    raw_summary = summarize_tickets(arm_ticket_rows + baseline_ticket_rows)
    raw_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    annual = annual_rows(budget_rows)
    issue_profit = issue_profit_rows(budget_rows)
    regime = issue_regime_rows(issue_profit, big_loss_roi_threshold=args.regime_big_loss_roi_threshold)
    regime_summary = regime_summary_rows(regime)
    ex_best = ex_best_issue_rows(issue_profit)
    recent_summary = summarize_tickets(recent_subset(budget_rows, 2023, 2025))
    recent_summary.sort(key=lambda row: float(row["roi"]), reverse=True)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "unified_leg_selector_raw_tickets.csv", arm_ticket_rows + baseline_ticket_rows)
    write_csv(out / "unified_leg_selector_raw_summary.csv", raw_summary)
    write_csv(out / "unified_leg_selector_budget_fractional_tickets.csv", budget_rows)
    write_csv(out / "unified_leg_selector_summary.csv", summary)
    write_csv(out / "unified_leg_selector_recent_2023_2025_summary.csv", recent_summary)
    write_csv(out / "unified_leg_selector_annual_summary.csv", annual)
    write_csv(out / "unified_leg_selector_issue_profit.csv", issue_profit)
    write_csv(out / "unified_leg_selector_regime.csv", regime)
    write_csv(out / "unified_leg_selector_regime_summary.csv", regime_summary)
    write_csv(out / "unified_leg_selector_ex_best_issue_summary.csv", ex_best)
    write_csv(out / "unified_leg_selector_decisions.csv", decision_rows)
    write_csv(out / "unified_leg_selector_coverage.csv", coverage_rows)
    write_csv(out / "unified_leg_selector_windows.csv", window_rows)

    report = [
        "# N=7 unified leg selector / depth gate",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Min year: `{args.min_year}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Issue budget: `{args.issue_budget_units}`",
        f"- Allocations: `{args.allocations}`",
        f"- Reallocate unused budget to balanced: `{args.reallocate_unused_to_balanced}`",
        f"- Balanced arm: `{strategy_by_arm['balanced']}`",
        f"- Tail arm: `{strategy_by_arm['tail']}`",
        f"- K-line big-loss threshold: `{args.regime_big_loss_roi_threshold}`",
        "",
        "## Same-Budget Summary",
        "",
        md_table(compact_summary(summary), limit=80),
        "## 2023-2025 Same-Budget Summary",
        "",
        md_table(compact_summary(recent_summary), limit=80),
        "## Ex-Best Issue Summary",
        "",
        md_table(ex_best, limit=80),
        "## K-Line Regime Summary",
        "",
        md_table(regime_summary, limit=120),
        "## Raw Arm Summary",
        "",
        md_table(compact_summary(raw_summary), limit=80),
        "## Files",
        "",
        "- `unified_leg_selector_summary.csv`",
        "- `unified_leg_selector_recent_2023_2025_summary.csv`",
        "- `unified_leg_selector_annual_summary.csv`",
        "- `unified_leg_selector_issue_profit.csv`",
        "- `unified_leg_selector_regime.csv`",
        "- `unified_leg_selector_regime_summary.csv`",
        "- `unified_leg_selector_ex_best_issue_summary.csv`",
        "- `unified_leg_selector_decisions.csv`",
        "- `unified_leg_selector_budget_fractional_tickets.csv`",
        "",
    ]
    (out / "unified_leg_selector_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'unified_leg_selector_report.md'}")
    print(f"Wrote {len(budget_rows)} budgeted rows and {len(decision_rows)} decision rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_unified_leg_selector"))
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--train-issues", type=int, default=24)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--max-proxy-odds", type=float, default=30.0)
    parser.add_argument("--min-anchor-score-ratio", type=float, default=0.0)
    parser.add_argument("--min-protected-score-ratio", type=float, default=0.0)
    parser.add_argument("--protect-score-floor-ratio", type=float, default=0.85)
    parser.add_argument("--target-protected-per-ticket", type=int, default=2)
    parser.add_argument("--max-full-cover-per-ticket", type=int, default=1)
    parser.add_argument("--max-composition-leg-uses", type=int, default=0)
    parser.add_argument("--full-cover-min-proxy-odds", type=float, default=12.0)
    parser.add_argument("--full-protect-score-floor-ratio", type=float, default=0.80)
    parser.add_argument("--line-gap-threshold", type=float, default=0.5)
    parser.add_argument("--draw-stability-max-abs-log-move", type=float, default=0.08)
    parser.add_argument("--line-gap-soft-boost", type=float, default=1.12)
    parser.add_argument("--line-gap-soft-haircut", type=float, default=0.85)
    parser.add_argument("--regime-big-loss-roi-threshold", type=float, default=-0.75)
    parser.add_argument(
        "--allocations",
        default=(
            "unified_bal100_tail0=1,0;"
            "unified_bal80_tail20=0.8,0.2;"
            "unified_bal70_tail30=0.7,0.3;"
            "unified_bal60_tail40=0.6,0.4;"
            "unified_bal0_tail100=0,1"
        ),
    )
    parser.add_argument("--reallocate-unused-to-balanced", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
