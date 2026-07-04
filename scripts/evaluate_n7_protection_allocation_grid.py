#!/usr/bin/env python3
"""Allocation grid around the N7 core + protected-ticket + N5 sleeve idea."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import (
    ISSUE_BUDGET,
    annual_rows,
    fnum,
    load_issue_calendar,
    row_order,
    summarize,
    with_calendar,
    write_equity_svg,
)
from scripts.evaluate_n7_core_ticket_protection import (
    N5_OVERLAP_PATH,
    N5_OVERLAP_STRATEGY,
    N5_QUALITY_STRATEGY,
    combine_portfolio,
    load_issue_arm,
    write_csv_all,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


CORE_ARM = "core_base__budget256_fractional"
BASELINE_NAME = "grid_core192_n5ov64"

PROTECT_ARMS = {
    "draw_top_ev_k1": "core_tp_only_draw_top_ev_k1__budget256_fractional",
    "draw_top_ev_k2": "core_tp_only_draw_top_ev_k2__budget256_fractional",
    "draw_top_ev_k3": "core_tp_only_draw_top_ev_k3__budget256_fractional",
    "alt_top_ev_k1": "core_tp_only_alt_top_ev_k1__budget256_fractional",
    "full_top_ev_k1": "core_tp_only_full_top_ev_k1__budget256_fractional",
    "full_top_ev_k3": "core_tp_only_full_top_ev_k3__budget256_fractional",
    "draw_risk_k1": "core_tp_only_draw_risk_k1__budget256_fractional",
    "draw_low_hit_k1": "core_tp_only_draw_low_hit_k1__budget256_fractional",
}

N5_ARMS = {
    "n5ov": ("n5_overlap", N5_OVERLAP_STRATEGY),
    "n5quality": ("n5_quality_overlap", N5_QUALITY_STRATEGY),
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_strategy_maps(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["strategy"])][str(row["issue"])] = copied
    return dict(out)


def ordered_issues(calendar: dict[str, dict[str, object]], arms: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    issues = set()
    for arm in (CORE_ARM, "n5_overlap", "n5_quality_overlap"):
        issues.update(arms.get(arm, {}).keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def value_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def allocation_specs(
    *,
    include_low_hit: bool,
    core_units: list[float],
    protect_units: list[float],
    min_n5_units: float,
) -> list[tuple[str, dict[str, float], dict[str, object]]]:
    specs: list[tuple[str, dict[str, float], dict[str, object]]] = []
    specs.append((BASELINE_NAME, {CORE_ARM: 192.0, "n5_overlap": 64.0}, {"protect_label": "none", "n5_label": "n5ov"}))
    protect_items = [
        (label, arm)
        for label, arm in PROTECT_ARMS.items()
        if include_low_hit or "low_hit" not in label
    ]
    for n5_label, (n5_arm, _strategy) in N5_ARMS.items():
        for protect_label, protect_arm in protect_items:
            for core in core_units:
                for protect in protect_units:
                    n5 = ISSUE_BUDGET - core - protect
                    if protect <= 0 or n5 < min_n5_units:
                        continue
                    name = (
                        f"grid_c{value_label(core)}_p{value_label(protect)}_"
                        f"{protect_label}_{n5_label}{value_label(n5)}"
                    )
                    specs.append(
                        (
                            name,
                            {CORE_ARM: core, protect_arm: protect, n5_arm: n5},
                            {
                                "core_units": core,
                                "protect_units": protect,
                                "n5_units": n5,
                                "protect_label": protect_label,
                                "protect_arm": protect_arm,
                                "n5_label": n5_label,
                                "n5_arm": n5_arm,
                            },
                        )
                    )
    return specs


def max_underwater_profit_window(rows: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    worst = {
        "maxdd_window_start_issue": "",
        "maxdd_window_end_issue": "",
        "maxdd_window_issues": 0,
        "maxdd_window_wins": 0,
        "maxdd_window_full_losses": 0,
    }
    worst_dd = 0.0
    for idx, row in enumerate(ordered):
        equity += fnum(row.get("profit_units"))
        if equity >= peak:
            peak = equity
            peak_idx = idx
            continue
        dd = equity - peak
        if dd < worst_dd:
            segment = ordered[peak_idx + 1 : idx + 1]
            worst_dd = dd
            worst = {
                "maxdd_window_start_issue": str(ordered[peak_idx]["issue"]) if peak_idx >= 0 else "",
                "maxdd_window_end_issue": str(row["issue"]),
                "maxdd_window_issues": len(segment),
                "maxdd_window_wins": sum(1 for item in segment if fnum(item.get("profit_units")) > 0),
                "maxdd_window_full_losses": sum(
                    1
                    for item in segment
                    if fnum(item.get("stake_units")) > 0
                    and fnum(item.get("profit_units")) <= -0.999 * fnum(item.get("stake_units"))
                ),
            }
    return worst


def pareto_front(summary: pd.DataFrame) -> pd.DataFrame:
    rows = summary.to_dict("records")
    keep = []
    for row in rows:
        dominated = False
        for other in rows:
            if other is row:
                continue
            better_or_equal = (
                fnum(other["profit_units"]) >= fnum(row["profit_units"])
                and fnum(other["max_drawdown_units"]) >= fnum(row["max_drawdown_units"])
                and fnum(other["roi_ex_best_issue"]) >= fnum(row["roi_ex_best_issue"])
            )
            strictly_better = (
                fnum(other["profit_units"]) > fnum(row["profit_units"])
                or fnum(other["max_drawdown_units"]) > fnum(row["max_drawdown_units"])
                or fnum(other["roi_ex_best_issue"]) > fnum(row["roi_ex_best_issue"])
            )
            if better_or_equal and strictly_better:
                dominated = True
                break
        if not dominated:
            keep.append(row)
    return pd.DataFrame(keep).sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False])


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    arms = load_strategy_maps(args.protection_issue_profit, calendar)
    for arm, strategy in N5_ARMS.values():
        arms[arm] = load_issue_arm(args.n5_overlap_path, strategy, arm, calendar)
    issues = ordered_issues(calendar, arms)

    core_units = [float(x) for x in args.core_units]
    protect_units = [float(x) for x in args.protect_units]
    specs = allocation_specs(
        include_low_hit=args.include_low_hit,
        core_units=core_units,
        protect_units=protect_units,
        min_n5_units=args.min_n5_units,
    )

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta_by_name: dict[str, dict[str, object]] = {}
    for name, allocation, meta in specs:
        rows = combine_portfolio(
            portfolio=name,
            issues=issues,
            arms=arms,
            allocation=allocation,
            calendar=calendar,
        )
        for row in rows:
            row.update(meta)
        all_rows.extend(rows)
        series[name] = rows
        meta_by_name[name] = dict(meta)

    summaries = []
    for name, rows in series.items():
        summary = summarize(rows, args.recent_min_year, args.recent_max_year)
        summary.update(meta_by_name.get(name, {}))
        summary.update(max_underwater_profit_window(rows))
        summaries.append(summary)
    summary_df = pd.DataFrame(summaries)
    summary_df["profit_to_dd"] = summary_df["profit_units"] / summary_df["max_drawdown_units"].abs()
    summary_df["recommended_score"] = (
        summary_df["profit_units"]
        + 1.8 * summary_df["max_drawdown_units"]
        + 90000.0 * summary_df["roi_ex_best_issue"]
        + 35000.0 * summary_df["recent_roi"]
    )
    summary_df = summary_df.sort_values(
        ["recommended_score", "profit_units", "max_drawdown_units"],
        ascending=[False, False, False],
    )
    annual = annual_rows(all_rows)
    pareto = pareto_front(summary_df)

    baseline = summary_df[summary_df["portfolio"] == BASELINE_NAME].iloc[0]
    risk_cap = fnum(baseline["max_drawdown_units"])
    robust = summary_df[
        (summary_df["max_drawdown_units"] >= risk_cap)
        & (summary_df["roi_ex_best_issue"] >= fnum(baseline["roi_ex_best_issue"]))
        & (summary_df["max_dead_streak"] <= fnum(baseline["max_dead_streak"]))
    ].copy()
    robust = robust.sort_values(["profit_units", "recent_profit_units"], ascending=[False, False])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "protection_allocation_grid_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "protection_allocation_grid_summary.csv", index=False)
    write_csv(args.output_dir / "protection_allocation_grid_annual.csv", annual)
    pareto.to_csv(args.output_dir / "protection_allocation_grid_pareto.csv", index=False)
    robust.to_csv(args.output_dir / "protection_allocation_grid_robust.csv", index=False)

    plot_names = [BASELINE_NAME]
    for name in robust["portfolio"].head(4).tolist() + pareto["portfolio"].head(4).tolist():
        if name not in plot_names:
            plot_names.append(name)
    write_equity_svg(args.figure_path, {name: series[name] for name in plot_names[:7]}, calendar)

    selected_names = [BASELINE_NAME]
    selected_names += [name for name in robust["portfolio"].head(8).tolist() if name not in selected_names]
    selected = summary_df[summary_df["portfolio"].isin(selected_names)].copy()
    selected["portfolio"] = pd.Categorical(selected["portfolio"], selected_names, ordered=True)
    selected = selected.sort_values("portfolio")
    top_score = summary_df.head(12)
    top_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(12)
    top_dd = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(12)

    best = robust.iloc[0] if not robust.empty else summary_df.iloc[0]
    report = [
        "# N7 Protected Ticket Allocation Grid",
        "",
        "## Scope",
        "",
        "- 固定每期 `256` units，不做空仓。",
        "- 输入 arm 来自 `n7_core_ticket_protection`，这里只调资金比例。",
        f"- Core grid: `{','.join(str(int(x)) for x in core_units)}`; protected grid: `{','.join(str(int(x)) for x in protect_units)}`; N5 remainder min `{args.min_n5_units:g}`.",
        "- `robust` 约束：maxDD 不差于 `192 core + 64 N5`，ex-best ROI 不差于基线，最长全亏不差于基线。",
        "",
        "## Decision",
        "",
        f"- 当前 robust 首选：`{best['portfolio']}`，profit `{fnum(best['profit_units']):,.0f}`，ROI `{fnum(best['roi']):.2f}`，maxDD `{fnum(best['max_drawdown_units']):,.0f}`，最长全亏 `{int(fnum(best['max_dead_streak']))}`，近三年 profit `{fnum(best['recent_profit_units']):,.0f}`，ex-best ROI `{fnum(best['roi_ex_best_issue']):.2f}`。",
        "- 如果首选仍是 `draw_top_ev_k1` 附近，说明保护票不该扩大成多票保护，而应该保持小额、集中投给最有 EV 的保护票。",
        "",
        "## Selected Robust",
        "",
        md_table(
            selected[
                [
                    "portfolio",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "protect_label",
                    "n5_label",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                    "profit_to_dd",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Top Recommended Score",
        "",
        md_table(
            top_score[
                [
                    "portfolio",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "protect_label",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                    "recommended_score",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Top Profit",
        "",
        md_table(
            top_profit[
                [
                    "portfolio",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "protect_label",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Top MaxDD",
        "",
        md_table(
            top_dd[
                [
                    "portfolio",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "protect_label",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_drawdown_full_loss_equiv",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Pareto Front",
        "",
        md_table(
            pareto[
                [
                    "portfolio",
                    "core_units",
                    "protect_units",
                    "n5_units",
                    "protect_label",
                    "profit_units",
                    "max_drawdown_units",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                ]
            ].head(30).to_dict("records"),
            limit=30,
        ),
        "",
        "## Interpretation",
        "",
        "- `low_hit` 仍保留在网格中用于反例，但不应仅因 profit 排名靠前就采用；需要同时看 maxDD 和 ex-best ROI。",
        "- 若扩大 protected ticket units 后 maxDD 没改善，说明保护票的主要价值是凸性补充，不是稳定止血。",
        f"- Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument(
        "--protection-issue-profit",
        type=Path,
        default=Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_issue_profit.csv"),
    )
    parser.add_argument("--n5-overlap-path", type=Path, default=N5_OVERLAP_PATH)
    parser.add_argument("--core-units", type=float, nargs="+", default=[128, 144, 160, 176, 192, 208])
    parser.add_argument("--protect-units", type=float, nargs="+", default=[16, 24, 32, 48, 64, 80])
    parser.add_argument("--min-n5-units", type=float, default=32.0)
    parser.add_argument("--include-low-hit", action="store_true", default=True)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_protection_allocation_grid_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_protection_allocation_grid_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_protection_allocation_grid_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
