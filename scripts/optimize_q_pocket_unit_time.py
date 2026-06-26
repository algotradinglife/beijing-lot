#!/usr/bin/env python3
"""Rank q-pocket issue-level candidates by unit-time performance."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


@dataclass(frozen=True)
class InputSpec:
    label: str
    path: Path


def as_float(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def parse_input(raw: str) -> InputSpec:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("input must be LABEL=PATH")
    label, path = raw.split("=", 1)
    label = label.strip()
    path = path.strip()
    if not label or not path:
        raise argparse.ArgumentTypeError("input must be LABEL=PATH")
    return InputSpec(label=label, path=Path(path))


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def issue_year(issue: str) -> int | None:
    text = issue.strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    return 2000 + int(text[:2])


def max_drawdown(profits: list[float], initial_equity: float = 10_000.0) -> float:
    equity = initial_equity
    peak = equity
    max_dd = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, (equity - peak) / peak)
    return max_dd


def max_loss_streak(profits: list[float]) -> int:
    current = 0
    worst = 0
    for profit in profits:
        if profit > 0:
            current = 0
        else:
            current += 1
            worst = max(worst, current)
    return worst


def rolling_rows(rows: list[dict[str, object]], windows: list[int]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    vals = sorted(rows, key=lambda row: str(row["issue"]))
    for window in windows:
        if len(vals) < window:
            continue
        for end_idx in range(window, len(vals) + 1):
            chunk = vals[end_idx - window : end_idx]
            stake = sum(as_float(row, "stake_units") for row in chunk)
            profit = sum(as_float(row, "profit_units") for row in chunk)
            out.append(
                {
                    "window_issues": window,
                    "start_issue": chunk[0]["issue"],
                    "end_issue": chunk[-1]["issue"],
                    "stake_units": stake,
                    "profit_units": profit,
                    "roi": profit / stake if stake > 0 else float("nan"),
                    "profit_per_100_issues": profit / window * 100,
                }
            )
    return out


def load_rows(inputs: list[InputSpec]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for spec in inputs:
        if not spec.path.exists():
            raise FileNotFoundError(spec.path)
        with spec.path.open(newline="", encoding="utf-8") as f:
            for raw in csv.DictReader(f):
                issue = str(raw["issue"])
                year = issue_year(issue)
                if year is None:
                    continue
                row = dict(raw)
                row["source"] = spec.label
                if row.get("wf_selector"):
                    row["selector"] = str(row["wf_selector"])
                    row["allocation_policy"] = "walkforward_policy_selector"
                else:
                    row["selector"] = str(row.get("selector") or row.get("gate") or "")
                    row["allocation_policy"] = str(row.get("allocation_policy") or "full_stake")
                row["issue_year"] = year
                rows.append(row)
    rows.sort(key=lambda row: (str(row["source"]), str(row["selector"]), str(row["allocation_policy"]), str(row["issue"])))
    return rows


def summarize_group(
    rows: list[dict[str, object]],
    windows: list[int],
    *,
    min_worst_52_profit: float,
    min_worst_104_profit: float,
    min_drawdown_pct: float,
    max_losing_years: int,
    min_profit_per_100: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    vals = sorted(rows, key=lambda row: str(row["issue"]))
    stake = sum(as_float(row, "stake_units") for row in vals)
    profit = sum(as_float(row, "profit_units") for row in vals)
    tickets = sum(as_float(row, "tickets") for row in vals)
    hits = sum(as_float(row, "hits") for row in vals)
    deployed = [row for row in vals if as_float(row, "stake_units") > 0]
    profits = [as_float(row, "profit_units") for row in vals]
    deployed_profits = [as_float(row, "profit_units") for row in deployed]
    years = sorted({int(row["issue_year"]) for row in vals})
    span_years = max(1, max(years) - min(years) + 1) if years else 1

    annual_profit: dict[int, float] = defaultdict(float)
    for row in vals:
        annual_profit[int(row["issue_year"])] += as_float(row, "profit_units")
    losing_years = sum(1 for year in years if annual_profit[year] < 0)

    ranked = sorted(vals, key=lambda row: as_float(row, "profit_units"), reverse=True)
    best_profit = as_float(ranked[0], "profit_units") if ranked else 0.0
    second_profit = as_float(ranked[1], "profit_units") if len(ranked) > 1 else 0.0
    ex_top1 = ranked[1:]
    ex_top2 = ranked[2:]
    ex1_stake = sum(as_float(row, "stake_units") for row in ex_top1)
    ex1_profit = sum(as_float(row, "profit_units") for row in ex_top1)
    ex2_stake = sum(as_float(row, "stake_units") for row in ex_top2)
    ex2_profit = sum(as_float(row, "profit_units") for row in ex_top2)

    roll = rolling_rows(vals, windows)
    roll_by_window: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in roll:
        roll_by_window[int(row["window_issues"])].append(row)

    summary: dict[str, object] = {
        "source": vals[0]["source"] if vals else "",
        "selector": vals[0]["selector"] if vals else "",
        "allocation_policy": vals[0]["allocation_policy"] if vals else "",
        "issues": len(vals),
        "deployed_issues": len(deployed),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake > 0 else float("nan"),
        "hit_rate": hits / tickets if tickets > 0 else float("nan"),
        "issue_win_rate": (
            sum(1 for row in deployed if as_float(row, "profit_units") > 0) / len(deployed)
            if deployed
            else float("nan")
        ),
        "profit_per_100_issues": profit / len(vals) * 100 if vals else float("nan"),
        "stake_per_100_issues": stake / len(vals) * 100 if vals else float("nan"),
        "profit_per_year": profit / span_years,
        "stake_per_year": stake / span_years,
        "losing_years": losing_years,
        "max_drawdown_pct_on_10000": max_drawdown(profits),
        "max_nonpositive_streak_issues": max_loss_streak(profits),
        "max_loss_streak_deployed_issues": max_loss_streak(deployed_profits),
        "best_issue": ranked[0]["issue"] if ranked else "",
        "best_issue_profit_units": best_profit,
        "best_issue_profit_share": best_profit / profit if profit > 0 and best_profit > 0 else "",
        "top2_issue_profit_share": (
            (best_profit + max(0.0, second_profit)) / profit if profit > 0 and best_profit > 0 else ""
        ),
        "ex_top1_roi": ex1_profit / ex1_stake if ex1_stake > 0 else float("nan"),
        "ex_top2_roi": ex2_profit / ex2_stake if ex2_stake > 0 else float("nan"),
    }

    for window in windows:
        window_rows = roll_by_window.get(window, [])
        if not window_rows:
            continue
        by_profit = sorted(window_rows, key=lambda row: as_float(row, "profit_units"))
        worst = by_profit[0]
        best = by_profit[-1]
        prefix = f"w{window}"
        summary[f"{prefix}_positive_window_rate"] = sum(
            1 for row in window_rows if as_float(row, "profit_units") > 0
        ) / len(window_rows)
        summary[f"{prefix}_avg_profit_units"] = sum(as_float(row, "profit_units") for row in window_rows) / len(window_rows)
        summary[f"{prefix}_worst_profit_units"] = worst["profit_units"]
        summary[f"{prefix}_worst_profit_per_100_issues"] = worst["profit_per_100_issues"]
        summary[f"{prefix}_worst_start_issue"] = worst["start_issue"]
        summary[f"{prefix}_worst_end_issue"] = worst["end_issue"]
        summary[f"{prefix}_best_profit_units"] = best["profit_units"]
        summary[f"{prefix}_best_start_issue"] = best["start_issue"]
        summary[f"{prefix}_best_end_issue"] = best["end_issue"]

    failures: list[str] = []
    if as_float(summary, "profit_per_100_issues") < min_profit_per_100:
        failures.append("profit_per_100")
    if as_float(summary, "max_drawdown_pct_on_10000") < min_drawdown_pct:
        failures.append("max_drawdown")
    if int(summary["losing_years"]) > max_losing_years:
        failures.append("losing_years")
    if "w52_worst_profit_units" in summary and as_float(summary, "w52_worst_profit_units") < min_worst_52_profit:
        failures.append("w52_worst")
    if "w104_worst_profit_units" in summary and as_float(summary, "w104_worst_profit_units") < min_worst_104_profit:
        failures.append("w104_worst")

    summary["constraint_pass"] = 0 if failures else 1
    summary["constraint_failures"] = ";".join(failures)
    summary["unit_time_score"] = as_float(summary, "profit_per_100_issues") - 10_000.0 * len(failures)
    return summary, roll


def annual_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                str(row["source"]),
                str(row["selector"]),
                str(row["allocation_policy"]),
                int(row["issue_year"]),
            )
        ].append(row)
    out: list[dict[str, object]] = []
    for (source, selector, policy, year), vals in sorted(grouped.items()):
        stake = sum(as_float(row, "stake_units") for row in vals)
        profit = sum(as_float(row, "profit_units") for row in vals)
        out.append(
            {
                "source": source,
                "selector": selector,
                "allocation_policy": policy,
                "year": year,
                "issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
                "profit_per_100_issues": profit / len(vals) * 100 if vals else float("nan"),
            }
        )
    return out


def compact(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "source",
        "selector",
        "allocation_policy",
        "constraint_pass",
        "issues",
        "stake_units",
        "profit_units",
        "roi",
        "profit_per_100_issues",
        "profit_per_year",
        "losing_years",
        "max_drawdown_pct_on_10000",
        "w52_worst_profit_units",
        "w104_worst_profit_units",
        "w52_positive_window_rate",
        "w104_positive_window_rate",
        "ex_top1_roi",
        "ex_top2_roi",
        "constraint_failures",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def run(args: argparse.Namespace) -> None:
    inputs = [parse_input(raw) for raw in args.input]
    windows = parse_ints(args.rolling_windows)
    rows = load_rows(inputs)

    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["source"]), str(row["selector"]), str(row["allocation_policy"]))].append(row)

    summaries: list[dict[str, object]] = []
    rolling: list[dict[str, object]] = []
    for key, vals in sorted(grouped.items()):
        summary, roll = summarize_group(
            vals,
            windows,
            min_worst_52_profit=args.min_worst_52_profit,
            min_worst_104_profit=args.min_worst_104_profit,
            min_drawdown_pct=args.min_drawdown_pct,
            max_losing_years=args.max_losing_years,
            min_profit_per_100=args.min_profit_per_100,
        )
        summaries.append(summary)
        for row in roll:
            converted = dict(row)
            converted["source"], converted["selector"], converted["allocation_policy"] = key
            rolling.append(converted)

    summaries.sort(
        key=lambda row: (
            int(row["constraint_pass"]),
            as_float(row, "profit_per_100_issues"),
            as_float(row, "w104_worst_profit_units"),
        ),
        reverse=True,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "unit_time_candidate_summary.csv", summaries)
    write_csv(args.output_dir / "unit_time_rolling_windows.csv", rolling)
    write_csv(args.output_dir / "unit_time_annual_summary.csv", annual_summary(rows))
    write_csv(args.output_dir / "unit_time_top_candidates.csv", summaries[: args.top_n])

    passing = [row for row in summaries if int(row["constraint_pass"]) == 1]
    report = [
        "# Q-pocket Unit-Time Optimization",
        "",
        "Candidates are ranked by `profit_per_100_issues` after rolling stress constraints.",
        "",
        f"- Inputs: `{', '.join(args.input)}`",
        f"- Rolling windows: `{args.rolling_windows}`",
        f"- Constraints: w52 >= {args.min_worst_52_profit}, w104 >= {args.min_worst_104_profit}, "
        f"maxDD >= {args.min_drawdown_pct}, losing years <= {args.max_losing_years}, "
        f"profit/100 >= {args.min_profit_per_100}",
        f"- Passing candidates: {len(passing)} / {len(summaries)}",
        "",
        "## Top Passing Candidates",
        md_table(compact(passing[: args.top_n])),
        "## Top Candidates Including Failed Constraints",
        md_table(compact(summaries[: args.top_n])),
        "",
        "## Files",
        "",
        "- `unit_time_candidate_summary.csv`",
        "- `unit_time_top_candidates.csv`",
        "- `unit_time_rolling_windows.csv`",
        "- `unit_time_annual_summary.csv`",
        "",
    ]
    (args.output_dir / "unit_time_optimization_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'unit_time_optimization_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="Input spec LABEL=CSV_PATH")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rolling-windows", default="24,52,104")
    parser.add_argument("--min-worst-52-profit", type=float, default=-900.0)
    parser.add_argument("--min-worst-104-profit", type=float, default=-1400.0)
    parser.add_argument("--min-drawdown-pct", type=float, default=-0.14)
    parser.add_argument("--max-losing-years", type=int, default=4)
    parser.add_argument("--min-profit-per-100", type=float, default=0.0)
    parser.add_argument("--top-n", type=int, default=20)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
