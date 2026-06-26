#!/usr/bin/env python3
"""Evaluate N=7 q-pocket whitelist on the historical full-3SP CSV.

This is a retrospective SP-native validation. It uses the CSV's three SP values
as the price surface and settles with the recorded result. It is useful for
long-horizon q-pocket stability, but it is not a 10h/1h entry simulation.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, transform_legs_for_depth
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_q_pocket_whitelist import (
    compact_summary,
    coverage_snapshot,
    default_gate_specs,
    filter_legs_for_spec,
    leg_detail_rows,
    leg_meta,
    make_constrained_depth_tickets,
    parse_gate_specs,
    stress_summary,
    ticket_composition_rows,
)
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    Leg,
    break_even_factor,
    build_q_baseline_legs,
    dedup_legs_by_match,
    group_by_issue,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


ACTION_COLS = {"3": "sp_3", "1": "sp_1", "0": "sp_0"}


def load_3sp_action_rows(csv_path: Path, min_year: int) -> tuple[list[ActionRow], list[str], dict[str, object]]:
    df = pd.read_csv(csv_path)
    df["kickoff_dt"] = pd.to_datetime(df["kickoff_ts"], errors="coerce")
    df["season_year"] = df["kickoff_dt"].dt.year
    for col in ("expect", "match_no", "handicap", "winning_sp", "sp_3", "sp_1", "sp_0"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["result_code"] = df["result_code"].astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
    df = df[
        (df["season_year"] >= min_year)
        & df["expect"].notna()
        & df["match_no"].notna()
        & df["handicap"].notna()
        & df["result_code"].isin(["3", "1", "0"])
        & df["sp_3"].gt(1.0)
        & df["sp_1"].gt(1.0)
        & df["sp_0"].gt(1.0)
    ].copy()
    df = df.sort_values(["kickoff_dt", "expect", "match_no"]).reset_index(drop=True)

    issue_dates = df.groupby("expect")["kickoff_dt"].max().sort_values()
    issue_order = [str(int(issue)) for issue in issue_dates.index.tolist()]
    issue_order_set = set(issue_order)
    rows: list[ActionRow] = []
    for idx, row in df.iterrows():
        issue = str(int(row.expect))
        if issue not in issue_order_set:
            continue
        match_id = idx + 1
        for action, sp_col in ACTION_COLS.items():
            sp = float(row[sp_col])
            hit = 1 if str(row.result_code) == action else 0
            rows.append(
                ActionRow(
                    match_id=match_id,
                    issue=issue,
                    match_idx=int(row.match_no),
                    kickoff_ts=str(row.kickoff_ts),
                    season_year=int(row.season_year),
                    league=str(row.league) if pd.notna(row.league) else "",
                    hcp=float(row.handicap),
                    result_code=str(row.result_code),
                    winning_sp=sp,
                    action_code=action,
                    action_label=action,
                    selection_set=action,
                    cover_count=1,
                    hit=hit,
                    factor=sp if hit else 0.0,
                    euro_final_odds=sp,
                    euro_final_p=1.0 / sp,
                    euro_1h_odds=None,
                    euro_1h_p=None,
                    euro_10h_odds=None,
                    euro_10h_p=None,
                    euro_final_rank=None,
                )
            )

    meta = {
        "n_matches": int(len(df)),
        "n_action_rows": int(len(rows)),
        "n_issues": int(len(issue_order)),
        "date_start": str(df["kickoff_dt"].min().date()) if len(df) else "",
        "date_end": str(df["kickoff_dt"].max().date()) if len(df) else "",
    }
    return rows, issue_order, meta


def market_probs_by_match(rows: list[ActionRow]) -> dict[int, np.ndarray]:
    by_match: dict[int, dict[str, float]] = {}
    for row in rows:
        if row.euro_final_odds and row.euro_final_odds > 1.0:
            by_match.setdefault(row.match_id, {})[row.action_code] = 1.0 / float(row.euro_final_odds)
    out = {}
    for match_id, vals in by_match.items():
        probs = np.asarray([vals.get("3", 0.0), vals.get("1", 0.0), vals.get("0", 0.0)], dtype=float)
        total = float(probs.sum())
        out[match_id] = probs / total if total > 0 else np.asarray([1 / 3, 1 / 3, 1 / 3], dtype=float)
    return out


def run(args: argparse.Namespace) -> None:
    action_rows, issues, data_meta = load_3sp_action_rows(args.csv, args.min_year)
    action_by_issue = group_by_issue(action_rows)
    gate_specs = parse_gate_specs(args.gate_specs)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    composition_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    candidate_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        train_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
        test_rows = action_by_issue.get(test_issue, [])
        if len(train_rows) < args.min_train_actions or not test_rows:
            continue

        q_model, global_q = train_q_model(train_rows, snapshot="final", prior_n=args.q_prior_n)
        q_legs = build_q_baseline_legs(
            test_rows,
            q_model,
            global_q,
            snapshot="final",
            min_proxy_odds=args.min_sp,
            max_proxy_odds=args.max_sp,
            min_score_factor=threshold,
        )
        if len(q_legs) < args.n_legs:
            continue

        market_by_match = market_probs_by_match(test_rows)
        base_legs, base_weights = transform_legs_for_depth(
            q_legs,
            policy=args.depth_policy,
            probs_by_match=market_by_match,
            market_by_match=market_by_match,
            min_score_factor=threshold,
        )
        if len(base_legs) < args.n_legs:
            continue

        metas = {}
        for leg in base_legs:
            meta = leg_meta(leg, test_rows, "final")
            if meta is not None:
                metas[leg.leg_id] = meta
        candidate_rows.extend(leg_detail_rows(base_legs, metas, "all_q_candidates_3sp", test_issue))

        baseline_strategy = f"q_baseline_3sp_{args.depth_policy}"
        baseline_tickets = make_depth_weighted_tickets(
            base_legs,
            depth_weights=base_weights,
            strategy=baseline_strategy,
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            max_leg_uses=args.max_depth_leg_uses,
            max_ticket_overlap=args.max_depth_ticket_overlap,
        )
        settled = [settle_ticket(ticket) for ticket in baseline_tickets]
        ticket_rows.extend(settled)
        composition_rows.extend(ticket_composition_rows(baseline_tickets, metas, settled))
        coverage_rows.append(
            coverage_snapshot(
                strategy=baseline_strategy,
                test_issue=test_issue,
                q_legs=base_legs,
                policy_legs=base_legs,
                tickets=baseline_tickets,
                metas=metas,
            )
        )

        for spec in gate_specs:
            policy_legs = filter_legs_for_spec(base_legs, metas, spec)
            tag_counts = {
                tag: sum(1 for leg in dedup_legs_by_match(policy_legs) if metas.get(leg.leg_id) and metas[leg.leg_id].tag == tag)
                for tag in ("core", "tail", "draw_tail")
            }
            strategy = f"q_pocket_3sp_{spec.name}"
            skipped_reason = ""
            tickets = []
            if tag_counts["core"] < spec.min_issue_core_legs:
                skipped_reason = f"core_legs<{spec.min_issue_core_legs}"
            elif len(dedup_legs_by_match(policy_legs)) < args.n_legs:
                skipped_reason = "eligible_legs<n_legs"
            else:
                tickets = make_constrained_depth_tickets(
                    policy_legs,
                    metas=metas,
                    depth_weights=base_weights,
                    spec=spec,
                    strategy=strategy,
                    issue=test_issue,
                    n_legs=args.n_legs,
                    max_tickets=args.max_tickets_per_issue,
                    overlap_penalty=args.overlap_penalty,
                    train_start_issue=train_issues[0],
                    train_end_issue=train_issues[-1],
                    max_leg_uses=args.max_depth_leg_uses,
                )
                if not tickets:
                    skipped_reason = "ticket_constraints_unsatisfied"
            settled = [settle_ticket(ticket) for ticket in tickets]
            ticket_rows.extend(settled)
            composition_rows.extend(ticket_composition_rows(tickets, metas, settled))
            candidate_rows.extend(leg_detail_rows(policy_legs, metas, strategy, test_issue))
            coverage_rows.append(
                coverage_snapshot(
                    strategy=strategy,
                    test_issue=test_issue,
                    q_legs=base_legs,
                    policy_legs=policy_legs,
                    tickets=tickets,
                    metas=metas,
                    skipped_reason=skipped_reason,
                )
            )

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_actions": len(train_rows),
                "n_test_actions": len(test_rows),
                "n_q_legs": len(q_legs),
                "n_base_legs": len(base_legs),
                "n_whitelist_legs": len(metas),
            }
        )

    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=False)
    summary = summarize_tickets(budget_rows)
    summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    stress = stress_summary(budget_rows)
    stress_by_strategy = {str(row["strategy"]): row for row in stress}
    issue_profit = issue_profit_rows(budget_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "q_pocket_3sp_tickets.csv", ticket_rows)
    write_csv(out / "q_pocket_3sp_budget_rows.csv", budget_rows)
    write_csv(out / "q_pocket_3sp_summary.csv", summary)
    write_csv(out / "q_pocket_3sp_stress_summary.csv", stress)
    write_csv(out / "q_pocket_3sp_issue_profit.csv", issue_profit)
    write_csv(out / "q_pocket_3sp_coverage.csv", coverage_rows)
    write_csv(out / "q_pocket_3sp_ticket_composition.csv", composition_rows)
    write_csv(out / "q_pocket_3sp_candidates.csv", candidate_rows)
    write_csv(out / "q_pocket_3sp_windows.csv", window_rows)

    report = [
        "# N=7 q-pocket whitelist 3SP retrospective evaluation",
        "",
        f"- CSV: `{args.csv}`",
        f"- Date span: `{data_meta['date_start']}` to `{data_meta['date_end']}`",
        f"- Matches / issues: `{data_meta['n_matches']}` / `{data_meta['n_issues']}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Same-budget issue stake: `{args.issue_budget_units}`",
        "",
        "This is a retrospective SP-native validation, not a 10h/1h entry simulation.",
        "",
        "## Budget Summary",
        md_table(compact_summary(summary, stress_by_strategy)),
        "## Stress Summary",
        md_table(stress[:40]),
        "## Coverage Snapshot",
        md_table(coverage_rows[:80]),
        "",
    ]
    (out / "q_pocket_3sp_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'q_pocket_3sp_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/raw/beidan_full_3sp.csv")
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_q_pocket_whitelist_3sp"))
    parser.add_argument("--min-year", type=int, default=2018)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-actions", type=int, default=500)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=20.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--min-sp", type=float, default=3.0)
    parser.add_argument("--max-sp", type=float, default=8.0)
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--gate-specs", default="all")
    args = parser.parse_args()
    if not args.csv.exists():
        raise SystemExit(f"CSV not found: {args.csv}")
    run(args)


if __name__ == "__main__":
    main()
