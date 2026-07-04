#!/usr/bin/env python3
"""Build fixed N7/N5/N3 budget-ratio portfolios from issue-level arms."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_rotating_n5_sleeve_combo import (
    N7_ARMS,
    annual_rows,
    combine_issue_rows,
    fnum,
    load_issue_calendar,
    read_csv,
    rows_by_strategy,
    summarize,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


N5_OP_STRATEGY = "dynamic_static_n5x90__budget256_fractional"
N5_STD_STRATEGY = "dynamic_static_n5x90__budget256_fractional"
N3_STRATEGY = "dynamic_static_n3x180__budget256_fractional"


def parse_strings(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def allocation_grid(
    *,
    n7_values: list[int],
    step: int,
    total_budget: int,
    max_n3: int,
    include_n5std: bool,
) -> list[dict[str, int]]:
    out: list[dict[str, int]] = []
    for n7 in n7_values:
        remainder = total_budget - n7
        if remainder < 0:
            continue
        for n3 in range(0, min(max_n3, remainder) + 1, step):
            left_after_n3 = remainder - n3
            if include_n5std:
                for n5std in range(0, left_after_n3 + 1, step):
                    out.append(
                        {
                            "n7": n7,
                            "n5op": left_after_n3 - n5std,
                            "n5std": n5std,
                            "n3": n3,
                        }
                    )
            else:
                out.append({"n7": n7, "n5op": left_after_n3, "n5std": 0, "n3": n3})
    dedup = {tuple(sorted(item.items())): item for item in out}
    return list(dedup.values())


def portfolio_name(n7_label: str, allocation: dict[str, int]) -> str:
    return (
        f"{n7_label}__n7{allocation['n7']}"
        f"_op{allocation['n5op']}_n5{allocation['n5std']}_n3{allocation['n3']}"
    )


def build(args: argparse.Namespace) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    n7 = rows_by_strategy(args.n7_issue_profit)
    n5op = rows_by_strategy(args.n5_op05_issue_profit)
    n5std = rows_by_strategy(args.n5_standard_issue_profit)
    n3std = rows_by_strategy(args.n3_standard_issue_profit)
    calendar = load_issue_calendar(args.db)
    selected_n7 = parse_strings(args.n7_arms)
    missing_labels = [label for label in selected_n7 if label not in N7_ARMS]
    if missing_labels:
        raise SystemExit(f"unknown N7 labels: {missing_labels}")

    allocations = allocation_grid(
        n7_values=parse_ints(args.n7_values),
        step=args.step,
        total_budget=args.total_budget,
        max_n3=args.max_n3,
        include_n5std=args.include_n5std,
    )

    issue_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    for n7_label in selected_n7:
        n7_strategy = N7_ARMS[n7_label]
        if n7_strategy not in n7:
            raise SystemExit(f"missing N7 strategy: {n7_strategy}")
        for allocation in allocations:
            legs = [(n7, n7_strategy, allocation["n7"] / 512.0, n7_label)]
            if allocation["n5op"]:
                legs.append((n5op, N5_OP_STRATEGY, allocation["n5op"] / 256.0, "N5op"))
            if allocation["n5std"]:
                legs.append((n5std, N5_STD_STRATEGY, allocation["n5std"] / 256.0, "N5std"))
            if allocation["n3"]:
                legs.append((n3std, N3_STRATEGY, allocation["n3"] / 256.0, "N3"))
            portfolio = portfolio_name(n7_label, allocation)
            rows = combine_issue_rows(portfolio, legs, calendar)
            issue_rows.extend(rows)
            summary = summarize(rows, args.recent_min_year, args.recent_max_year)
            protection = allocation["n5op"] + allocation["n5std"] + allocation["n3"]
            summary.update(
                {
                    "n7_arm": n7_label,
                    "n7_budget_units": allocation["n7"],
                    "n5op_budget_units": allocation["n5op"],
                    "n5std_budget_units": allocation["n5std"],
                    "n3_budget_units": allocation["n3"],
                    "n7_share": allocation["n7"] / args.total_budget,
                    "n5_share": (allocation["n5op"] + allocation["n5std"]) / args.total_budget,
                    "n3_share": allocation["n3"] / args.total_budget,
                    "protection_share": protection / args.total_budget,
                    "n_types": sum(1 for key in ("n7", "n5op", "n5std", "n3") if allocation[key] > 0),
                }
            )
            summary_rows.append(summary)
    summary_rows.sort(key=lambda row: (fnum(row["profit_units"]), fnum(row["non_full_loss_rate"])), reverse=True)
    return issue_rows, summary_rows


def run(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    issue_rows, summary_rows = build(args)
    write_csv(args.output_dir / "n7_n5_n3_ratio_issue_profit.csv", issue_rows)
    write_csv(args.output_dir / "n7_n5_n3_ratio_summary.csv", summary_rows)
    write_csv(args.output_dir / "n7_n5_n3_ratio_annual.csv", annual_rows(issue_rows))
    report = [
        "# N7/N5/N3 fixed ratio grid",
        "",
        f"- Total budget: `{args.total_budget}` units per issue",
        f"- N7 values: `{args.n7_values}`",
        f"- N3 max: `{args.max_n3}`",
        f"- Step: `{args.step}`",
        "",
        "## Top Profit",
        "",
        md_table(summary_rows, limit=30),
        "",
        "## High Non-Full-Loss With ROI >= 0.8",
        "",
        md_table(
            [
                row
                for row in sorted(summary_rows, key=lambda item: fnum(item["non_full_loss_rate"]), reverse=True)
                if fnum(row["roi"]) >= 0.8
            ],
            limit=30,
        ),
        "",
    ]
    (args.output_dir / "n7_n5_n3_ratio_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'n7_n5_n3_ratio_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--n7-issue-profit",
        type=Path,
        default=Path("results/n7_rotating_leg_coverage_t30_20260628/rotating_cover_production_budget512_issue_profit.csv"),
    )
    parser.add_argument(
        "--n5-op05-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_overlap050_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument(
        "--n5-standard-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_smoothing_optional_budget256_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument(
        "--n3-standard-issue-profit",
        type=Path,
        default=Path("results/n_dynamic_issue_depth_n3_sweep_20260628/n_dynamic_issue_depth_issue_profit.csv"),
    )
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--n7-arms", default="rot_draw05_tail,rot_draw20_tail,current,rot_full05_head,rot_unc10_head_k2")
    parser.add_argument("--n7-values", default="256,320,384,448,512")
    parser.add_argument("--step", type=int, default=32)
    parser.add_argument("--total-budget", type=int, default=512)
    parser.add_argument("--max-n3", type=int, default=160)
    parser.add_argument("--include-n5std", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_n5_n3_ratio_grid_20260628_timefix"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
