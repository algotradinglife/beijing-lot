#!/usr/bin/env python3
"""Summarize q-pocket ticket results by historical periods."""
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

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


DEFAULT_PERIODS = (
    "2014-2017:2014:2017",
    "2018-2020:2018:2020",
    "2021-2023:2021:2023",
    "2024-2025:2024:2025",
)


def issue_year(issue: str) -> int | None:
    text = str(issue).strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    year = 2000 + int(text[:2])
    return year if 2000 <= year <= 2099 else None


def parse_period(raw: str) -> tuple[str, int, int]:
    parts = raw.split(":")
    if len(parts) != 3:
        raise ValueError(f"period must be label:start:end, got {raw!r}")
    label, start, end = parts
    return label, int(start), int(end)


def load_budget_rows(result_dir: Path, label: str) -> list[dict[str, object]]:
    path = result_dir / "q_pocket_budget_rows.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            year = issue_year(str(row["issue"]))
            if year is None:
                continue
            row = dict(row)
            row["run_label"] = label
            row["issue_year"] = year
            rows.append(row)
    return rows


def ex_top_issue_stats(issue_rows: list[dict[str, object]], top_n: int) -> dict[str, float]:
    kept = issue_rows[top_n:]
    stake = sum(float(row["stake_units"]) for row in kept)
    profit = sum(float(row["profit_units"]) for row in kept)
    tickets = sum(float(row["tickets"]) for row in kept)
    hits = sum(float(row["hits"]) for row in kept)
    return {
        "roi": profit / stake if stake > 0 else float("nan"),
        "hit_rate": hits / tickets if tickets > 0 else float("nan"),
        "issue_win_rate": (
            sum(1 for row in kept if float(row["profit_units"]) > 0) / len(kept)
            if kept
            else float("nan")
        ),
        "profit": profit,
        "stake": stake,
    }


