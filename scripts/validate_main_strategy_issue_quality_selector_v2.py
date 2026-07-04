#!/usr/bin/env python3
"""Frozen validation for the issue-quality selector v2 candidate."""
from __future__ import annotations

import argparse
import csv
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.render_main_strategy_leg_ev_depth_html as html_base
from scripts.evaluate_main_strategy_issue_quality_selector_v2 import (
    BASELINE,
    BUDGET,
    DEFENSIVE,
    FEATURE_PATH,
    ISSUE_PROFIT_PATH,
    FeatureContext,
    clone_choice,
    fnum,
    full_loss,
    load_features,
    load_portfolios,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    ordered_issues,
    row_order,
    row_year,
    summarize,
)


RULE_NAME = "state_L6_DD9000_OR_weakcount_ge4_q0p1_h120"
STATE_REF = "state_L6_DD9000"
QUALITY_Q = 0.10
QUALITY_HISTORY = 120
MIN_HISTORY = 40
WEAK_COUNT_CUTOFF = 4
LOSS_TRIGGER = 6
DD_TRIGGER = 9000.0

OUT_DIR = Path("results/main_strategy_issue_quality_selector_v2_validation_20260629")
OUT_HTML = Path("docs/research/main_strategy_issue_quality_selector_v2_validation_2026-06-29.html")
OUT_MD = Path("docs/research/main_strategy_issue_quality_selector_v2_validation_2026-06-29.md")


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def replay_static(
    *,
    name: str,
    chosen_state: str,
    issues: list[str],
    base_by_issue: dict[str, dict[str, object]],
    defensive_by_issue: dict[str, dict[str, object]],
    features_by_issue: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    rows = []
    for issue in issues:
        base = base_by_issue[issue]
        defensive = defensive_by_issue[issue]
        chosen = defensive if chosen_state == "defensive" else base
        rows.append(
            clone_choice(
                issue=issue,
                portfolio_name=name,
                chosen=chosen,
                base=base,
                defensive=defensive,
                state=chosen_state,
                quality_signal=chosen_state == "defensive",
                state_signal=False,
                reason="static",
                ctx=None,
                features=features_by_issue.get(issue, {}),
            )
        )
    return rows


def replay_frozen(
    *,
    name: str,
    issues: list[str],
    base_by_issue: dict[str, dict[str, object]],
    defensive_by_issue: dict[str, dict[str, object]],
    features_by_issue: dict[str, dict[str, object]],
    ctx: FeatureContext,
    use_quality: bool,
    use_state: bool,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    equity = 0.0
    peak = 0.0
    loss_streak = 0
    for issue in issues:
        base = base_by_issue[issue]
        defensive = defensive_by_issue[issue]
        weak_count = ctx.weak_count(issue)
        quality_signal = use_quality and weak_count >= WEAK_COUNT_CUTOFF
        pre_equity = equity
        pre_peak = peak
        pre_drawdown = peak - equity
        pre_loss_streak = loss_streak
        loss_signal = use_state and pre_loss_streak >= LOSS_TRIGGER
        dd_signal = use_state and pre_drawdown >= DD_TRIGGER
        state_signal = loss_signal or dd_signal
        use_defensive = quality_signal or state_signal
        reason_parts = []
        if quality_signal:
            reason_parts.append(f"weak_count>={WEAK_COUNT_CUTOFF}")
        if loss_signal:
            reason_parts.append(f"loss_streak>={LOSS_TRIGGER}")
        if dd_signal:
            reason_parts.append(f"drawdown>={DD_TRIGGER:g}")
        chosen = defensive if use_defensive else base
        row = clone_choice(
            issue=issue,
            portfolio_name=name,
            chosen=chosen,
            base=base,
            defensive=defensive,
            state="defensive" if use_defensive else "base",
            quality_signal=quality_signal,
            state_signal=state_signal,
            reason=";".join(reason_parts),
            ctx=ctx,
            features=features_by_issue.get(issue, {}),
        )
        row.update(
            {
                "pre_equity_units": pre_equity,
                "pre_peak_units": pre_peak,
                "pre_drawdown_units": pre_drawdown,
                "pre_loss_streak": pre_loss_streak,
                "loss_trigger_signal": int(loss_signal),
                "drawdown_trigger_signal": int(dd_signal),
                "quality_only_signal": int(quality_signal and not state_signal),
                "state_only_signal": int(state_signal and not quality_signal),
                "quality_and_state_signal": int(quality_signal and state_signal),
                "switch_helped": int(use_defensive and fnum(row.get("delta_vs_base_units")) > 1e-9),
                "switch_hurt": int(use_defensive and fnum(row.get("delta_vs_base_units")) < -1e-9),
                "switch_flat": int(use_defensive and abs(fnum(row.get("delta_vs_base_units"))) <= 1e-9),
                "saved_full_loss": int(use_defensive and full_loss(base) and not full_loss(defensive)),
                "created_full_loss": int(use_defensive and not full_loss(base) and full_loss(defensive)),
                "defensive_big_rescue": int(use_defensive and fnum(row.get("delta_vs_base_units")) >= 1000.0),
            }
        )
        rows.append(row)

        profit = fnum(row.get("profit_units"))
        equity += profit
        peak = max(peak, equity)
        loss_streak = loss_streak + 1 if profit < 0 else 0
    return rows


def add_summary_deltas(rows: list[dict[str, object]]) -> None:
    base = next(row for row in rows if row["portfolio"] == BASELINE)
    for row in rows:
        row["delta_profit_per_256_vs_base"] = fnum(row.get("profit_per_256")) - fnum(base.get("profit_per_256"))
        row["delta_roi_vs_base"] = fnum(row.get("roi")) - fnum(base.get("roi"))
        row["delta_maxdd_units_vs_base"] = fnum(row.get("max_drawdown_units")) - fnum(base.get("max_drawdown_units"))
        row["delta_loss_streak_vs_base"] = fnum(row.get("max_loss_streak")) - fnum(base.get("max_loss_streak"))
        row["delta_issue_win_pp_vs_base"] = (fnum(row.get("issue_win_rate")) - fnum(base.get("issue_win_rate"))) * 100.0
        row["delta_full_loss_pp_vs_base"] = (fnum(row.get("full_loss_rate")) - fnum(base.get("full_loss_rate"))) * 100.0
        row["delta_recent_profit_per_256_vs_base"] = fnum(row.get("recent_profit_per_256")) - fnum(
            base.get("recent_profit_per_256")
        )


def annual_rows(series: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for portfolio, rows in series.items():
        grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            grouped[row_year(row)].append(row)
        for year, vals in sorted(grouped.items()):
            stake = len(vals) * BUDGET
            profit = sum(fnum(row.get("profit_units")) for row in vals)
            out.append(
                {
                    "portfolio": portfolio,
                    "year": year,
                    "n_issues": len(vals),
                    "stake_units": stake,
                    "profit_units": profit,
                    "profit_per_256": profit / (BUDGET / 256.0),
                    "roi": profit / stake if stake else math.nan,
                    "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals),
                    "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals),
                    "full_loss_rate": sum(1 for row in vals if full_loss(row)) / len(vals),
                    "max_drawdown_units": max_drawdown_units(vals),
                    "max_loss_streak": max_loss_streak(vals),
                }
            )
    base_by_year = {
        int(row["year"]): row for row in out if row["portfolio"] == BASELINE
    }
    for row in out:
        base = base_by_year.get(int(row["year"]))
        if base:
            row["delta_profit_per_256_vs_base"] = fnum(row.get("profit_per_256")) - fnum(base.get("profit_per_256"))
            row["delta_maxdd_units_vs_base"] = fnum(row.get("max_drawdown_units")) - fnum(base.get("max_drawdown_units"))
    return out


def period_predicates():
    return [
        ("all", lambda row: True),
        ("train_like_2014_2022", lambda row: 2014 <= row_year(row) <= 2022),
        ("recent_2023_2025", lambda row: 2023 <= row_year(row) <= 2025),
        ("weak_recent_2024_2025", lambda row: 2024 <= row_year(row) <= 2025),
        ("pre_covid_2014_2019", lambda row: 2014 <= row_year(row) <= 2019),
        ("covid_recovery_2020_2022", lambda row: 2020 <= row_year(row) <= 2022),
    ]


def subset_summary(rows: list[dict[str, object]], *, portfolio: str, period: str) -> dict[str, object]:
    stake = len(rows) * BUDGET
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    return {
        "portfolio": portfolio,
        "period": period,
        "n_issues": len(rows),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (BUDGET / 256.0),
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows) if rows else math.nan,
        "non_full_loss_rate": sum(1 for row in rows if not full_loss(row)) / len(rows) if rows else math.nan,
        "full_loss_rate": sum(1 for row in rows if full_loss(row)) / len(rows) if rows else math.nan,
        "max_drawdown_units": max_drawdown_units(rows),
        "max_loss_streak": max_loss_streak(rows),
        "max_dead_streak": max_dead_streak(rows),
    }


def period_rows(series: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for period, predicate in period_predicates():
        base_rows = [row for row in series[BASELINE] if predicate(row)]
        base = subset_summary(base_rows, portfolio=BASELINE, period=period)
        for portfolio, rows in series.items():
            sub = [row for row in rows if predicate(row)]
            item = subset_summary(sub, portfolio=portfolio, period=period)
            item["delta_profit_per_256_vs_base"] = fnum(item.get("profit_per_256")) - fnum(base.get("profit_per_256"))
            item["delta_maxdd_units_vs_base"] = fnum(item.get("max_drawdown_units")) - fnum(base.get("max_drawdown_units"))
            item["delta_loss_streak_vs_base"] = fnum(item.get("max_loss_streak")) - fnum(base.get("max_loss_streak"))
            out.append(item)
    return out


def ex_best_rows(series: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for period, predicate in period_predicates()[:4]:
        for portfolio, rows in series.items():
            sub = sorted([row for row in rows if predicate(row)], key=row_order)
            if not sub:
                continue
            best = max(sub, key=lambda row: fnum(row.get("profit_units")))
            sub_ex = [row for row in sub if str(row["issue"]) != str(best["issue"])]
            stake = len(sub) * BUDGET
            stake_ex = len(sub_ex) * BUDGET
            profit = sum(fnum(row.get("profit_units")) for row in sub)
            profit_ex = sum(fnum(row.get("profit_units")) for row in sub_ex)
            out.append(
                {
                    "portfolio": portfolio,
                    "period": period,
                    "n_issues": len(sub),
                    "profit_units": profit,
                    "roi": profit / stake if stake else math.nan,
                    "best_issue": best["issue"],
                    "best_issue_profit_units": fnum(best.get("profit_units")),
                    "profit_ex_best_issue": profit_ex,
                    "roi_ex_best_issue": profit_ex / stake_ex if stake_ex else math.nan,
                    "max_drawdown_ex_best_units": max_drawdown_units(sub_ex),
                    "max_loss_streak_ex_best": max_loss_streak(sub_ex),
                }
            )
    return out


def rolling_rows(series: dict[str, list[dict[str, object]]], windows: tuple[int, ...] = (40, 80, 120)):
    base_rows = sorted(series[BASELINE], key=row_order)
    issue_order = [str(row["issue"]) for row in base_rows]
    by_portfolio = {
        portfolio: {str(row["issue"]): row for row in rows}
        for portfolio, rows in series.items()
    }
    rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for window in windows:
        for start in range(0, max(0, len(issue_order) - window + 1)):
            issues = issue_order[start : start + window]
            base = [by_portfolio[BASELINE][issue] for issue in issues]
            for portfolio in (STATE_REF, RULE_NAME, DEFENSIVE):
                dyn = [by_portfolio[portfolio][issue] for issue in issues]
                base_profit = sum(fnum(row.get("profit_units")) for row in base)
                dyn_profit = sum(fnum(row.get("profit_units")) for row in dyn)
                item = {
                    "portfolio": portfolio,
                    "window": window,
                    "start_issue": issues[0],
                    "end_issue": issues[-1],
                    "start_year": row_year(dyn[0]),
                    "end_year": row_year(dyn[-1]),
                    "base_profit_units": base_profit,
                    "dynamic_profit_units": dyn_profit,
                    "delta_profit_units": dyn_profit - base_profit,
                    "base_maxdd_units": max_drawdown_units(base),
                    "dynamic_maxdd_units": max_drawdown_units(dyn),
                    "delta_maxdd_units": max_drawdown_units(dyn) - max_drawdown_units(base),
                    "base_loss_streak": max_loss_streak(base),
                    "dynamic_loss_streak": max_loss_streak(dyn),
                    "delta_loss_streak": max_loss_streak(dyn) - max_loss_streak(base),
                }
                rows.append(item)
        for portfolio in (STATE_REF, RULE_NAME, DEFENSIVE):
            sub = [row for row in rows if row["portfolio"] == portfolio and int(row["window"]) == window]
            deltas = [fnum(row.get("delta_profit_units")) for row in sub]
            dd_deltas = [fnum(row.get("delta_maxdd_units")) for row in sub]
            loss_deltas = [fnum(row.get("delta_loss_streak")) for row in sub]
            summaries.append(
                {
                    "portfolio": portfolio,
                    "window": window,
                    "n_windows": len(sub),
                    "positive_profit_delta_rate": sum(1 for value in deltas if value > 0) / len(deltas) if deltas else math.nan,
                    "positive_maxdd_delta_rate": sum(1 for value in dd_deltas if value > 0) / len(dd_deltas) if dd_deltas else math.nan,
                    "both_positive_rate": sum(
                        1
                        for row in sub
                        if fnum(row.get("delta_profit_units")) > 0 and fnum(row.get("delta_maxdd_units")) > 0
                    )
                    / len(sub)
                    if sub
                    else math.nan,
                    "avg_profit_delta": statistics.mean(deltas) if deltas else math.nan,
                    "median_profit_delta": statistics.median(deltas) if deltas else math.nan,
                    "worst_profit_delta": min(deltas) if deltas else math.nan,
                    "best_profit_delta": max(deltas) if deltas else math.nan,
                    "avg_maxdd_delta": statistics.mean(dd_deltas) if dd_deltas else math.nan,
                    "worst_maxdd_delta": min(dd_deltas) if dd_deltas else math.nan,
                    "avg_loss_streak_delta": statistics.mean(loss_deltas) if loss_deltas else math.nan,
                }
            )
    return rows, summaries


def switch_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    switched = [row for row in rows if row.get("state") == "defensive"]
    groups = [
        ("all_switches", switched),
        ("quality_only", [row for row in switched if int(fnum(row.get("quality_only_signal"))) == 1]),
        ("state_involved", [row for row in switched if int(fnum(row.get("state_signal"))) == 1]),
        ("quality_and_state", [row for row in switched if int(fnum(row.get("quality_and_state_signal"))) == 1]),
    ]
    out = []
    for name, vals in groups:
        out.append(
            {
                "group": name,
                "n": len(vals),
                "delta_vs_base_units": sum(fnum(row.get("delta_vs_base_units")) for row in vals),
                "helped_count": sum(int(fnum(row.get("switch_helped"))) for row in vals),
                "hurt_count": sum(int(fnum(row.get("switch_hurt"))) for row in vals),
                "flat_count": sum(int(fnum(row.get("switch_flat"))) for row in vals),
                "saved_full_loss_count": sum(int(fnum(row.get("saved_full_loss"))) for row in vals),
                "created_full_loss_count": sum(int(fnum(row.get("created_full_loss"))) for row in vals),
                "big_rescue_count": sum(int(fnum(row.get("defensive_big_rescue"))) for row in vals),
            }
        )
    return out


def normalized_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        copied = dict(row)
        copied["profit_units"] = fnum(row.get("profit_units")) / (BUDGET / 256.0)
        copied["stake_units"] = 256.0
        out.append(copied)
    return out


def make_html(
    *,
    output: Path,
    summary: list[dict[str, object]],
    annual: list[dict[str, object]],
    periods: list[dict[str, object]],
    ex_best: list[dict[str, object]],
    rolling_summary: list[dict[str, object]],
    switch_rows: list[dict[str, object]],
    issue_rows: list[dict[str, object]],
) -> None:
    focused = [BASELINE, STATE_REF, RULE_NAME, DEFENSIVE]
    html_base.FOCUSED = focused
    html_base.COLORS = {
        BASELINE: "#2f855a",
        STATE_REF: "#4c78a8",
        RULE_NAME: "#f58518",
        DEFENSIVE: "#e45756",
    }
    issue_focus = [row for row in issue_rows if row["portfolio"] in focused]
    eq, dd = html_base.build_series([{k: str(v) for k, v in row.items()} for row in issue_focus])
    eq_norm, _ = html_base.build_series([{k: str(v) for k, v in row.items()} for row in normalized_rows(issue_focus)])
    equity_svg = html_base.line_svg(eq, title="Frozen selector v2 validation: total profit", y_label="cumulative total profit")
    norm_svg = html_base.line_svg(eq_norm, title="Frozen selector v2 validation: profit/256", y_label="cumulative profit/256")
    dd_svg = html_base.line_svg(dd, title="Frozen selector v2 validation: drawdown", y_label="equity - running peak")
    annual_svg = html_base.annual_profit_svg([{k: str(v) for k, v in row.items()} for row in annual if row["portfolio"] in focused])

    summary_cols = [
        ("portfolio", "portfolio", "text"),
        ("profit_per_256", "profit/256", "num"),
        ("roi", "ROI", "roi"),
        ("delta_profit_per_256_vs_base", "profit/256 Δ", "num"),
        ("max_drawdown_units", "maxDD", "num"),
        ("delta_maxdd_units_vs_base", "maxDD Δ", "num"),
        ("max_loss_streak", "loss streak", "num"),
        ("delta_loss_streak_vs_base", "loss streak Δ", "num"),
        ("issue_win_rate", "issue win", "pct"),
        ("delta_issue_win_pp_vs_base", "issue win Δ pp", "num2"),
        ("full_loss_rate", "full loss", "pct"),
        ("recent_profit_per_256", "2023-25 profit/256", "num"),
        ("delta_recent_profit_per_256_vs_base", "2023-25 Δ", "num"),
    ]
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>Frozen Selector v2 Validation</title>
<style>
:root {{ --bg:#f7f7f4; --fg:#171717; --muted:#666; --border:#d8d2c7; --panel:#fff; --head:#eef2ef; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif; line-height:1.62; }}
main {{ max-width:1240px; margin:0 auto; padding:28px 28px 72px; }}
h1 {{ margin:0 0 8px; font-size:30px; }}
h2 {{ margin:34px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--border); font-size:21px; }}
.meta {{ color:var(--muted); font-size:14px; }}
.callout {{ background:#fff7e6; border-left:4px solid #9a6500; padding:12px 16px; border-radius:0 6px 6px 0; margin:18px 0; }}
.chart-wrap {{ background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:14px; overflow-x:auto; margin:14px 0; }}
.chart {{ width:100%; min-width:980px; height:auto; display:block; background:#fff; }}
.chart-title {{ font-size:18px; font-weight:700; fill:#222; }}
.axis-label,.tick,.legend {{ fill:#555; font-size:12px; }}
.axis {{ stroke:#8d887f; stroke-width:1; }}
.grid {{ stroke:#e5e1d8; stroke-width:1; }}
.zero {{ stroke:#888; stroke-width:1.3; stroke-dasharray:4 4; }}
table {{ width:100%; border-collapse:collapse; background:var(--panel); font-size:13px; margin:10px 0 18px; }}
th,td {{ border:1px solid var(--border); padding:7px 9px; text-align:left; vertical-align:top; }}
th {{ background:var(--head); font-weight:700; }}
tbody tr:nth-child(even) {{ background:rgba(0,0,0,.025); }}
td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
code {{ background:#ece8df; padding:1px 5px; border-radius:4px; }}
</style>
</head>
<body>
<main>
<h1>Frozen Selector v2 Validation</h1>
<p class="meta">固定规则：<code>{RULE_NAME}</code>。参数不再 sweep：loss streak >= 6 或 drawdown >= 9000，或 rolling weak_count >= 4。weak_count 使用 q=10%、120 期历史、最少 40 期历史。</p>
<div class="callout">本报告只验证冻结规则，不做参数选择。所有切换判定只依赖当期下注前 feature 和此前已发生 PnL。</div>

<h2>Summary</h2>
{html_base.table_html(summary, summary_cols)}

<h2>Equity / Drawdown</h2>
<div class="chart-wrap">{equity_svg}</div>
<div class="chart-wrap">{norm_svg}</div>
<div class="chart-wrap">{dd_svg}</div>
<div class="chart-wrap">{annual_svg}</div>

<h2>Period Stress</h2>
{html_base.table_html(periods, [
    ("portfolio", "portfolio", "text"),
    ("period", "period", "text"),
    ("n_issues", "n", "num"),
    ("profit_per_256", "profit/256", "num"),
    ("roi", "ROI", "roi"),
    ("delta_profit_per_256_vs_base", "profit/256 Δ", "num"),
    ("max_drawdown_units", "maxDD", "num"),
    ("delta_maxdd_units_vs_base", "maxDD Δ", "num"),
    ("max_loss_streak", "loss streak", "num"),
    ("delta_loss_streak_vs_base", "loss streak Δ", "num"),
    ("issue_win_rate", "issue win", "pct"),
    ("full_loss_rate", "full loss", "pct"),
])}

<h2>Ex Best Issue</h2>
{html_base.table_html(ex_best, [
    ("portfolio", "portfolio", "text"),
    ("period", "period", "text"),
    ("n_issues", "n", "num"),
    ("profit_units", "profit", "num"),
    ("roi", "ROI", "roi"),
    ("best_issue", "best issue", "text"),
    ("best_issue_profit_units", "best profit", "num"),
    ("profit_ex_best_issue", "profit ex-best", "num"),
    ("roi_ex_best_issue", "ROI ex-best", "roi"),
    ("max_drawdown_ex_best_units", "maxDD ex-best", "num"),
    ("max_loss_streak_ex_best", "loss streak ex-best", "num"),
])}

<h2>Rolling Window Stability</h2>
{html_base.table_html(rolling_summary, [
    ("portfolio", "portfolio", "text"),
    ("window", "window", "num"),
    ("n_windows", "n", "num"),
    ("positive_profit_delta_rate", "profit+ rate", "pct"),
    ("positive_maxdd_delta_rate", "maxDD+ rate", "pct"),
    ("both_positive_rate", "both+ rate", "pct"),
    ("avg_profit_delta", "avg profit Δ", "num"),
    ("median_profit_delta", "median profit Δ", "num"),
    ("worst_profit_delta", "worst profit Δ", "num"),
    ("avg_maxdd_delta", "avg maxDD Δ", "num"),
    ("worst_maxdd_delta", "worst maxDD Δ", "num"),
    ("avg_loss_streak_delta", "avg loss streak Δ", "num2"),
])}

<h2>Switch Attribution</h2>
{html_base.table_html(switch_rows, [
    ("group", "group", "text"),
    ("n", "n", "num"),
    ("delta_vs_base_units", "delta vs base", "num"),
    ("helped_count", "helped", "num"),
    ("hurt_count", "hurt", "num"),
    ("flat_count", "flat", "num"),
    ("saved_full_loss_count", "saved full loss", "num"),
    ("created_full_loss_count", "created full loss", "num"),
    ("big_rescue_count", "big rescue", "num"),
])}
</main>
</body>
</html>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


def make_md(path: Path, summary: list[dict[str, object]], switch_rows: list[dict[str, object]], rolling_summary: list[dict[str, object]]) -> None:
    by_name = {row["portfolio"]: row for row in summary}
    rule = by_name[RULE_NAME]
    base = by_name[BASELINE]
    state = by_name[STATE_REF]
    switch = {row["group"]: row for row in switch_rows}
    lines = [
        "# Frozen Selector v2 Validation",
        "",
        "Date: 2026-06-29",
        "",
        f"Frozen rule: `{RULE_NAME}`.",
        "",
        "Parameters are fixed: loss streak >= 6 or drawdown >= 9000, or rolling weak_count >= 4 using q=10%, 120-issue history, minimum 40 historical issues.",
        "",
        "## Main Result",
        "",
        "| portfolio | profit/256 | ROI | maxDD | max loss streak | issue win | recent profit/256 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in (base, state, rule, by_name[DEFENSIVE]):
        lines.append(
            f"| `{row['portfolio']}` | {fnum(row['profit_per_256']):.1f} | {fnum(row['roi']):.3f} | "
            f"{fnum(row['max_drawdown_units']):.1f} | {int(fnum(row['max_loss_streak']))} | "
            f"{fnum(row['issue_win_rate']) * 100:.2f}% | {fnum(row['recent_profit_per_256']):.1f} |"
        )
    lines.extend(
        [
            "",
            "Compared with baseline, the frozen rule keeps nearly all profit while reducing maxDD and longest loss streak:",
            "",
            f"- profit/256 delta: {fnum(rule['delta_profit_per_256_vs_base']):+.1f}",
            f"- maxDD delta: {fnum(rule['delta_maxdd_units_vs_base']):+.1f}",
            f"- max loss streak delta: {fnum(rule['delta_loss_streak_vs_base']):+.0f}",
            f"- issue win delta: {fnum(rule['delta_issue_win_pp_vs_base']):+.2f}pp",
            "",
            "## Switch Attribution",
            "",
            "| group | n | delta vs base | helped | hurt | flat |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for group in ("all_switches", "quality_only", "state_involved", "quality_and_state"):
        row = switch[group]
        lines.append(
            f"| {group} | {int(fnum(row['n']))} | {fnum(row['delta_vs_base_units']):.1f} | "
            f"{int(fnum(row['helped_count']))} | {int(fnum(row['hurt_count']))} | {int(fnum(row['flat_count']))} |"
        )
    lines.extend(
        [
            "",
            "## Rolling Stability",
            "",
            "Rolling windows are mixed: the rule is not a universal profit improver in every sub-window. Its value is mainly risk-shape improvement with limited profit give-up.",
            "",
            "| portfolio | window | profit+ rate | maxDD+ rate | both+ rate | avg profit delta | avg maxDD delta |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in rolling_summary:
        if row["portfolio"] != RULE_NAME:
            continue
        lines.append(
            f"| `{row['portfolio']}` | {int(fnum(row['window']))} | {fnum(row['positive_profit_delta_rate']) * 100:.1f}% | "
            f"{fnum(row['positive_maxdd_delta_rate']) * 100:.1f}% | {fnum(row['both_positive_rate']) * 100:.1f}% | "
            f"{fnum(row['avg_profit_delta']):.1f} | {fnum(row['avg_maxdd_delta']):.1f} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            "Promote this frozen rule as a paper/live-shadow candidate, not yet as the automatic staking default. The next engineering step is to expose baseline vs frozen-selector recommendations in the WebUI plan page with the decision log.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    args.output_dir.mkdir(parents=True, exist_ok=True)
    portfolios = load_portfolios(args.issue_profit)
    features = load_features(args.features)
    issues = ordered_issues(portfolios)
    base_by_issue = portfolios[BASELINE]
    defensive_by_issue = portfolios[DEFENSIVE]
    ctx = FeatureContext(
        issues=issues,
        features_by_issue=features,
        q=QUALITY_Q,
        history=QUALITY_HISTORY,
        min_history=MIN_HISTORY,
    )

    series = {
        BASELINE: replay_static(
            name=BASELINE,
            chosen_state="base",
            issues=issues,
            base_by_issue=base_by_issue,
            defensive_by_issue=defensive_by_issue,
            features_by_issue=features,
        ),
        STATE_REF: replay_frozen(
            name=STATE_REF,
            issues=issues,
            base_by_issue=base_by_issue,
            defensive_by_issue=defensive_by_issue,
            features_by_issue=features,
            ctx=ctx,
            use_quality=False,
            use_state=True,
        ),
        RULE_NAME: replay_frozen(
            name=RULE_NAME,
            issues=issues,
            base_by_issue=base_by_issue,
            defensive_by_issue=defensive_by_issue,
            features_by_issue=features,
            ctx=ctx,
            use_quality=True,
            use_state=True,
        ),
        DEFENSIVE: replay_static(
            name=DEFENSIVE,
            chosen_state="defensive",
            issues=issues,
            base_by_issue=base_by_issue,
            defensive_by_issue=defensive_by_issue,
            features_by_issue=features,
        ),
    }

    summary = [summarize(rows, portfolio=name) for name, rows in series.items()]
    add_summary_deltas(summary)
    annual = annual_rows(series)
    periods = period_rows(series)
    ex_best = ex_best_rows(series)
    rolling, rolling_summary = rolling_rows(series)
    switches = switch_summary(series[RULE_NAME])
    issue_rows = [row for rows in series.values() for row in rows]

    write_rows(args.output_dir / "frozen_selector_summary.csv", summary)
    write_rows(args.output_dir / "frozen_selector_annual.csv", annual)
    write_rows(args.output_dir / "frozen_selector_periods.csv", periods)
    write_rows(args.output_dir / "frozen_selector_ex_best.csv", ex_best)
    write_rows(args.output_dir / "frozen_selector_rolling_windows.csv", rolling)
    write_rows(args.output_dir / "frozen_selector_rolling_summary.csv", rolling_summary)
    write_rows(args.output_dir / "frozen_selector_switch_summary.csv", switches)
    write_rows(args.output_dir / "frozen_selector_decision_log.csv", series[RULE_NAME])
    write_rows(args.output_dir / "frozen_selector_issue_profit.csv", issue_rows)
    make_html(
        output=args.output,
        summary=summary,
        annual=annual,
        periods=periods,
        ex_best=ex_best,
        rolling_summary=rolling_summary,
        switch_rows=switches,
        issue_rows=issue_rows,
    )
    make_md(args.markdown, summary=summary, switch_rows=switches, rolling_summary=rolling_summary)
    print(f"Wrote {args.output_dir}")
    print(f"Wrote {args.output}")
    print(f"Wrote {args.markdown}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=FEATURE_PATH)
    parser.add_argument("--issue-profit", type=Path, default=ISSUE_PROFIT_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--output", type=Path, default=OUT_HTML)
    parser.add_argument("--markdown", type=Path, default=OUT_MD)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
