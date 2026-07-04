#!/usr/bin/env python3
"""Evaluate x2/x4/x8 fixed-budget scaling with more diversity and protection."""
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
    full_loss,
    load_issue_calendar,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    row_order,
    row_year,
    write_equity_svg,
)
from scripts.evaluate_n7_core_ticket_protection import (
    N5_OVERLAP_PATH,
    N5_OVERLAP_STRATEGY,
    N5_QUALITY_STRATEGY,
    load_issue_arm,
    write_csv_all,
)
from scripts.evaluate_n7_protection_allocation_grid import CORE_ARM, load_strategy_maps, max_underwater_profit_window
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


PROTECTION_ISSUE_PATH = Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_issue_profit.csv")
HIGH_N_ISSUE_PATH = Path("results/high_n_selector_20260628/high_n_selector_issue_profit.csv")
HIGH_N_SOURCE = "ev_m0p95_p0p8_full_opt__budget256_fractional"

PROTECT_ARMS = {
    "draw": "core_tp_only_draw_top_ev_k1__budget256_fractional",
    "draw2": "core_tp_only_draw_top_ev_k2__budget256_fractional",
    "alt": "core_tp_only_alt_top_ev_k1__budget256_fractional",
    "full": "core_tp_only_full_top_ev_k1__budget256_fractional",
    "full3": "core_tp_only_full_top_ev_k3__budget256_fractional",
}

