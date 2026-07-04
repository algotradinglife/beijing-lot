#!/usr/bin/env python3
"""Validate the frozen N7 384 dynamic sleeve rule and attribute switches."""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_384_drawdown_dynamic import (
    SELECTED_PORTFOLIO,
    drawdown_window,
    fnum,
    full_loss,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    percentile,
    row_order,
    row_year,
    summarize_issue_rows,
)
from scripts.evaluate_n7_384_weak_quality_dynamic import (
    annual_rows,
    load_features,
    load_portfolios,
    ordered_issues,
    write_csv_all,
    write_equity_svg,
)
from scripts.walkforward_beidan_strategy_eval import md_table


BASE_BUDGET = 384.0
BASE_PORTFOLIO = SELECTED_PORTFOLIO
DEFENSIVE_PORTFOLIO = "b384_dd64_smooth80_convex19"
FEATURE = "core_avg_pred_ev"
FEATURE_SIDE = "low"
FEATURE_Q = 0.15
HISTORY_ISSUES = 80
MIN_HISTORY_ISSUES = 40
RULE_NAME = (
    "frozen_core_avg_pred_ev_low_q15_h80__"
    "def_b384_dd64_smooth80_convex19__base_b384_dd32_smooth80_convex19"
)


def dynamic_full_loss(row: dict[str, object]) -> bool:
    stake = fnum(row.get("stake_units"), BASE_BUDGET)
    return stake > 0 and fnum(row.get("profit_units")) <= -0.999 * stake


def replay_frozen_rule(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    features_by_issue: dict[str, dict[str, object]],
    feature: str,
    q: float,
    history: int,
    min_history: int,
) -> list[dict[str, object]]:
    hist: list[float] = []
    out: list[dict[str, object]] = []
    for issue in issues:
        base = rows_by_portfolio[BASE_PORTFOLIO][issue]
        defensive = rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue]
        value = fnum(features_by_issue.get(issue, {}).get(feature), math.nan)
        recent = hist[-history:]
        threshold = math.nan
        switched = False
        if len(recent) >= min_history and math.isfinite(value):
            threshold = percentile(recent, q)
            switched = value <= threshold if math.isfinite(threshold) else False
        chosen = defensive if switched else base
        base_profit = fnum(base.get("profit_units"))
        defensive_profit = fnum(defensive.get("profit_units"))
        dynamic_profit = fnum(chosen.get("profit_units"))
        delta = dynamic_profit - base_profit
        row = dict(chosen)
        row.update(
            {
                "portfolio": RULE_NAME,
                "issue": issue,
                "stake_units": BASE_BUDGET,
                "profit_units": dynamic_profit,
                "roi": dynamic_profit / BASE_BUDGET,
                "chosen_portfolio": DEFENSIVE_PORTFOLIO if switched else BASE_PORTFOLIO,
                "switched": int(switched),
                "state": "defensive" if switched else "base",
                "quality_feature": feature,
                "quality_value": value if math.isfinite(value) else "",
                "quality_threshold": threshold if math.isfinite(threshold) else "",
                "quality_history_n": len(recent),
                "base_profit_units": base_profit,
                "defensive_profit_units": defensive_profit,
                "delta_vs_base_units": delta,
                "base_full_loss": int(full_loss(base)),
                "defensive_full_loss": int(full_loss(defensive)),
                "dynamic_full_loss": int(dynamic_full_loss({"stake_units": BASE_BUDGET, "profit_units": dynamic_profit})),
                "base_win": int(base_profit > 0),
                "defensive_win": int(defensive_profit > 0),
                "dynamic_win": int(dynamic_profit > 0),
                "switch_helped": int(switched and delta > 1e-9),
                "switch_hurt": int(switched and delta < -1e-9),
                "switch_flat": int(switched and abs(delta) <= 1e-9),
                "saved_full_loss": int(switched and full_loss(base) and not full_loss(defensive)),
                "created_full_loss": int(switched and not full_loss(base) and full_loss(defensive)),
                "missed_base_big_win": int(switched and base_profit >= 5000 and defensive_profit < base_profit),
                "defensive_big_rescue": int(switched and delta >= 1000),
            }
        )
        out.append(row)
        if math.isfinite(value):
            hist.append(value)
    return out


