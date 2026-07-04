#!/usr/bin/env python3
"""Analyze whether N7 performance is constrained by candidate pool size.

The analysis joins pre-match candidate metrics from the N7 EV framework with
the current N7 core issue PnL.  It separates outcome count from distinct match
count, because N=7 only benefits from a large candidate pool when high-EV
outcomes are spread across enough matches.
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

from scripts.evaluate_n3_independent_selector import fnum, write_csv_all
from scripts.walkforward_beidan_strategy_eval import md_table


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pearson(xs: list[float], ys: list[float]) -> float:
    vals = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(vals) < 2:
        return math.nan
    xs = [x for x, _ in vals]
    ys = [y for _, y in vals]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return math.nan
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    out = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        rank = (i + j - 1) / 2.0 + 1.0
        for k in range(i, j):
            out[ordered[k][0]] = rank
        i = j
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    vals = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(vals) < 2:
        return math.nan
    return pearson(ranks([x for x, _ in vals]), ranks([y for _, y in vals]))


def max_drawdown(profits: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def load_candidate_pool(outcomes_path: Path, decisions_path: Path, source_strategy: str) -> dict[str, dict[str, object]]:
    raw: dict[str, dict[str, object]] = defaultdict(
        lambda: {
            "total_options": 0,
            "total_matches": set(),
            "q15_options": 0,
            "q15_matches": set(),
            "q20_options": 0,
            "q20_matches": set(),
            "q23_options": 0,
            "q23_matches": set(),
            "standalone_evpos_options": 0,
            "standalone_evpos_matches": set(),
            "n7_evpos_options": 0,
            "n7_evpos_matches": set(),
            "sum_q20": 0.0,
            "sum_q23": 0.0,
            "top_q": 0.0,
        }
    )
    for row in read_csv(outcomes_path):
        if row.get("strategy") != source_strategy:
            continue
        issue = str(row["issue"])
        match_id = str(row["match_id"])
        q = fnum(row.get("q"))
        ev_standalone = fnum(row.get("outcome_ev_standalone"))
        ev_n7 = fnum(row.get("outcome_ev_n7"))
        item = raw[issue]
        item["total_options"] = int(item["total_options"]) + 1
        item["total_matches"].add(match_id)
        item["top_q"] = max(fnum(item["top_q"]), q)
        if q >= 1.5:
            item["q15_options"] = int(item["q15_options"]) + 1
            item["q15_matches"].add(match_id)
        if q >= 2.0:
            item["q20_options"] = int(item["q20_options"]) + 1
            item["q20_matches"].add(match_id)
            item["sum_q20"] = fnum(item["sum_q20"]) + q
        if q >= 2.3:
            item["q23_options"] = int(item["q23_options"]) + 1
            item["q23_matches"].add(match_id)
            item["sum_q23"] = fnum(item["sum_q23"]) + q
        if ev_standalone > 0:
            item["standalone_evpos_options"] = int(item["standalone_evpos_options"]) + 1
            item["standalone_evpos_matches"].add(match_id)
        if ev_n7 > 0:
            item["n7_evpos_options"] = int(item["n7_evpos_options"]) + 1
            item["n7_evpos_matches"].add(match_id)

    decision_raw: dict[str, dict[str, float]] = defaultdict(
        lambda: {
            "decision_matches": 0.0,
            "decision_cover_slots": 0.0,
            "sum_decision_score": 0.0,
            "top_decision_score": 0.0,
        }
    )
    for row in read_csv(decisions_path):
        if row.get("strategy") != source_strategy:
            continue
        issue = str(row["issue"])
        item = decision_raw[issue]
        item["decision_matches"] += 1
        item["decision_cover_slots"] += fnum(row.get("chosen_cover_count"))
        score = fnum(row.get("chosen_score"))
        item["sum_decision_score"] += score
        item["top_decision_score"] = max(item["top_decision_score"], score)

    out: dict[str, dict[str, object]] = {}
    for issue, item in raw.items():
        decisions = decision_raw.get(issue, {})
        q20_options = int(item["q20_options"])
        q23_options = int(item["q23_options"])
        decision_matches = fnum(decisions.get("decision_matches"))
        q20_matches = len(item["q20_matches"])
        q23_matches = len(item["q23_matches"])
        out[issue] = {
            "issue": issue,
            "total_options": int(item["total_options"]),
            "total_matches": len(item["total_matches"]),
            "q15_options": int(item["q15_options"]),
            "q15_matches": len(item["q15_matches"]),
            "q20_options": q20_options,
            "q20_matches": q20_matches,
            "q23_options": q23_options,
            "q23_matches": q23_matches,
            "standalone_evpos_options": int(item["standalone_evpos_options"]),
            "standalone_evpos_matches": len(item["standalone_evpos_matches"]),
            "n7_evpos_options": int(item["n7_evpos_options"]),
            "n7_evpos_matches": len(item["n7_evpos_matches"]),
            "avg_q20": fnum(item["sum_q20"]) / q20_options if q20_options else math.nan,
            "avg_q23": fnum(item["sum_q23"]) / q23_options if q23_options else math.nan,
            "top_q": fnum(item["top_q"]),
            "q20_match_surplus_vs_n7": q20_matches - 7,
            "q23_match_surplus_vs_n7": q23_matches - 7,
            "decision_matches": decision_matches,
            "decision_cover_slots": fnum(decisions.get("decision_cover_slots")),
            "avg_decision_score": fnum(decisions.get("sum_decision_score")) / decision_matches
            if decision_matches
            else math.nan,
            "top_decision_score": fnum(decisions.get("top_decision_score")),
        }
    return out


def load_n7_issue_rows(path: Path, *, model: str, sleeve_label: str) -> list[dict[str, object]]:
    rows = []
    for row in read_csv(path):
        if row.get("model") != model or row.get("sleeve_label") != sleeve_label:
            continue
        rows.append(
            {
                "issue": str(row["issue"]),
                "calendar_year": int(fnum(row.get("calendar_year"))),
                "stake_units": fnum(row.get("stake_units")),
                "profit_units": fnum(row.get("profit_units")),
                "roi": fnum(row.get("roi")),
                "tickets": fnum(row.get("tickets")),
                "hits": fnum(row.get("hits")),
                "issue_win": 1 if fnum(row.get("profit_units")) > 0 else 0,
                "non_full_loss": 1 if fnum(row.get("profit_units")) > -0.999 * fnum(row.get("stake_units")) else 0,
            }
        )
    return rows


def join_rows(issue_rows: list[dict[str, object]], pool: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in issue_rows:
        issue = str(row["issue"])
        if issue not in pool:
            continue
        out.append({**row, **pool[issue]})
    return out


def correlation_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    metrics = [
        "total_matches",
        "q15_matches",
        "q20_matches",
        "q23_matches",
        "standalone_evpos_matches",
        "n7_evpos_matches",
        "decision_matches",
        "decision_cover_slots",
        "avg_decision_score",
        "top_decision_score",
        "avg_q20",
        "top_q",
    ]
    out = []
    for metric in metrics:
        xs = [fnum(row.get(metric), math.nan) for row in rows]
        profit = [fnum(row.get("profit_units"), math.nan) for row in rows]
        roi = [fnum(row.get("roi"), math.nan) for row in rows]
        win = [fnum(row.get("issue_win"), math.nan) for row in rows]
        out.append(
            {
                "metric": metric,
                "pearson_profit": pearson(xs, profit),
                "spearman_profit": spearman(xs, profit),
                "spearman_roi": spearman(xs, roi),
                "spearman_issue_win": spearman(xs, win),
            }
        )
    return out


def annual_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["calendar_year"])].append(row)
    out = []
    for year, vals in sorted(grouped.items()):
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(fnum(row.get("issue_win")) for row in vals) / len(vals) if vals else math.nan,
                "non_full_loss_rate": sum(fnum(row.get("non_full_loss")) for row in vals) / len(vals)
                if vals
                else math.nan,
                "avg_total_matches": avg(vals, "total_matches"),
                "avg_q20_matches": avg(vals, "q20_matches"),
                "avg_q23_matches": avg(vals, "q23_matches"),
                "avg_n7_evpos_matches": avg(vals, "n7_evpos_matches"),
                "avg_decision_matches": avg(vals, "decision_matches"),
                "avg_decision_cover_slots": avg(vals, "decision_cover_slots"),
                "avg_decision_score": avg(vals, "avg_decision_score"),
                "avg_top_q": avg(vals, "top_q"),
                "max_drawdown_units": max_drawdown([fnum(row.get("profit_units")) for row in vals]),
            }
        )
    return out


def avg(rows: list[dict[str, object]], key: str) -> float:
    vals = [fnum(row.get(key), math.nan) for row in rows]
    vals = [v for v in vals if math.isfinite(v)]
    return sum(vals) / len(vals) if vals else math.nan


def bin_rows(rows: list[dict[str, object]], metric: str, cuts: list[float]) -> list[dict[str, object]]:
    out = []
    for lo, hi in zip(cuts, cuts[1:]):
        vals = [row for row in rows if lo <= fnum(row.get(metric), -math.inf) < hi]
        if not vals:
            continue
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "metric": metric,
                "bucket": f"{lo:g}-{hi:g}",
                "n_issues": len(vals),
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(fnum(row.get("issue_win")) for row in vals) / len(vals),
                "non_full_loss_rate": sum(fnum(row.get("non_full_loss")) for row in vals) / len(vals),
                "avg_metric": avg(vals, metric),
                "avg_decision_score": avg(vals, "avg_decision_score"),
            }
        )
    return out


def top_bottom_years(annual: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        [
            {
                "year": row["year"],
                "profit_units": row["profit_units"],
                "roi": row["roi"],
                "avg_q20_matches": row["avg_q20_matches"],
                "avg_decision_matches": row["avg_decision_matches"],
                "avg_decision_score": row["avg_decision_score"],
            }
            for row in annual
        ],
        key=lambda row: fnum(row["profit_units"]),
    )


def run(args: argparse.Namespace) -> None:
    pool = load_candidate_pool(args.outcomes_path, args.decisions_path, args.source_strategy)
    issue_rows = load_n7_issue_rows(args.issue_profit_path, model=args.model, sleeve_label=args.sleeve_label)
    joined = join_rows(issue_rows, pool)
    corr = correlation_rows(joined)
    annual = annual_rows(joined)
    bins = []
    bins.extend(bin_rows(joined, "q20_matches", [0, 40, 70, 110, 10_000]))
    bins.extend(bin_rows(joined, "decision_matches", [0, 40, 70, 110, 150, 10_000]))
    years_by_profit = top_bottom_years(annual)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "n7_candidate_pool_by_issue.csv", joined)
    write_csv_all(args.output_dir / "n7_candidate_pool_annual.csv", annual)
    write_csv_all(args.output_dir / "n7_candidate_pool_correlations.csv", corr)
    write_csv_all(args.output_dir / "n7_candidate_pool_bins.csv", bins)

    keep_corr = [
        "metric",
        "pearson_profit",
        "spearman_profit",
        "spearman_roi",
        "spearman_issue_win",
    ]
    keep_annual = [
        "year",
        "n_issues",
        "profit_units",
        "roi",
        "issue_win_rate",
        "avg_q20_matches",
        "avg_decision_matches",
        "avg_decision_score",
        "max_drawdown_units",
    ]
    report = [
        "# N7 candidate pool constraint audit",
        "",
        f"- N7 PnL source: `{args.issue_profit_path}` filtered by `model={args.model}`, `sleeve_label={args.sleeve_label}`.",
        f"- Candidate source: `{args.outcomes_path}` and `{args.decisions_path}`, `strategy={args.source_strategy}`.",
        "- `q20_matches` means distinct matches with at least one pre-match outcome `q >= 2.0`.",
        "- Distinct match count matters more than raw outcome count for N=7, because one ticket needs seven different matches.",
        "",
        "## Correlations",
        "",
        md_table([{key: row.get(key, "") for key in keep_corr} for row in corr], limit=40),
        "",
        "## Annual Shape",
        "",
        md_table([{key: row.get(key, "") for key in keep_annual} for row in annual], limit=40),
        "",
        "## Buckets",
        "",
        md_table(bins, limit=40),
        "",
        "## Worst/Best Years By Profit",
        "",
        md_table(years_by_profit, limit=40),
        "",
        "## Read",
        "",
        "- Candidate pool size is a real regime variable, but it is not a complete explanation of N7 PnL.",
        "- Issue-level monotonic correlations are positive but modest; profit is still dominated by rare convex hits.",
        "- Thin high-EV match pools should be treated as a sizing/selector warning, not as a hard no-bet rule.",
        "- The practical use is likely dynamic N/depth: high candidate breadth can justify higher N or more diverse tickets; thin breadth should push toward lower-N/high-win sleeves or smaller core exposure.",
        "",
        "## Files",
        "",
        f"- Issue join: `{args.output_dir / 'n7_candidate_pool_by_issue.csv'}`",
        f"- Annual: `{args.output_dir / 'n7_candidate_pool_annual.csv'}`",
        f"- Correlations: `{args.output_dir / 'n7_candidate_pool_correlations.csv'}`",
        f"- Buckets: `{args.output_dir / 'n7_candidate_pool_bins.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outcomes-path",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_outcomes.csv"),
    )
    parser.add_argument(
        "--decisions-path",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_decisions.csv"),
    )
    parser.add_argument("--source-strategy", default="ev_m0p95_p0p8_full_opt")
    parser.add_argument(
        "--issue-profit-path",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--model", default="core512_none0")
    parser.add_argument("--sleeve-label", default="none")
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_candidate_pool_constraint_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_candidate_pool_constraint_2026-06-28.md"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
