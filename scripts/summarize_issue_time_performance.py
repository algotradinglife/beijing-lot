#!/usr/bin/env python3
"""Summarize issue-level strategy rows into time-normalized performance views."""
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


def as_float(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key, default)
        if value == "":
            return default
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def issue_year(issue: str) -> int | None:
    text = str(issue).strip()
    if len(text) < 2 or not text[:2].isdigit():
        return None
    return 2000 + int(text[:2])


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_segments(raw: str) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    for chunk in raw.split(","):
        text = chunk.strip()
        if not text:
            continue
        if "-" not in text:
            year = int(text)
            segments.append((year, year))
            continue
        start_text, end_text = text.split("-", 1)
        start = int(start_text)
        end = int(end_text)
        if end < start:
            raise ValueError(f"Invalid segment: {text}")
        segments.append((start, end))
    return segments


def load_rows(path: Path, selectors: set[str], policies: set[str]) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(path)
    rows: list[dict[str, object]] = []
    with path.open(newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            selector = str(raw.get("wf_selector") or raw.get("selector", ""))
            policy = "walkforward_policy_selector" if raw.get("wf_selector") else str(raw.get("allocation_policy") or "full_stake")
            if selectors and selector not in selectors:
                continue
            if policies and policy not in policies:
                continue
            year = issue_year(str(raw["issue"]))
            if year is None:
                continue
            row = dict(raw)
            row["selector"] = selector
            row["allocation_policy"] = policy
            row["issue_year"] = year
            rows.append(row)
    rows.sort(key=lambda row: str(row["issue"]))
    return rows


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


def summarize_group(rows: list[dict[str, object]], extra: dict[str, object] | None = None) -> dict[str, object]:
    stake = sum(as_float(row, "stake_units") for row in rows)
    profit = sum(as_float(row, "profit_units") for row in rows)
    hits = sum(as_float(row, "hits") for row in rows)
    tickets = sum(as_float(row, "tickets") for row in rows)
    deployed = [row for row in rows if as_float(row, "stake_units") > 0]
    profits = [as_float(row, "profit_units") for row in rows]
    deployed_profits = [as_float(row, "profit_units") for row in deployed]
    issue_count = len(rows)
    deployed_count = len(deployed)
    years = sorted({int(row["issue_year"]) for row in rows})
    span_years = max(1.0, (max(years) - min(years) + 1) if years else 1.0)
    result = {
        "issues": issue_count,
        "deployed_issues": deployed_count,
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake > 0 else float("nan"),
        "hit_rate": hits / tickets if tickets > 0 else float("nan"),
        "issue_win_rate": (
            sum(1 for row in deployed if as_float(row, "profit_units") > 0) / deployed_count
            if deployed_count
            else float("nan")
        ),
        "avg_stake_per_issue": stake / issue_count if issue_count else float("nan"),
        "avg_profit_per_issue": profit / issue_count if issue_count else float("nan"),
        "avg_profit_per_deployed_issue": profit / deployed_count if deployed_count else float("nan"),
        "profit_per_100_issues": profit / issue_count * 100 if issue_count else float("nan"),
        "stake_per_100_issues": stake / issue_count * 100 if issue_count else float("nan"),
        "profit_per_year": profit / span_years,
        "stake_per_year": stake / span_years,
        "max_drawdown_pct_on_10000": max_drawdown(profits),
        "max_nonpositive_streak_issues": max_loss_streak(profits),
        "max_loss_streak_deployed_issues": max_loss_streak(deployed_profits),
    }
    if extra:
        result.update(extra)
    return result


def annual_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("selector", "")), str(row.get("allocation_policy", "")), int(row["issue_year"]))].append(row)
    out: list[dict[str, object]] = []
    for (selector, policy, year), vals in sorted(grouped.items()):
        out.append(summarize_group(vals, {"selector": selector, "allocation_policy": policy, "year": year}))
    return out


def total_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("selector", "")), str(row.get("allocation_policy", "")))].append(row)
    out: list[dict[str, object]] = []
    for (selector, policy), vals in sorted(grouped.items()):
        out.append(summarize_group(vals, {"selector": selector, "allocation_policy": policy}))
    return out


def segment_summary(rows: list[dict[str, object]], segments: list[tuple[int, int]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("selector", "")), str(row.get("allocation_policy", "")))].append(row)
    out: list[dict[str, object]] = []
    for (selector, policy), vals in sorted(grouped.items()):
        for start_year, end_year in segments:
            chunk = [row for row in vals if start_year <= int(row["issue_year"]) <= end_year]
            if not chunk:
                continue
            losing_years = 0
            for year in range(start_year, end_year + 1):
                year_profit = sum(as_float(row, "profit_units") for row in chunk if int(row["issue_year"]) == year)
                if year_profit < 0:
                    losing_years += 1
            out.append(
                summarize_group(
                    chunk,
                    {
                        "selector": selector,
                        "allocation_policy": policy,
                        "segment": f"{start_year}-{end_year}",
                        "losing_years": losing_years,
                    },
                )
            )
    return out


def rolling_summary(rows: list[dict[str, object]], windows: list[int]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("selector", "")), str(row.get("allocation_policy", "")))].append(row)
    out: list[dict[str, object]] = []
    for (selector, policy), vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda row: str(row["issue"]))
        for window in windows:
            if len(vals) < window:
                continue
            for end_idx in range(window, len(vals) + 1):
                chunk = vals[end_idx - window : end_idx]
                row = summarize_group(
                    chunk,
                    {
                        "selector": selector,
                        "allocation_policy": policy,
                        "window_issues": window,
                        "start_issue": chunk[0]["issue"],
                        "end_issue": chunk[-1]["issue"],
                    },
                )
                out.append(row)
    return out