def max_dead_streak_rows(rows: list[dict[str, object]]) -> int:
    cur = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if dynamic_full_loss(row):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize_rows(rows: list[dict[str, object]], *, portfolio: str) -> dict[str, object]:
    summary = summarize_issue_rows(rows, portfolio=portfolio, budget=BASE_BUDGET)
    summary["max_dead_streak"] = max_dead_streak_rows(rows)
    return summary


def period_summary(
    *,
    name: str,
    base_rows: list[dict[str, object]],
    defensive_rows: list[dict[str, object]],
    dynamic_rows: list[dict[str, object]],
) -> dict[str, object]:
    switched = [row for row in dynamic_rows if int(fnum(row.get("switched"))) == 1]
    base_profit = sum(fnum(row.get("profit_units")) for row in base_rows)
    defensive_profit = sum(fnum(row.get("profit_units")) for row in defensive_rows)
    dynamic_profit = sum(fnum(row.get("profit_units")) for row in dynamic_rows)
    stake = len(dynamic_rows) * BASE_BUDGET
    switch_base_profit = sum(fnum(row.get("base_profit_units")) for row in switched)
    switch_defensive_profit = sum(fnum(row.get("defensive_profit_units")) for row in switched)
    return {
        "period": name,
        "n_issues": len(dynamic_rows),
        "stake_units": stake,
        "switch_count": len(switched),
        "switch_rate": len(switched) / len(dynamic_rows) if dynamic_rows else math.nan,
        "base_profit_units": base_profit,
        "defensive_always_profit_units": defensive_profit,
        "dynamic_profit_units": dynamic_profit,
        "dynamic_delta_vs_base": dynamic_profit - base_profit,
        "base_roi": base_profit / stake if stake else math.nan,
        "defensive_always_roi": defensive_profit / stake if stake else math.nan,
        "dynamic_roi": dynamic_profit / stake if stake else math.nan,
        "base_maxdd_units": max_drawdown_units(base_rows),
        "dynamic_maxdd_units": max_drawdown_units(dynamic_rows),
        "maxdd_delta_vs_base": max_drawdown_units(dynamic_rows) - max_drawdown_units(base_rows),
        "base_full_loss_rate": sum(1 for row in base_rows if full_loss(row)) / len(base_rows) if base_rows else math.nan,
        "dynamic_full_loss_rate": sum(1 for row in dynamic_rows if dynamic_full_loss(row)) / len(dynamic_rows)
        if dynamic_rows
        else math.nan,
        "base_max_dead_streak": max_dead_streak(base_rows),
        "dynamic_max_dead_streak": max_dead_streak_rows(dynamic_rows),
        "switch_base_profit_units": switch_base_profit,
        "switch_defensive_profit_units": switch_defensive_profit,
        "switch_delta_units": switch_defensive_profit - switch_base_profit,
        "switch_helped_count": sum(int(fnum(row.get("switch_helped"))) for row in switched),
        "switch_hurt_count": sum(int(fnum(row.get("switch_hurt"))) for row in switched),
        "saved_full_loss_count": sum(int(fnum(row.get("saved_full_loss"))) for row in switched),
        "created_full_loss_count": sum(int(fnum(row.get("created_full_loss"))) for row in switched),
        "missed_base_big_win_count": sum(int(fnum(row.get("missed_base_big_win"))) for row in switched),
        "defensive_big_rescue_count": sum(int(fnum(row.get("defensive_big_rescue"))) for row in switched),
    }


def split_rows(rows: list[dict[str, object]], predicate) -> list[dict[str, object]]:
    return [row for row in rows if predicate(row)]


