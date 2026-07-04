#!/usr/bin/env python3
"""Render a static HTML report for main-strategy leg EV depth replay."""
from __future__ import annotations

import argparse
import csv
import html
import math
from collections import defaultdict
from pathlib import Path


FOCUSED = [
    "current_reference_256",
    "baseline_384_hybrid",
    "b384_ev_depth_v1",
    "b384_confidence_depth_v1",
    "b384_q_payout_depth_v1",
    "b384_hybrid_depth_v1",
]

COLORS = {
    "current_reference_256": "#4c78a8",
    "baseline_384_hybrid": "#2f855a",
    "b384_ev_depth_v1": "#f58518",
    "b384_confidence_depth_v1": "#b279a2",
    "b384_q_payout_depth_v1": "#e45756",
    "b384_hybrid_depth_v1": "#72b7b2",
}


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def fmt_num(value: object, digits: int = 0) -> str:
    number = fnum(value, math.nan)
    if not math.isfinite(number):
        return ""
    return f"{number:,.{digits}f}"


def fmt_pct(value: object, digits: int = 1) -> str:
    return f"{fnum(value) * 100:.{digits}f}%"


def esc(value: object) -> str:
    return html.escape(str(value))


def table_html(rows: list[dict[str, object]], columns: list[tuple[str, str, str]]) -> str:
    if not rows:
        return "<p class=\"muted\">No rows.</p>"
    head = "".join(f"<th>{esc(label)}</th>" for _key, label, _kind in columns)
    body_rows = []
    for row in rows:
        cells = []
        for key, _label, kind in columns:
            value = row.get(key, "")
            cls = "num" if kind in {"num", "pct"} else ""
            if kind == "num":
                text = fmt_num(value, 0)
            elif kind == "num2":
                cls = "num"
                text = fmt_num(value, 2)
            elif kind == "pct":
                text = fmt_pct(value)
            elif kind == "roi":
                cls = "num"
                text = fmt_num(value, 3)
            else:
                text = esc(value)
            cells.append(f"<td class=\"{cls}\">{text}</td>")
        body_rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"


def issue_order(row: dict[str, str]) -> tuple[int, str]:
    return (int(fnum(row.get("issue_order"), 10**9)), str(row.get("issue", "")))


