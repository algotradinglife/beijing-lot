#!/usr/bin/env python3
"""Export latest-issue candidate tickets for the N=7 main + cold-tail plan.

This script intentionally writes pre-settlement plan rows: no hit, payout, or
realized profit columns are included in the live candidate files.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_combo_main_cold_tail import (
    build_cold_candidates,
    build_main_tickets,
    cold_profile,
    conditional_triggered,
    filter_cold_candidates_for_overlap,
)
from scripts.evaluate_cold_high_odds_tail import build_ticket as build_cold_ticket
from scripts.evaluate_n7_confidence_coverage import model_probabilities
from scripts.evaluate_n7_depth_draw_cover import group_samples_by_issue
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras, market_probs
from scripts.walkforward_beidan_strategy_eval import (
    RETURN_RATE,
    Ticket,
    default_db_path,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    md_table,
    write_csv,
)


def ticket_plan_row(ticket: Ticket, family: str) -> dict[str, object]:
    stake_units = 1
    pred_factor_product = 1.0
    pred_hit_prob = 1.0
    n_full = 0
    n_double = 0
    legs_desc: list[str] = []
    leg_details: list[str] = []
    for leg in ticket.legs:
        row = leg.row
        stake_units *= row.cover_count
        pred_factor_product *= max(0.0, float(leg.score_factor))
        pred_hit_prob *= max(0.0, min(1.0, float(leg.p_hat)))
        if row.cover_count == 3:
            n_full += 1
        elif row.cover_count == 2:
            n_double += 1
        legs_desc.append(f"{row.match_id}:{row.action_code}@{row.hcp:g}")
        leg_details.append(
            f"{row.match_id}:{row.action_code}:p={leg.p_hat:.4f}:score={leg.score_factor:.4f}:cover={row.cover_count}"
        )
    pred_ev_per_stake = RETURN_RATE * pred_factor_product - 1.0
    return {
        "family": family,
        "strategy": ticket.strategy,
        "issue": ticket.issue,
        "n_legs": ticket.n_legs,
        "ticket_idx": ticket.ticket_idx,
        "train_start_issue": ticket.train_start_issue,
        "train_end_issue": ticket.train_end_issue,
        "n_full_cover": n_full,
        "n_double_cover": n_double,
        "stake_units": stake_units,
        "pred_hit_prob": pred_hit_prob,
        "pred_factor_product": pred_factor_product,
        "pred_ev_per_stake": pred_ev_per_stake,
        "pred_profit_units": stake_units * pred_ev_per_stake,
        "legs": ";".join(legs_desc),
        "leg_details": ";".join(leg_details),
    }


def cold_candidate_rows(candidates: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
    ranked = sorted(
        candidates,
        key=lambda c: (
            math.log(max(float(c["score_factor"]), 1e-9))
            + 0.20 * math.log(max(float(c["odds"]), 1e-9))
            + 0.15 * math.log(max(float(c["model_market_ratio"]), 1e-9)),
            float(c["model_p"]),
        ),
        reverse=True,
    )
    rows: list[dict[str, object]] = []
    for idx, c in enumerate(ranked[:limit], start=1):
        row = c["row"]
        assert not isinstance(row, dict)
        rows.append(
            {
                "rank": idx,
                "issue": row.issue,
                "match_id": int(c["match_id"]),
                "match_idx": row.match_idx,
                "league": row.league,
                "kickoff_ts": row.kickoff_ts,
                "hcp": row.hcp,
                "action_code": c["action_code"],
                "odds": float(c["odds"]),
                "model_p": float(c["model_p"]),
                "market_p": float(c["market_p"]),
                "model_market_ratio": float(c["model_market_ratio"]),
                "score_factor": float(c["score_factor"]),
                "market_rank": int(c["rank"]),
                "top2_agree": int(bool(c["top2_agree"])),
            }
        )
    return rows


def pick_issue(issues: list[str], requested: str | None, train_issues: int) -> tuple[int, str]:
    if requested:
        if requested not in issues:
            raise SystemExit(f"issue not found: {requested}")
        idx = issues.index(requested)
    else:
        idx = len(issues) - 1
    if idx < train_issues:
        raise SystemExit(f"issue {issues[idx]} does not have {train_issues} prior train issues")
    return idx, issues[idx]


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    issue_idx, test_issue = pick_issue(issues, args.issue, args.train_issues)

    train_issues = issues[issue_idx - args.train_issues : issue_idx]
    train_action_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
    test_action_rows = action_by_issue.get(test_issue, [])
    train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
    test_samples = samples_by_issue.get(test_issue, [])
    if len(train_samples) < args.min_train_matches or not test_samples:
        raise SystemExit("not enough train/test samples for candidate export")

    model_probs = model_probabilities(args, train_samples, test_samples)
    main_tickets, main_diag = build_main_tickets(
        args=args,
        test_issue=test_issue,
        train_issues=train_issues,
        train_action_rows=train_action_rows,
        test_action_rows=test_action_rows,
        test_samples=test_samples,
        model_probs=model_probs,
        market=market_probs(test_samples),
    )

    raw_cold_candidates = build_cold_candidates(
        test_samples=test_samples,
        model_probs=model_probs,
        snapshot=args.cold_snapshot,
    )
    cold_candidates, overlap_diag = filter_cold_candidates_for_overlap(
        raw_cold_candidates,
        main_tickets,
        args.cold_overlap_filter,
    )
    cold_ticket, cold_candidate_matches = build_cold_ticket(
        issue=test_issue,
        train_start_issue=train_issues[0],
        train_end_issue=train_issues[-1],
        profile=cold_profile(args),
        candidates=cold_candidates,
    )

    main_plan_rows = [ticket_plan_row(ticket, "main") for ticket in main_tickets]
    cold_plan_rows = [ticket_plan_row(cold_ticket, "cold")] if cold_ticket is not None else []
    main_budget = sum(float(r["stake_units"]) for r in main_plan_rows)
    cold_budget = sum(float(r["stake_units"]) for r in cold_plan_rows)
    cold_metrics = None
    if cold_plan_rows:
        cold_metrics = {
            "pred_hit_prob": float(cold_plan_rows[0]["pred_hit_prob"]),
            "pred_ev_per_stake": float(cold_plan_rows[0]["pred_ev_per_stake"]),
        }
    window = {
        "issue": test_issue,
        "train_start_issue": train_issues[0],
        "train_end_issue": train_issues[-1],
        "n_train_matches": len(train_samples),
        "n_test_matches": len(test_samples),
        "main_snapshot": args.main_snapshot,
        "cold_snapshot": args.cold_snapshot,
        "cold_overlap_filter": args.cold_overlap_filter,
        **main_diag,
        **overlap_diag,
        "n_cold_candidate_matches": cold_candidate_matches,
        "n_cold_tickets": len(cold_plan_rows),
    }
    triggered = conditional_triggered(
        budget=main_budget,
        cold={"stake": cold_budget, "profit": 0.0, "tickets": float(len(cold_plan_rows)), "hits": 0.0},
        cold_metrics=cold_metrics,
        window=window,
        args=args,
    )
    main_share = args.conditional_main_share if triggered else 1.0
    cold_share = max(0.0, 1.0 - main_share)
    decision = [
        {
            "issue": test_issue,
            "train_start_issue": train_issues[0],
            "train_end_issue": train_issues[-1],
            "triggered": int(triggered),
            "main_share": main_share,
            "cold_share": cold_share,
            "main_budget_units": main_budget,
            "cold_ticket_stake_units": cold_budget,
            "cold_pred_hit_prob": cold_metrics["pred_hit_prob"] if cold_metrics else "",
            "cold_pred_ev_per_stake": cold_metrics["pred_ev_per_stake"] if cold_metrics else "",
            "n_main_tickets": len(main_plan_rows),
            "n_cold_candidate_matches": cold_candidate_matches,
            "n_q_legs": int(window["n_q_legs"]),
            "n_main_match_ids": int(window["n_main_match_ids"]),
            "n_main_covered_pairs": int(window["n_main_covered_pairs"]),
            "candidate_note": "pre-settlement export; no hit/payout/profit columns",
        }
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "live_decision.csv", decision)
    write_csv(args.output_dir / "live_main_tickets.csv", main_plan_rows)
    write_csv(args.output_dir / "live_cold_tickets.csv", cold_plan_rows)
    write_csv(args.output_dir / "live_cold_candidates.csv", cold_candidate_rows(cold_candidates, args.max_candidate_rows))
    write_csv(args.output_dir / "live_window.csv", [window])

    report = [
        "# Combo Live Candidate Export",
        "",
        "This is a pre-settlement plan export. It trains only on prior issues, but the current historical DB contains settled rows; do not use hit/payout fields from other tables when manually reviewing this issue.",
        "",
        "## Decision",
        md_table(decision),
        "## Main Tickets",
        md_table(main_plan_rows[: min(10, len(main_plan_rows))]),
        "## Cold Ticket",
        md_table(cold_plan_rows),
        "## Window",
        md_table([window]),
        "",
        "## Files",
        "",
        "- `live_decision.csv`",
        "- `live_main_tickets.csv`",
        "- `live_cold_tickets.csv`",
        "- `live_cold_candidates.csv`",
        "- `live_window.csv`",
        "",
    ]
    (args.output_dir / "live_candidates_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'live_candidates_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/combo_live_candidates"))
    parser.add_argument("--issue")
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--main-n-legs", type=int, default=7)
    parser.add_argument("--max-main-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--main-snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--dynamic-policy", default="model_draw_ratio_t0.55_k2")
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    parser.add_argument("--cold-snapshot", choices=("final", "1h", "10h"), default="1h")
    parser.add_argument("--cold-n-legs", type=int, default=3)
    parser.add_argument("--cold-min-odds", type=float, default=5.0)
    parser.add_argument("--cold-max-odds", type=float, default=20.0)
    parser.add_argument("--cold-min-model-p", type=float, default=0.16)
    parser.add_argument("--cold-min-ratio", type=float, default=1.25)
    parser.add_argument("--cold-rank-min", type=int, default=3)
    parser.add_argument("--cold-require-top2", action="store_true", default=True)
    parser.add_argument("--cold-overlap-filter", choices=("none", "exact", "covered", "match"), default="match")
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
    parser.add_argument("--max-candidate-rows", type=int, default=100)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