def build_period_summaries(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    dynamic_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    dyn_by_issue = {str(row["issue"]): row for row in dynamic_rows}
    base_all = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues]
    defensive_all = [rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue] for issue in issues]
    periods = [
        ("all", lambda row: True),
        ("train_like_2014_2022", lambda row: 2014 <= row_year(row) <= 2022),
        ("recent_2023_2025", lambda row: 2023 <= row_year(row) <= 2025),
        ("pre_covid_2014_2019", lambda row: 2014 <= row_year(row) <= 2019),
        ("covid_recovery_2020_2022", lambda row: 2020 <= row_year(row) <= 2022),
        ("weak_recent_2024_2025", lambda row: 2024 <= row_year(row) <= 2025),
    ]
    out: list[dict[str, object]] = []
    for name, pred in periods:
        base = [row for row in base_all if pred(row)]
        defensive = [row for row in defensive_all if pred(row)]
        dynamic = [row for row in dynamic_rows if pred(row)]
        out.append(period_summary(name=name, base_rows=base, defensive_rows=defensive, dynamic_rows=dynamic))

    for year in sorted({row_year(row) for row in dynamic_rows}):
        if year <= 0:
            continue
        base = [row for row in base_all if row_year(row) == year]
        defensive = [row for row in defensive_all if row_year(row) == year]
        dynamic = [row for row in dynamic_rows if row_year(row) == year]
        out.append(period_summary(name=f"year_{year}", base_rows=base, defensive_rows=defensive, dynamic_rows=dynamic))
    return out


def rolling_windows(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    dynamic_rows: list[dict[str, object]],
    windows: tuple[int, ...] = (40, 80, 120),
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    dyn_by_issue = {str(row["issue"]): row for row in dynamic_rows}
    base_all = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues]
    defensive_all = [rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue] for issue in issues]
    dynamic_all = [dyn_by_issue[issue] for issue in issues]
    rows: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for window in windows:
        for start in range(0, max(0, len(issues) - window + 1)):
            end = start + window
            base = base_all[start:end]
            defensive = defensive_all[start:end]
            dynamic = dynamic_all[start:end]
            row = period_summary(
                name=f"rolling_{window}_{issues[start]}_{issues[end - 1]}",
                base_rows=base,
                defensive_rows=defensive,
                dynamic_rows=dynamic,
            )
            row.update(
                {
                    "window": window,
                    "start_issue": issues[start],
                    "end_issue": issues[end - 1],
                    "start_year": row_year(dynamic[0]),
                    "end_year": row_year(dynamic[-1]),
                }
            )
            rows.append(row)
        sub = [row for row in rows if int(row.get("window", 0)) == window]
        summary.append(
            {
                "window": window,
                "n_windows": len(sub),
                "positive_delta_rate": sum(1 for row in sub if fnum(row.get("dynamic_delta_vs_base")) > 0)
                / len(sub)
                if sub
                else math.nan,
                "positive_maxdd_delta_rate": sum(1 for row in sub if fnum(row.get("maxdd_delta_vs_base")) > 0)
                / len(sub)
                if sub
                else math.nan,
                "both_positive_rate": sum(
                    1
                    for row in sub
                    if fnum(row.get("dynamic_delta_vs_base")) > 0 and fnum(row.get("maxdd_delta_vs_base")) > 0
                )
                / len(sub)
                if sub
                else math.nan,
                "avg_delta_units": sum(fnum(row.get("dynamic_delta_vs_base")) for row in sub) / len(sub)
                if sub
                else math.nan,
                "median_delta_units": float(pd.Series([fnum(row.get("dynamic_delta_vs_base")) for row in sub]).median())
                if sub
                else math.nan,
                "worst_delta_units": min((fnum(row.get("dynamic_delta_vs_base")) for row in sub), default=math.nan),
                "best_delta_units": max((fnum(row.get("dynamic_delta_vs_base")) for row in sub), default=math.nan),
                "avg_maxdd_delta_units": sum(fnum(row.get("maxdd_delta_vs_base")) for row in sub) / len(sub)
                if sub
                else math.nan,
                "worst_maxdd_delta_units": min((fnum(row.get("maxdd_delta_vs_base")) for row in sub), default=math.nan),
            }
        )
    return rows, summary


