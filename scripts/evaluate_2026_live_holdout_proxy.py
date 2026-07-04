#!/usr/bin/env python3
"""Evaluate a no-leakage 2026 live-data holdout proxy.

This is intentionally a proxy, not the full production 384 replay.  It uses
2026 live snapshots and settlements from ``beidan_live.db`` and freezes the q
model on pre-2026 historical rows.  The objective is to answer whether the
current N7 EV/topology direction still has signal on the available 2026 live
data without feeding 2026 results back into training.
"""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_selector import (
    build_portfolio_issue_rows,
    replay_policy,
    summarize_issue_rows,
    ticket_features,
)
from scripts.evaluate_n7_ev_framework_selector import (
    build_ev_candidates,
    decision_chain_rows,
    make_tickets_for_protection_mode,
    strategy_name,
)
from scripts.evaluate_n7_high_sp_anchor_protection import (
    compact_summary,
    option_stats,
    regime_summary_rows,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_unified_leg_selector import ex_best_issue_rows
from scripts.walkforward_beidan_strategy_eval import (
    ActionRow,
    break_even_factor,
    build_q_baseline_legs,
    group_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
)


OUTCOMES = ("3", "1", "0")
ACTION_DEFS = {
    "3": ("胜", "3", 1),
    "1": ("平", "1", 1),
    "0": ("负", "0", 1),
    "31": ("胜平", "31", 2),
    "30": ("胜负", "30", 2),
    "10": ("平负", "10", 2),
    "310": ("胜平负", "310", 3),
}
OUTCOME_TO_BOOK_INDEX = {"3": 0, "1": 1, "0": 2}


@dataclass(frozen=True)
class Book:
    odds: tuple[float, float, float]
    probs: tuple[float, float, float]
    snapshot_ts: str


def first_existing(paths: tuple[Path, ...]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def parse_ts(raw: object) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    text = text.removesuffix("Z").replace("T", " ")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


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


def normalize_probs(odds: tuple[float, float, float]) -> tuple[float, float, float] | None:
    if any(o <= 1.0 or not math.isfinite(o) for o in odds):
        return None
    inv = [1.0 / o for o in odds]
    total = sum(inv)
    if total <= 0:
        return None
    return tuple(v / total for v in inv)  # type: ignore[return-value]


def make_book(row: sqlite3.Row) -> Book | None:
    odds = (fnum(row["eu_h"], math.nan), fnum(row["eu_d"], math.nan), fnum(row["eu_a"], math.nan))
    probs = normalize_probs(odds)
    if probs is None:
        return None
    return Book(odds=odds, probs=probs, snapshot_ts=str(row["snapshot_ts"]))


def select_book(snaps: list[sqlite3.Row], target: datetime) -> Book | None:
    candidates: list[tuple[datetime, sqlite3.Row]] = []
    for row in snaps:
        ts = parse_ts(row["snapshot_ts"])
        if ts is None or ts > target:
            continue
        if row["eu_h"] is None or row["eu_d"] is None or row["eu_a"] is None:
            continue
        candidates.append((ts, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return make_book(candidates[-1][1])


def load_live_snapshots(conn: sqlite3.Connection) -> dict[str, list[sqlite3.Row]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT match_id, snapshot_ts, sp_3, sp_1, sp_0, eu_h, eu_d, eu_a, source
        FROM snapshots
        ORDER BY match_id, snapshot_ts
        """
    ).fetchall()
    out: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        out[str(row["match_id"])].append(row)
    return dict(out)


def live_issue_inventory(conn: sqlite3.Connection, snapshots: dict[str, list[sqlite3.Row]]) -> list[dict[str, object]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            m.issue,
            COUNT(DISTINCT m.match_id) AS matches,
            COUNT(DISTINCT s.match_id) AS settled,
            COUNT(DISTINCT CASE WHEN s.result_code IN ('3','1','0') AND s.winning_sp > 0 THEN s.match_id END) AS usable_settled,
            MIN(m.kickoff_ts) AS issue_start_ts,
            MAX(m.kickoff_ts) AS issue_close_ts
        FROM matches m
        LEFT JOIN settlements s ON s.match_id = m.match_id
        GROUP BY m.issue
        ORDER BY m.issue
        """
    ).fetchall()
    out: list[dict[str, object]] = []
    for row in rows:
        issue = str(row["issue"])
        snap_rows = conn.execute(
            """
            SELECT m.match_id, m.kickoff_ts
            FROM matches m
            WHERE m.issue = ?
            """,
            (issue,),
        ).fetchall()
        complete_1h = 0
        complete_10h = 0
        complete_pre_kick = 0
        first_snap = ""
        last_snap = ""
        for item in snap_rows:
            kickoff = parse_ts(item["kickoff_ts"])
            if kickoff is None:
                continue
            srows = snapshots.get(str(item["match_id"]), [])
            if srows:
                first_snap = min(first_snap or str(srows[0]["snapshot_ts"]), str(srows[0]["snapshot_ts"]))
                last_snap = max(last_snap, str(srows[-1]["snapshot_ts"]))
            complete_pre_kick += int(select_book(srows, kickoff) is not None)
            complete_1h += int(select_book(srows, kickoff - timedelta(hours=1)) is not None)
            complete_10h += int(select_book(srows, kickoff - timedelta(hours=10)) is not None)
        matches = int(row["matches"])
        settled = int(row["settled"])
        out.append(
            {
                "issue": issue,
                "matches": matches,
                "settled_matches": settled,
                "usable_settled_matches": int(row["usable_settled"]),
                "full_issue_settled": int(matches > 0 and settled == matches),
                "pre_kick_eu_snapshot_matches": complete_pre_kick,
                "snapshot_1h_eu_matches": complete_1h,
                "snapshot_10h_eu_matches": complete_10h,
                "issue_start_ts": row["issue_start_ts"] or "",
                "issue_close_ts": row["issue_close_ts"] or "",
                "first_snapshot_ts": first_snap,
                "last_snapshot_ts": last_snap,
            }
        )
    return out


def load_2026_live_action_rows(
    live_db: Path,
    *,
    require_full_issue_settlement: bool,
    min_1h_snapshot_matches: int,
) -> tuple[list[ActionRow], list[dict[str, object]]]:
    conn = sqlite3.connect(live_db)
    conn.row_factory = sqlite3.Row
    snapshots = load_live_snapshots(conn)
    inventory = live_issue_inventory(conn, snapshots)
    full_issues = {str(row["issue"]) for row in inventory if int(row["full_issue_settled"]) == 1}
    enough_snapshot_issues = {
        str(row["issue"]) for row in inventory if int(row["snapshot_1h_eu_matches"]) >= min_1h_snapshot_matches
    }
    match_rows = conn.execute(
        """
        SELECT
            m.match_id,
            m.issue,
            m.match_idx,
            m.kickoff_ts,
            m.league,
            m.handicap_line,
            s.result_code,
            s.winning_sp
        FROM matches m
        JOIN settlements s ON s.match_id = m.match_id
        WHERE s.result_code IN ('3','1','0')
          AND s.winning_sp IS NOT NULL
          AND s.winning_sp > 0
          AND m.handicap_line IS NOT NULL
        ORDER BY m.issue, m.match_idx
        """
    ).fetchall()

    out: list[ActionRow] = []
    for row in match_rows:
        issue = str(row["issue"])
        if require_full_issue_settlement and issue not in full_issues:
            continue
        if issue not in enough_snapshot_issues:
            continue
        kickoff = parse_ts(row["kickoff_ts"])
        if kickoff is None:
            continue
        snap_rows = snapshots.get(str(row["match_id"]), [])
        final_book = select_book(snap_rows, kickoff)
        book_1h = select_book(snap_rows, kickoff - timedelta(hours=1))
        book_10h = select_book(snap_rows, kickoff - timedelta(hours=10))
        if book_1h is None:
            continue
        match_id_int = int(str(row["issue"])) * 1000 + int(row["match_idx"])
        result = str(row["result_code"])
        winning_sp = float(row["winning_sp"])
        hcp = float(row["handicap_line"])
        season_year = int(str(row["kickoff_ts"])[:4])
        for action_code, (label, selection_set, cover_count) in ACTION_DEFS.items():
            hit = int(result in set(selection_set))
            factor = winning_sp / cover_count if hit else 0.0
            outcome_idx = OUTCOME_TO_BOOK_INDEX.get(action_code)
            out.append(
                ActionRow(
                    match_id=match_id_int,
                    issue=issue,
                    match_idx=int(row["match_idx"]),
                    kickoff_ts=str(row["kickoff_ts"]),
                    season_year=season_year,
                    league=str(row["league"] or ""),
                    hcp=hcp,
                    result_code=result,
                    winning_sp=winning_sp,
                    action_code=action_code,
                    action_label=label,
                    selection_set=selection_set,
                    cover_count=cover_count,
                    hit=hit,
                    factor=factor,
                    euro_final_odds=(final_book.odds[outcome_idx] if final_book and outcome_idx is not None else None),
                    euro_final_p=(final_book.probs[outcome_idx] if final_book and outcome_idx is not None else None),
                    euro_1h_odds=(book_1h.odds[outcome_idx] if outcome_idx is not None else None),
                    euro_1h_p=(book_1h.probs[outcome_idx] if outcome_idx is not None else None),
                    euro_10h_odds=(book_10h.odds[outcome_idx] if book_10h and outcome_idx is not None else None),
                    euro_10h_p=(book_10h.probs[outcome_idx] if book_10h and outcome_idx is not None else None),
                    euro_final_rank=None,
                    kelly_final=None,
                    kelly_10h=None,
                    kelly_1h=None,
                    kelly_initial=None,
                    kelly_move_10h_final=None,
                )
            )
    conn.close()
    return out, inventory


def train_frozen_q_model(
    hist_db: Path,
    *,
    min_year: int,
    snapshot: str,
    prior_n: int,
    train_mode: str,
    train_issues: int,
    settlement_quality: str | None,
) -> tuple[dict[tuple[str, str, str, str], float], float, dict[str, object]]:
    rows = load_action_rows(hist_db, min_year, settlement_quality=settlement_quality)
    rows = [row for row in rows if str(row.issue) < "26000"]
    by_issue = group_by_issue(rows)
    issues = sorted(by_issue)
    if train_mode == "last_n":
        selected_issues = issues[-train_issues:]
    elif train_mode == "all":
        selected_issues = issues
    else:
        raise ValueError(f"unknown train_mode: {train_mode}")
    selected_rows = [row for issue in selected_issues for row in by_issue[issue]]
    q_model, global_q = train_q_model(selected_rows, snapshot=snapshot, prior_n=prior_n)
    meta = {
        "hist_db": str(hist_db),
        "train_mode": train_mode,
        "train_issues": len(selected_issues),
        "train_start_issue": selected_issues[0] if selected_issues else "",
        "train_end_issue": selected_issues[-1] if selected_issues else "",
        "train_rows": len(selected_rows),
        "global_q": global_q,
        "q_model_cells": len(q_model),
        "settlement_quality": settlement_quality or "all",
    }
    return q_model, global_q, meta


def run_holdout(args: argparse.Namespace) -> None:
    q_model, global_q, train_meta = train_frozen_q_model(
        args.hist_db,
        min_year=args.min_year,
        snapshot=args.snapshot,
        prior_n=args.q_prior_n,
        train_mode=args.train_mode,
        train_issues=args.train_issues,
        settlement_quality=args.settlement_quality or None,
    )
    live_rows, inventory = load_2026_live_action_rows(
        args.live_db,
        require_full_issue_settlement=args.require_full_issue_settlement,
        min_1h_snapshot_matches=args.min_1h_snapshot_matches,
    )
    by_issue = group_by_issue(live_rows)
    issues = sorted(by_issue)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    decision_rows: list[dict[str, object]] = []
    outcome_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue in issues:
        test_rows = by_issue[issue]
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
            issue=issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=str(train_meta["train_start_issue"]),
            train_end_issue=str(train_meta["train_end_issue"]),
            full_rows={},
            action_model={},
        )
        ticket_rows.extend(settle_ticket(ticket) for ticket in q_tickets)

        strategy = strategy_name(
            args.min_match_score_ratio,
            args.protection_score_floor_ratio,
            allow_full=args.allow_full,
            n_legs=args.n_legs,
            target_protected_per_ticket=args.target_protected_per_ticket,
            ticket_protection_mode=args.ticket_protection_mode,
        )
        candidates, decisions, issue_outcomes, issue_coverages = build_ev_candidates(
            test_rows,
            stats_by_match,
            strategy=strategy,
            threshold=threshold,
            min_match_score_ratio=args.min_match_score_ratio,
            protection_score_floor_ratio=args.protection_score_floor_ratio,
            min_single_odds=args.min_single_odds,
            max_single_odds=args.max_single_odds,
            min_protected_hit_gain=args.min_protected_hit_gain,
            require_protection_contains_best_single=args.require_protection_contains_best_single,
            allow_full=args.allow_full,
        )
        tickets = make_tickets_for_protection_mode(
            candidates,
            strategy=strategy,
            issue=issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=str(train_meta["train_start_issue"]),
            train_end_issue=str(train_meta["train_end_issue"]),
            ticket_protection_mode=args.ticket_protection_mode,
            target_protected_per_ticket=args.target_protected_per_ticket,
            max_full_cover_per_ticket=args.max_full_cover_per_ticket,
            require_target_protection=args.require_target_protection,
            max_leg_uses=args.max_composition_leg_uses,
        )
        ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)
        decision_rows.extend(decisions)
        outcome_rows.extend(issue_outcomes)
        coverage_rows.extend(issue_coverages)
        window_rows.append(
            {
                "test_issue": issue,
                "train_start_issue": train_meta["train_start_issue"],
                "train_end_issue": train_meta["train_end_issue"],
                "leakage_guard": "frozen_pre_2026_training_only",
                "snapshot": args.snapshot,
                "threshold": threshold,
                "n_test_action_rows": len(test_rows),
                "n_test_matches": len({row.match_id for row in test_rows}),
                "n_q_legs": len(q_legs),
                "n_q_tickets": len(q_tickets),
                "n_ev_candidates": len(candidates),
                "n_ev_tickets": len(tickets),
            }
        )

    raw_summary = summarize_tickets(ticket_rows)
    budget_rows = budgeted_ticket_rows(ticket_rows, issue_budget_units=args.issue_budget_units, fractional=True)
    budget_summary = summarize_tickets(budget_rows)
    issue_profit = issue_profit_rows(budget_rows)
    ex_best = ex_best_issue_rows(issue_profit)
    chain = decision_chain_rows(
        outcome_rows=outcome_rows,
        decision_rows=decision_rows,
        ticket_rows=ticket_rows,
        budget_summary=budget_summary,
        threshold=threshold,
    )

    selector_ticket_rows: list[dict[str, object]] = []
    selector_issue_rows: list[dict[str, object]] = []
    if budget_rows:
        tickets_df = pd.DataFrame(budget_rows)
        feature_rows = tickets_df.apply(
            lambda row: ticket_features(row, q_conf={}, line_gaps={}, line_gap_threshold=0.25),
            axis=1,
        ).apply(pd.Series)
        tickets_df = pd.concat([tickets_df, feature_rows], axis=1)
        source_strategy = f"{strategy}__budget{args.issue_budget_units:g}_fractional"
        policies = [
            "all",
            "draw_free",
            "topology_exact_6n0_1p3_d0",
            "topology_neg0_ge6_d0",
            "topology_neg0_ge5_pos3_ge1_d0",
            "selector_v1_topology_priority",
        ]
        for policy in policies:
            tr, ir = replay_policy(
                tickets_df,
                source_strategy=source_strategy,
                policy=policy,
                issue_budget=args.issue_budget_units,
                top_k=args.selector_top_k,
            )
            selector_ticket_rows.extend(tr)
            selector_issue_rows.extend(ir)
        selector_issue_rows.extend(
            build_portfolio_issue_rows(selector_issue_rows, issue_budget=args.issue_budget_units)
        )
    selector_summary = summarize_issue_rows(selector_issue_rows, "2026_holdout") if selector_issue_rows else []

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "live_holdout_inventory.csv", inventory)
    write_csv_all(args.output_dir / "live_holdout_windows.csv", window_rows)
    write_csv_all(args.output_dir / "live_holdout_raw_tickets.csv", ticket_rows)
    write_csv_all(args.output_dir / "live_holdout_budgeted_tickets.csv", budget_rows)
    write_csv_all(args.output_dir / "live_holdout_raw_summary.csv", raw_summary)
    write_csv_all(args.output_dir / "live_holdout_summary.csv", budget_summary)
    write_csv_all(args.output_dir / "live_holdout_issue_profit.csv", issue_profit)
    write_csv_all(args.output_dir / "live_holdout_ex_best_issue_summary.csv", ex_best)
    write_csv_all(args.output_dir / "live_holdout_decision_chain.csv", chain)
    write_csv_all(args.output_dir / "live_holdout_decisions.csv", decision_rows)
    write_csv_all(args.output_dir / "live_holdout_outcomes.csv", outcome_rows)
    write_csv_all(args.output_dir / "live_holdout_coverages.csv", coverage_rows)
    write_csv_all(args.output_dir / "high_n_selector_selected_tickets.csv", selector_ticket_rows)
    write_csv_all(args.output_dir / "high_n_selector_issue_profit.csv", selector_issue_rows)
    write_csv_all(args.output_dir / "high_n_selector_summary.csv", selector_summary)

    tested_inventory = [row for row in inventory if str(row["issue"]) in issues]
    excluded = [row for row in inventory if str(row["issue"]) not in issues]
    report = [
        "# 2026 Live Holdout Proxy",
        "",
        "Date: 2026-06-29",
        "",
        "## Scope",
        "",
        "- This is a 2026-only live-data proxy, not the full production 384 replay.",
        "- Training is frozen on pre-2026 historical rows; 2026 results are not used to train q.",
        f"- Historical DB: `{args.hist_db}`",
        f"- Live DB: `{args.live_db}`",
        f"- Snapshot used for selection: `{args.snapshot}`",
        f"- Training mode: `{train_meta['train_mode']}` from `{train_meta['train_start_issue']}` to `{train_meta['train_end_issue']}`.",
        f"- Full issue settlement required: `{args.require_full_issue_settlement}`.",
        "",
        "## Data Inventory",
        "",
        md_table(inventory, limit=40),
        "",
        "## Tested Issues",
        "",
        md_table(tested_inventory, limit=40),
        "",
        "## Excluded Issues",
        "",
        md_table(excluded, limit=40),
        "",
        "## Budgeted Strategy Summary",
        "",
        md_table(compact_summary(budget_summary), limit=40),
        "",
        "## High-N Selector Summary",
        "",
        md_table(selector_summary, limit=80),
        "",
        "## Ex-Best Issue",
        "",
        md_table(ex_best, limit=40),
        "",
        "## Decision Chain",
        "",
        md_table(chain, limit=80),
        "",
        "## Interpretation Notes",
        "",
        "- The no-leakage guard uses only snapshots at or before the 1h target before kickoff.",
        "- Partially settled issues are excluded by default to avoid selecting from a biased subset of matches.",
        "- `26011-26050` are settlement-only in local data and are not used here because they lack live snapshots.",
        "- The full production 384 sleeve replay still requires extending the standard modeling DB and ticket-generation chain into 2026.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'live_holdout_inventory.csv'}`",
        f"- `{args.output_dir / 'live_holdout_summary.csv'}`",
        f"- `{args.output_dir / 'live_holdout_issue_profit.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_summary.csv'}`",
        f"- `{args.output_dir / 'high_n_selector_issue_profit.csv'}`",
    ]
    report_text = "\n".join(report)
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text(report_text, encoding="utf-8")
    if args.docs_report_path:
        args.docs_report_path.parent.mkdir(parents=True, exist_ok=True)
        args.docs_report_path.write_text(report_text, encoding="utf-8")
    print(f"Wrote {args.report_path}")
    if args.docs_report_path:
        print(f"Wrote {args.docs_report_path}")
    print(f"Loaded {len(live_rows)} live action rows across {len(issues)} tested issues")


def main() -> None:
    default_hist = first_existing(
        (
            Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
            Path("../../data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
            Path("/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite"),
        )
    )
    default_live = first_existing(
        (
            Path("data/beidan_live.db"),
            Path("../../data/beidan_live.db"),
            Path("/home/drwho1985/workspace/soccer/beijing-lot/data/beidan_live.db"),
        )
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hist-db", type=Path, default=default_hist)
    parser.add_argument("--live-db", type=Path, default=default_live)
    parser.add_argument("--output-dir", type=Path, default=Path("results/2026_live_holdout_proxy_20260629"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("results/2026_live_holdout_proxy_20260629/live_holdout_report.md"),
    )
    parser.add_argument(
        "--docs-report-path",
        type=Path,
        default=Path("docs/research/2026_live_holdout_proxy_2026-06-29.md"),
    )
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--settlement-quality", default="")
    parser.add_argument("--train-mode", choices=("last_n", "all"), default="last_n")
    parser.add_argument("--train-issues", type=int, default=24)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--min-match-score-ratio", type=float, default=0.95)
    parser.add_argument("--protection-score-floor-ratio", type=float, default=0.8)
    parser.add_argument("--min-single-odds", type=float, default=1.0)
    parser.add_argument("--max-single-odds", type=float, default=30.0)
    parser.add_argument("--min-protected-hit-gain", type=float, default=0.02)
    parser.add_argument("--target-protected-per-ticket", type=int, default=2)
    parser.add_argument("--max-full-cover-per-ticket", type=int, default=1)
    parser.add_argument("--max-composition-leg-uses", type=int, default=0)
    parser.add_argument("--ticket-protection-mode", choices=("quota", "single", "optional"), default="optional")
    parser.add_argument("--selector-top-k", type=int, default=30)
    parser.add_argument("--require-target-protection", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-protection-contains-best-single", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--allow-full", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-full-issue-settlement", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--min-1h-snapshot-matches", type=int, default=7)
    args = parser.parse_args()
    if not args.hist_db.exists():
        raise SystemExit(f"historical DB not found: {args.hist_db}")
    if not args.live_db.exists():
        raise SystemExit(f"live DB not found: {args.live_db}")
    run_holdout(args)


if __name__ == "__main__":
    main()
