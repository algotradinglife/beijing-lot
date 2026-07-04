#!/usr/bin/env python3
"""Compare capital performance for high-N selector arms.

Input is the issue-level output produced by ``evaluate_high_n_selector.py``.
The accounting assumes a fixed 256-unit stake per active issue.  Calendar-budget
metrics also charge skipped/no-signal issues as opportunity budget so that
narrow selectors can be compared with always-on selectors.
"""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table


SOURCE = "ev_m0p95_p0p8_full_opt__budget256_fractional"
ARM_LABELS = {
    "all": "p0.8 all",
    "topology_neg0_ge6_d0": "core neg0>=6 d0",
    "portfolio_realloc_90_core_neg0ge6_10_exact": "90 core / 10 exact",
    "portfolio_realloc_80_core_neg0ge6_20_exact": "80 core / 20 exact",
    "portfolio_realloc_70_core_neg0ge6_30_exact": "70 core / 30 exact",
    "topology_exact_6n0_1p3_d0": "exact 6n0+1p3",
    "selector_v1_topology_priority": "priority convex",
}
PLOT_SELECTORS = [
    "all",
    "topology_neg0_ge6_d0",
    "portfolio_realloc_90_core_neg0ge6_10_exact",
    "portfolio_realloc_80_core_neg0ge6_20_exact",
    "portfolio_realloc_70_core_neg0ge6_30_exact",
    "topology_exact_6n0_1p3_d0",
]


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def issue_year(issue: object) -> int:
    text = str(issue)
    if len(text) >= 2 and text[:2].isdigit():
        yy = int(text[:2])
        return 2000 + yy if yy < 80 else 1900 + yy
    return 0


def issue_sort_key(issue: object) -> tuple[int, str]:
    return issue_year(issue), str(issue)