def max_drawdown(rows: list[dict[str, object]], *, group_by_issue: bool) -> float:
    equity = 10_000.0
    peak = equity
    max_dd = 0.0
    if group_by_issue:
        grouped: dict[str, float] = defaultdict(float)
        for row in rows:
            grouped[str(row["issue"])] += float(row["profit_units"])
        series = [grouped[issue] for issue in sorted(grouped)]
    else:
        ordered = sorted(rows, key=lambda row: (str(row["issue"]), int(row["ticket_idx"])))
        series = [float(row["profit_units"]) for row in ordered]
    for profit in series:
        equity += profit
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def summarize(rows: list[dict[str, object]], periods: list[tuple[str, int, int]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    period_rows: list[dict[str, object]] = []
    issue_profit_rows: list[dict[str, object]] = []
    for label, start, end in periods:
        period_subset = [row for row in rows if start <= int(row["issue_year"]) <= end]
        grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        for row in period_subset:
            grouped[(str(row["run_label"]), str(row["strategy"]))].append(row)
        for (run_label, strategy), vals in sorted(grouped.items()):
            by_issue: dict[str, dict[str, float]] = defaultdict(
                lambda: {"stake_units": 0.0, "profit_units": 0.0, "hits": 0.0, "tickets": 0.0}
            )
            for row in vals:
                issue = str(row["issue"])
                by_issue[issue]["stake_units"] += float(row["stake_units"])
                by_issue[issue]["profit_units"] += float(row["profit_units"])
                by_issue[issue]["hits"] += float(row["hit"])
                by_issue[issue]["tickets"] += 1.0
            issues = [
                {
                    "run_label": run_label,
                    "period": label,
                    "strategy": strategy,
                    "issue": issue,
                    **data,
                    "roi": data["profit_units"] / data["stake_units"] if data["stake_units"] > 0 else float("nan"),
                }
                for issue, data in by_issue.items()
            ]
            issues.sort(key=lambda row: float(row["profit_units"]), reverse=True)
            issue_profit_rows.extend(sorted(issues, key=lambda row: row["issue"]))

            stake = sum(float(row["stake_units"]) for row in vals)
            profit = sum(float(row["profit_units"]) for row in vals)
            hits = sum(float(row["hit"]) for row in vals)
            profitable_issues = sum(1 for row in issues if float(row["profit_units"]) > 0)
            best_profit = float(issues[0]["profit_units"]) if issues else 0.0
            second_profit = float(issues[1]["profit_units"]) if len(issues) > 1 else 0.0
            ex1 = ex_top_issue_stats(issues, 1)
            ex2 = ex_top_issue_stats(issues, 2)
            verdict = "negative"
            if profit > 0 and ex1["roi"] > 0 and ex2["roi"] > 0:
                verdict = "robust"
            elif profit > 0 and ex1["roi"] > 0:
                verdict = "top2_sensitive_positive"
            elif profit > 0:
                verdict = "jackpot_dependent"
            period_rows.append(
                {
                    "run_label": run_label,
                    "period": label,
                    "strategy": strategy,
                    "n_issues": len(issues),
                    "n_tickets": len(vals),
                    "hit_rate": hits / len(vals) if vals else float("nan"),
                    "issue_win_rate": profitable_issues / len(issues) if issues else float("nan"),
                    "profitable_issues": profitable_issues,
                    "total_stake_units": stake,
                    "total_profit_units": profit,
                    "roi": profit / stake if stake > 0 else float("nan"),
                    "best_issue": issues[0]["issue"] if issues else "",
                    "best_issue_profit_units": best_profit,
                    "best_issue_profit_share": best_profit / profit if profit > 0 and best_profit > 0 else "",
                    "top2_issue_profit_share": (
                        (best_profit + max(0.0, second_profit)) / profit
                        if profit > 0 and best_profit > 0
                        else ""
                    ),
                    "ex_top1_roi": ex1["roi"],
                    "ex_top1_hit_rate": ex1["hit_rate"],
                    "ex_top1_issue_win_rate": ex1["issue_win_rate"],
                    "ex_top2_roi": ex2["roi"],
                    "ex_top2_hit_rate": ex2["hit_rate"],
                    "ex_top2_issue_win_rate": ex2["issue_win_rate"],
                    "max_drawdown_pct_on_10000_ticket": max_drawdown(vals, group_by_issue=False),
                    "max_drawdown_pct_on_10000_issue": max_drawdown(vals, group_by_issue=True),
                    "verdict": verdict,
                }
            )
    period_rows.sort(key=lambda row: (str(row["run_label"]), str(row["period"]), str(row["strategy"])))
    return period_rows, issue_profit_rows


def compact_rows(rows: list[dict[str, object]], strategy_filter: set[str]) -> list[dict[str, object]]:
    keep = [
        "run_label",
        "period",
        "strategy",
        "n_issues",
        "hit_rate",
        "issue_win_rate",
        "total_stake_units",
        "total_profit_units",
        "roi",
        "best_issue_profit_share",
        "ex_top1_roi",
        "ex_top2_roi",
        "max_drawdown_pct_on_10000_issue",
        "verdict",
    ]
    out = []
    for row in rows:
        if strategy_filter and str(row["strategy"]) not in strategy_filter:
            continue
        out.append({key: row.get(key, "") for key in keep})
    return out


def parse_input(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError("--input must be label=path")
    label, path = raw.split("=", 1)
    return label, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="label=result_dir. May be repeated.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--period", action="append", default=list(DEFAULT_PERIODS), help="label:start_year:end_year")
    parser.add_argument(
        "--report-strategy",
        action="append",
        default=[],
        help="Strategy to show in the compact markdown table. May be repeated.",
    )
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    input_labels = []
    for raw in args.input:
        label, path = parse_input(raw)
        input_labels.append(f"{label}={path}")
        rows.extend(load_budget_rows(path, label))
    periods = [parse_period(raw) for raw in args.period]
    period_rows, issue_rows = summarize(rows, periods)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "period_summary.csv", period_rows)
    write_csv(args.output_dir / "period_issue_profit.csv", issue_rows)

    strategy_filter = set(args.report_strategy)
    report = [
        "# Q-pocket period robustness",
        "",
        "## Inputs",
        "",
        *[f"- `{label}`" for label in input_labels],
        "",
        "## Compact Summary",
        md_table(compact_rows(period_rows, strategy_filter)),
        "",
        "## Files",
        "",
        "- `period_summary.csv`",
        "- `period_issue_profit.csv`",
        "",
    ]
    (args.output_dir / "period_robustness_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'period_robustness_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
