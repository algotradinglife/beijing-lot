#!/usr/bin/env python3
"""Next-round defensive optimization for baseline_384_hybrid.

Order:
1. Fine-grid smooth/convex Pareto sweep around the current 384 hybrid.
2. Drawdown anatomy baseline vs defensive_smooth90_convex10.
3. No-lookahead regime switch between baseline and defensive_smooth90.
"""
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

from scripts.evaluate_high_n_fixed256_diversity import annual_rows, fnum, full_loss, load_issue_calendar, row_order
from scripts.evaluate_n7_sleeve_mix_capital import (
    ARM_ISSUE_PATH,
    CONVEX_ARM,
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

import scripts.render_main_strategy_leg_ev_depth_html as html_base


BASE_BUDGET = 256.0
TOTAL_BUDGET = 384.0
DD_UNITS = 32.0
REMAINING = TOTAL_BUDGET - BASE_BUDGET - DD_UNITS
BASELINE_NAME = "baseline_384_hybrid"
DEFENSIVE_NAME = "defensive_smooth90_convex10"


def fine_grid_specs(step: int) -> list[tuple[str, float, dict[str, float], str]]:
    specs: list[tuple[str, float, dict[str, float], str]] = [
        ("current_reference_256", BASE_BUDGET, {}, "Current fixed-256 reference.")
    ]
    for smooth_pct in range(80, 101, step):
        convex_pct = 100 - smooth_pct
        name = f"smooth{smooth_pct:03d}_convex{convex_pct:03d}"
        if smooth_pct == 80:
            name = BASELINE_NAME
        elif smooth_pct == 90:
            name = DEFENSIVE_NAME
        elif smooth_pct == 100:
            name = "defensive_smooth100"
        allocation = {
            DD_ARM: DD_UNITS,
            SMOOTH_ARM: REMAINING * smooth_pct / 100.0,
        }
        if convex_pct > 0:
            allocation[CONVEX_ARM] = REMAINING * convex_pct / 100.0
        specs.append(
            (
                name,
                TOTAL_BUDGET,
                allocation,
                f"dd32 + smooth{smooth_pct} / convex{convex_pct} focused defensive grid.",
            )
        )
    return specs


def allocation_label(allocation: dict[str, float]) -> str:
    return "; ".join(
        key.removeprefix("n7prot_").removesuffix("__budget256_fractional") + f"={value:g}"
        for key, value in allocation.items()
        if value > 1e-9
    )


def add_delta_columns(summary_rows: list[dict[str, object]], baseline_name: str = BASELINE_NAME) -> None:
    baseline = next(row for row in summary_rows if row["portfolio"] == baseline_name)
    keys = {
        "roi": "delta_roi_vs_baseline",
        "profit_per_256": "delta_profit_per_256_vs_baseline",
        "issue_win_rate": "delta_issue_win_pp_vs_baseline",
        "non_full_loss_rate": "delta_non_full_loss_pp_vs_baseline",
        "full_loss_rate": "delta_full_loss_pp_vs_baseline",
        "max_drawdown_units": "delta_maxdd_units_vs_baseline",
        "max_loss_streak": "delta_loss_streak_vs_baseline",
        "max_dead_streak": "delta_dead_streak_vs_baseline",
        "recent_profit_per_256": "delta_recent_profit_per_256_vs_baseline",
    }
    for row in summary_rows:
        for key, out_key in keys.items():
            value = fnum(row.get(key)) - fnum(baseline.get(key))
            if key.endswith("_rate"):
                value *= 100.0
            row[out_key] = value


def pareto_frontier(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates = [row for row in rows if fnum(row.get("issue_budget")) == TOTAL_BUDGET and fnum(row.get("roi")) >= 0.8]
    front: list[dict[str, object]] = []
    for row in candidates:
        dominated = False
        for other in candidates:
            if other is row:
                continue
            better_or_equal = (
                fnum(other.get("roi")) >= fnum(row.get("roi"))
                and fnum(other.get("issue_win_rate")) >= fnum(row.get("issue_win_rate"))
                and fnum(other.get("non_full_loss_rate")) >= fnum(row.get("non_full_loss_rate"))
                and fnum(other.get("max_drawdown_units")) >= fnum(row.get("max_drawdown_units"))
                and fnum(other.get("max_loss_streak")) <= fnum(row.get("max_loss_streak"))
                and fnum(other.get("max_dead_streak")) <= fnum(row.get("max_dead_streak"))
            )
            strict = (
                fnum(other.get("roi")) > fnum(row.get("roi"))
                or fnum(other.get("issue_win_rate")) > fnum(row.get("issue_win_rate"))
                or fnum(other.get("non_full_loss_rate")) > fnum(row.get("non_full_loss_rate"))
                or fnum(other.get("max_drawdown_units")) > fnum(row.get("max_drawdown_units"))
                or fnum(other.get("max_loss_streak")) < fnum(row.get("max_loss_streak"))
                or fnum(other.get("max_dead_streak")) < fnum(row.get("max_dead_streak"))
            )
            if better_or_equal and strict:
                dominated = True
                break
        if not dominated:
            copied = dict(row)
            copied["pareto_front"] = 1
            front.append(copied)
    return sorted(front, key=lambda r: (fnum(r.get("max_drawdown_units")), fnum(r.get("roi"))), reverse=True)


def find_maxdd_window(rows: list[dict[str, object]]) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    worst = 0.0
    worst_peak_idx = -1
    worst_trough_idx = -1
    equities = []
    for idx, row in enumerate(ordered):
        equity += fnum(row.get("profit_units"))
        equities.append(equity)
        if equity > peak:
            peak = equity
            peak_idx = idx
        dd = equity - peak
        if dd < worst:
            worst = dd
            worst_peak_idx = peak_idx
            worst_trough_idx = idx
    start = max(0, worst_peak_idx + 1)
    end = max(start, worst_trough_idx)
    return {
        "maxdd": worst,
        "start_idx": start,
        "end_idx": end,
        "start_issue": ordered[start]["issue"] if ordered else "",
        "end_issue": ordered[end]["issue"] if ordered else "",
        "issues": ordered[start : end + 1],
    }


def find_loss_streak(rows: list[dict[str, object]]) -> dict[str, object]:
    best_start = best_end = -1
    cur_start = -1
    ordered = sorted(rows, key=row_order)
    for idx, row in enumerate(ordered):
        if fnum(row.get("profit_units")) < 0:
            if cur_start < 0:
                cur_start = idx
            if idx - cur_start > best_end - best_start:
                best_start, best_end = cur_start, idx
        else:
            cur_start = -1
    segment = ordered[best_start : best_end + 1] if best_start >= 0 else []
    return {
        "loss_streak": len(segment),
        "start_issue": segment[0]["issue"] if segment else "",
        "end_issue": segment[-1]["issue"] if segment else "",
        "profit_units": sum(fnum(row.get("profit_units")) for row in segment),
    }


def window_summary(portfolio: str, rows: list[dict[str, object]]) -> dict[str, object]:
    window = find_maxdd_window(rows)
    segment = window["issues"]
    worst_issue = min(segment, key=lambda row: fnum(row.get("profit_units"))) if segment else {}
    loss_streak = find_loss_streak(rows)
    return {
        "portfolio": portfolio,
        "maxdd": window["maxdd"],
        "window_start_issue": window["start_issue"],
        "window_end_issue": window["end_issue"],
        "window_issues": len(segment),
        "window_profit_units": sum(fnum(row.get("profit_units")) for row in segment),
        "window_wins": sum(1 for row in segment if fnum(row.get("profit_units")) > 0),
        "window_losses": sum(1 for row in segment if fnum(row.get("profit_units")) < 0),
        "window_full_losses": sum(1 for row in segment if full_loss(row)),
        "worst_issue": worst_issue.get("issue", ""),
        "worst_issue_profit": fnum(worst_issue.get("profit_units")),
        "max_loss_streak": loss_streak["loss_streak"],
        "loss_streak_start_issue": loss_streak["start_issue"],
        "loss_streak_end_issue": loss_streak["end_issue"],
        "loss_streak_profit_units": loss_streak["profit_units"],
    }


def compare_baseline_window(
    baseline_rows: list[dict[str, object]],
    defensive_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    window = find_maxdd_window(baseline_rows)
    defensive_by_issue = {str(row["issue"]): row for row in defensive_rows}
    out = []
    for row in window["issues"]:
        issue = str(row["issue"])
        other = defensive_by_issue[issue]
        base_profit = fnum(row.get("profit_units"))
        def_profit = fnum(other.get("profit_units"))
        out.append(
            {
                "issue": issue,
                "issue_order": row.get("issue_order", ""),
                "calendar_year": row.get("calendar_year", ""),
                "baseline_profit": base_profit,
                "defensive_profit": def_profit,
                "defensive_minus_baseline": def_profit - base_profit,
                "baseline_full_loss": int(full_loss(row)),
                "defensive_full_loss": int(full_loss(other)),
                "baseline_hits": row.get("hits", ""),
                "defensive_hits": other.get("hits", ""),
                "baseline_tickets": row.get("tickets", ""),
                "defensive_tickets": other.get("tickets", ""),
            }
        )
    summary = [
        {
            "comparison": "baseline_maxdd_window",
            "start_issue": window["start_issue"],
            "end_issue": window["end_issue"],
            "n_issues": len(out),
            "baseline_profit": sum(fnum(row["baseline_profit"]) for row in out),
            "defensive_profit": sum(fnum(row["defensive_profit"]) for row in out),
            "defensive_minus_baseline": sum(fnum(row["defensive_minus_baseline"]) for row in out),
            "defensive_better_issues": sum(1 for row in out if fnum(row["defensive_minus_baseline"]) > 0),
            "defensive_worse_issues": sum(1 for row in out if fnum(row["defensive_minus_baseline"]) < 0),
            "baseline_full_losses": sum(int(row["baseline_full_loss"]) for row in out),
            "defensive_full_losses": sum(int(row["defensive_full_loss"]) for row in out),
        }
    ]
    return out, summary


def simulate_switch(
    *,
    name: str,
    baseline_rows: list[dict[str, object]],
    defensive_rows: list[dict[str, object]],
    loss_trigger: int,
    drawdown_trigger: float,
) -> list[dict[str, object]]:
    defensive_by_issue = {str(row["issue"]): row for row in defensive_rows}
    out = []
    equity = 0.0
    peak = 0.0
    loss_streak = 0
    for base_row in sorted(baseline_rows, key=row_order):
        prior_drawdown = peak - equity
        use_defensive = loss_streak >= loss_trigger or prior_drawdown >= drawdown_trigger
        selected = defensive_by_issue[str(base_row["issue"])] if use_defensive else base_row
        row = dict(selected)
        row["portfolio"] = name
        row["selected_arm"] = DEFENSIVE_NAME if use_defensive else BASELINE_NAME
        row["prior_loss_streak"] = loss_streak
        row["prior_drawdown_units"] = prior_drawdown
        out.append(row)
        profit = fnum(row.get("profit_units"))
        equity += profit
        peak = max(peak, equity)
        loss_streak = loss_streak + 1 if profit < 0 else 0
    return out


def run_switch_grid(
    baseline_rows: list[dict[str, object]],
    defensive_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    issue_rows = []
    summary_rows = []
    annual = []
    configs: list[tuple[str, int, float]] = [
        ("static_baseline", 10**6, 10**12),
        ("static_defensive90", 0, 0),
    ]
    for loss_trigger in (4, 6, 8, 10, 12):
        for drawdown_trigger in (3000.0, 6000.0, 9000.0, 12000.0, 15000.0):
            configs.append((f"switch_L{loss_trigger}_DD{int(drawdown_trigger)}", loss_trigger, drawdown_trigger))
    for name, loss_trigger, drawdown_trigger in configs:
        if name == "static_baseline":
            rows = [dict(row, portfolio=name, selected_arm=BASELINE_NAME) for row in baseline_rows]
        elif name == "static_defensive90":
            rows = [dict(row, portfolio=name, selected_arm=DEFENSIVE_NAME) for row in defensive_rows]
        else:
            rows = simulate_switch(
                name=name,
                baseline_rows=baseline_rows,
                defensive_rows=defensive_rows,
                loss_trigger=loss_trigger,
                drawdown_trigger=drawdown_trigger,
            )
        issue_rows.extend(rows)
        summary = summarize(rows, TOTAL_BUDGET, 2023, 2025)
        summary["loss_trigger"] = "" if name.startswith("static") else loss_trigger
        summary["drawdown_trigger"] = "" if name.startswith("static") else drawdown_trigger
        summary["defensive_issue_count"] = sum(1 for row in rows if row.get("selected_arm") == DEFENSIVE_NAME)
        summary["defensive_issue_share"] = summary["defensive_issue_count"] / len(rows)
        summary_rows.append(summary)
        annual.extend(annual_rows(rows))
    add_delta_columns(summary_rows, baseline_name="static_baseline")
    return issue_rows, summary_rows, annual


def fmt(value: object, digits: int = 3) -> str:
    number = fnum(value, math.nan)
    if not math.isfinite(number):
        return ""
    return f"{number:.{digits}f}"


def make_html(
    *,
    path: Path,
    fine_summary: list[dict[str, object]],
    pareto: list[dict[str, object]],
    anatomy_rows: list[dict[str, object]],
    window_compare_summary: list[dict[str, object]],
    switch_summary: list[dict[str, object]],
    fine_issue_rows: list[dict[str, object]],
    switch_issue_rows: list[dict[str, object]],
) -> None:
    html_base.FOCUSED = [BASELINE_NAME, DEFENSIVE_NAME, "defensive_smooth100"]
    html_base.COLORS = {
        BASELINE_NAME: "#2f855a",
        DEFENSIVE_NAME: "#e45756",
        "defensive_smooth100": "#7f7f7f",
    }
    fine_curve_rows = [row for row in fine_issue_rows if row.get("portfolio") in html_base.FOCUSED]
    eq, dd = html_base.build_series([{k: str(v) for k, v in row.items()} for row in fine_curve_rows])
    html_base.FOCUSED = ["static_baseline", "static_defensive90"] + [
        row["portfolio"]
        for row in sorted(
            [r for r in switch_summary if str(r["portfolio"]).startswith("switch_")],
            key=lambda r: (fnum(r.get("max_drawdown_units")), fnum(r.get("roi"))),
            reverse=True,
        )[:3]
    ]
    html_base.COLORS = {
        "static_baseline": "#2f855a",
        "static_defensive90": "#e45756",
        html_base.FOCUSED[2] if len(html_base.FOCUSED) > 2 else "x": "#4c78a8",
        html_base.FOCUSED[3] if len(html_base.FOCUSED) > 3 else "y": "#f58518",
        html_base.FOCUSED[4] if len(html_base.FOCUSED) > 4 else "z": "#b279a2",
    }
    switch_curve_rows = [row for row in switch_issue_rows if row.get("portfolio") in html_base.FOCUSED]
    sw_eq, sw_dd = html_base.build_series([{k: str(v) for k, v in row.items()} for row in switch_curve_rows])

    grid_rows = [
        row
        for row in fine_summary
        if row["portfolio"] in {BASELINE_NAME, DEFENSIVE_NAME, "defensive_smooth100"}
        or str(row["portfolio"]).startswith("smooth08")
        or str(row["portfolio"]).startswith("smooth09")
    ]
    switch_top = sorted(
        switch_summary,
        key=lambda r: (
            fnum(r.get("max_drawdown_units")),
            -fnum(r.get("max_loss_streak")),
            fnum(r.get("roi")),
        ),
        reverse=True,
    )[:12]

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>北单主策略防守优化下一轮</title>
<style>
body {{ margin:0; background:#f7f7f4; color:#171717; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",Arial,sans-serif; line-height:1.65; }}
main {{ max-width:1240px; margin:0 auto; padding:28px 28px 72px; }}
h1 {{ font-size:30px; margin:0 0 8px; }} h2 {{ font-size:21px; margin:34px 0 12px; padding-bottom:6px; border-bottom:1px solid #d7d2c8; }}
.meta {{ color:#666; font-size:14px; }} .callout {{ background:#fff7e6; border-left:4px solid #8a5a00; padding:12px 16px; margin:18px 0; border-radius:0 6px 6px 0; }}
.chart-wrap {{ background:#fff; border:1px solid #d7d2c8; border-radius:8px; padding:14px; overflow-x:auto; margin:14px 0; }}
.chart {{ width:100%; min-width:980px; height:auto; display:block; background:#fff; }}
.chart-title {{ font-size:18px; font-weight:700; fill:#222; }} .axis-label,.tick,.legend {{ fill:#555; font-size:12px; }} .legend.small {{ font-size:10px; }}
.axis {{ stroke:#8d887f; stroke-width:1; }} .grid {{ stroke:#e5e1d8; stroke-width:1; }} .zero {{ stroke:#888; stroke-width:1.3; stroke-dasharray:4 4; }}
table {{ width:100%; border-collapse:collapse; background:#fff; font-size:13px; margin:10px 0 18px; }}
th,td {{ border:1px solid #d7d2c8; padding:7px 9px; text-align:left; vertical-align:top; }} th {{ background:#eef2ef; font-weight:700; }}
tbody tr:nth-child(even) {{ background:rgba(0,0,0,0.025); }} td.num {{ text-align:right; font-variant-numeric:tabular-nums; }}
code {{ background:#ece8df; padding:1px 5px; border-radius:4px; }}
</style></head><body><main>
<h1>北单主策略防守优化下一轮</h1>
<p class="meta">顺序：1% fine-grid -> drawdown anatomy -> no-lookahead regime switch。</p>
<div class="callout"><b>当前结论：</b><code>{BASELINE_NAME}</code> 保留为均衡备选；
<code>{DEFENSIVE_NAME}</code> 是更符合“适当降 ROI 换 loss/maxDD 改善”的静态候选。
动态 switch 初步只作为 paper 对照，不能先于静态 Pareto 进入推荐。</div>

<h2>1. Fine-grid Pareto</h2>
{html_base.table_html(grid_rows, [
    ("portfolio", "portfolio", "text"),
    ("roi", "ROI", "roi"),
    ("profit_per_256", "profit/256", "num"),
    ("delta_roi_vs_baseline", "ROI Δ", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("delta_issue_win_pp_vs_baseline", "issue win Δpp", "num2"),
    ("full_loss_rate", "full-loss", "pct"),
    ("delta_full_loss_pp_vs_baseline", "full-loss Δpp", "num2"),
    ("max_drawdown_units", "maxDD", "num"),
    ("delta_maxdd_units_vs_baseline", "maxDD Δ", "num"),
    ("max_loss_streak", "loss streak", "num"),
    ("delta_loss_streak_vs_baseline", "loss streak Δ", "num"),
    ("roi_ex_best_issue", "ex-best ROI", "roi"),
])}
<h3>Pareto frontier</h3>
{html_base.table_html(pareto, [
    ("portfolio", "portfolio", "text"),
    ("roi", "ROI", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("max_drawdown_units", "maxDD", "num"),
    ("max_loss_streak", "loss streak", "num"),
    ("allocation", "allocation", "text"),
])}
<div class="chart-wrap">{html_base.line_svg(eq, title="Fine-grid equity: baseline vs defensive", y_label="cumulative profit")}</div>
<div class="chart-wrap">{html_base.line_svg(dd, title="Fine-grid drawdown: baseline vs defensive", y_label="drawdown")}</div>

<h2>3. Drawdown anatomy</h2>
{html_base.table_html(anatomy_rows, [
    ("portfolio", "portfolio", "text"),
    ("maxdd", "maxDD", "num"),
    ("window_start_issue", "start", "text"),
    ("window_end_issue", "end", "text"),
    ("window_issues", "issues", "num"),
    ("window_wins", "wins", "num"),
    ("window_full_losses", "full losses", "num"),
    ("worst_issue", "worst issue", "text"),
    ("worst_issue_profit", "worst profit", "num"),
    ("max_loss_streak", "loss streak", "num"),
    ("loss_streak_start_issue", "loss start", "text"),
    ("loss_streak_end_issue", "loss end", "text"),
])}
<h3>Baseline maxDD window comparison</h3>
{html_base.table_html(window_compare_summary, [
    ("comparison", "window", "text"),
    ("start_issue", "start", "text"),
    ("end_issue", "end", "text"),
    ("n_issues", "n", "num"),
    ("baseline_profit", "baseline profit", "num"),
    ("defensive_profit", "defensive profit", "num"),
    ("defensive_minus_baseline", "improvement", "num"),
    ("defensive_better_issues", "better issues", "num"),
    ("defensive_worse_issues", "worse issues", "num"),
    ("baseline_full_losses", "baseline full-loss", "num"),
    ("defensive_full_losses", "defensive full-loss", "num"),
])}

<h2>2. Regime switch paper test</h2>
<p class="meta">规则只使用当前期之前的已结算 equity/drawdown/loss-streak，不看当前赛果。</p>
{html_base.table_html(switch_top, [
    ("portfolio", "portfolio", "text"),
    ("roi", "ROI", "roi"),
    ("profit_per_256", "profit/256", "num"),
    ("max_drawdown_units", "maxDD", "num"),
    ("max_loss_streak", "loss streak", "num"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("defensive_issue_share", "defensive share", "pct"),
    ("loss_trigger", "L trigger", "text"),
    ("drawdown_trigger", "DD trigger", "num"),
])}
<div class="chart-wrap">{html_base.line_svg(sw_eq, title="Switch equity paper test", y_label="cumulative profit")}</div>
<div class="chart-wrap">{html_base.line_svg(sw_dd, title="Switch drawdown paper test", y_label="drawdown")}</div>

<h2>文件</h2>
<ul>
<li><code>results/main_strategy_defensive_next_round_20260629/fine_grid_summary.csv</code></li>
<li><code>results/main_strategy_defensive_next_round_20260629/drawdown_anatomy.csv</code></li>
<li><code>results/main_strategy_defensive_next_round_20260629/switch_summary.csv</code></li>
</ul>
</main></body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, default=Path("results/main_strategy_defensive_next_round_20260629"))
    parser.add_argument(
        "--html",
        type=Path,
        default=Path("docs/research/main_strategy_defensive_next_round_2026-06-29.html"),
    )
    args = parser.parse_args()

    calendar = load_issue_calendar(args.db)
    current = load_current(CURRENT_ISSUE_PATH, calendar)
    arms = load_arms(ARM_ISSUE_PATH, calendar)
    issues = ordered_issues(calendar, current)

    fine_issue_rows: list[dict[str, object]] = []
    fine_summary: list[dict[str, object]] = []
    fine_annual: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    for name, budget, allocation, rationale in fine_grid_specs(args.step):
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
        series[name] = rows
        fine_issue_rows.extend(rows)
        summary = summarize(rows, budget, 2023, 2025)
        summary["allocation"] = allocation_label(allocation)
        summary["rationale"] = rationale
        fine_summary.append(summary)
        fine_annual.extend(annual_rows(rows))
    add_delta_columns(fine_summary)
    pareto = pareto_frontier(fine_summary)

    baseline_rows = series[BASELINE_NAME]
    defensive_rows = series[DEFENSIVE_NAME]
    anatomy = [
        window_summary(BASELINE_NAME, baseline_rows),
        window_summary(DEFENSIVE_NAME, defensive_rows),
    ]
    window_compare, window_compare_summary = compare_baseline_window(baseline_rows, defensive_rows)

    switch_issue_rows, switch_summary, switch_annual = run_switch_grid(baseline_rows, defensive_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "fine_grid_issue_profit.csv", fine_issue_rows)
    write_csv_all(args.output_dir / "fine_grid_summary.csv", fine_summary)
    write_csv_all(args.output_dir / "fine_grid_annual.csv", fine_annual)
    write_csv_all(args.output_dir / "pareto_frontier.csv", pareto)
    write_csv_all(args.output_dir / "drawdown_anatomy.csv", anatomy)
    write_csv_all(args.output_dir / "baseline_window_issue_diff.csv", window_compare)
    write_csv_all(args.output_dir / "baseline_window_compare_summary.csv", window_compare_summary)
    write_csv_all(args.output_dir / "switch_issue_profit.csv", switch_issue_rows)
    write_csv_all(args.output_dir / "switch_summary.csv", switch_summary)
    write_csv_all(args.output_dir / "switch_annual.csv", switch_annual)
    make_html(
        path=args.html,
        fine_summary=fine_summary,
        pareto=pareto,
        anatomy_rows=anatomy,
        window_compare_summary=window_compare_summary,
        switch_summary=switch_summary,
        fine_issue_rows=fine_issue_rows,
        switch_issue_rows=switch_issue_rows,
    )
    print(f"Wrote {args.output_dir}")
    print(f"Wrote {args.html}")


if __name__ == "__main__":
    main()