def load_issue_dates(db: Path) -> dict[str, str]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT issue, MIN(kickoff_ts) AS issue_date
        FROM matches
        WHERE issue IS NOT NULL
          AND issue != ''
        GROUP BY issue
        """
    ).fetchall()
    conn.close()
    return {
        str(row["issue"]): str(row["issue_date"])
        for row in rows
        if row["issue"] is not None and row["issue_date"] is not None
    }


def longest_underwater(equity_after: list[float]) -> int:
    peak = 0.0
    streak = 0
    best = 0
    for value in equity_after:
        if value >= peak:
            peak = value
            streak = 0
        else:
            streak += 1
            best = max(best, streak)
    return best


def longest_loss_streak(profits: list[float]) -> int:
    streak = 0
    best = 0
    for profit in profits:
        if profit < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def max_drawdown_from_profits(profits: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def summarize_curve(curve: pd.DataFrame, *, calendar_issues: int, issue_budget: float, label: str) -> dict[str, object]:
    active = curve[curve["active"] == 1].copy()
    profit = float(curve["profit_units"].sum())
    deployed = float(active["stake_units"].sum())
    calendar_budget = calendar_issues * issue_budget
    best = float(active["profit_units"].max()) if not active.empty else 0.0
    worst = float(active["profit_units"].min()) if not active.empty else 0.0
    ex_best_profit = profit - best
    ex_best_stake = deployed - (issue_budget if best > 0 else 0.0)
    equity = curve["cum_profit_units"].tolist()
    max_dd = float(curve["drawdown_units"].min()) if not curve.empty else 0.0
    years = sorted(set(int(v) for v in curve["year"].dropna()))
    span = max(1, max(years) - min(years) + 1) if years else 1
    return {
        "label": label,
        "calendar_issues": calendar_issues,
        "active_issues": int(active["issue"].nunique()),
        "deployment_rate": active["issue"].nunique() / calendar_issues if calendar_issues else math.nan,
        "stake_units": deployed,
        "profit_units": profit,
        "roi_on_deployed": profit / deployed if deployed else math.nan,
        "roi_on_calendar_budget": profit / calendar_budget if calendar_budget else math.nan,
        "profit_per_calendar_issue": profit / calendar_issues if calendar_issues else math.nan,
        "profit_per_year": profit / span,
        "issue_win_rate": float((active["profit_units"] > 0).mean()) if not active.empty else math.nan,
        "non_full_loss_rate": float((active["profit_units"] > -0.999999 * issue_budget).mean()) if not active.empty else math.nan,
        "max_drawdown_units": max_dd,
        "max_drawdown_vs_calendar_budget": max_dd / calendar_budget if calendar_budget else math.nan,
        "max_loss_streak": longest_loss_streak(active["profit_units"].tolist()),
        "longest_underwater_issues": longest_underwater(equity),
        "best_issue_profit": best,
        "best_issue_profit_share": best / profit if profit > 0 else math.nan,
        "worst_issue_profit": worst,
        "ex_best_roi_on_deployed": ex_best_profit / ex_best_stake if ex_best_stake > 0 else math.nan,
        "bankroll_for_25pct_dd": abs(max_dd) / 0.25 if max_dd < 0 else 0.0,
        "bankroll_for_15pct_dd": abs(max_dd) / 0.15 if max_dd < 0 else 0.0,
    }


def build_curves(rows: pd.DataFrame, *, issue_dates: dict[str, str], issue_budget: float) -> pd.DataFrame:
    selectors = [selector for selector in PLOT_SELECTORS if selector in set(rows["selector"])]
    calendar = sorted(set(rows["issue"].astype(str)), key=issue_sort_key)
    out = []
    for selector in selectors:
        arm = rows[rows["selector"] == selector].copy()
        by_issue = {str(row["issue"]): row for row in arm.to_dict("records")}
        equity = 0.0
        peak = 0.0
        label = ARM_LABELS.get(selector, selector)
        for idx, issue in enumerate(calendar):
            row = by_issue.get(issue)
            active = 1 if row is not None else 0
            stake = fnum(row.get("stake_units")) if row is not None else 0.0
            profit = fnum(row.get("profit_units")) if row is not None else 0.0
            equity += profit
            peak = max(peak, equity)
            drawdown = equity - peak
            out.append(
                {
                    "selector": selector,
                    "label": label,
                    "issue": issue,
                    "issue_order": idx + 1,
                    "issue_date": issue_dates.get(issue, ""),
                    "year": issue_year(issue),
                    "active": active,
                    "stake_units": stake,
                    "profit_units": profit,
                    "cum_profit_units": equity,
                    "drawdown_units": drawdown,
                    "peak_units": peak,
                }
            )
    return pd.DataFrame(out)


def annual_summary(curves: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (selector, label, year), group in curves.groupby(["selector", "label", "year"], sort=True):
        active = group[group["active"] == 1]
        stake = float(active["stake_units"].sum())
        profit = float(group["profit_units"].sum())
        rows.append(
            {
                "selector": selector,
                "label": label,
                "year": int(year),
                "calendar_issues": int(group["issue"].nunique()),
                "active_issues": int(active["issue"].nunique()),
                "stake_units": stake,
                "profit_units": profit,
                "roi_on_deployed": profit / stake if stake else math.nan,
                "issue_win_rate": float((active["profit_units"] > 0).mean()) if not active.empty else math.nan,
                "window_max_drawdown_units": max_drawdown_from_profits(group["profit_units"].tolist()),
            }
        )
    return pd.DataFrame(rows)


def window_summary(curves: pd.DataFrame, *, min_year: int, max_year: int) -> pd.DataFrame:
    rows = []
    recent = curves[curves["year"].between(min_year, max_year)].copy()
    for (selector, label), group in recent.groupby(["selector", "label"], sort=True):
        active = group[group["active"] == 1]
        stake = float(active["stake_units"].sum())
        profit = float(group["profit_units"].sum())
        rows.append(
            {
                "selector": selector,
                "label": label,
                "period": f"{min_year}-{max_year}",
                "calendar_issues": int(group["issue"].nunique()),
                "active_issues": int(active["issue"].nunique()),
                "deployment_rate": active["issue"].nunique() / group["issue"].nunique()
                if group["issue"].nunique()
                else math.nan,
                "stake_units": stake,
                "profit_units": profit,
                "roi_on_deployed": profit / stake if stake else math.nan,
                "issue_win_rate": float((active["profit_units"] > 0).mean()) if not active.empty else math.nan,
                "window_max_drawdown_units": max_drawdown_from_profits(group["profit_units"].tolist()),
            }
        )
    return pd.DataFrame(rows)


def plot_curves(curves: pd.DataFrame, output_path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    for label, group in curves.groupby("label", sort=False):
        group = group.sort_values("issue_order")
        ax1.plot(group["issue_order"], group["cum_profit_units"], linewidth=1.8, label=label)
        ax2.plot(group["issue_order"], group["drawdown_units"], linewidth=1.4, label=label)
    ax1.axhline(0, color="#666", linewidth=0.8, linestyle="--")
    ax2.axhline(0, color="#666", linewidth=0.8)
    ax1.set_title("High-N Selector Capital Curves, Fixed 256 Units Per Active Issue")
    ax1.set_ylabel("Cumulative profit units")
    ax2.set_ylabel("Drawdown units")
    ax2.set_xlabel("Settled issue order")
    ax1.grid(True, alpha=0.25)
    ax2.grid(True, alpha=0.25)
    ax1.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def compact(rows: pd.DataFrame, columns: list[str], limit: int = 20) -> list[dict[str, object]]:
    if rows.empty:
        return []
    return rows[columns].head(limit).to_dict("records")


def run(args: argparse.Namespace) -> None:
    rows = pd.read_csv(args.issue_profit_path)
    rows = rows[rows["source_strategy"] == args.source_strategy].copy()
    rows = rows[rows["selector"].isin(PLOT_SELECTORS)].copy()
    rows["issue"] = rows["issue"].astype(str)
    rows["year"] = rows["issue"].map(issue_year)

    issue_dates = load_issue_dates(args.db)
    curves = build_curves(rows, issue_dates=issue_dates, issue_budget=args.issue_budget)
    calendar_issues = curves["issue"].nunique()

    summary_rows = []
    for (selector, label), group in curves.groupby(["selector", "label"], sort=False):
        summary_rows.append(
            {
                "selector": selector,
                **summarize_curve(
                    group.sort_values("issue_order"),
                    calendar_issues=calendar_issues,
                    issue_budget=args.issue_budget,
                    label=label,
                ),
            }
        )
    summary = pd.DataFrame(summary_rows).sort_values("profit_units", ascending=False)
    recent = window_summary(curves, min_year=2023, max_year=2025).sort_values("profit_units", ascending=False)
    annual = annual_summary(curves)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output_dir / "high_n_capital_summary.csv", index=False)
    recent.to_csv(args.output_dir / "high_n_capital_recent_2023_2025.csv", index=False)
    annual.to_csv(args.output_dir / "high_n_capital_annual.csv", index=False)
    curves.to_csv(args.output_dir / "high_n_capital_equity_curve.csv", index=False)
    plot_curves(curves, args.figure_path)

    display_cols = [
        "label",
        "calendar_issues",
        "active_issues",
        "deployment_rate",
        "profit_units",
        "roi_on_deployed",
        "roi_on_calendar_budget",
        "profit_per_year",
        "issue_win_rate",
        "max_drawdown_units",
        "longest_underwater_issues",
        "ex_best_roi_on_deployed",
        "bankroll_for_25pct_dd",
    ]
    recent_cols = [
        "label",
        "calendar_issues",
        "active_issues",
        "profit_units",
        "roi_on_deployed",
        "issue_win_rate",
        "window_max_drawdown_units",
    ]
    annual_focus = annual[annual["selector"].isin(["all", "topology_neg0_ge6_d0", "portfolio_realloc_80_core_neg0ge6_20_exact"])]
    report = [
        "# High-N Capital Performance Comparison",
        "",
        "## Scope",
        "",
        f"- Source strategy: `{args.source_strategy}`",
        f"- Issue stake: `{args.issue_budget}` units per active issue.",
        "- Calendar-budget ROI treats every issue in the comparison calendar as if 256 units of capital were reserved, even when a narrow selector has no bet.",
        f"- Equity figure: `{args.figure_path}`",
        "",
        "## Overall",
        "",
        md_table(compact(summary, display_cols, limit=20)),
        "",
        "## Recent 2023-2025",
        "",
        md_table(compact(recent, recent_cols, limit=20)),
        "",
        "## Annual Focus",
        "",
        md_table(
            compact(
                annual_focus.sort_values(["label", "year"]),
                [
                    "label",
                    "year",
                    "active_issues",
                    "profit_units",
                    "roi_on_deployed",
                    "issue_win_rate",
                    "window_max_drawdown_units",
                ],
                limit=80,
            )
        ),
        "",
        "## Read",
        "",
        "- The pure exact topology has the highest recent convexity, but its full-history capital curve is too jagged for a main allocation.",
        "- The broad `core neg0>=6 d0` arm is the more reliable high-N core.",
        "- The 80/20 core/exact portfolio improves recent upside while keeping drawdown close to the broad core.",
        "- `all` has the smoothest deployment and higher issue win rate, but materially weaker profit density in 2023-2025.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'high_n_capital_summary.csv'}`",
        f"- `{args.output_dir / 'high_n_capital_recent_2023_2025.csv'}`",
        f"- `{args.output_dir / 'high_n_capital_annual.csv'}`",
        f"- `{args.output_dir / 'high_n_capital_equity_curve.csv'}`",
        f"- `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-profit-path",
        type=Path,
        default=Path("results/high_n_selector_20260628/high_n_selector_issue_profit.csv"),
    )
    parser.add_argument("--source-strategy", default=SOURCE)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--issue-budget", type=float, default=256.0)
    parser.add_argument("--output-dir", type=Path, default=Path("results/high_n_capital_performance_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/high_n_capital_performance_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/high_n_capital_performance_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
