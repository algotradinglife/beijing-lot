#!/usr/bin/env python3
"""Merge N=7 rotating coverage arms back into the full production issue set."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_rotating_leg_coverage import fnum, summarize
from scripts.walkforward_beidan_strategy_eval import write_csv


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def base_rows(path: Path, strategy: str) -> list[dict[str, object]]:
    rows = [dict(row) for row in read_csv(path) if row.get("strategy") == strategy]
    if not rows:
        raise SystemExit(f"no base rows for {strategy} in {path}")
    return rows


def strategies(rows: list[dict[str, str]]) -> list[str]:
    return sorted({row["strategy"] for row in rows})


def production_rows_for_strategy(
    *,
    base: list[dict[str, object]],
    replacement_rows: list[dict[str, str]],
    replacement_strategy: str,
    output_strategy: str,
) -> list[dict[str, object]]:
    by_issue = {
        str(row["issue"]): dict(row)
        for row in replacement_rows
        if row.get("strategy") == replacement_strategy
    }
    out = []
    replaced = 0
    for row in base:
        issue = str(row["issue"])
        if issue in by_issue:
            merged = dict(by_issue[issue])
            replaced += 1
        else:
            merged = dict(row)
        merged["strategy"] = output_strategy
        merged["replacement_strategy"] = replacement_strategy if issue in by_issue else ""
        merged["base_strategy"] = row["strategy"]
        merged["was_replaced"] = int(issue in by_issue)
        out.append(merged)
    if replaced == 0:
        raise SystemExit(f"replacement strategy had no overlapping issues: {replacement_strategy}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budgets", type=float, nargs="+", default=[256.0, 512.0])
    parser.add_argument(
        "--base-dir-template",
        default="results/n_dynamic_issue_smoothing_optional_budget{budget}_20260628",
        help="Format string containing {budget}.",
    )
    parser.add_argument("--base-strategy-template", default="dynamic_low5_mid7_high7x30__budget{budget}_fractional")
    parser.add_argument("--replacement-dir", type=Path, default=Path("results/n7_rotating_leg_coverage_20260628"))
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_rotating_leg_coverage_20260628"))
    args = parser.parse_args()

    for budget in args.budgets:
        expected = args.base_strategy_template.format(budget=int(budget))
        path = Path(args.base_dir_template.format(budget=int(budget))) / "n_dynamic_issue_depth_issue_profit.csv"
        if not any(row.get("strategy") == expected for row in read_csv(path)):
            raise SystemExit(f"base strategy not found for budget {budget:g}: {expected}")

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    all_issue_rows: list[dict[str, object]] = []
    all_summary_rows: list[dict[str, object]] = []
    for budget in args.budgets:
        base_strategy = args.base_strategy_template.format(budget=int(budget))
        base_path = Path(args.base_dir_template.format(budget=int(budget))) / "n_dynamic_issue_depth_issue_profit.csv"
        repl_path = args.replacement_dir / f"rotating_cover_budget{budget:g}_issue_profit.csv"
        base = base_rows(base_path, base_strategy)
        replacement_rows = read_csv(repl_path)

        budget_issue_rows: list[dict[str, object]] = []
        current_strategy = f"prod_current_main__budget{budget:g}"
        for row in base:
            current = dict(row)
            current["strategy"] = current_strategy
            current["replacement_strategy"] = ""
            current["base_strategy"] = row["strategy"]
            current["was_replaced"] = 0
            budget_issue_rows.append(current)

        for replacement_strategy in strategies(replacement_rows):
            budget_issue_rows.extend(
                production_rows_for_strategy(
                    base=base,
                    replacement_rows=replacement_rows,
                    replacement_strategy=replacement_strategy,
                    output_strategy=f"prod_{replacement_strategy}",
                )
            )

        summary = summarize(budget_issue_rows, args.recent_min_year, args.recent_max_year)
        replaced_counts = defaultdict(int)
        for issue_row in budget_issue_rows:
            if fnum(issue_row.get("was_replaced")) > 0:
                replaced_counts[str(issue_row["strategy"])] += 1
        for row in summary:
            row["budget_units_per_issue"] = budget
            row["replaced_issue_count"] = replaced_counts[str(row["strategy"])]
        write_csv(out_dir / f"rotating_cover_production_budget{budget:g}_issue_profit.csv", budget_issue_rows)
        write_csv(out_dir / f"rotating_cover_production_budget{budget:g}_summary.csv", summary)
        all_issue_rows.extend(budget_issue_rows)
        all_summary_rows.extend(summary)

    write_csv(out_dir / "rotating_cover_production_issue_profit.csv", all_issue_rows)
    write_csv(out_dir / "rotating_cover_production_summary.csv", all_summary_rows)
    print(f"Wrote {out_dir / 'rotating_cover_production_summary.csv'}")


if __name__ == "__main__":
    main()
