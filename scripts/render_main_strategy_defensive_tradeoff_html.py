#!/usr/bin/env python3
"""Render defensive ROI-vs-drawdown trade-off HTML for the Beidan main strategy."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.render_main_strategy_leg_ev_depth_html as base


FOCUSED = [
    "current_reference_256",
    "baseline_384_hybrid",
    "defensive_smooth85_convex15",
    "defensive_smooth90_convex10",
    "defensive_smooth95_convex05",
    "defensive_smooth100",
    "lossstreak_smooth80_midconvex20",
]

COLORS = {
    "current_reference_256": "#4c78a8",
    "baseline_384_hybrid": "#2f855a",
    "defensive_smooth85_convex15": "#f58518",
    "defensive_smooth90_convex10": "#e45756",
    "defensive_smooth95_convex05": "#72b7b2",
    "defensive_smooth100": "#7f7f7f",
    "lossstreak_smooth80_midconvex20": "#b279a2",
}


def signed(value: float, digits: int = 0) -> str:
    return f"{value:+,.{digits}f}"


def pct_delta(value: float, digits: int = 1) -> str:
    return f"{value:+.{digits}f}pp"


def normalized_issue_rows(issue_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in issue_rows:
        copied = dict(row)
        scale = base.fnum(row.get("stake_units")) / 256.0
        if scale > 0:
            copied["profit_units"] = str(base.fnum(row.get("profit_units")) / scale)
            copied["stake_units"] = "256"
        out.append(copied)
    return out


def render(args: argparse.Namespace) -> None:
    base.FOCUSED = FOCUSED
    base.COLORS = COLORS
    result_dir = args.result_dir
    summary_all = base.read_rows(result_dir / "defensive_summary.csv")
    issue_rows = base.read_rows(result_dir / "defensive_issue_profit.csv")
    annual = base.read_rows(result_dir / "defensive_annual.csv")
    summary_map = {r["portfolio"]: r for r in summary_all}

    summary = [summary_map[p] for p in FOCUSED if p in summary_map]
    promoted = summary_map["baseline_384_hybrid"]

    metric_rows = []
    for row in summary:
        maxdd_delta = base.fnum(row["max_drawdown_units"]) - base.fnum(promoted["max_drawdown_units"])
        max_loss_delta = base.fnum(row["max_loss_streak"]) - base.fnum(promoted["max_loss_streak"])
        issue_win_delta = (base.fnum(row["issue_win_rate"]) - base.fnum(promoted["issue_win_rate"])) * 100
        full_loss_delta = (base.fnum(row["full_loss_rate"]) - base.fnum(promoted["full_loss_rate"])) * 100
        roi_delta = base.fnum(row["roi"]) - base.fnum(promoted["roi"])
        metric_rows.append(
            {
                "portfolio": row["portfolio"],
                "issue_budget": row["issue_budget"],
                "profit_units": row["profit_units"],
                "profit_per_256": row["profit_per_256"],
                "roi": row["roi"],
                "roi_delta": signed(roi_delta, 3),
                "issue_win_rate": row["issue_win_rate"],
                "issue_win_delta": pct_delta(issue_win_delta),
                "full_loss_rate": row["full_loss_rate"],
                "full_loss_delta": pct_delta(full_loss_delta),
                "max_drawdown_units": row["max_drawdown_units"],
                "maxdd_delta": signed(maxdd_delta, 0),
                "max_drawdown_per_256": row["max_drawdown_per_256"],
                "max_loss_streak": row["max_loss_streak"],
                "max_loss_delta": signed(max_loss_delta, 0),
                "max_dead_streak": row["max_dead_streak"],
                "roi_ex_best_issue": row["roi_ex_best_issue"],
                "recent_profit_per_256": row["recent_profit_per_256"],
                "recent_roi": row["recent_roi"],
                "allocation": row.get("allocation", ""),
            }
        )

    recent_rows = [
        r
        for r in annual
        if r.get("portfolio") in FOCUSED and int(base.fnum(r.get("year"))) >= 2023
    ]
    recent_rows.sort(key=lambda r: (FOCUSED.index(r["portfolio"]), int(base.fnum(r["year"]))))
    eq, dd = base.build_series([r for r in issue_rows if r.get("portfolio") in FOCUSED])
    eq_norm, _dd_norm = base.build_series(normalized_issue_rows([r for r in issue_rows if r.get("portfolio") in FOCUSED]))
    equity_svg = base.line_svg(eq, title="资金曲线：防守候选累计 total profit", y_label="cumulative total profit")
    equity_norm_svg = base.line_svg(eq_norm, title="资金曲线：累计 profit/256 归一化", y_label="cumulative profit/256")
    dd_svg = base.line_svg(dd, title="回撤曲线：防守候选 equity - running peak", y_label="drawdown")
    annual_svg = base.annual_profit_svg([r for r in annual if r.get("portfolio") in FOCUSED])

    anti_rows = []
    leg_summary = Path("results/main_strategy_leg_ev_depth_20260629/portfolio_summary.csv")
    if leg_summary.exists():
        leg_rows = {r["portfolio"]: r for r in base.read_rows(leg_summary)}
        for p in ["b384_ev_depth_v1", "b384_confidence_depth_v1", "b384_q_payout_depth_v1", "b384_hybrid_depth_v1"]:
            if p not in leg_rows:
                continue
            r = leg_rows[p]
            anti_rows.append(
                {
                    "portfolio": p,
                    "profit_units": r["profit_units"],
                    "roi": r["roi"],
                    "issue_win_rate": r["issue_win_rate"],
                    "non_full_loss_rate": r["non_full_loss_rate"],
                    "max_drawdown_units": r["max_drawdown_units"],
                    "max_dead_streak": r["max_dead_streak"],
                }
            )

    html_text = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>北单主策略防守取舍报告</title>
<style>
:root {{
  --bg: #f7f7f4; --fg: #171717; --muted: #666; --border: #d7d2c8;
  --panel: #fff; --head: #eef2ef; --accent: #2f855a;
  --warn-bg: #fff7e6; --warn: #8a5a00; --bad-bg: #faeeee; --bad: #9b2c2c;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
    "Hiragino Sans GB", "Microsoft YaHei", Arial, sans-serif;
  line-height: 1.65;
}}
main {{ max-width: 1240px; margin: 0 auto; padding: 28px 28px 72px; }}
h1 {{ font-size: 30px; margin: 0 0 8px; }}
h2 {{ font-size: 21px; margin: 34px 0 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }}
.meta {{ color: var(--muted); font-size: 14px; }}
.callout {{ background: var(--warn-bg); border-left: 4px solid var(--warn); padding: 12px 16px; margin: 18px 0; border-radius: 0 6px 6px 0; }}
.badcallout {{ background: var(--bad-bg); border-left-color: var(--bad); }}
.chart-wrap {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px; overflow-x: auto; margin: 14px 0; }}
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
</style>
</head>
<body>
<main>
<h1>北单主策略防守取舍报告</h1>
<p class="meta">生成日期：2026-06-29。目标函数：允许 ROI 下降，优先改善 loss、full-loss、loss streak 与 maxDD。</p>

<div class="callout">
  <b>修正后的结论：</b><code>baseline_384_hybrid</code> 仍然是很好的均衡备选；
  如果当前目标是“适当降低 ROI 换更好的 loss/回撤体感”，
  更合理的优化方向是 <code>defensive_smooth90_convex10</code>。
  它相对 baseline 把 ROI 从 1.409 降到 1.191，但 maxDD 从 -15077 改到 -13882，
  max loss streak 从 30 降到 19，issue win 从 17.8% 升到 18.8%，full-loss 基本不变。
</div>

<h2>防守候选关键指标</h2>
<p class="meta"><code>total profit</code> 是按该策略实际每期预算累计的绝对利润；
<code>profit/256</code> 是把 320/384/512 等不同预算统一归一到每 256 单位后的利润。前后报告若数字不同，通常就是这两个口径不同。</p>
{base.table_html(metric_rows, [
    ("portfolio", "portfolio", "text"),
    ("issue_budget", "budget", "num"),
    ("profit_units", "total profit", "num"),
    ("profit_per_256", "profit/256", "num"),
    ("roi", "ROI", "roi"),
    ("roi_delta", "ROI Δ vs promoted", "text"),
    ("issue_win_rate", "issue win", "pct"),
    ("issue_win_delta", "issue win Δ", "text"),
    ("full_loss_rate", "full-loss", "pct"),
    ("full_loss_delta", "full-loss Δ", "text"),
    ("max_drawdown_units", "maxDD", "num"),
    ("maxdd_delta", "maxDD Δ", "text"),
    ("max_drawdown_per_256", "maxDD/256", "num"),
    ("max_loss_streak", "loss streak", "num"),
    ("max_loss_delta", "loss streak Δ", "text"),
    ("max_dead_streak", "dead streak", "num"),
    ("roi_ex_best_issue", "ex-best ROI", "roi"),
    ("recent_profit_per_256", "2023-2025 profit/256", "num"),
    ("recent_roi", "2023-2025 ROI", "roi"),
])}

<h2>资金曲线与回撤曲线</h2>
<div class="chart-wrap">{equity_svg}</div>
<div class="chart-wrap">{equity_norm_svg}</div>
<div class="chart-wrap">{dd_svg}</div>
<div class="chart-wrap">{annual_svg}</div>

<h2>2023-2025 年度表现</h2>
<p class="meta">2025 当前只有 15 期，不应与全年数据等量解读。</p>
{base.table_html(recent_rows, [
    ("portfolio", "portfolio", "text"),
    ("year", "year", "text"),
    ("n_issues", "n", "num"),
    ("profit_units", "profit", "num"),
    ("roi", "ROI", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("max_drawdown_units", "maxDD", "num"),
])}

<h2>反例：v1 动态 depth 走偏在哪里</h2>
<div class="callout badcallout">
  v1 动态 depth arms 的问题不是利润，而是风险目标错了：它们倾向于挑更凸的 extra sleeve，
  导致 issue win、non-full-loss 和 maxDD 明显劣化。这正是你指出的“走反方向”。
</div>
{base.table_html(anti_rows, [
    ("portfolio", "portfolio", "text"),
    ("profit_units", "profit", "num"),
    ("roi", "ROI", "roi"),
    ("issue_win_rate", "issue win", "pct"),
    ("non_full_loss_rate", "non-full-loss", "pct"),
    ("max_drawdown_units", "maxDD", "num"),
    ("max_dead_streak", "dead streak", "num"),
])}

<h2>建议</h2>
<p>短期把报告和前端默认候选改为四档：</p>
<ul>
  <li><code>baseline_384_hybrid</code>：收益/风险均衡主备选，保留高凸性。</li>
  <li><code>defensive_smooth90_convex10</code>：当前最推荐的“适当降 ROI 换回撤/loss 改善”优化版。</li>
  <li><code>defensive_smooth100</code>：更强防守版，ROI 损失更大。</li>
  <li><code>lossstreak_smooth80_midconvex20</code>：只想压 loss streak、但不明显改善 maxDD 时的对照。</li>
</ul>
<p>下一步的 selector 目标函数应该从“最大化 ROI/EV”改成多目标约束：</p>
<p><code>maximize expected profit subject to maxDD, full-loss rate, loss streak, miss_1/miss_2 not worse than baseline_384_hybrid</code></p>
</main>
</body>
</html>
"""
    args.output.write_text(html_text, encoding="utf-8")
    print(f"Wrote {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, default=Path("results/main_strategy_defensive_tradeoff_20260629"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/research/main_strategy_defensive_tradeoff_2026-06-29.html"),
    )
    render(parser.parse_args())


if __name__ == "__main__":
    main()