def drawdown_attribution(
    *,
    issues: list[str],
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    dynamic_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    dyn_by_issue = {str(row["issue"]): row for row in dynamic_rows}
    base_all = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues]
    dynamic_all = [dyn_by_issue[issue] for issue in issues]
    out: list[dict[str, object]] = []
    for label, source_rows in (("base_maxdd_window", base_all), ("dynamic_maxdd_window", dynamic_all)):
        dd = drawdown_window(source_rows)
        start = int(dd["start_idx"])
        end = int(dd["end_idx"]) + 1
        window_issues = {str(row["issue"]) for row in source_rows[start:end]}
        base = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues if issue in window_issues]
        defensive = [rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue] for issue in issues if issue in window_issues]
        dynamic = [dyn_by_issue[issue] for issue in issues if issue in window_issues]
        row = period_summary(name=label, base_rows=base, defensive_rows=defensive, dynamic_rows=dynamic)
        row.update(
            {
                "peak_issue": dd["peak_issue"],
                "trough_issue": dd["trough_issue"],
                "window_issues": dd["issues"],
                "source_maxdd_units": dd["maxdd_units"],
            }
        )
        out.append(row)
    return out


def switch_attribution_rows(dynamic_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    switched = [row for row in dynamic_rows if int(fnum(row.get("switched"))) == 1]
    by_year: list[dict[str, object]] = []
    for year in sorted({row_year(row) for row in switched}):
        rows = [row for row in switched if row_year(row) == year]
        base_profit = sum(fnum(row.get("base_profit_units")) for row in rows)
        defensive_profit = sum(fnum(row.get("defensive_profit_units")) for row in rows)
        by_year.append(
            {
                "year": year,
                "switch_count": len(rows),
                "base_profit_on_switched": base_profit,
                "defensive_profit_on_switched": defensive_profit,
                "switch_delta_units": defensive_profit - base_profit,
                "helped_count": sum(int(fnum(row.get("switch_helped"))) for row in rows),
                "hurt_count": sum(int(fnum(row.get("switch_hurt"))) for row in rows),
                "saved_full_loss_count": sum(int(fnum(row.get("saved_full_loss"))) for row in rows),
                "created_full_loss_count": sum(int(fnum(row.get("created_full_loss"))) for row in rows),
                "missed_base_big_win_count": sum(int(fnum(row.get("missed_base_big_win"))) for row in rows),
                "defensive_big_rescue_count": sum(int(fnum(row.get("defensive_big_rescue"))) for row in rows),
            }
        )
    top_helped = sorted(switched, key=lambda row: fnum(row.get("delta_vs_base_units")), reverse=True)[:40]
    top_hurt = sorted(switched, key=lambda row: fnum(row.get("delta_vs_base_units")))[:40]
    cols = [
        "issue",
        "calendar_year",
        "issue_close_ts",
        "quality_value",
        "quality_threshold",
        "base_profit_units",
        "defensive_profit_units",
        "delta_vs_base_units",
        "base_full_loss",
        "defensive_full_loss",
        "saved_full_loss",
        "created_full_loss",
        "missed_base_big_win",
        "defensive_big_rescue",
    ]
    return by_year, [{col: row.get(col, "") for col in cols} for row in top_helped], [
        {col: row.get(col, "") for col in cols} for row in top_hurt
    ]


def md_rows(rows: list[dict[str, object]], cols: list[str], limit: int = 40) -> list[dict[str, object]]:
    return [{col: row.get(col, "") for col in cols} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    rows_by_portfolio = load_portfolios(args.issue_profit)
    features_by_issue = load_features(args.features)
    for port in (BASE_PORTFOLIO, DEFENSIVE_PORTFOLIO):
        if port not in rows_by_portfolio:
            raise SystemExit(f"missing portfolio in issue profit: {port}")
    issues = ordered_issues(rows_by_portfolio)
    dynamic_rows = replay_frozen_rule(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        features_by_issue=features_by_issue,
        feature=FEATURE,
        q=FEATURE_Q,
        history=HISTORY_ISSUES,
        min_history=MIN_HISTORY_ISSUES,
    )
    base_rows = [rows_by_portfolio[BASE_PORTFOLIO][issue] for issue in issues]
    defensive_rows = [rows_by_portfolio[DEFENSIVE_PORTFOLIO][issue] for issue in issues]
    dynamic_summary = [
        summarize_rows(base_rows, portfolio=BASE_PORTFOLIO),
        summarize_rows(defensive_rows, portfolio=DEFENSIVE_PORTFOLIO),
        summarize_rows(dynamic_rows, portfolio=RULE_NAME),
    ]
    period_rows = build_period_summaries(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        dynamic_rows=dynamic_rows,
    )
    rolling_rows, rolling_summary = rolling_windows(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        dynamic_rows=dynamic_rows,
    )
    dd_attr = drawdown_attribution(
        issues=issues,
        rows_by_portfolio=rows_by_portfolio,
        dynamic_rows=dynamic_rows,
    )
    switch_by_year, top_helped, top_hurt = switch_attribution_rows(dynamic_rows)
    dynamic_annual = annual_rows(base_rows + defensive_rows + dynamic_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "frozen_dynamic_issue_profit.csv", dynamic_rows)
    write_csv_all(args.output_dir / "frozen_dynamic_summary.csv", dynamic_summary)
    write_csv_all(args.output_dir / "frozen_dynamic_period_summary.csv", period_rows)
    write_csv_all(args.output_dir / "frozen_dynamic_annual.csv", dynamic_annual)
    write_csv_all(args.output_dir / "frozen_dynamic_rolling_windows.csv", rolling_rows)
    write_csv_all(args.output_dir / "frozen_dynamic_rolling_summary.csv", rolling_summary)
    write_csv_all(args.output_dir / "frozen_dynamic_drawdown_attribution.csv", dd_attr)
    write_csv_all(args.output_dir / "frozen_dynamic_switch_by_year.csv", switch_by_year)
    write_csv_all(args.output_dir / "frozen_dynamic_top_helped_switches.csv", top_helped)
    write_csv_all(args.output_dir / "frozen_dynamic_top_hurt_switches.csv", top_hurt)
    write_equity_svg(
        args.figure_path,
        {
            BASE_PORTFOLIO: base_rows,
            DEFENSIVE_PORTFOLIO: defensive_rows,
            RULE_NAME: dynamic_rows,
        },
    )

    dynamic = dynamic_summary[2]
    base = dynamic_summary[0]
    summary_cols = [
        "portfolio",
        "profit_per_256",
        "roi",
        "issue_win_rate",
        "non_full_loss_rate",
        "full_loss_rate",
        "max_drawdown_units",
        "max_drawdown_per_256",
        "max_loss_streak",
        "max_dead_streak",
        "best_issue_profit_units",
        "roi_ex_best_issue",
        "recent_profit_per_256",
    ]
    period_cols = [
        "period",
        "n_issues",
        "switch_count",
        "switch_rate",
        "base_profit_units",
        "dynamic_profit_units",
        "dynamic_delta_vs_base",
        "base_roi",
        "dynamic_roi",
        "base_maxdd_units",
        "dynamic_maxdd_units",
        "maxdd_delta_vs_base",
        "base_max_dead_streak",
        "dynamic_max_dead_streak",
        "switch_delta_units",
        "saved_full_loss_count",
        "created_full_loss_count",
        "missed_base_big_win_count",
        "defensive_big_rescue_count",
    ]
    rolling_cols = [
        "window",
        "n_windows",
        "positive_delta_rate",
        "positive_maxdd_delta_rate",
        "both_positive_rate",
        "avg_delta_units",
        "median_delta_units",
        "worst_delta_units",
        "best_delta_units",
        "avg_maxdd_delta_units",
        "worst_maxdd_delta_units",
    ]
    switch_cols = [
        "year",
        "switch_count",
        "base_profit_on_switched",
        "defensive_profit_on_switched",
        "switch_delta_units",
        "helped_count",
        "hurt_count",
        "saved_full_loss_count",
        "created_full_loss_count",
        "missed_base_big_win_count",
        "defensive_big_rescue_count",
    ]
    top_switch_cols = [
        "issue",
        "calendar_year",
        "issue_close_ts",
        "quality_value",
        "quality_threshold",
        "base_profit_units",
        "defensive_profit_units",
        "delta_vs_base_units",
        "base_full_loss",
        "defensive_full_loss",
        "saved_full_loss",
        "created_full_loss",
        "missed_base_big_win",
        "defensive_big_rescue",
    ]
    report = [
        "# N7 384 Frozen Dynamic Rule Validation",
        "",
        "## Frozen Rule",
        "",
        "```text",
        f"feature = {FEATURE}",
        f"history = {HISTORY_ISSUES} prior issues",
        f"threshold = prior rolling bottom {int(FEATURE_Q * 100)}%",
        f"if feature <= threshold: use {DEFENSIVE_PORTFOLIO}",
        f"else: use {BASE_PORTFOLIO}",
        "```",
        "",
        "The rule is fixed in this report. No parameter search is performed here.",
        "",
        "## Overall",
        "",
        md_table(md_rows(dynamic_summary, summary_cols, limit=10), limit=10),
        "",
        "## Period And Annual Validation",
        "",
        md_table(md_rows(period_rows, period_cols, limit=40), limit=40),
        "",
        "## Rolling Window Validation",
        "",
        md_table(md_rows(rolling_summary, rolling_cols, limit=10), limit=10),
        "",
        "## Drawdown Attribution",
        "",
        md_table(md_rows(dd_attr, period_cols + ["peak_issue", "trough_issue", "window_issues", "source_maxdd_units"], limit=10), limit=10),
        "",
        "## Switch Attribution By Year",
        "",
        md_table(md_rows(switch_by_year, switch_cols, limit=40), limit=40),
        "",
        "## Top Helped Switches",
        "",
        md_table(md_rows(top_helped, top_switch_cols, limit=20), limit=20),
        "",
        "## Top Hurt Switches",
        "",
        md_table(md_rows(top_hurt, top_switch_cols, limit=20), limit=20),
        "",
        "## Interpretation",
        "",
        f"- Frozen dynamic profit/256 changes by `{fnum(dynamic['profit_per_256']) - fnum(base['profit_per_256']):.1f}` versus static 384.",
        f"- Frozen dynamic maxDD changes by `{fnum(dynamic['max_drawdown_units']) - fnum(base['max_drawdown_units']):.1f}` units versus static 384.",
        f"- It switches `{sum(int(fnum(row.get('switched'))) for row in dynamic_rows)}` of `{len(dynamic_rows)}` issues.",
        "- This is a rule-validation report, not a new parameter search.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'frozen_dynamic_issue_profit.csv'}`",
        f"- `{args.output_dir / 'frozen_dynamic_period_summary.csv'}`",
        f"- `{args.output_dir / 'frozen_dynamic_rolling_windows.csv'}`",
        f"- `{args.output_dir / 'frozen_dynamic_drawdown_attribution.csv'}`",
        f"- `{args.output_dir / 'frozen_dynamic_switch_by_year.csv'}`",
        f"- `{args.output_dir / 'frozen_dynamic_top_helped_switches.csv'}`",
        f"- `{args.output_dir / 'frozen_dynamic_top_hurt_switches.csv'}`",
        f"- `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")
    print(f"Wrote {args.output_dir / 'frozen_dynamic_period_summary.csv'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-profit",
        type=Path,
        default=Path("results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv"),
    )
    parser.add_argument(
        "--features",
        type=Path,
        default=Path("results/n7_384_drawdown_dynamic_20260629/issue_prebet_features.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/n7_384_frozen_dynamic_validation_20260629"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_384_frozen_dynamic_validation_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_384_frozen_dynamic_validation_2026-06-29.svg"),
    )
    args = parser.parse_args()
    for path in (args.issue_profit, args.features):
        if not path.exists():
            raise SystemExit(f"missing input: {path}")
    run(args)


if __name__ == "__main__":
    main()
