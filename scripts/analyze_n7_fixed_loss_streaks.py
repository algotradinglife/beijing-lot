#!/usr/bin/env python3
"""Analyze common traits inside fixed-stake N=7 losing streaks.

This is a diagnostic script for selector work. It reads an existing backtest
directory and compares issue-level pre-bet features for:

* issues inside long losing streaks,
* other losing issues,
* profitable issues.

Settlement columns are also emitted for diagnosis, but the group comparison is
focused on features visible before settlement: odds, q/p_hat score, handicap,
league, selected outcome mix, and ticket-level predicted EV/hit probability.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def issue_year(issue: str) -> int:
    return 2000 + int(issue[:2])


def issue_sort_key(issue: str) -> tuple[int, str]:
    return issue_year(issue), issue


def fval(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    if raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if math.isfinite(value) else default


def parse_leg_match_ids(legs: str) -> list[int]:
    out = []
    for item in legs.split(";"):
        if not item:
            continue
        match_part = item.split(":", 1)[0]
        try:
            out.append(int(match_part))
        except ValueError:
            continue
    return out


def select_strategy(rows: list[dict[str, str]], regex: str) -> str:
    pattern = re.compile(regex)
    strategies = sorted({row["strategy"] for row in rows if pattern.search(row["strategy"])})
    if not strategies:
        raise SystemExit(f"no strategy matches regex: {regex}")
    if len(strategies) > 1:
        print(f"Multiple strategies matched; using first: {strategies[0]}", file=sys.stderr)
    return strategies[0]


def strip_budget_suffix(strategy: str) -> str:
    return strategy.split("__budget", 1)[0]


def mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else float("nan")


def median(vals: list[float]) -> float:
    return statistics.median(vals) if vals else float("nan")


def percentile(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    vals = sorted(vals)
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)


def classify_streaks(issue_rows: list[dict[str, str]], min_streak: int) -> tuple[dict[str, int], list[dict[str, object]]]:
    streak_id_by_issue: dict[str, int] = {}
    streak_rows: list[dict[str, object]] = []
    current: list[dict[str, str]] = []
    streak_id = 0

    def flush() -> None:
        nonlocal streak_id
        if len(current) < min_streak:
            return
        streak_id += 1
        profit = sum(fval(row, "profit_units") for row in current)
        stake = sum(fval(row, "stake_units") for row in current)
        for row in current:
            streak_id_by_issue[row["issue"]] = streak_id
        streak_rows.append(
            {
                "streak_id": streak_id,
                "start_issue": current[0]["issue"],
                "end_issue": current[-1]["issue"],
                "start_year": issue_year(current[0]["issue"]),
                "end_year": issue_year(current[-1]["issue"]),
                "length": len(current),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
            }
        )

    for row in issue_rows:
        if fval(row, "profit_units") < 0:
            current.append(row)
        else:
            flush()
            current = []
    flush()
    return streak_id_by_issue, streak_rows


def build_issue_features(
    *,
    strategy: str,
    base_strategy: str,
    issue_rows: list[dict[str, str]],
    ticket_rows: list[dict[str, str]],
    decision_rows: list[dict[str, str]],
    min_streak: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    streak_id_by_issue, streaks = classify_streaks(issue_rows, min_streak)
    tickets_by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in ticket_rows:
        if row.get("strategy") == strategy or row.get("original_strategy") == base_strategy:
            tickets_by_issue[row["issue"]].append(row)

    decisions_by_issue_match: dict[tuple[str, int], dict[str, str]] = {}
    for row in decision_rows:
        if row.get("strategy") == base_strategy:
            decisions_by_issue_match[(row["issue"], int(row["match_id"]))] = row

    out: list[dict[str, object]] = []
    selected_decision_rows: list[dict[str, object]] = []
    for issue_row in issue_rows:
        issue = issue_row["issue"]
        tickets = tickets_by_issue.get(issue, [])
        match_counter: Counter[int] = Counter()
        pred_ev = []
        pred_hit = []
        for ticket in tickets:
            pred_ev.append(fval(ticket, "pred_ev_per_stake", float("nan")))
            pred_hit.append(fval(ticket, "pred_hit_prob", float("nan")))
            match_counter.update(parse_leg_match_ids(ticket.get("legs", "")))
        selected_decisions = [
            decisions_by_issue_match[(issue, match_id)]
            for match_id in match_counter
            if (issue, match_id) in decisions_by_issue_match
        ]
        group = (
            "long_loss_streak"
            if issue in streak_id_by_issue
            else ("other_loss" if fval(issue_row, "profit_units") < 0 else "profitable")
        )
        for selected in selected_decisions:
            selected_decision_rows.append(
                {
                    "issue": issue,
                    "year": issue_year(issue),
                    "group": group,
                    "match_id": selected["match_id"],
                    "league": selected.get("league", ""),
                    "hcp": fval(selected, "hcp"),
                    "best_single_code": selected.get("best_single_code", ""),
                    "best_single_odds": fval(selected, "best_single_odds"),
                    "best_single_p_hat": fval(selected, "best_single_p_hat"),
                    "best_single_score": fval(selected, "best_single_score"),
                    "best_single_ev_n7": fval(selected, "best_single_ev_n7"),
                    "hit": fval(selected, "hit"),
                }
            )
        odds = [fval(row, "best_single_odds") for row in selected_decisions]
        p_hats = [fval(row, "best_single_p_hat") for row in selected_decisions]
        scores = [fval(row, "best_single_score") for row in selected_decisions]
        evs = [fval(row, "best_single_ev_n7") for row in selected_decisions]
        hcps = [fval(row, "hcp") for row in selected_decisions]
        protected_flags = [1.0 if row.get("protected_code") else 0.0 for row in selected_decisions]
        realized_leg_hits = [fval(row, "hit") for row in selected_decisions]
        outcomes = Counter(row.get("best_single_code", "") for row in selected_decisions)
        leagues = Counter(row.get("league", "") for row in selected_decisions)
        total_decisions = len(selected_decisions)
        top_league, top_league_count = ("", 0)
        if leagues:
            top_league, top_league_count = leagues.most_common(1)[0]
        row = {
            "strategy": strategy,
            "base_strategy": base_strategy,
            "issue": issue,
            "year": issue_year(issue),
            "group": group,
            "streak_id": streak_id_by_issue.get(issue, ""),
            "tickets": int(float(issue_row.get("tickets", 0) or 0)),
            "hits": int(float(issue_row.get("hits", 0) or 0)),
            "stake_units": fval(issue_row, "stake_units"),
            "profit_units": fval(issue_row, "profit_units"),
            "roi": fval(issue_row, "roi"),
            "unique_matches": total_decisions,
            "avg_ticket_pred_ev": mean([v for v in pred_ev if math.isfinite(v)]),
            "avg_ticket_pred_hit": mean([v for v in pred_hit if math.isfinite(v)]),
            "avg_odds": mean(odds),
            "median_odds": median(odds),
            "p75_odds": percentile(odds, 0.75),
            "max_odds": max(odds) if odds else float("nan"),
            "avg_p_hat": mean(p_hats),
            "avg_score": mean(scores),
            "avg_ev_n7": mean(evs),
            "avg_hcp": mean(hcps),
            "share_hcp_positive": sum(1 for hcp in hcps if hcp > 0) / len(hcps) if hcps else float("nan"),
            "share_hcp_negative": sum(1 for hcp in hcps if hcp < 0) / len(hcps) if hcps else float("nan"),
            "share_hcp_zero": sum(1 for hcp in hcps if hcp == 0) / len(hcps) if hcps else float("nan"),
            "share_outcome_3": outcomes["3"] / total_decisions if total_decisions else float("nan"),
            "share_outcome_1": outcomes["1"] / total_decisions if total_decisions else float("nan"),
            "share_outcome_0": outcomes["0"] / total_decisions if total_decisions else float("nan"),
            "protected_candidate_share": mean(protected_flags),
            "realized_selected_leg_hit_rate": mean(realized_leg_hits),
            "top_league": top_league,
            "top_league_share": top_league_count / total_decisions if total_decisions else float("nan"),
        }
        out.append(row)
    return out, streaks, selected_decision_rows


def group_summary(issue_features: list[dict[str, object]]) -> list[dict[str, object]]:
    numeric_keys = [
        "tickets",
        "hits",
        "profit_units",
        "roi",
        "unique_matches",
        "avg_ticket_pred_ev",
        "avg_ticket_pred_hit",
        "avg_odds",
        "median_odds",
        "p75_odds",
        "max_odds",
        "avg_p_hat",
        "avg_score",
        "avg_ev_n7",
        "avg_hcp",
        "share_hcp_positive",
        "share_hcp_negative",
        "share_hcp_zero",
        "share_outcome_3",
        "share_outcome_1",
        "share_outcome_0",
        "protected_candidate_share",
        "realized_selected_leg_hit_rate",
        "top_league_share",
    ]
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in issue_features:
        grouped[str(row["group"])].append(row)
    out = []
    for group, rows in sorted(grouped.items()):
        item: dict[str, object] = {
            "group": group,
            "n_issues": len(rows),
            "total_profit_units": sum(float(row["profit_units"]) for row in rows),
            "issue_win_rate": sum(1 for row in rows if float(row["profit_units"]) > 0) / len(rows) if rows else float("nan"),
        }
        for key in numeric_keys:
            vals = [float(row[key]) for row in rows if isinstance(row.get(key), (int, float)) and math.isfinite(float(row[key]))]
            item[f"avg_{key}"] = mean(vals)
        out.append(item)
    return out


def categorical_counts(selected_decision_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    league_counts: Counter[tuple[str, str]] = Counter()
    outcome_hcp_counts: Counter[tuple[str, str, str]] = Counter()
    for row in selected_decision_rows:
        group = str(row["group"])
        league_counts[(group, str(row.get("league", "")))] += 1
        hcp = float(row.get("hcp", 0.0))
        if hcp > 0:
            hcp_bucket = "hcp_positive"
        elif hcp < 0:
            hcp_bucket = "hcp_negative"
        else:
            hcp_bucket = "hcp_zero"
        outcome_hcp_counts[(group, str(row.get("best_single_code", "")), hcp_bucket)] += 1

    league_rows = [
        {"group": group, "league": league, "count": count}
        for (group, league), count in league_counts.most_common()
    ]
    outcome_hcp_rows = [
        {"group": group, "outcome": outcome, "hcp_bucket": hcp_bucket, "count": count}
        for (group, outcome, hcp_bucket), count in outcome_hcp_counts.most_common()
    ]
    return league_rows, outcome_hcp_rows


def run(args: argparse.Namespace) -> None:
    result_dir = args.result_dir.resolve()
    issue_rows_all = read_csv(result_dir / "ev_framework_issue_profit.csv")
    strategy = select_strategy(issue_rows_all, args.strategy_regex)
    base_strategy = strip_budget_suffix(strategy)
    issue_rows = sorted(
        [row for row in issue_rows_all if row["strategy"] == strategy],
        key=lambda row: issue_sort_key(row["issue"]),
    )
    ticket_rows = read_csv(result_dir / "ev_framework_budget_fractional_tickets.csv")
    decision_rows = read_csv(result_dir / "ev_framework_decisions.csv")
    features, streaks, selected_decision_rows = build_issue_features(
        strategy=strategy,
        base_strategy=base_strategy,
        issue_rows=issue_rows,
        ticket_rows=ticket_rows,
        decision_rows=decision_rows,
        min_streak=args.min_streak,
    )
    summaries = group_summary(features)
    league_rows, outcome_hcp_rows = categorical_counts(selected_decision_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "loss_streaks.csv", streaks)
    write_csv(out / "loss_streak_issue_features.csv", features)
    write_csv(out / "loss_streak_group_summary.csv", summaries)
    write_csv(out / "loss_streak_selected_decisions.csv", selected_decision_rows)
    write_csv(out / "loss_streak_league_counts.csv", league_rows)
    write_csv(out / "loss_streak_outcome_hcp_counts.csv", outcome_hcp_rows)

    report = [
        "# N=7 fixed-stake losing streak diagnostics",
        "",
        f"- Result dir: `{result_dir}`",
        f"- Strategy: `{strategy}`",
        f"- Base strategy: `{base_strategy}`",
        f"- Min losing streak length: `{args.min_streak}`",
        "",
        "## Losing Streaks",
        "",
        md_table(streaks, limit=80),
        "## Group Summary",
        "",
        md_table(summaries, limit=20),
        "## League Counts",
        "",
        md_table(league_rows, limit=40),
        "## Outcome + Handicap Counts",
        "",
        md_table(outcome_hcp_rows, limit=40),
        "## Files",
        "",
        "- `loss_streaks.csv`",
        "- `loss_streak_issue_features.csv`",
        "- `loss_streak_group_summary.csv`",
        "- `loss_streak_selected_decisions.csv`",
        "- `loss_streak_league_counts.csv`",
        "- `loss_streak_outcome_hcp_counts.csv`",
        "",
    ]
    (out / "loss_streak_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'loss_streak_report.md'}")
    print(f"Wrote {len(streaks)} streak rows and {len(features)} issue feature rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_loss_streak_diagnostics"))
    parser.add_argument("--strategy-regex", default=r"7s0p__budget")
    parser.add_argument("--min-streak", type=int, default=5)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
