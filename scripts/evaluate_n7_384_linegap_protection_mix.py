#!/usr/bin/env python3
"""Mix line-gap guided N7 protection sleeves inside the selected 384 budget."""
from __future__ import annotations

import argparse
import math
import re
import sys
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_sleeve_mix_capital import (
    CURRENT_PORTFOLIO,
    ISSUE_BUDGET,
    annual_rows,
    combine_rows,
    load_arms,
    load_current,
    ordered_issues,
    short_arm,
    summarize,
    write_csv_all,
    write_equity_svg,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


CURRENT_ISSUE_PATH = Path(
    "results/n7_multi_leg_protection_overlay_large_20260629/"
    "multi_leg_protection_overlay_issue_profit.csv"
)
ARM_ISSUE_PATH = Path(
    "results/n7_linegap_protection_modes_20260629/"
    "multi_leg_protection_issue_profit.csv"
)

TOTAL_BUDGET = 384.0
DD_UNITS = 32.0
SMOOTH_UNITS = 76.8
CONVEX_UNITS = 19.2
DEFENSIVE_DD_UNITS = 64.0
DEFENSIVE_SMOOTH_UNITS = 64.0

MODES = ("risk", "linegap_ev_weak", "linegap_weak", "low_hit_linegap")
FOCUSED_MODES = ("risk", "linegap_ev_weak")
SMOOTH_SHAPES = ("same_ticket4", "c4_k2", "c4_k3", "c4_k4")
CORE_SMOOTH_SHAPES = ("same_ticket4", "c4_k2")


def arm(shape: str, policy: str, mode: str) -> str:
    return f"n7prot_{shape}_{policy}_{mode}__budget256_fractional"


def label_fragment(strategy: str) -> str:
    text = short_arm(strategy)
    for prefix in ("same_ticket", "linegap_", "low_hit_"):
        text = text.replace(prefix, "")
    text = text.replace("__budget256_fractional", "")
    return re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")


def spec_name(prefix: str, allocation: dict[str, float]) -> str:
    pieces = [prefix]
    for strategy, units in allocation.items():
        pieces.append(f"{label_fragment(strategy)}_{int(round(units * 10)):04d}")
    return "__".join(pieces)


def available(strategy: str, arms: dict[str, dict[str, dict[str, object]]]) -> bool:
    return strategy in arms


def add_spec(
    specs: list[tuple[str, dict[str, float], str]],
    *,
    prefix: str,
    allocation: dict[str, float],
    rationale: str,
    arms: dict[str, dict[str, dict[str, object]]],
) -> None:
    clean = {strategy: units for strategy, units in allocation.items() if units > 1e-9}
    if all(available(strategy, arms) for strategy in clean):
        specs.append((spec_name(prefix, clean), clean, rationale))


def build_specs(arms: dict[str, dict[str, dict[str, object]]]) -> list[tuple[str, dict[str, float], str]]:
    specs: list[tuple[str, dict[str, float], str]] = []

    selected = {
        arm("same_ticket2", "alt", "risk"): DD_UNITS,
        arm("same_ticket4", "full", "risk"): SMOOTH_UNITS,
        arm("same_ticket2", "draw", "risk"): CONVEX_UNITS,
    }
    add_spec(
        specs,
        prefix="b384_selected_risk",
        allocation=selected,
        rationale="Current selected 384 sleeve mix rebuilt from the line-gap run.",
        arms=arms,
    )

    # Same topology as the selected 384 mix, but replace each sleeve's leg scorer.
    for dd_mode, smooth_mode, draw_mode in product(MODES, MODES, MODES):
        allocation = {
            arm("same_ticket2", "alt", dd_mode): DD_UNITS,
            arm("same_ticket4", "full", smooth_mode): SMOOTH_UNITS,
            arm("same_ticket2", "draw", draw_mode): CONVEX_UNITS,
        }
        add_spec(
            specs,
            prefix="b384_same_layout",
            allocation=allocation,
            rationale="Same selected topology; only protection scoring mode changes.",
            arms=arms,
        )

    # Focused replacement across smoother shapes, keeping only risk/linegap_ev_weak modes.
    for dd_mode, smooth_shape, smooth_mode, draw_mode in product(
        FOCUSED_MODES,
        SMOOTH_SHAPES,
        FOCUSED_MODES,
        FOCUSED_MODES,
    ):
        allocation = {
            arm("same_ticket2", "alt", dd_mode): DD_UNITS,
            arm(smooth_shape, "full", smooth_mode): SMOOTH_UNITS,
            arm("same_ticket2", "draw", draw_mode): CONVEX_UNITS,
        }
        add_spec(
            specs,
            prefix="b384_smooth_shape",
            allocation=allocation,
            rationale="Risk/linegap_ev_weak scorer with alternative smoothing shapes.",
            arms=arms,
        )

    draw_candidates = sorted(strategy for strategy in arms if "_draw_" in strategy)
    for dd_mode, smooth_shape, smooth_mode, draw_strategy in product(
        FOCUSED_MODES,
        CORE_SMOOTH_SHAPES,
        FOCUSED_MODES,
        draw_candidates,
    ):
        allocation = {
            arm("same_ticket2", "alt", dd_mode): DD_UNITS,
            arm(smooth_shape, "full", smooth_mode): SMOOTH_UNITS,
            draw_strategy: CONVEX_UNITS,
        }
        add_spec(
            specs,
            prefix="b384_draw_shape",
            allocation=allocation,
            rationale="Same 384 budget; convex sleeve explores all generated draw protection shapes.",
            arms=arms,
        )

    # Defensive structure found by the drawdown allocator: 64 DD + 64 smoothing, no convex draw sleeve.
    for dd_mode, smooth_shape, smooth_mode in product(MODES, SMOOTH_SHAPES, MODES):
        allocation = {
            arm("same_ticket2", "alt", dd_mode): DEFENSIVE_DD_UNITS,
            arm(smooth_shape, "full", smooth_mode): DEFENSIVE_SMOOTH_UNITS,
        }
        add_spec(
            specs,
            prefix="b384_def64_64",
            allocation=allocation,
            rationale="Defensive 384 structure: 64 DD sleeve plus 64 smoothing sleeve, no convex sleeve.",
            arms=arms,
        )

    # Preserve order but remove accidental duplicates.
    seen: set[str] = set()
    unique: list[tuple[str, dict[str, float], str]] = []
    for name, allocation, rationale in specs:
        key = ";".join(f"{strategy}:{units:g}" for strategy, units in sorted(allocation.items()))
        if key in seen:
            continue
        seen.add(key)
        unique.append((name, allocation, rationale))
    return unique


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    current = load_current(args.current_issue_path, calendar)
    arms = load_arms(args.arm_issue_path, calendar)
    issues = ordered_issues(calendar, current)
    specs = build_specs(arms)
    if not specs:
        raise SystemExit("no valid line-gap sleeve specs")

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {
        CURRENT_PORTFOLIO: {"allocation": "", "rationale": "Current fixed-256 reference."}
    }

    current_rows: list[dict[str, object]] = []
    for issue in issues:
        row = dict(current[issue])
        row["portfolio"] = CURRENT_PORTFOLIO
        current_rows.append(row)
    series[CURRENT_PORTFOLIO] = current_rows
    all_rows.extend(current_rows)

    for name, allocation, rationale in specs:
        rows = combine_rows(
            name=name,
            total_budget=TOTAL_BUDGET,
            allocation=allocation,
            rationale=rationale,
            issues=issues,
            current=current,
            arms=arms,
            calendar=calendar,
        )
        all_rows.extend(rows)
        series[name] = rows
        meta[name] = {
            "allocation": "; ".join(
                f"{short_arm(strategy)}={units:g}" for strategy, units in allocation.items() if units > 1e-9
            ),
            "rationale": rationale,
        }

    summaries: list[dict[str, object]] = []
    for name, rows in series.items():
        budget = TOTAL_BUDGET if name != CURRENT_PORTFOLIO else ISSUE_BUDGET
        row = summarize(rows, budget, args.recent_min_year, args.recent_max_year)
        row.update(meta[name])
        summaries.append(row)

    summary_df = pd.DataFrame(summaries)
    selected_name = next(name for name in series if name.startswith("b384_selected_risk"))
    selected = summary_df[summary_df["portfolio"] == selected_name].iloc[0]
    selected_profit = float(selected["profit_per_256"])
    selected_maxdd = float(selected["max_drawdown_units"])
    selected_recent = float(selected["recent_profit_per_256"])
    selected_roi = float(selected["roi"])
    summary_df["profit_per_256_delta_vs_selected"] = summary_df["profit_per_256"] - selected_profit
    summary_df["maxdd_delta_vs_selected"] = summary_df["max_drawdown_units"] - selected_maxdd
    summary_df["recent_profit_per_256_delta_vs_selected"] = summary_df["recent_profit_per_256"] - selected_recent
    summary_df["roi_delta_vs_selected"] = summary_df["roi"] - selected_roi
    summary_df["balanced_score"] = (
        summary_df["profit_per_256_delta_vs_selected"]
        + 3.0 * summary_df["maxdd_delta_vs_selected"]
        + 0.35 * summary_df["recent_profit_per_256_delta_vs_selected"]
    )
    summary_df = summary_df.sort_values(["balanced_score", "profit_per_256"], ascending=[False, False])
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "linegap_mix_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "linegap_mix_summary.csv", index=False)
    write_csv(args.output_dir / "linegap_mix_annual.csv", annual)

    candidate_df = summary_df[summary_df["portfolio"] != CURRENT_PORTFOLIO].copy()
    dominates = candidate_df[
        (candidate_df["profit_per_256_delta_vs_selected"] >= 0)
        & (candidate_df["maxdd_delta_vs_selected"] >= 0)
    ].sort_values(["maxdd_delta_vs_selected", "profit_per_256_delta_vs_selected"], ascending=[False, False])
    profit_improves = candidate_df[candidate_df["profit_per_256_delta_vs_selected"] > 0].sort_values(
        ["profit_per_256_delta_vs_selected", "maxdd_delta_vs_selected"],
        ascending=[False, False],
    )
    dd_improves = candidate_df[candidate_df["maxdd_delta_vs_selected"] > 0].sort_values(
        ["maxdd_delta_vs_selected", "profit_per_256_delta_vs_selected"],
        ascending=[False, False],
    )
    balanced = candidate_df.sort_values(["balanced_score", "profit_per_256"], ascending=[False, False])
    selected_summary = summary_df[summary_df["portfolio"].isin([CURRENT_PORTFOLIO, selected_name])]

    plot_names = [selected_name]
    for name in balanced["portfolio"].head(8).tolist():
        if name not in plot_names:
            plot_names.append(name)
    if CURRENT_PORTFOLIO not in plot_names:
        plot_names.insert(0, CURRENT_PORTFOLIO)
    write_equity_svg(args.figure_path, {name: series[name] for name in plot_names if name in series}, calendar)

    top_names = [selected_name] + [name for name in balanced["portfolio"].head(8).tolist() if name != selected_name]
    top_annual = pd.DataFrame(annual)
    if not top_annual.empty:
        top_annual = top_annual[top_annual["portfolio"].isin(top_names)]
        top_annual = top_annual.sort_values(["portfolio", "year"])

    cols = [
        "portfolio",
        "profit_per_256",
        "profit_per_256_delta_vs_selected",
        "roi",
        "max_drawdown_units",
        "maxdd_delta_vs_selected",
        "max_drawdown_budget_equiv",
        "issue_win_rate",
        "non_full_loss_rate",
        "max_dead_streak",
        "recent_profit_per_256",
        "recent_profit_per_256_delta_vs_selected",
        "allocation",
    ]
    report = [
        "# N7 384 Line-Gap Protection Mix",
        "",
        "## Scope",
        "",
        "- Base remains the current fixed-256 N7 strategy.",
        "- Per-issue budget is fixed at 384 units.",
        "- This test only changes the extra 128-unit protection sleeves; no low-N hedge is added.",
        f"- Candidate sleeve mixes evaluated: `{len(specs)}`.",
        "",
        "## Selected Reference",
        "",
        md_table(selected_summary[cols].to_dict("records"), limit=10),
        "",
        "## Candidates Improving Both Profit And MaxDD",
        "",
        md_table(dominates[cols].to_dict("records"), limit=25),
        "",
        "## Best MaxDD Improvements",
        "",
        md_table(dd_improves[cols].to_dict("records"), limit=25),
        "",
        "## Best Profit Improvements",
        "",
        md_table(profit_improves[cols].to_dict("records"), limit=25),
        "",
        "## Best Balanced Score",
        "",
        md_table(balanced[cols + ["balanced_score"]].to_dict("records"), limit=25),
        "",
        "## Annual Rows For Top Balanced Candidates",
        "",
        md_table(top_annual.to_dict("records"), limit=120) if not top_annual.empty else "_No annual rows._",
        "",
        "## Interpretation",
        "",
        "- Positive `maxdd_delta_vs_selected` means the drawdown is less negative than the selected 384 profile.",
        "- A replacement is actionable only if the mixed 384 portfolio improves the whole curve, not merely the standalone sleeve.",
        f"- Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")
    print(f"Wrote {args.output_dir / 'linegap_mix_summary.csv'}")


def load_issue_calendar(db_path: Path) -> dict[str, dict[str, object]]:
    from scripts.evaluate_n7_sleeve_mix_capital import load_issue_calendar as _load_issue_calendar

    return _load_issue_calendar(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--current-issue-path", type=Path, default=CURRENT_ISSUE_PATH)
    parser.add_argument("--arm-issue-path", type=Path, default=ARM_ISSUE_PATH)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/n7_384_linegap_protection_mix_20260629"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_384_linegap_protection_mix_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_384_linegap_protection_mix_2026-06-29.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
