#!/usr/bin/env python3
"""Focused defensive trade-off around the current 384 Beidan main strategy."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import annual_rows, load_issue_calendar
from scripts.evaluate_n7_sleeve_mix_capital import (
    ARM_ISSUE_PATH,
    CONVEX_ARM,
    CONVEX_MID_ARM,
    CONVEX_WIDE_ARM,
    CURRENT_ISSUE_PATH,
    DD_ARM,
    SMOOTH_ARM,
    combine_rows,
    load_arms,
    load_current,
    ordered_issues,
    summarize,
    write_csv_all,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path


TOTAL_BUDGET = 384.0
BASE_BUDGET = 256.0
DD_UNITS = 32.0
REMAINING = TOTAL_BUDGET - BASE_BUDGET - DD_UNITS


def defensive_specs() -> list[tuple[str, dict[str, float], str]]:
    specs: list[tuple[str, dict[str, float], str]] = [
        (
            "current_reference_256",
            {},
            "Current fixed-256 reference.",
        ),
        (
            "baseline_384_hybrid",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.80, CONVEX_ARM: REMAINING * 0.20},
            "Current balanced 384 candidate: smooth80 + convex20.",
        ),
        (
            "defensive_smooth85_convex15",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.85, CONVEX_ARM: REMAINING * 0.15},
            "Slightly reduce convex draw sleeve and move budget to smoothing.",
        ),
        (
            "defensive_smooth90_convex10",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.90, CONVEX_ARM: REMAINING * 0.10},
            "Moderate defensive interpolation between baseline and smooth100.",
        ),
        (
            "defensive_smooth95_convex05",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.95, CONVEX_ARM: REMAINING * 0.05},
            "Heavy smoothing, small convex draw sleeve.",
        ),
        (
            "defensive_smooth100",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING},
            "Pure smoothing extra sleeve; strongest existing drawdown/loss-streak trade-off.",
        ),
        (
            "lossstreak_smooth80_midconvex20",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.80, CONVEX_MID_ARM: REMAINING * 0.20},
            "Replace same-ticket draw convex sleeve with midconvex variant to reduce loss streak.",
        ),
        (
            "lossstreak_smooth90_midconvex10",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.90, CONVEX_MID_ARM: REMAINING * 0.10},
            "Defensive smoothing plus smaller midconvex sleeve.",
        ),
        (
            "issuewin_smooth80_wideconvex20",
            {DD_ARM: DD_UNITS, SMOOTH_ARM: REMAINING * 0.80, CONVEX_WIDE_ARM: REMAINING * 0.20},
            "Wide convex draw-top-EV sleeve; tests non-full-loss improvement.",
        ),
    ]
    return specs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/main_strategy_defensive_tradeoff_20260629"))
    args = parser.parse_args()

    calendar = load_issue_calendar(args.db)
    current = load_current(CURRENT_ISSUE_PATH, calendar)
    arms = load_arms(ARM_ISSUE_PATH, calendar)
    issues = ordered_issues(calendar, current)

    issue_rows = []
    series = {}
    meta = {}
    for name, allocation, rationale in defensive_specs():
        budget = BASE_BUDGET if name == "current_reference_256" else TOTAL_BUDGET
        rows = combine_rows(
            name=name,
            total_budget=budget,
            allocation=allocation,
            rationale=rationale,
            issues=issues,
            current=current,
            arms=arms,
            calendar=calendar,
        )
        issue_rows.extend(rows)
        series[name] = rows
        meta[name] = (budget, allocation, rationale)

    summary_rows = []
    for name, rows in series.items():
        budget, allocation, rationale = meta[name]
        row = summarize(rows, budget, 2023, 2025)
        row["allocation"] = "; ".join(
            key.removeprefix("n7prot_").removesuffix("__budget256_fractional") + f"={value:g}"
            for key, value in allocation.items()
            if value > 1e-9
        )
        row["rationale"] = rationale
        summary_rows.append(row)
    annual = []
    for rows in series.values():
        annual.extend(annual_rows(rows))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "defensive_issue_profit.csv", issue_rows)
    write_csv_all(args.output_dir / "defensive_summary.csv", summary_rows)
    write_csv_all(args.output_dir / "defensive_annual.csv", annual)
    print(f"Wrote {args.output_dir}")


if __name__ == "__main__":
    main()