def build_series(issue_rows: list[dict[str, str]]) -> tuple[dict[str, list[tuple[float, float, str]]], dict[str, list[tuple[float, float, str]]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in issue_rows:
        if row.get("portfolio") in FOCUSED:
            grouped[str(row["portfolio"])].append(row)
    equity_series: dict[str, list[tuple[float, float, str]]] = {}
    drawdown_series: dict[str, list[tuple[float, float, str]]] = {}
    for portfolio, rows in grouped.items():
        equity = 0.0
        peak = 0.0
        eq_points = []
        dd_points = []
        for idx, row in enumerate(sorted(rows, key=issue_order)):
            equity += fnum(row.get("profit_units"))
            peak = max(peak, equity)
            label = str(row.get("issue_close_ts") or row.get("issue"))
            eq_points.append((idx, equity, label))
            dd_points.append((idx, equity - peak, label))
        equity_series[portfolio] = eq_points
        drawdown_series[portfolio] = dd_points
    return equity_series, drawdown_series


def nice_money(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000:
        return f"{sign}{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{sign}{value / 1_000:.0f}k"
    return f"{sign}{value:.0f}"


def line_svg(
    series: dict[str, list[tuple[float, float, str]]],
    *,
    title: str,
    y_label: str,
    height: int = 430,
    width: int = 1180,
) -> str:
    left, right, top, bottom = 72, 24, 44, 70
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [y for points in series.values() for _x, y, _label in points]
    xs = [x for points in series.values() for x, _y, _label in points]
    if not values or not xs:
        return ""
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(values), max(values)
    if min_y == max_y:
        min_y -= 1
        max_y += 1
    pad = (max_y - min_y) * 0.08
    min_y -= pad
    max_y += pad

    def sx(x: float) -> float:
        return left + (x - min_x) / max(1, max_x - min_x) * plot_w

    def sy(y: float) -> float:
        return top + (max_y - y) / (max_y - min_y) * plot_h

    y_ticks = [min_y + (max_y - min_y) * i / 5 for i in range(6)]
    x_ticks = [min_x + (max_x - min_x) * i / 5 for i in range(6)]
    axis = [
        f"<text x='{left}' y='24' class='chart-title'>{esc(title)}</text>",
        f"<text x='{left}' y='{height - 18}' class='axis-label'>Issue timeline</text>",
        f"<text x='14' y='{top + 14}' class='axis-label'>{esc(y_label)}</text>",
        f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top + plot_h}' class='axis'/>",
        f"<line x1='{left}' y1='{top + plot_h}' x2='{left + plot_w}' y2='{top + plot_h}' class='axis'/>",
    ]
    for tick in y_ticks:
        y = sy(tick)
        axis.append(f"<line x1='{left}' y1='{y:.1f}' x2='{left + plot_w}' y2='{y:.1f}' class='grid'/>")
        axis.append(f"<text x='{left - 10}' y='{y + 4:.1f}' text-anchor='end' class='tick'>{nice_money(tick)}</text>")
    for tick in x_ticks:
        x = sx(tick)
        axis.append(f"<line x1='{x:.1f}' y1='{top + plot_h}' x2='{x:.1f}' y2='{top + plot_h + 5}' class='axis'/>")
        axis.append(f"<text x='{x:.1f}' y='{top + plot_h + 22}' text-anchor='middle' class='tick'>{int(tick)}</text>")

    if min_y < 0 < max_y:
        y0 = sy(0)
        axis.append(f"<line x1='{left}' y1='{y0:.1f}' x2='{left + plot_w}' y2='{y0:.1f}' class='zero'/>")

    paths = []
    legend = []
    legend_x = left
    legend_y = height - 42
    for idx, portfolio in enumerate(FOCUSED):
        points = series.get(portfolio, [])
        if not points:
            continue
        color = COLORS.get(portfolio, "#555")
        poly = " ".join(f"{sx(x):.1f},{sy(y):.1f}" for x, y, _label in points)
        paths.append(f"<polyline points='{poly}' fill='none' stroke='{color}' stroke-width='2.2'/>")
        lx = legend_x + (idx % 3) * 330
        ly = legend_y + (idx // 3) * 20
        legend.append(f"<rect x='{lx}' y='{ly - 9}' width='12' height='12' fill='{color}' rx='2'/>")
        legend.append(f"<text x='{lx + 18}' y='{ly + 1}' class='legend'>{esc(portfolio)}</text>")
    return (
        f"<svg viewBox='0 0 {width} {height}' role='img' class='chart'>"
        + "".join(axis)
        + "".join(paths)
        + "".join(legend)
        + "</svg>"
    )


def annual_profit_svg(annual_rows: list[dict[str, str]], *, height: int = 430, width: int = 1180) -> str:
    rows = [r for r in annual_rows if r.get("portfolio") in FOCUSED]
    years = sorted({int(fnum(r.get("year"))) for r in rows})
    if not rows or not years:
        return ""
    left, right, top, bottom = 72, 24, 44, 80
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [fnum(r.get("profit_units")) for r in rows]
    min_y, max_y = min(values), max(values)
    pad = (max_y - min_y) * 0.08 or 1
    min_y -= pad
    max_y += pad

    def sy(y: float) -> float:
        return top + (max_y - y) / (max_y - min_y) * plot_h

    by_key = {(r["portfolio"], int(fnum(r["year"]))): r for r in rows}
    group_w = plot_w / len(years)
    bar_w = group_w / (len(FOCUSED) + 1)
    parts = [
        f"<svg viewBox='0 0 {width} {height}' role='img' class='chart'>",
        f"<text x='{left}' y='24' class='chart-title'>Annual profit by portfolio</text>",
        f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top + plot_h}' class='axis'/>",
        f"<line x1='{left}' y1='{top + plot_h}' x2='{left + plot_w}' y2='{top + plot_h}' class='axis'/>",
    ]
    for i in range(6):
        tick = min_y + (max_y - min_y) * i / 5
        y = sy(tick)
        parts.append(f"<line x1='{left}' y1='{y:.1f}' x2='{left + plot_w}' y2='{y:.1f}' class='grid'/>")
        parts.append(f"<text x='{left - 10}' y='{y + 4:.1f}' text-anchor='end' class='tick'>{nice_money(tick)}</text>")
    y0 = sy(0)
    parts.append(f"<line x1='{left}' y1='{y0:.1f}' x2='{left + plot_w}' y2='{y0:.1f}' class='zero'/>")
    for yi, year in enumerate(years):
        x0 = left + yi * group_w
        parts.append(f"<text x='{x0 + group_w / 2:.1f}' y='{height - 42}' text-anchor='middle' class='tick'>{year}</text>")
        for pi, portfolio in enumerate(FOCUSED):
            row = by_key.get((portfolio, year))
            if not row:
                continue
            val = fnum(row.get("profit_units"))
            x = x0 + (pi + 0.5) * bar_w
            y = sy(max(0, val))
            h = abs(sy(val) - sy(0))
            if val < 0:
                y = sy(0)
            parts.append(
                f"<rect x='{x:.1f}' y='{y:.1f}' width='{bar_w * 0.82:.1f}' height='{h:.1f}' "
                f"fill='{COLORS.get(portfolio, '#555')}' opacity='0.86'/>"
            )
    legend_y = height - 20
    for idx, portfolio in enumerate(FOCUSED):
        lx = left + idx * 180
        parts.append(f"<rect x='{lx}' y='{legend_y - 9}' width='12' height='12' fill='{COLORS.get(portfolio, '#555')}' rx='2'/>")
        parts.append(f"<text x='{lx + 18}' y='{legend_y + 1}' class='legend small'>{esc(portfolio)}</text>")
    parts.append("</svg>")
    return "".join(parts)


def render(args: argparse.Namespace) -> None:
    result_dir = args.result_dir
    summary = read_rows(result_dir / "portfolio_summary.csv")
    issue_rows = read_rows(result_dir / "portfolio_issue_profit.csv")
    annual = read_rows(result_dir / "portfolio_annual.csv")
    distance = read_rows(result_dir / "ticket_distance_summary.csv")
    leg_cells = read_rows(result_dir / "leg_cell_summary.csv")

    summary = [r for r in summary if r.get("portfolio") in FOCUSED]
    summary.sort(key=lambda r: FOCUSED.index(r["portfolio"]))
    recent_rows = [
        r
        for r in annual
        if r.get("portfolio") in FOCUSED and int(fnum(r.get("year"))) >= 2023
    ]
    recent_rows.sort(key=lambda r: (FOCUSED.index(r["portfolio"]), int(fnum(r["year"]))))
    distance_rows = [
        r
        for r in distance
        if r.get("portfolio") in FOCUSED
        and str(r.get("n_legs")) == "7"
        and r.get("near_miss_bucket") in {"hit", "miss_1", "miss_2", "miss_3"}
    ]
    distance_rows.sort(key=lambda r: (FOCUSED.index(r["portfolio"]), str(r["near_miss_bucket"])))
    cell_rows = [
        r
        for r in leg_cells
        if r.get("portfolio") in {"baseline_384_hybrid", "b384_q_payout_depth_v1", "b384_confidence_depth_v1"}
        and r.get("sp_bucket") != "missing"
    ][:36]

    equity, drawdown = build_series(issue_rows)
    equity_svg = line_svg(equity, title="资金曲线：累计 profit", y_label="cumulative profit")
    dd_svg = line_svg(drawdown, title="回撤曲线：equity - running peak", y_label="drawdown")
    annual_svg = annual_profit_svg(annual)

    metric_rows: list[dict[str, object]] = []
    for row in summary:
        metric_rows.append(
            {
                "portfolio": row["portfolio"],
                "profit_units": row["profit_units"],
                "roi": row["roi"],
                "issue_win_rate": row["issue_win_rate"],
                "non_full_loss_rate": row["non_full_loss_rate"],
                "max_drawdown_units": row["max_drawdown_units"],
                "max_dead_streak": row["max_dead_streak"],
                "roi_ex_best_issue": row["roi_ex_best_issue"],
                "roi_ex_top2_issues": row["roi_ex_top2_issues"],
                "recent_2023_2025_profit_units": row["recent_2023_2025_profit_units"],
                "recent_2023_2025_roi": row["recent_2023_2025_roi"],
            }
        )

    html_text = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>北单主策略腿级 EV / Depth 回放报告</title>
<style>
:root {{
  --bg: #f7f7f4;
  --fg: #171717;
  --muted: #666;
  --border: #d7d2c8;
  --panel: #ffffff;
  --head: #eef2ef;
  --accent: #2f855a;
  --warn: #8a5a00;
  --warn-bg: #fff7e6;
  --bad: #9b2c2c;
  --good: #276749;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif;
  line-height: 1.65;
}}
main {{ max-width: 1240px; margin: 0 auto; padding: 28px 28px 72px; }}
h1 {{ font-size: 30px; margin: 0 0 8px; }}
h2 {{ font-size: 21px; margin: 34px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
p {{ margin: 8px 0; }}
.meta {{ color: var(--muted); font-size: 14px; }}
.callout {{ background: var(--warn-bg); border-left: 4px solid var(--warn); padding: 12px 16px; margin: 18px 0; border-radius: 0 6px 6px 0; }}
.grid2 {{ display: grid; grid-template-columns: 1fr; gap: 18px; }}
.chart-wrap {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; overflow-x: auto; }}
.chart {{ width: 100%; min-width: 980px; height: auto; display: block; background: #fff; }}
.chart-title {{ font-size: 18px; font-weight: 700; fill: #222; }}
.axis-label, .tick, .legend {{ fill: #555; font-size: 12px; }}
.legend.small {{ font-size: 10px; }}
.axis {{ stroke: #8d887f; stroke-width: 1; }}
.grid {{ stroke: #e5e1d8; stroke-width: 1; }}
.zero {{ stroke: #888; stroke-width: 1.3; stroke-dasharray: 4 4; }}
table {{ width: 100%; border-collapse: collapse; background: var(--panel); font-size: 13px; margin: 10px 0 18px; }}
th, td {{ border: 1px solid var(--border); padding: 7px 9px; text-align: left; vertical-align: top; }}
th {{ background: var(--head); font-weight: 700; }}
tbody tr:nth-child(even) {{ background: rgba(0,0,0,0.025); }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
code {{ background: #ece8df; padding: 1px 5px; border-radius: 4px; }}
.files li {{ margin: 3px 0; }}
</style>
</head>
<body>
<main>
<h1>北单主策略腿级 EV / Depth 回放报告</h1>
<p class="meta">生成日期：2026-06-29。数据来源：<code>results/main_strategy_leg_ev_depth_20260629</code>。</p>

<div class="callout">
  <b>核心结论：</b>固定 384 主候选 <code>baseline_384_hybrid</code> 仍是当前推荐方案。
  v1 动态 depth arms 有些 ROI 更高，但 issue win、non-full-loss、maxDD 和 N7 hit ticket 数都弱于固定 384，
  暂不能替代主策略。下一步应改进赛前 <code>prob_score/confidence</code> 校准，并把 near-miss/maxDD 显式放进 selector。
</div>

<h2>关键指标</h2>
{table_html(metric_rows, [
    ("portfolio", "portfolio", "text"),
    ("profit_units", "profit", "num"),
    ("roi", "ROI", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("max_drawdown_units", "maxDD", "num"),
    ("max_dead_streak", "dead streak", "num"),
    ("roi_ex_best_issue", "ex-best ROI", "roi"),
    ("roi_ex_top2_issues", "ex-top2 ROI", "roi"),
    ("recent_2023_2025_profit_units", "2023-2025 profit", "num"),
    ("recent_2023_2025_roi", "2023-2025 ROI", "roi"),
])}

<h2>资金曲线</h2>
<div class="grid2">
  <div class="chart-wrap">{equity_svg}</div>
  <div class="chart-wrap">{dd_svg}</div>
  <div class="chart-wrap">{annual_svg}</div>
</div>

<h2>2023-2025 年度表现</h2>
<p class="meta">2025 当前只有 15 期，不能与全年数据等量解读。</p>
{table_html(recent_rows, [
    ("portfolio", "portfolio", "text"),
    ("year", "year", "text"),
    ("n_issues", "n", "num"),
    ("profit_units", "profit", "num"),
    ("roi", "ROI", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("max_drawdown_units", "maxDD", "num"),
])}

<h2>N7 Near-miss</h2>
{table_html(distance_rows, [
    ("portfolio", "portfolio", "text"),
    ("near_miss_bucket", "bucket", "text"),
    ("n_tickets", "tickets", "num"),
    ("stake_units", "stake", "num"),
    ("profit_units", "profit", "num"),
    ("roi", "ROI", "roi"),
])}

<h2>腿级 Cell 摘要</h2>
<p class="meta">只展示部分已过滤掉 missing SP 的 cell；完整表在 <code>leg_cell_summary.csv</code>。</p>
{table_html(cell_rows, [
    ("portfolio", "portfolio", "text"),
    ("score_mode", "score mode", "text"),
    ("outcome_label", "outcome", "text"),
    ("sp_bucket", "SP", "text"),
    ("handicap_bucket", "handicap", "text"),
    ("selected_type", "type", "text"),
    ("n_leg_outcomes", "n", "num"),
    ("hit_rate", "hit rate", "pct"),
    ("avg_decision_sp_proxy", "avg SP", "num2"),
    ("avg_depth_score", "avg depth", "num2"),
])}

<h2>文件</h2>
<ul class="files">
  <li><code>docs/research/main_strategy_leg_ev_depth_replay_2026-06-29.html</code></li>
  <li><code>docs/research/main_strategy_leg_ev_depth_replay_2026-06-29.md</code></li>
  <li><code>results/main_strategy_leg_ev_depth_20260629/portfolio_summary.csv</code></li>
  <li><code>results/main_strategy_leg_ev_depth_20260629/portfolio_issue_profit.csv</code></li>
  <li><code>results/main_strategy_leg_ev_depth_20260629/ticket_distance_summary.csv</code></li>
  <li><code>results/main_strategy_leg_ev_depth_20260629/leg_cell_summary.csv</code></li>
</ul>
</main>
</body>
</html>
"""
    args.output.write_text(html_text, encoding="utf-8")
    print(f"Wrote {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=Path("results/main_strategy_leg_ev_depth_20260629"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/research/main_strategy_leg_ev_depth_replay_2026-06-29.html"),
    )
    render(parser.parse_args())


if __name__ == "__main__":
    main()
