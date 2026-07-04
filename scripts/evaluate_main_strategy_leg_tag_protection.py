#!/usr/bin/env python3
"""Apply p/q leg-decision tags back to the current main N7 strategy.

The p-first depth allocator is not a standalone replacement, but its per-leg
table is useful.  This script keeps the current 256-unit main strategy fixed
and tests small protected sleeves selected by those leg-level tags.
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows  # noqa: E402
from scripts.evaluate_n7_same_ticket_leg_coverage import (  # noqa: E402
    action_code_for,
    action_lookup,
    parse_ticket,
    selection_set,
)
from scripts.evaluate_p_core_q_overlay_arm import (  # noqa: E402
    BASELINE_PORTFOLIOS,
    DEFAULT_DB,
    annual_rows,
    fnum,
    load_baseline_issue_rows,
    load_issue_calendar,
    md_table,
    read_csv_rows,
    row_order,
    summarize,
    write_csv,
    write_equity_svg,
)
from scripts.walkforward_beidan_strategy_eval import (  # noqa: E402
    ActionRow,
    Leg,
    Ticket,
    load_action_rows,
    settle_ticket,
)


DEFAULT_SELECTED = ROOT / "results/high_n_selector_plus2026_linefill_20260630/high_n_selector_enriched_source_tickets.csv"
DEFAULT_BASELINE = ROOT / "results/n7_sleeve_mix_capital_plus2026_linefill_20260630/sleeve_mix_issue_profit.csv"
DEFAULT_OLD_ARMS = ROOT / "results/n7_multi_leg_protection_overlay_large_plus2026_linefill_20260630/multi_leg_protection_issue_profit.csv"
DEFAULT_LEG_DECISIONS = ROOT / "results/p_first_depth_allocator_384_20260701/p_first_depth_allocator_leg_decisions.csv"
DEFAULT_OUT = ROOT / "results/main_strategy_leg_tag_protection_384_20260701"
DEFAULT_REPORT = ROOT / "docs/research/main_strategy_leg_tag_protection_384_2026-07-01.md"
DEFAULT_FIGURE = ROOT / "docs/research/figures/main_strategy_leg_tag_protection_384_2026-07-01.svg"

CURRENT = "current_reference_256"
SOURCE_STRATEGY = "ev_m0p95_p0p8_full_opt__budget256_fractional"
CORE_SELECTOR = "topology_neg0_ge6_d0"
DD_ARM = "n7prot_same_ticket2_alt_risk__budget256_fractional"
SMOOTH_ARM = "n7prot_same_ticket4_full_risk__budget256_fractional"
CONVEX_ARM = "n7prot_same_ticket2_draw_risk__budget256_fractional"
OUTCOMES = ("3", "1", "0")
ARM_BUDGET = 256.0
PORTFOLIO_BUDGET = 384.0


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_leg_decisions(path: Path) -> dict[tuple[str, int], dict[str, object]]:
    out: dict[tuple[str, int], dict[str, object]] = {}
    for row in read_csv_rows(path):
        copied: dict[str, object] = dict(row)
        for key in (
            "top_p",
            "top_q",
            "second_p",
            "second_q",
            "third_p",
            "third_q",
            "draw_p",
            "draw_q",
            "top_q_p",
            "top_q_value",
            "p_gap",
            "second_ratio",
            "entropy",
            "match_quality",
        ):
            copied[key] = fnum(copied.get(key))
        for key in ("eligible_core", "suggest_double", "suggest_q_overlay", "suggest_full_watch"):
            copied[key] = int(fnum(copied.get(key)))
        out[(str(row["issue"]), int(fnum(row["match_id"])))] = copied
    return out


def load_issue_arm_rows(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        copied: dict[str, object] = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["strategy"])][str(row["issue"])] = copied
    return dict(out)


def load_core_source_rows(path: Path) -> list[dict[str, object]]:
    rows = []
    for row in read_csv_rows(path):
        source = row.get("source_strategy") or row.get("strategy")
        if source != SOURCE_STRATEGY:
            continue
        selector = row.get("selector")
        if selector is None and row.get("is_neg0_ge6_d0") == "1":
            selector = CORE_SELECTOR
            row["selector"] = CORE_SELECTOR
        if selector != CORE_SELECTOR:
            continue
        rows.append(dict(row))
    if not rows:
        raise SystemExit(f"no core selected tickets in {path}")
    return rows


def outcome_stats(decision: dict[str, object]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for prefix in ("top", "second", "third"):
        action = str(decision.get(f"{prefix}_action", ""))
        if not action:
            continue
        stats[action] = {
            "p": fnum(decision.get(f"{prefix}_p")),
            "q": fnum(decision.get(f"{prefix}_q")),
            "odds": fnum(decision.get(f"{prefix}_odds")),
        }
    return stats


def selected_p_q(decision: dict[str, object], selected: set[str]) -> tuple[float, float]:
    stats = outcome_stats(decision)
    p = sum(stats.get(action, {}).get("p", 0.0) for action in selected)
    q = sum(stats.get(action, {}).get("q", 0.0) for action in selected)
    return p, q


def target_row_for(actions: dict[tuple[int, str], ActionRow], match_id: int, target: set[str]) -> ActionRow | None:
    code = action_code_for(target)
    if code is None:
        return None
    return actions.get((match_id, code))


def candidate_for_leg(
    *,
    leg: Leg,
    decision: dict[str, object],
    actions: dict[tuple[int, str], ActionRow],
    mode: str,
) -> tuple[float, ActionRow, str] | None:
    current = selection_set(leg.row.action_code)
    if len(current) >= 3:
        return None
    stats = outcome_stats(decision)
    current_p, current_q = selected_p_q(decision, current)
    entropy = fnum(decision.get("entropy"))
    p_gap = fnum(decision.get("p_gap"))
    second_ratio = fnum(decision.get("second_ratio"))
    top_action = str(decision.get("top_action", ""))
    second_action = str(decision.get("second_action", ""))
    top_q_action = str(decision.get("top_q_action", ""))
    draw_p = fnum(decision.get("draw_p"))
    draw_q = fnum(decision.get("draw_q"))

    proposals: list[tuple[float, set[str], str]] = []
    if top_action and top_action not in current:
        top = stats.get(top_action, {})
        score = 2.2 * max(0.0, top.get("p", 0.0) - current_p) + 0.25 * max(0.0, top.get("q", 0.0) - current_q)
        score += 0.35 * entropy + 0.15 * max(0.0, 0.25 - p_gap)
        proposals.append((score, set(current) | {top_action}, "add_top_p"))

    double_code = str(decision.get("double_action_code", ""))
    if int(fnum(decision.get("suggest_double"))) and double_code:
        double_set = selection_set(double_code)
        if current < double_set:
            score = 1.1 * second_ratio + 0.8 * fnum(decision.get("second_p")) + 0.25 * fnum(decision.get("second_q"))
            score += 0.20 * entropy - 0.20 * p_gap
            proposals.append((score, double_set, "suggested_double"))

    if second_action and second_action not in current and second_ratio >= 0.62:
        second = stats.get(second_action, {})
        score = 0.9 * second_ratio + second.get("p", 0.0) + 0.20 * second.get("q", 0.0) + 0.10 * entropy
        proposals.append((score, set(current) | {second_action}, "add_second_p"))

    if "1" not in current and draw_p >= 0.20:
        score = 1.4 * draw_p + 0.25 * draw_q + 0.20 * entropy
        proposals.append((score, set(current) | {"1"}, "add_draw"))

    if top_q_action and top_q_action not in current and int(fnum(decision.get("suggest_q_overlay"))):
        score = 0.55 * fnum(decision.get("top_q_value")) + 0.35 * fnum(decision.get("top_q_p")) + 0.10 * entropy
        proposals.append((score, set(current) | {top_q_action}, "add_top_q"))

    if int(fnum(decision.get("suggest_full_watch"))) or (entropy >= 0.92 and fnum(decision.get("third_p")) >= 0.17):
        score = 0.85 * entropy + 0.8 * fnum(decision.get("third_p")) + 0.25 * draw_p
        proposals.append((score, set(OUTCOMES), "full_watch"))

    if mode == "prob_guard":
        proposals = [item for item in proposals if item[2] in {"add_top_p", "suggested_double", "add_second_p"}]
    elif mode == "draw_guard":
        proposals = [item for item in proposals if item[2] == "add_draw"]
    elif mode == "q_alt":
        proposals = [item for item in proposals if item[2] == "add_top_q"]
    elif mode == "full_watch":
        proposals = [item for item in proposals if item[2] == "full_watch"]
    elif mode == "hybrid":
        pass
    else:
        raise ValueError(f"unknown tag mode: {mode}")

    valid: list[tuple[float, ActionRow, str]] = []
    for score, target, reason in proposals:
        if target == current:
            continue
        row = target_row_for(actions, leg.row.match_id, target)
        if row is None or row.action_code == leg.row.action_code:
            continue
        valid.append((score, row, reason))
    if not valid:
        return None
    return max(valid, key=lambda item: item[0])


def convert_ticket_by_tags(
    *,
    ticket: Ticket,
    strategy: str,
    issue: str,
    decisions: dict[tuple[str, int], dict[str, object]],
    actions: dict[tuple[int, str], ActionRow],
    mode: str,
    leg_count: int,
) -> tuple[Ticket, dict[str, object]] | None:
    candidates = []
    for idx, leg in enumerate(ticket.legs):
        decision = decisions.get((issue, leg.row.match_id))
        if decision is None:
            continue
        candidate = candidate_for_leg(leg=leg, decision=decision, actions=actions, mode=mode)
        if candidate is None:
            continue
        score, target_row, reason = candidate
        candidates.append((score, idx, target_row, reason, decision))
    candidates.sort(key=lambda item: item[0], reverse=True)
    chosen = candidates[:leg_count]
    if not chosen:
        return None
    by_idx = {idx: (score, target, reason, decision) for score, idx, target, reason, decision in chosen}
    converted_legs = []
    reasons = []
    added_p = 0.0
    score_sum = 0.0
    for idx, leg in enumerate(ticket.legs):
        item = by_idx.get(idx)
        if item is None:
            converted_legs.append(leg)
            continue
        score, target, reason, decision = item
        before_set = selection_set(leg.row.action_code)
        after_set = selection_set(target.action_code)
        before_p, _before_q = selected_p_q(decision, before_set)
        after_p, _after_q = selected_p_q(decision, after_set)
        added_p += max(0.0, after_p - before_p)
        score_sum += score
        reasons.append(f"{leg.row.match_id}:{leg.row.action_code}->{target.action_code}:{reason}:{score:.3f}")
        converted_legs.append(
            Leg(
                row=target,
                strategy=strategy,
                score_factor=score,
                p_hat=max(0.001, min(0.999, after_p)),
                source_rule=f"tag_mode={mode};{reason};score={score:.4f}",
                is_full_cover=target.cover_count == 3,
            )
        )
    converted = Ticket(
        strategy=strategy,
        issue=ticket.issue,
        n_legs=ticket.n_legs,
        ticket_idx=ticket.ticket_idx,
        train_start_issue=ticket.train_start_issue,
        train_end_issue=ticket.train_end_issue,
        legs=tuple(converted_legs),
    )
    return converted, {
        "tag_score": score_sum,
        "tag_added_p": added_p,
        "tag_reasons": ";".join(reasons),
        "tag_converted_legs": len(chosen),
    }


def scaled_settled_row(
    ticket: Ticket,
    source: dict[str, object],
    strategy: str,
    source_scale: float,
    tag_meta: dict[str, object],
) -> dict[str, object]:
    raw = settle_ticket(ticket)
    out = dict(raw)
    out.update(
        {
            "strategy": strategy,
            "source_strategy": source.get("strategy", ""),
            "source_selector": source.get("selector", ""),
            "source_ticket_idx": source.get("ticket_idx", ""),
            "source_pred_ev_per_stake": fnum(source.get("pred_ev_per_stake")),
            "source_pred_hit_prob": fnum(source.get("pred_hit_prob")),
            "source_selector_score": fnum(source.get("selector_score")),
            "source_weight_scale": source_scale,
            **tag_meta,
        }
    )
    for key in ("stake_units", "payout_units", "profit_units"):
        out[key] = fnum(raw.get(key)) * source_scale
    out["roi"] = fnum(out["profit_units"]) / fnum(out["stake_units"]) if fnum(out["stake_units"]) else math.nan
    # Let the budget allocator rank tag sleeves by leg-level protection value,
    # not by the original q-heavy ticket EV.
    out["pred_ev_per_stake"] = fnum(tag_meta.get("tag_score"))
    out["pred_hit_prob"] = fnum(tag_meta.get("tag_added_p"))
    return out


def build_tag_raw_rows(
    *,
    source_rows: list[dict[str, object]],
    actions: dict[tuple[int, str], ActionRow],
    decisions: dict[tuple[str, int], dict[str, object]],
    modes: list[str],
    ticket_counts: list[int],
    leg_counts: list[int],
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in source_rows:
        grouped[str(row["issue"])].append(row)

    out: list[dict[str, object]] = []
    for mode in modes:
        for ticket_count in ticket_counts:
            for leg_count in leg_counts:
                strategy = f"tagonly_{mode}_t{ticket_count}_l{leg_count}"
                for issue, rows in grouped.items():
                    converted_rows = []
                    for source in rows:
                        ticket = parse_ticket(source, actions)
                        if ticket is None:
                            continue
                        base_raw = settle_ticket(ticket)
                        base_stake = fnum(base_raw.get("stake_units"), 1.0)
                        source_scale = fnum(source.get("stake_units")) / base_stake if base_stake else 0.0
                        converted = convert_ticket_by_tags(
                            ticket=ticket,
                            strategy=strategy,
                            issue=issue,
                            decisions=decisions,
                            actions=actions,
                            mode=mode,
                            leg_count=leg_count,
                        )
                        if converted is None:
                            continue
                        converted_ticket, meta = converted
                        row = scaled_settled_row(converted_ticket, source, strategy, source_scale, meta)
                        converted_rows.append(row)
                    converted_rows.sort(
                        key=lambda row: (
                            fnum(row.get("tag_score")),
                            fnum(row.get("tag_added_p")),
                            fnum(row.get("source_pred_ev_per_stake")),
                        ),
                        reverse=True,
                    )
                    out.extend(converted_rows[:ticket_count])
    return out


def map_issue_rows(rows: list[dict[str, object]], key: str = "strategy") -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        out[str(row[key])][str(row["issue"])] = dict(row)
    return dict(out)


def combine_portfolio(
    *,
    name: str,
    issues: list[str],
    current: dict[str, dict[str, object]],
    arms: dict[str, dict[str, dict[str, object]]],
    allocation: dict[str, float],
    calendar: dict[str, dict[str, object]],
    fallback_arm: str | None = SMOOTH_ARM,
) -> list[dict[str, object]]:
    rows = []
    for issue in issues:
        cur = current[issue]
        profit = fnum(cur.get("profit_units"))
        tickets = fnum(cur.get("tickets"))
        hits = fnum(cur.get("hits"))
        parts = ["current:256"]
        for arm, units in allocation.items():
            if units <= 1e-9:
                continue
            row = arms.get(arm, {}).get(issue)
            fallback_used = False
            if row is None and fallback_arm:
                row = arms.get(fallback_arm, {}).get(issue)
                fallback_used = row is not None
            if row is None:
                parts.append(f"unfilled:{arm}:{units:g}")
                continue
            stake = fnum(row.get("stake_units"), ARM_BUDGET)
            scale = units / stake if stake > 0 else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{'fallback_' if fallback_used else ''}{arm}:{units:g}")
        row_out = {
            "portfolio": name,
            "issue": issue,
            "stake_units": PORTFOLIO_BUDGET,
            "profit_units": profit,
            "roi": profit / PORTFOLIO_BUDGET,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
        }
        row_out.update(calendar.get(issue, {}))
        rows.append(row_out)
    return rows


def portfolio_specs(tag_arms: list[str]) -> list[tuple[str, dict[str, float]]]:
    specs: list[tuple[str, dict[str, float]]] = []
    for arm in tag_arms:
        suffix = arm.removeprefix("tagonly_").removesuffix("__budget256_fractional")
        specs.extend(
            [
                (f"tag384_tag128_{suffix}", {arm: 128.0}),
                (f"tag384_dd32_tag96_{suffix}", {DD_ARM: 32.0, arm: 96.0}),
                (f"tag384_dd32_smooth64_tag32_{suffix}", {DD_ARM: 32.0, SMOOTH_ARM: 64.0, arm: 32.0}),
                (f"tag384_dd32_smooth76_tag19_{suffix}", {DD_ARM: 32.0, SMOOTH_ARM: 76.8, arm: 19.2}),
                (f"tag384_dd32_tag76_convex19_{suffix}", {DD_ARM: 32.0, arm: 76.8, CONVEX_ARM: 19.2}),
            ]
        )
    return specs


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    baselines = load_baseline_issue_rows(args.baseline_path, calendar)
    current_rows = baselines[CURRENT]
    current = {str(row["issue"]): row for row in current_rows}
    issues = sorted(current, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))
    old_arms = load_issue_arm_rows(args.old_arms_path, calendar)

    actions_all = load_action_rows(args.db, args.min_year)
    actions = action_lookup(actions_all)
    source_rows = load_core_source_rows(args.selected_tickets)
    decisions = load_leg_decisions(args.leg_decisions)

    raw_rows = build_tag_raw_rows(
        source_rows=source_rows,
        actions=actions,
        decisions=decisions,
        modes=[item.strip() for item in args.modes.split(",") if item.strip()],
        ticket_counts=[int(item) for item in args.ticket_counts.split(",") if item.strip()],
        leg_counts=[int(item) for item in args.leg_counts.split(",") if item.strip()],
    )
    budgeted = budgeted_ticket_rows(raw_rows, issue_budget_units=ARM_BUDGET, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    for row in issue_rows:
        row.update(calendar.get(str(row["issue"]), {}))
    tag_arms = map_issue_rows(issue_rows)
    arms = {**old_arms, **tag_arms}

    rows_by_portfolio: dict[str, list[dict[str, object]]] = {
        name: rows for name, rows in baselines.items() if name in BASELINE_PORTFOLIOS
    }
    portfolio_rows: list[dict[str, object]] = []
    for name, allocation in portfolio_specs(sorted(tag_arms)):
        rows = combine_portfolio(
            name=name,
            issues=issues,
            current=current,
            arms=arms,
            allocation=allocation,
            calendar=calendar,
        )
        rows_by_portfolio[name] = rows
        portfolio_rows.extend(rows)

    summaries = [summarize(rows, name) for name, rows in rows_by_portfolio.items()]
    for row in summaries:
        row["utility_drawdown_first"] = (
            2.0 * fnum(row.get("max_drawdown_units"))
            + 0.10 * fnum(row.get("profit_units"))
            + 65000.0 * fnum(row.get("non_full_loss_rate"))
            + 35000.0 * fnum(row.get("issue_win_rate"))
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "leg_tag_protection_raw_tickets.csv", raw_rows)
    write_csv_all(args.output_dir / "leg_tag_protection_budgeted_tickets.csv", budgeted)
    write_csv(args.output_dir / "leg_tag_protection_issue_profit.csv", issue_rows)
    write_csv(args.output_dir / "leg_tag_protection_portfolio_issue_profit.csv", portfolio_rows)
    write_csv(args.output_dir / "leg_tag_protection_summary.csv", sorted(summaries, key=lambda row: fnum(row.get("utility_drawdown_first")), reverse=True))
    write_csv(args.output_dir / "leg_tag_protection_annual.csv", annual_rows(rows_by_portfolio))

    baselines_summary = [row for row in summaries if row["portfolio"] in BASELINE_PORTFOLIOS]
    variants = [row for row in summaries if str(row["portfolio"]).startswith("tag384")]
    viable = [row for row in variants if fnum(row.get("profit_units")) > 0 and fnum(row.get("recent_profit_units")) > 0]
    best_utility = sorted(viable, key=lambda row: fnum(row.get("utility_drawdown_first")), reverse=True)[:15]
    best_dd = sorted(viable, key=lambda row: (fnum(row.get("max_drawdown_units")), fnum(row.get("profit_units"))), reverse=True)[:15]
    best_profit = sorted(viable, key=lambda row: fnum(row.get("profit_units")), reverse=True)[:15]
    stable_baseline = next((row for row in baselines_summary if row["portfolio"] == "b384_dd32_smooth100"), None)
    watchlist: list[dict[str, object]] = []
    if stable_baseline:
        base_profit = fnum(stable_baseline.get("profit_units"))
        base_dd = fnum(stable_baseline.get("max_drawdown_units"))
        base_nonfull = fnum(stable_baseline.get("non_full_loss_rate"))
        base_recent = fnum(stable_baseline.get("recent_profit_units"))
        watchlist = [
            row for row in variants
            if fnum(row.get("profit_units")) >= 0.95 * base_profit
            and fnum(row.get("recent_profit_units")) >= 0.95 * base_recent
            and fnum(row.get("non_full_loss_rate")) >= base_nonfull
            and fnum(row.get("max_drawdown_units")) >= base_dd - 1000.0
        ]
        watchlist.sort(
            key=lambda row: (
                -fnum(row.get("max_loss_streak")),
                fnum(row.get("non_full_loss_rate")),
                fnum(row.get("profit_units")),
            ),
            reverse=True,
        )
    figure_names = ["b384_dd32_smooth100", "b384_dd32_smooth80_convex19"] + [str(row["portfolio"]) for row in best_utility[:5]]
    write_equity_svg(args.figure_path, {name: rows_by_portfolio[name] for name in figure_names if name in rows_by_portfolio})

    cols = [
        "portfolio",
        "profit_units",
        "roi",
        "issue_win_rate",
        "non_full_loss_rate",
        "full_loss_rate",
        "max_drawdown_units",
        "max_loss_streak",
        "max_dead_streak",
        "recent_profit_units",
        "recent_roi",
        "avg_tickets_per_issue",
        "parts",
    ]
    best = best_utility[0] if best_utility else None
    baseline = next((row for row in baselines_summary if row["portfolio"] == "b384_dd32_smooth100"), None)
    report = [
        "# Main strategy leg-tag protection validation",
        "",
        "## Scope",
        "",
        f"- Main stake is fixed to `{CURRENT}`: 256 units per issue.",
        "- New sleeves protect the existing high-N core tickets using the leg decision table from the p-first depth allocator.",
        "- The tested 384 portfolios use current 256 plus combinations of old DD/smooth sleeves and new tag-only sleeves.",
        f"- Source tickets: `{args.selected_tickets}` / `{SOURCE_STRATEGY}` / `{CORE_SELECTOR}`.",
        f"- Leg decision table: `{args.leg_decisions}`.",
        "",
        "## Baselines",
        "",
        md_table(baselines_summary, cols, limit=10),
        "",
        "## Best drawdown-first viable tag variants",
        "",
        md_table(best_utility, cols + ["utility_drawdown_first"], limit=15),
        "",
        "## Best absolute maxDD viable tag variants",
        "",
        md_table(best_dd, cols, limit=15),
        "",
        "## Watchlist Near Stable Baseline",
        "",
        md_table(watchlist, cols + ["utility_drawdown_first"], limit=15),
        "",
        "## Best profit tag variants",
        "",
        md_table(best_profit, cols, limit=15),
        "",
        "## Interpretation",
        "",
    ]
    if best and baseline:
        report.append(
            "- Highest utility tag variant is not automatically promotable: "
            f"`{best['portfolio']}` profit `{fnum(best.get('profit_units')):,.1f}`, "
            f"ROI `{fnum(best.get('roi')):.3f}`, full-loss `{fnum(best.get('full_loss_rate')):.3f}`, "
            f"maxDD `{fnum(best.get('max_drawdown_units')):,.1f}`."
        )
        report.append(
            "- Current stable baseline: "
            f"`b384_dd32_smooth100` profit `{fnum(baseline.get('profit_units')):,.1f}`, "
            f"ROI `{fnum(baseline.get('roi')):.3f}`, full-loss `{fnum(baseline.get('full_loss_rate')):.3f}`, "
            f"maxDD `{fnum(baseline.get('max_drawdown_units')):,.1f}`."
        )
    if watchlist and baseline:
        first = watchlist[0]
        report.append(
            "- Best watchlist paper arm: "
            f"`{first['portfolio']}` profit `{fnum(first.get('profit_units')):,.1f}`, "
            f"ROI `{fnum(first.get('roi')):.3f}`, non-full-loss `{fnum(first.get('non_full_loss_rate')):.3f}`, "
            f"maxDD `{fnum(first.get('max_drawdown_units')):,.1f}`, "
            f"max loss streak `{int(fnum(first.get('max_loss_streak')))}`. "
            "It improves loss-streak/full-loss slightly but does not beat stable baseline maxDD."
        )
    report.extend(
        [
            "- Decision: do not replace the stable baseline yet. Tag sleeves are useful as a small paper arm, especially `prob_guard/hybrid` with tiny 19.2-unit allocation.",
            "- High-profit `full_watch` and large tag allocations are convex variants, not defensive variants; they raise maxDD/full-loss and should not be used for drawdown control.",
            f"- Equity figure: `{args.figure_path}`",
            "",
        ]
    )
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'leg_tag_protection_summary.csv'}")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--baseline-path", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--old-arms-path", type=Path, default=DEFAULT_OLD_ARMS)
    parser.add_argument("--selected-tickets", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--leg-decisions", type=Path, default=DEFAULT_LEG_DECISIONS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--figure-path", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--min-year", type=int, default=2013)
    parser.add_argument("--modes", default="prob_guard,draw_guard,q_alt,full_watch,hybrid")
    parser.add_argument("--ticket-counts", default="1,2,4")
    parser.add_argument("--leg-counts", default="1,2,3")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