def rolling_extremes(rolling_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, int], list[dict[str, object]]] = defaultdict(list)
    for row in rolling_rows:
        grouped[(str(row["selector"]), str(row["allocation_policy"]), int(row["window_issues"]))].append(row)
    out: list[dict[str, object]] = []
    for (selector, policy, window), vals in sorted(grouped.items()):
        vals_by_profit = sorted(vals, key=lambda row: as_float(row, "profit_units"))
        vals_by_roi = sorted(vals, key=lambda row: as_float(row, "roi"))
        worst_profit = vals_by_profit[0]
        best_profit = vals_by_profit[-1]
        worst_roi = vals_by_roi[0]
        best_roi = vals_by_roi[-1]
        out.append(
            {
                "selector": selector,
                "allocation_policy": policy,
                "window_issues": window,
                "n_windows": len(vals),
                "avg_profit_units": sum(as_float(row, "profit_units") for row in vals) / len(vals),
                "avg_roi": sum(as_float(row, "roi") for row in vals) / len(vals),
                "positive_profit_window_rate": sum(1 for row in vals if as_float(row, "profit_units") > 0) / len(vals),
                "worst_profit_units": worst_profit["profit_units"],
                "worst_profit_start_issue": worst_profit["start_issue"],
                "worst_profit_end_issue": worst_profit["end_issue"],
                "worst_roi": worst_roi["roi"],
                "worst_roi_start_issue": worst_roi["start_issue"],
                "worst_roi_end_issue": worst_roi["end_issue"],
                "best_profit_units": best_profit["profit_units"],
                "best_profit_start_issue": best_profit["start_issue"],
                "best_profit_end_issue": best_profit["end_issue"],
                "best_roi": best_roi["roi"],
                "best_roi_start_issue": best_roi["start_issue"],
                "best_roi_end_issue": best_roi["end_issue"],
            }
        )
    return out


def compact_total(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "selector",
        "allocation_policy",
        "issues",
        "deployed_issues",
        "stake_units",
        "profit_units",
        "roi",
        "avg_profit_per_issue",
        "profit_per_100_issues",
        "profit_per_year",
        "max_drawdown_pct_on_10000",
        "max_nonpositive_streak_issues",
        "max_loss_streak_deployed_issues",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def compact_annual(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "selector",
        "allocation_policy",
        "year",
        "issues",
        "deployed_issues",
        "stake_units",
        "profit_units",
        "roi",
        "avg_profit_per_issue",
        "max_drawdown_pct_on_10000",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def compact_segment(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "selector",
        "allocation_policy",
        "segment",
        "issues",
        "deployed_issues",
        "stake_units",
        "profit_units",
        "roi",
        "profit_per_year",
        "profit_per_100_issues",
        "losing_years",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def compact_rolling(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "selector",
        "allocation_policy",
        "window_issues",
        "n_windows",
        "avg_profit_units",
        "avg_roi",
        "positive_profit_window_rate",
        "worst_profit_units",
        "worst_profit_start_issue",
        "worst_profit_end_issue",
        "worst_roi",
        "worst_roi_start_issue",
        "worst_roi_end_issue",
        "best_profit_units",
        "best_profit_start_issue",
        "best_profit_end_issue",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--selector", action="append", default=[])
    parser.add_argument("--allocation-policy", action="append", default=[])
    parser.add_argument("--rolling-windows", default="24,52,104")
    parser.add_argument("--segments", default="")
    args = parser.parse_args()

    rows = load_rows(args.input, set(args.selector), set(args.allocation_policy))
    if not rows:
        raise SystemExit("No rows matched the requested filters.")
    windows = parse_ints(args.rolling_windows)
    segments = parse_segments(args.segments)
    total_rows = total_summary(rows)
    annual_rows = annual_summary(rows)
    segment_rows = segment_summary(rows, segments) if segments else []
    rolling_rows = rolling_summary(rows, windows)
    rolling_extreme_rows = rolling_extremes(rolling_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "time_total_summary.csv", total_rows)
    write_csv(args.output_dir / "time_annual_summary.csv", annual_rows)
    if segment_rows:
        write_csv(args.output_dir / "time_segment_summary.csv", segment_rows)
    write_csv(args.output_dir / "time_rolling_windows.csv", rolling_rows)
    write_csv(args.output_dir / "time_rolling_extremes.csv", rolling_extreme_rows)

    report = [
        "# Issue Time Performance",
        "",
        f"- Input: `{args.input}`",
        f"- Rolling windows: `{args.rolling_windows}`",
        "- ROI is still profit / stake inside the selected bucket; unit-time fields are `profit_per_year`, `profit_per_100_issues`, and rolling issue-window profit.",
        "",
        "## Total Normalized",
        md_table(compact_total(total_rows)),
        "## Annual",
        md_table(compact_annual(annual_rows)),
        "## Segments",
        md_table(compact_segment(segment_rows)) if segment_rows else "_No segments requested._",
        "## Rolling Extremes",
        md_table(compact_rolling(rolling_extreme_rows)),
        "",
        "## Files",
        "",
        "- `time_total_summary.csv`",
        "- `time_annual_summary.csv`",
        "- `time_segment_summary.csv`" if segment_rows else "",
        "- `time_rolling_windows.csv`",
        "- `time_rolling_extremes.csv`",
        "",
    ]
    (args.output_dir / "time_performance_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'time_performance_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
