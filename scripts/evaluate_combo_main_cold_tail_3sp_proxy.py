#!/usr/bin/env python3
"""Long-horizon 3SP proxy for the N=7 confidence main + cold tail combo.

The original combo depends on model probabilities and 1h/10h snapshots that are
only available in the normalized XLSM database. This script uses the historical
full-3SP CSV to run a longer retrospective structural check:

* q is trained walk-forward from past issues only;
* model probabilities are proxied by q-adjusted market probabilities;
* dynamic draw cover is applied by synthesizing double-cover rows in memory;
* cold high-SP tail uses the same candidate and allocation machinery.

It is not a 10h/1h entry simulation.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_cold_high_odds_tail import build_ticket as build_cold_ticket
from scripts.evaluate_cold_high_odds_tail import ColdProfile
from scripts.evaluate_combo_main_cold_tail import (
    aggregate_issue,
    build_cold_candidates,
    cold_profile,
    cold_ticket_metrics_by_issue,
    filter_cold_candidates_for_overlap,
    make_allocation_issue_rows,
    make_conditional_allocation_issue_rows,
    make_portfolio_issue_rows,
    max_drawdown,
    max_loss_streak,
    settle_rows,
    summarize_allocation_rows,
    summarize_issue_rows,
)
from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, transform_legs_for_depth
from scripts.evaluate_n7_dynamic_draw_cover import dynamic_draw_cover_ticket
from scripts.evaluate_n7_q_pocket_whitelist_3sp import load_3sp_action_rows
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, MatchSample, build_samples
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Ticket,
    break_even_factor,
    build_q_baseline_legs,
    group_by_issue as group_action_rows_by_issue,
    md_table,
    q_key,
    snapshot_odds_p,
    snapshot_rank_lookup,
    train_q_model,
    write_csv,
)


COVER_ACTION_SETS = {
    "31": ("3", "1"),
    "30": ("3", "0"),
    "10": ("1", "0"),
    "310": ("3", "1", "0"),
}


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def cold_profile_from_args(args: argparse.Namespace) -> ColdProfile:
    profile = cold_profile(args)
    if args.cold_allow_non_top2:
        return ColdProfile(
            name=profile.name.replace("_top2", "_allranks"),
            n_legs=profile.n_legs,
            min_odds=profile.min_odds,
            max_odds=profile.max_odds,
            min_model_p=profile.min_model_p,
            min_ratio=profile.min_ratio,
            rank_min=profile.rank_min,
            score_margin=profile.score_margin,
            require_top2=False,
        )
    return profile


def normalized_market_probabilities(samples: list[MatchSample], snapshot: str) -> np.ndarray:
    rows = []
    for sample in samples:
        vals = []
        for code in OUTCOMES:
            _, p = snapshot_odds_p(sample.rows[code], snapshot)
            vals.append(float(p or 0.0))
        total = sum(vals)
        if total <= 0:
            rows.append([1 / 3, 1 / 3, 1 / 3])
        else:
            rows.append([v / total for v in vals])
    return np.asarray(rows, dtype=float)


def q_adjusted_probabilities(
    samples: list[MatchSample],
    *,
    q_model: dict[tuple[str, str, str, str], float],
    global_q: float,
    snapshot: str,
) -> np.ndarray:
    rows = [row for sample in samples for row in sample.rows.values()]
    ranks = snapshot_rank_lookup(rows, snapshot)
    probs = []
    for sample in samples:
        vals = []
        for code in OUTCOMES:
            row = sample.rows[code]
            _, p = snapshot_odds_p(row, snapshot)
            if p is None or p <= 0:
                vals.append(0.0)
                continue
            key = q_key(row, p, ranks.get((row.match_id, row.action_code)))
            vals.append(max(1e-6, float(q_model.get(key, global_q)) * float(p)))
        total = sum(vals)
        if total <= 0:
            probs.append([1 / 3, 1 / 3, 1 / 3])
        else:
            probs.append([v / total for v in vals])
    return np.asarray(probs, dtype=float)


def synthesize_cover_rows(single_rows: list[ActionRow]) -> list[ActionRow]:
    grouped: dict[int, dict[str, ActionRow]] = defaultdict(dict)
    for row in single_rows:
        if row.action_code in OUTCOMES:
            grouped[row.match_id][row.action_code] = row

    out: list[ActionRow] = []
    for by_action in grouped.values():
        if any(code not in by_action for code in OUTCOMES):
            continue
        base = by_action["3"]
        result_code = str(base.result_code)
        winning_sp = float(by_action.get(result_code, base).winning_sp)
        for action_code, covered_codes in COVER_ACTION_SETS.items():
            hit = int(result_code in covered_codes)
            out.append(
                ActionRow(
                    match_id=base.match_id,
                    issue=base.issue,
                    match_idx=base.match_idx,
                    kickoff_ts=base.kickoff_ts,
                    season_year=base.season_year,
                    league=base.league,
                    hcp=base.hcp,
                    result_code=base.result_code,
                    winning_sp=winning_sp,
                    action_code=action_code,
                    action_label=action_code,
                    selection_set=action_code,
                    cover_count=len(covered_codes),
                    hit=hit,
                    factor=winning_sp if hit else 0.0,
                    euro_final_odds=None,
                    euro_final_p=None,
                    euro_1h_odds=None,
                    euro_1h_p=None,
                    euro_10h_odds=None,
                    euro_10h_p=None,
                    euro_final_rank=None,
                )
            )
    return out


def build_main_proxy_tickets(
    *,
    args: argparse.Namespace,
    test_issue: str,
    train_issues: list[str],
    test_action_rows: list[ActionRow],
    test_samples: list[MatchSample],
    q_model: dict[tuple[str, str, str, str], float],
    global_q: float,
    model_probs: np.ndarray,
    market_probs: np.ndarray,
) -> tuple[list[Ticket], dict[str, object]]:
    threshold = break_even_factor(args.main_n_legs) + args.min_factor_margin
    q_legs = build_q_baseline_legs(
        test_action_rows,
        q_model,
        global_q,
        snapshot="final",
        min_proxy_odds=args.baseline_min_proxy_odds,
        max_proxy_odds=args.baseline_max_proxy_odds,
        min_score_factor=threshold,
    )
    if len(q_legs) < args.main_n_legs:
        return [], {"n_q_legs": len(q_legs), "n_depth_legs": 0, "n_main_base_tickets": 0, "n_main_tickets": 0}

    model_by_match = {sample.match_id: model_probs[i] for i, sample in enumerate(test_samples)}
    market_by_match = {sample.match_id: market_probs[i] for i, sample in enumerate(test_samples)}
    depth_legs, depth_weights = transform_legs_for_depth(
        q_legs,
        policy=args.depth_policy,
        probs_by_match=model_by_match,
        market_by_match=market_by_match,
        min_score_factor=threshold,
    )
    depth_strategy = f"confidence_proxy_3sp_{args.depth_policy}"
    base_tickets = make_depth_weighted_tickets(
        depth_legs,
        depth_weights=depth_weights,
        strategy=depth_strategy,
        issue=test_issue,
        n_legs=args.main_n_legs,
        max_tickets=args.max_main_tickets_per_issue,
        overlap_penalty=args.overlap_penalty,
        train_start_issue=train_issues[0],
        train_end_issue=train_issues[-1],
        max_leg_uses=args.max_depth_leg_uses,
        max_ticket_overlap=args.max_depth_ticket_overlap,
    )
    if args.disable_dynamic_draw:
        main_tickets = base_tickets
    else:
        action_rows_with_covers = test_action_rows + synthesize_cover_rows(test_action_rows)
        action_lookup = {(row.match_id, row.action_code): row for row in action_rows_with_covers}
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        main_tickets = [
            dynamic_draw_cover_ticket(
                ticket,
                strategy_prefix=depth_strategy,
                dynamic_policy=args.dynamic_policy,
                action_lookup=action_lookup,
                samples_by_match=samples_by_match,
                model_probs_by_match=model_by_match,
                market_probs_by_match=market_by_match,
                require_positive_draw_edge=args.require_positive_draw_edge,
            )
            for ticket in base_tickets
        ]

    return main_tickets, {
        "n_q_legs": len(q_legs),
        "n_depth_legs": len(depth_legs),
        "n_main_base_tickets": len(base_tickets),
        "n_main_tickets": len(main_tickets),
    }


def issue_stress_summary(
    rows: list[dict[str, object]],
    *,
    group_field: str,
    stake_field: str,
    profit_field: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[group_field])].append(row)

    out: list[dict[str, object]] = []
    for group, vals in sorted(grouped.items()):
        chronological = sorted(vals, key=lambda r: str(r["issue"]))
        profits_chrono = [float(r[profit_field]) for r in chronological]
        ranked = sorted(vals, key=lambda r: float(r[profit_field]), reverse=True)
        stake = sum(float(r[stake_field]) for r in vals)
        profit = sum(float(r[profit_field]) for r in vals)

        def ex_top(k: int) -> tuple[float, float, float]:
            kept = ranked[k:]
            s = sum(float(r[stake_field]) for r in kept)
            p = sum(float(r[profit_field]) for r in kept)
            return s, p, p / s if s else float("nan")

        ex1_stake, ex1_profit, ex1_roi = ex_top(1)
        ex2_stake, ex2_profit, ex2_roi = ex_top(2)
        best_profit = float(ranked[0][profit_field]) if ranked else 0.0
        lottery_verdict = "negative"
        if profit > 0 and ex1_roi > 0 and ex2_roi > 0:
            lottery_verdict = "robust_lottery_tail"
        elif profit > 0 and ex1_roi > 0:
            lottery_verdict = "top2_sensitive_positive_tail"
        elif profit > 0:
            lottery_verdict = "jackpot_dependent"
        out.append(
            {
                group_field: group,
                "issues": len(vals),
                "stake": stake,
                "profit": profit,
                "roi": profit / stake if stake else float("nan"),
                "profitable_issues": sum(1 for r in vals if float(r[profit_field]) > 0),
                "best_issue": ranked[0]["issue"] if ranked else "",
                "best_issue_profit": best_profit,
                "best_issue_profit_share": best_profit / profit if profit > 0 and best_profit > 0 else "",
                "ex_top1_stake": ex1_stake,
                "ex_top1_profit": ex1_profit,
                "ex_top1_roi": ex1_roi,
                "ex_top2_stake": ex2_stake,
                "ex_top2_profit": ex2_profit,
                "ex_top2_roi": ex2_roi,
                "max_drawdown_units": max_drawdown(profits_chrono),
                "max_issue_loss_streak": max_loss_streak(profits_chrono),
                "lottery_stress_verdict": lottery_verdict,
            }
        )
    out.sort(key=lambda row: float(row["roi"]), reverse=True)
    return out


def run(args: argparse.Namespace) -> None:
    action_rows, issues, data_meta = load_3sp_action_rows(args.csv, args.min_year)
    samples = build_samples(action_rows)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue: dict[str, list[MatchSample]] = defaultdict(list)
    for sample in samples:
        samples_by_issue[sample.issue].append(sample)
    profile = cold_profile_from_args(args)
    target_tail_shares = parse_floats(args.target_tail_shares)

    main_ticket_rows: list[dict[str, object]] = []
    cold_ticket_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    evaluated_issues: list[str] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        train_action_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
        test_action_rows = action_by_issue.get(test_issue, [])
        test_samples = samples_by_issue.get(test_issue, [])
        if len(train_action_rows) < args.min_train_actions or not test_samples:
            continue

        q_model, global_q = train_q_model(train_action_rows, snapshot="final", prior_n=args.q_prior_n)
        model_probs = q_adjusted_probabilities(test_samples, q_model=q_model, global_q=global_q, snapshot="final")
        market_probs = normalized_market_probabilities(test_samples, "final")
        main_tickets, main_diag = build_main_proxy_tickets(
            args=args,
            test_issue=test_issue,
            train_issues=train_issues,
            test_action_rows=test_action_rows,
            test_samples=test_samples,
            q_model=q_model,
            global_q=global_q,
            model_probs=model_probs,
            market_probs=market_probs,
        )
        if not main_tickets:
            continue

        cold_candidates = build_cold_candidates(
            test_samples=test_samples,
            model_probs=model_probs,
            snapshot="final",
        )
        cold_candidates, overlap_diag = filter_cold_candidates_for_overlap(
            cold_candidates,
            main_tickets,
            args.cold_overlap_filter,
        )
        cold_ticket, cold_candidate_matches = build_cold_ticket(
            issue=test_issue,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            profile=profile,
            candidates=cold_candidates,
        )
        cold_tickets = [cold_ticket] if cold_ticket is not None else []

        main_ticket_rows.extend(settle_rows(main_tickets, family="main", ticket_weight=1.0))
        cold_ticket_rows.extend(settle_rows(cold_tickets, family="cold", ticket_weight=1.0))
        evaluated_issues.append(test_issue)
        window_rows.append(
            {
                "issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_actions": len(train_action_rows),
                "n_test_matches": len(test_samples),
                "probability_proxy": "rolling_q_adjusted_market_probabilities",
                "cold_overlap_filter": args.cold_overlap_filter,
                **main_diag,
                **overlap_diag,
                "n_cold_candidate_matches": cold_candidate_matches,
                "n_cold_tickets": len(cold_tickets),
            }
        )

    main_by_issue = aggregate_issue(main_ticket_rows)
    cold_by_issue = aggregate_issue(cold_ticket_rows)
    portfolio_issue_rows = make_portfolio_issue_rows(
        issues=evaluated_issues,
        main_by_issue=main_by_issue,
        cold_by_issue=cold_by_issue,
        target_tail_shares=target_tail_shares,
    )
    allocation_issue_rows = make_allocation_issue_rows(
        issues=evaluated_issues,
        main_by_issue=main_by_issue,
        cold_by_issue=cold_by_issue,
        main_shares=parse_floats(args.allocation_main_shares),
    )
    windows_by_issue = {str(row["issue"]): row for row in window_rows}
    conditional_issue_rows = make_conditional_allocation_issue_rows(
        issues=evaluated_issues,
        main_by_issue=main_by_issue,
        cold_by_issue=cold_by_issue,
        cold_metrics_by_issue=cold_ticket_metrics_by_issue(cold_ticket_rows),
        windows_by_issue=windows_by_issue,
        args=args,
    )

    portfolio_summary = summarize_issue_rows(portfolio_issue_rows, initial_bankroll=args.initial_bankroll)
    allocation_summary = summarize_allocation_rows(allocation_issue_rows, initial_bankroll=args.initial_bankroll)
    conditional_summary = summarize_allocation_rows(conditional_issue_rows, initial_bankroll=args.initial_bankroll)
    portfolio_stress = issue_stress_summary(
        portfolio_issue_rows,
        group_field="portfolio",
        stake_field="stake",
        profit_field="profit",
    )
    allocation_stress = issue_stress_summary(
        allocation_issue_rows,
        group_field="allocation",
        stake_field="budget",
        profit_field="profit",
    )
    conditional_stress = issue_stress_summary(
        conditional_issue_rows,
        group_field="allocation",
        stake_field="budget",
        profit_field="profit",
    )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "combo_3sp_proxy_main_tickets.csv", main_ticket_rows)
    write_csv(out / "combo_3sp_proxy_cold_tickets.csv", cold_ticket_rows)
    write_csv(out / "combo_3sp_proxy_issue_profit.csv", portfolio_issue_rows)
    write_csv(out / "combo_3sp_proxy_summary.csv", portfolio_summary)
    write_csv(out / "combo_3sp_proxy_allocation_issue_profit.csv", allocation_issue_rows)
    write_csv(out / "combo_3sp_proxy_allocation_summary.csv", allocation_summary)
    write_csv(out / "combo_3sp_proxy_conditional_issue_profit.csv", conditional_issue_rows)
    write_csv(out / "combo_3sp_proxy_conditional_summary.csv", conditional_summary)
    write_csv(out / "combo_3sp_proxy_portfolio_stress.csv", portfolio_stress)
    write_csv(out / "combo_3sp_proxy_allocation_stress.csv", allocation_stress)
    write_csv(out / "combo_3sp_proxy_conditional_stress.csv", conditional_stress)
    write_csv(out / "combo_3sp_proxy_windows.csv", window_rows)

    report = [
        "# N=7 confidence+cold 3SP proxy retrospective",
        "",
        f"- CSV: `{args.csv}`",
        f"- Date span: `{data_meta['date_start']}` to `{data_meta['date_end']}`",
        f"- Matches / issues: `{data_meta['n_matches']}` / `{data_meta['n_issues']}`",
        f"- Evaluated issues: `{len(evaluated_issues)}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Main proxy: `rolling_q_adjusted_market_probabilities + {args.depth_policy}`",
        f"- Dynamic draw: `{'disabled' if args.disable_dynamic_draw else args.dynamic_policy}`",
        f"- Cold: `{profile.name}`",
        f"- Cold overlap filter: `{args.cold_overlap_filter}`",
        "",
        "This is a final-3SP retrospective proxy. It is not a tradable 10h/1h entry backtest.",
        "",
        "## Same-Budget Allocation Summary",
        md_table(allocation_summary),
        "## Same-Budget Stress",
        md_table(allocation_stress),
        "## Conditional Allocation Summary",
        md_table(conditional_summary),
        "## Conditional Stress",
        md_table(conditional_stress),
        "## Extra-Tail Portfolio Summary",
        md_table(portfolio_summary),
        "## Extra-Tail Stress",
        md_table(portfolio_stress),
        "",
    ]
    (out / "combo_3sp_proxy_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'combo_3sp_proxy_report.md'}")
    print(f"Wrote {len(main_ticket_rows)} main ticket rows and {len(cold_ticket_rows)} cold ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/raw/beidan_full_3sp.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("results/combo_main_cold_tail_3sp_proxy"))
    parser.add_argument("--min-year", type=int, default=2018)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-actions", type=int, default=500)
    parser.add_argument("--main-n-legs", type=int, default=7)
    parser.add_argument("--max-main-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--dynamic-policy", default="model_draw_ratio_t0.55_k2")
    parser.add_argument("--disable-dynamic-draw", action="store_true")
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    parser.add_argument("--cold-n-legs", type=int, default=3)
    parser.add_argument("--cold-min-odds", type=float, default=5.0)
    parser.add_argument("--cold-max-odds", type=float, default=20.0)
    parser.add_argument("--cold-min-model-p", type=float, default=0.16)
    parser.add_argument("--cold-min-ratio", type=float, default=1.25)
    parser.add_argument("--cold-rank-min", type=int, default=3)
    parser.add_argument("--cold-require-top2", action="store_true", default=True)
    parser.add_argument("--cold-allow-non-top2", action="store_true")
    parser.add_argument("--cold-overlap-filter", choices=("none", "exact", "covered", "match"), default="match")
    parser.add_argument("--target-tail-shares", default="0.01,0.02,0.03")
    parser.add_argument("--allocation-main-shares", default="1.0,0.8,0.6,0.4")
    parser.add_argument("--conditional-main-share", type=float, default=0.80)
    parser.add_argument("--trigger-min-cold-candidate-matches", type=int, default=15)
    parser.add_argument("--trigger-min-cold-pred-hit-prob", type=float, default=0.0)
    parser.add_argument("--trigger-max-cold-pred-hit-prob", type=float, default=0.0)
    parser.add_argument("--trigger-min-cold-pred-ev", type=float, default=0.0)
    parser.add_argument("--trigger-min-main-budget", type=float, default=0.0)
    parser.add_argument("--trigger-max-main-budget", type=float, default=0.0)
    parser.add_argument("--trigger-min-q-legs", type=int, default=180)
    parser.add_argument("--trigger-max-q-legs", type=int, default=0)
    parser.add_argument("--trigger-min-main-match-ids", type=int, default=0)
    parser.add_argument("--trigger-max-main-match-ids", type=int, default=0)
    parser.add_argument("--trigger-min-main-covered-pairs", type=int, default=0)
    parser.add_argument("--trigger-max-main-covered-pairs", type=int, default=0)
    parser.add_argument("--initial-bankroll", type=float, default=10000.0)
    args = parser.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")
    run(args)


if __name__ == "__main__":
    main()