HIGH_N_SELECTORS = {
    "hn_draw_free": "draw_free",
    "hn_core80_priority": "portfolio_realloc_80_core_neg0ge6_20_priority",
    "hn_core80_exact": "portfolio_realloc_80_core_neg0ge6_20_exact",
    "hn_priority_tail": "selector_v1_topology_priority",
}


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_high_n_maps(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    selector_to_arm = {value: key for key, value in HIGH_N_SELECTORS.items()}
    for row in read_csv_rows(path):
        if row.get("source_strategy") != HIGH_N_SOURCE:
            continue
        arm = selector_to_arm.get(str(row.get("selector", "")))
        if arm is None:
            continue
        copied = dict(row)
        copied["arm"] = arm
        copied.update(calendar.get(str(row["issue"]), {}))
        out[arm][str(row["issue"])] = copied
    return dict(out)


def ordered_issues(calendar: dict[str, dict[str, object]], arms: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    issues = set()
    for arm in (CORE_ARM, "n5_overlap", "n5_quality_overlap"):
        issues.update(arms.get(arm, {}).keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def combine_budget_portfolio(
    *,
    portfolio: str,
    issue_budget: float,
    issues: list[str],
    arms: dict[str, dict[str, dict[str, object]]],
    allocation: dict[str, float],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    out = []
    for issue in issues:
        profit = 0.0
        tickets = 0.0
        hits = 0.0
        parts = []
        missing_units = 0.0
        for arm, units in allocation.items():
            if units <= 0:
                continue
            row = arms.get(arm, {}).get(issue)
            if row is None:
                missing_units += units
                continue
            row_stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = units / row_stake if row_stake else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{arm}:{units:g}")
        if missing_units:
            fallback = arms["n5_quality_overlap"].get(issue) or arms["n5_overlap"].get(issue)
            if fallback is None:
                raise SystemExit(f"missing fallback issue {issue}")
            row_stake = fnum(fallback.get("stake_units"), ISSUE_BUDGET)
            scale = missing_units / row_stake if row_stake else 0.0
            profit += fnum(fallback.get("profit_units")) * scale
            tickets += fnum(fallback.get("tickets")) * scale
            hits += fnum(fallback.get("hits")) * scale
            parts.append(f"fallback_n5_quality:{missing_units:g}")
        row = {
            "portfolio": portfolio,
            "issue": issue,
            "stake_units": issue_budget,
            "profit_units": profit,
            "roi": profit / issue_budget if issue_budget else math.nan,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
            "state": "static",
        }
        row.update(calendar.get(issue, {}))
        out.append(row)
    return out


def current_scaled_allocation(multiplier: int) -> dict[str, float]:
    return {
        CORE_ARM: 144.0 * multiplier,
        PROTECT_ARMS["draw"]: 48.0 * multiplier,
        "n5_overlap": 64.0 * multiplier,
    }


def scaling_specs() -> list[tuple[str, float, dict[str, float], str]]:
    specs: list[tuple[str, float, dict[str, float], str]] = []
    for multiplier in (1, 2, 4, 8):
        budget = ISSUE_BUDGET * multiplier
        specs.append(
            (
                f"x{multiplier}_linear_current",
                budget,
                current_scaled_allocation(multiplier),
                "same structure, scaled stake",
            )
        )

    specs.extend(
        [
            (
                "x2_balanced_diverse",
                512.0,
                {
                    CORE_ARM: 224.0,
                    PROTECT_ARMS["draw"]: 96.0,
                    PROTECT_ARMS["alt"]: 32.0,
                    PROTECT_ARMS["full"]: 32.0,
                    "n5_overlap": 80.0,
                    "n5_quality_overlap": 48.0,
                },
                "more top-EV draw, small alt/full protection, more N5",
            ),
            (
                "x2_n5_smoother",
                512.0,
                {
                    CORE_ARM: 192.0,
                    PROTECT_ARMS["draw"]: 64.0,
                    PROTECT_ARMS["alt"]: 32.0,
                    PROTECT_ARMS["full"]: 32.0,
                    "n5_overlap": 128.0,
                    "n5_quality_overlap": 64.0,
                },
                "lower convex core, larger N5 stabilizer",
            ),
            (
                "x2_convex_diverse",
                512.0,
                {
                    CORE_ARM: 208.0,
                    PROTECT_ARMS["draw"]: 96.0,
                    PROTECT_ARMS["alt"]: 32.0,
                    "n5_overlap": 96.0,
                    "n5_quality_overlap": 48.0,
                    "hn_core80_priority": 16.0,
                    "hn_priority_tail": 16.0,
                },
                "small extra high-N topology convexity",
            ),
            (
                "x4_balanced_diverse",
                1024.0,
                {
                    CORE_ARM: 384.0,
                    PROTECT_ARMS["draw"]: 176.0,
                    PROTECT_ARMS["alt"]: 80.0,
                    PROTECT_ARMS["full"]: 80.0,
                    "n5_overlap": 176.0,
                    "n5_quality_overlap": 96.0,
                    "hn_core80_priority": 32.0,
                },
                "scaled diversity with draw/alt/full/N5/high-N topology",
            ),
            (
                "x4_n5_smoother",
                1024.0,
                {
                    CORE_ARM: 320.0,
                    PROTECT_ARMS["draw"]: 128.0,
                    PROTECT_ARMS["alt"]: 64.0,
                    PROTECT_ARMS["full"]: 64.0,
                    "n5_overlap": 288.0,
                    "n5_quality_overlap": 128.0,
                    "hn_core80_priority": 32.0,
                },
                "larger N5 stabilizer at x4",
            ),
            (
                "x4_convex_diverse",
                1024.0,
                {
                    CORE_ARM: 352.0,
                    PROTECT_ARMS["draw"]: 176.0,
                    PROTECT_ARMS["alt"]: 80.0,
                    PROTECT_ARMS["full"]: 64.0,
                    "n5_overlap": 176.0,
                    "n5_quality_overlap": 96.0,
                    "hn_core80_priority": 48.0,
                    "hn_priority_tail": 32.0,
                },
                "keeps convex tail while diversifying protection",
            ),
            (
                "x8_balanced_diverse",
                2048.0,
                {
                    CORE_ARM: 704.0,
                    PROTECT_ARMS["draw"]: 320.0,
                    PROTECT_ARMS["alt"]: 192.0,
                    PROTECT_ARMS["full"]: 192.0,
                    "n5_overlap": 352.0,
                    "n5_quality_overlap": 192.0,
                    "hn_core80_priority": 64.0,
                    "hn_draw_free": 32.0,
                },
                "x8 balanced diversity",
            ),
            (
                "x8_n5_smoother",
                2048.0,
                {
                    CORE_ARM: 576.0,
                    PROTECT_ARMS["draw"]: 224.0,
                    PROTECT_ARMS["alt"]: 128.0,
                    PROTECT_ARMS["full"]: 128.0,
                    "n5_overlap": 576.0,
                    "n5_quality_overlap": 288.0,
                    "hn_core80_priority": 128.0,
                },
                "largest N5 stabilizer at x8",
            ),
            (
                "x8_convex_diverse",
                2048.0,
                {
                    CORE_ARM: 640.0,
                    PROTECT_ARMS["draw"]: 320.0,
                    PROTECT_ARMS["alt"]: 160.0,
                    PROTECT_ARMS["full"]: 128.0,
                    "n5_overlap": 384.0,
                    "n5_quality_overlap": 224.0,
                    "hn_core80_priority": 128.0,
                    "hn_priority_tail": 64.0,
                },
                "x8 with moderate topology tail",
            ),
        ]
    )
    return specs


def quantile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def summarize_budget(rows: list[dict[str, object]], budget: float, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    profits = [fnum(row.get("profit_units")) for row in ordered]
    recent = [row for row in ordered if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    years = sorted({row_year(row) for row in ordered if row_year(row) > 0})
    maxdd = max_drawdown_units(ordered)
    full_loss_rows = [row for row in ordered if full_loss(row)]
    out = {
        "portfolio": str(ordered[0]["portfolio"]) if ordered else "",
        "issue_budget": budget,
        "budget_multiplier": budget / ISSUE_BUDGET,
        "n_issues": len(ordered),
        "years": f"{min(years)}-{max(years)}" if years else "",
        "n_years": len(years),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (budget / ISSUE_BUDGET) if budget else math.nan,
        "roi": profit / stake if stake else math.nan,
        "avg_profit_per_year": profit / len(years) if years else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered)
        if ordered
        else math.nan,
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered) if ordered else math.nan,
        "full_loss_rate": len(full_loss_rows) / len(ordered) if ordered else math.nan,
        "small_loss_rate": sum(
            1 for row in ordered if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
        )
        / len(ordered)
        if ordered
        else math.nan,
        "median_issue_profit": quantile(profits, 0.5),
        "p10_issue_profit": quantile(profits, 0.10),
        "p25_issue_profit": quantile(profits, 0.25),
        "max_drawdown_units": maxdd,
        "max_drawdown_per_256": maxdd / (budget / ISSUE_BUDGET) if budget else math.nan,
        "max_drawdown_budget_equiv": abs(maxdd) / budget if budget else math.nan,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "best_issue_profit_per_256": best / (budget / ISSUE_BUDGET) if budget else math.nan,
        "roi_ex_best_issue": (profit - best) / (stake - budget) if stake > budget else math.nan,
        "recent_issues": len(recent),
        "recent_profit_units": recent_profit,
        "recent_profit_per_256": recent_profit / (budget / ISSUE_BUDGET) if budget else math.nan,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in ordered) / len(ordered) if ordered else math.nan,
    }
    out.update(max_underwater_profit_window(ordered))
    out["profit_to_dd"] = profit / abs(maxdd) if maxdd else math.nan
    return out


def normalized_rows(rows: list[dict[str, object]], divisor: float) -> list[dict[str, object]]:
    out = []
    for row in rows:
        copied = dict(row)
        copied["profit_units"] = fnum(row.get("profit_units")) / divisor
        copied["stake_units"] = fnum(row.get("stake_units")) / divisor
        copied["portfolio"] = f"{row.get('portfolio')}_norm256"
        out.append(copied)
    return out


def allocation_text(allocation: dict[str, float]) -> str:
    return "; ".join(f"{arm}={units:g}" for arm, units in allocation.items() if units > 0)


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    arms = load_strategy_maps(args.protection_issue_profit, calendar)
    arms.update(load_high_n_maps(args.high_n_issue_profit, calendar))
    arms["n5_overlap"] = load_issue_arm(N5_OVERLAP_PATH, N5_OVERLAP_STRATEGY, "n5_overlap", calendar)
    arms["n5_quality_overlap"] = load_issue_arm(N5_OVERLAP_PATH, N5_QUALITY_STRATEGY, "n5_quality_overlap", calendar)
    issues = ordered_issues(calendar, arms)

    all_rows: list[dict[str, object]] = []
    norm_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    norm_series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}

    for name, budget, allocation, rationale in scaling_specs():
        if abs(sum(allocation.values()) - budget) > 1e-6:
            raise SystemExit(f"allocation for {name} sums to {sum(allocation.values())}, expected {budget}")
        rows = combine_budget_portfolio(
            portfolio=name,
            issue_budget=budget,
            issues=issues,
            arms=arms,
            allocation=allocation,
            calendar=calendar,
        )
        for row in rows:
            row.update(
                {
                    "issue_budget": budget,
                    "budget_multiplier": budget / ISSUE_BUDGET,
                    "allocation": allocation_text(allocation),
                    "rationale": rationale,
                }
            )
        all_rows.extend(rows)
        series[name] = rows
        norm = normalized_rows(rows, budget / ISSUE_BUDGET)
        norm_rows.extend(norm)
        norm_series[name] = norm
        meta[name] = {
            "issue_budget": budget,
            "budget_multiplier": budget / ISSUE_BUDGET,
            "allocation": allocation_text(allocation),
            "rationale": rationale,
        }

    summaries = []
    for name, rows in series.items():
        budget = fnum(meta[name]["issue_budget"])
        summary = summarize_budget(rows, budget, args.recent_min_year, args.recent_max_year)
        summary.update(meta[name])
        summaries.append(summary)
    summary_df = pd.DataFrame(summaries)
    summary_df["smooth_score"] = (
        summary_df["profit_per_256"]
        + 30000.0 * summary_df["issue_win_rate"]
        + 45000.0 * summary_df["non_full_loss_rate"]
        + 1.2 * summary_df["max_drawdown_per_256"]
        + 60000.0 * summary_df["roi_ex_best_issue"]
    )
    summary_df = summary_df.sort_values(
        ["budget_multiplier", "smooth_score", "profit_per_256"], ascending=[True, False, False]
    )
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "capital_scaling_issue_profit.csv", all_rows)
    write_csv_all(args.output_dir / "capital_scaling_issue_profit_norm256.csv", norm_rows)
    summary_df.to_csv(args.output_dir / "capital_scaling_summary.csv", index=False)
    write_csv(args.output_dir / "capital_scaling_annual.csv", annual)

    plot_names = [
        "x1_linear_current",
        "x2_linear_current",
        "x2_balanced_diverse",
        "x2_n5_smoother",
        "x4_balanced_diverse",
        "x4_n5_smoother",
        "x8_balanced_diverse",
        "x8_n5_smoother",
    ]
    write_equity_svg(args.figure_path, {name: series[name] for name in plot_names if name in series}, calendar)
    write_equity_svg(
        args.norm_figure_path,
        {name: norm_series[name] for name in plot_names if name in norm_series},
        calendar,
    )

    selected = summary_df[
        summary_df["portfolio"].isin(plot_names)
        | summary_df["portfolio"].str.contains("convex_diverse")
    ].copy()
    best_by_budget = (
        summary_df.sort_values(["budget_multiplier", "smooth_score"], ascending=[True, False])
        .groupby("budget_multiplier", as_index=False)
        .head(1)
    )
    top_smooth = summary_df.sort_values(["smooth_score"], ascending=False).head(12)
    top_profit_norm = summary_df.sort_values(["profit_per_256", "max_drawdown_per_256"], ascending=[False, False]).head(12)
    top_dd_norm = summary_df.sort_values(["max_drawdown_budget_equiv", "profit_per_256"], ascending=[True, False]).head(12)

    report = [
        "# N7 Capital Scaling with Diversity and Protection",
        "",
        "## Scope",
        "",
        "- Fixed issue budgets tested: `256`, `512`, `1024`, `2048` units.",
        "- `linear_current` simply scales the current `144 core + 48 draw-protected + 64 N5 overlap` structure.",
        "- Diverse variants spend extra budget on top-EV draw/alt/full protected sleeves, N5 overlap/quality, and small high-N topology sleeves.",
        "- This evaluates whether larger stake plus more ticket diversity makes the equity curve smoother, not whether bankroll compounding is safe.",
        "",
        "## Decision",
        "",
        md_table(
            best_by_budget[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_units",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "max_dead_streak",
                    "recent_profit_units",
                    "recent_profit_per_256",
                    "roi_ex_best_issue",
                    "smooth_score",
                ]
            ].to_dict("records"),
            limit=10,
        ),
        "",
        "## Selected Comparison",
        "",
        md_table(
            selected[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_units",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
                    "max_drawdown_units",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "roi_ex_best_issue",
                    "avg_tickets_per_issue",
                ]
            ].sort_values(["issue_budget", "portfolio"]).to_dict("records"),
            limit=30,
        ),
        "",
        "## Top Smooth Score",
        "",
        md_table(
            top_smooth[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "roi_ex_best_issue",
                    "smooth_score",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Top Normalized Profit",
        "",
        md_table(
            top_profit_norm[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_units",
                    "profit_per_256",
                    "roi",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "issue_win_rate",
                    "non_full_loss_rate",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Lowest Normalized Drawdown",
        "",
        md_table(
            top_dd_norm[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "max_drawdown_units",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "recent_profit_per_256",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Allocation Details",
        "",
        md_table(
            summary_df[
                [
                    "portfolio",
                    "issue_budget",
                    "allocation",
                    "rationale",
                ]
            ].sort_values(["issue_budget", "portfolio"]).to_dict("records"),
            limit=40,
        ),
        "",
        "## Interpretation",
        "",
        "- If a diversified x2/x4/x8 arm has similar `profit_per_256` but better `max_drawdown_per_256` than `linear_current`, added capital is buying smoother exposure.",
        "- If normalized metrics do not improve, extra capital is mostly just scaling the same risk.",
        "- `N5_smoother` is expected to improve issue win/non-full-loss rates but may dilute convex payoff; `convex_diverse` tests the opposite tradeoff.",
        f"- Absolute figure: `{args.figure_path}`",
        f"- Normalized figure: `{args.norm_figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")
    print(f"Wrote {args.norm_figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--protection-issue-profit", type=Path, default=PROTECTION_ISSUE_PATH)
    parser.add_argument("--high-n-issue-profit", type=Path, default=HIGH_N_ISSUE_PATH)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_capital_scaling_diversity_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_capital_scaling_diversity_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_capital_scaling_diversity_absolute_2026-06-28.svg"),
    )
    parser.add_argument(
        "--norm-figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_capital_scaling_diversity_norm256_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
