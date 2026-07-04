#!/usr/bin/env python3
"""Plot cumulative profit curves with a real issue-close time axis."""
from __future__ import annotations

import argparse
import csv
import html
import math
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import write_csv

POLICIES = [
    (
        "fixed::current__512main",
        "Current 512 main",
        "#4b5563",
    ),
    (
        "fixed::rot_draw20_tail__512main",
        "High EV 512",
        "#dc2626",
    ),
    (
        "fixed::rot_draw20_tail__384main_128op05",
        "Default 384+128 N5",
        "#2563eb",
    ),
    (
        "fixed::rot_draw20_tail__384main_64op05_64n5x90",
        "Split N5 384+64+64",
        "#059669",
    ),
    (
        "played::draw_tail_to_full::w13::dd3::ls4",
        "Dynamic draw->full w13",
        "#7c3aed",
    ),
    (
        "played::split_base_to_full::w13::dd3::ls4",
        "Dynamic split->full w13",
        "#f59e0b",
    ),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fnum(value: object) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return out if math.isfinite(out) else 0.0


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.strip())


def nice_step(span: float, target_ticks: int = 8) -> float:
    if span <= 0:
        return 1.0
    raw = span / max(1, target_ticks)
    power = 10 ** math.floor(math.log10(raw))
    for mult in (1, 2, 5, 10):
        step = mult * power
        if raw <= step:
            return step
    return 10 * power


def axis_ticks(min_value: float, max_value: float, target_ticks: int = 8) -> list[float]:
    step = nice_step(max_value - min_value, target_ticks)
    start = math.floor(min_value / step) * step
    end = math.ceil(max_value / step) * step
    vals = []
    cur = start
    while cur <= end + step * 0.5:
        vals.append(cur)
        cur += step
    return vals


def money_label(value: float) -> str:
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1000:
        return f"{sign}{value / 1000:.0f}k"
    return f"{sign}{value:.0f}"


def build_series(rows: list[dict[str, str]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    wanted = {policy for policy, _label, _color in POLICIES}
    for row in rows:
        policy = str(row["policy"])
        if policy not in wanted:
            continue
        grouped.setdefault(policy, []).append(row)

    series: dict[str, list[dict[str, object]]] = {}
    for policy, vals in grouped.items():
        vals.sort(key=lambda row: (row.get("issue_close_ts", ""), row["issue"]))
        equity = 0.0
        peak = 0.0
        out = []
        for row in vals:
            equity += fnum(row["profit_units"])
            peak = max(peak, equity)
            out.append(
                {
                    "policy": policy,
                    "issue": row["issue"],
                    "date": parse_dt(row["issue_close_ts"]),
                    "issue_close_ts": row["issue_close_ts"],
                    "profit_units": fnum(row["profit_units"]),
                    "equity_units": equity,
                    "drawdown_units": equity - peak,
                    "chosen_arm": row.get("chosen_arm", ""),
                    "state": row.get("state", ""),
                }
            )
        series[policy] = out
    missing = wanted - set(series)
    if missing:
        raise SystemExit(f"missing policies: {sorted(missing)}")
    return series


def polyline(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)


def line_points(
    rows: list[dict[str, object]],
    *,
    x_scale,
    y_scale,
    value_key: str,
) -> list[tuple[float, float]]:
    return [(x_scale(row["date"]), y_scale(fnum(row[value_key]))) for row in rows]


def year_ticks(start: datetime, end: datetime) -> list[datetime]:
    years = range(start.year, end.year + 2)
    return [datetime(year, 1, 1) for year in years if start <= datetime(year, 1, 1) <= end]


def render_svg(series: dict[str, list[dict[str, object]]], output: Path) -> None:
    width = 1500
    height = 900
    left = 90
    right = 270
    top = 82
    panel_gap = 82
    bottom = 70
    chart_w = width - left - right
    profit_h = 430
    dd_top = top + profit_h + panel_gap
    dd_h = height - dd_top - bottom

    all_rows = [row for rows in series.values() for row in rows]
    min_date = min(row["date"] for row in all_rows)
    max_date = max(row["date"] for row in all_rows)
    min_ord = min_date.timestamp()
    max_ord = max_date.timestamp()

    max_equity = max(fnum(row["equity_units"]) for row in all_rows)
    min_equity = min(0.0, min(fnum(row["equity_units"]) for row in all_rows))
    equity_ticks = axis_ticks(min_equity, max_equity, 8)
    equity_min = min(equity_ticks)
    equity_max = max(equity_ticks)

    min_dd = min(fnum(row["drawdown_units"]) for row in all_rows)
    dd_ticks = axis_ticks(min_dd, 0.0, 5)
    dd_min = min(dd_ticks)
    dd_max = 0.0

    def x_scale(dt: datetime) -> float:
        if max_ord == min_ord:
            return left
        return left + (dt.timestamp() - min_ord) / (max_ord - min_ord) * chart_w

    def y_profit(value: float) -> float:
        return top + (equity_max - value) / (equity_max - equity_min) * profit_h

    def y_dd(value: float) -> float:
        return dd_top + (dd_max - value) / (dd_max - dd_min) * dd_h

    parts: list[str] = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append("<style>")
    parts.append(
        "text{font-family:Arial,'Noto Sans',sans-serif;fill:#111827}"
        ".axis{stroke:#9ca3af;stroke-width:1}.grid{stroke:#e5e7eb;stroke-width:1}"
        ".label{font-size:13px;fill:#374151}.small{font-size:12px;fill:#6b7280}"
        ".title{font-size:24px;font-weight:700}.subtitle{font-size:13px;fill:#4b5563}"
    )
    parts.append("</style>")
    parts.append('<rect x="0" y="0" width="1500" height="900" fill="#ffffff"/>')
    parts.append('<text x="90" y="36" class="title">N7/N5 Dynamic Sleeve Equity Curves</text>')
    parts.append(
        '<text x="90" y="60" class="subtitle">Time axis uses issue close time: MAX(kickoff_ts) per issue, not numeric issue id.</text>'
    )

    for tick in equity_ticks:
        y = y_profit(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" class="small">{money_label(tick)}</text>')
    for tick in dd_ticks:
        y = y_dd(tick)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 4:.1f}" text-anchor="end" class="small">{money_label(tick)}</text>')

    for tick in year_ticks(min_date, max_date):
        x = x_scale(tick)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + profit_h}" class="grid"/>')
        parts.append(f'<line x1="{x:.1f}" y1="{dd_top}" x2="{x:.1f}" y2="{dd_top + dd_h}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{height - 30}" text-anchor="middle" class="small">{tick.year}</text>')

    parts.append(f'<line x1="{left}" y1="{top + profit_h}" x2="{left + chart_w}" y2="{top + profit_h}" class="axis"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + profit_h}" class="axis"/>')
    parts.append(f'<line x1="{left}" y1="{dd_top + dd_h}" x2="{left + chart_w}" y2="{dd_top + dd_h}" class="axis"/>')
    parts.append(f'<line x1="{left}" y1="{dd_top}" x2="{left}" y2="{dd_top + dd_h}" class="axis"/>')
    parts.append(f'<text x="{left}" y="{top - 20}" class="label">Cumulative profit, units</text>')
    parts.append(f'<text x="{left}" y="{dd_top - 20}" class="label">Drawdown, units</text>')

    legend_x = left + chart_w + 28
    legend_y = top + 12
    for idx, (policy, label, color) in enumerate(POLICIES):
        rows = series[policy]
        pts = line_points(rows, x_scale=x_scale, y_scale=y_profit, value_key="equity_units")
        dd_pts = line_points(rows, x_scale=x_scale, y_scale=y_dd, value_key="drawdown_units")
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.4" points="{polyline(pts)}"/>'
        )
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="1.6" stroke-opacity="0.85" points="{polyline(dd_pts)}"/>'
        )
        final = rows[-1]
        x_last = x_scale(final["date"])
        y_last = y_profit(fnum(final["equity_units"]))
        parts.append(f'<circle cx="{x_last:.1f}" cy="{y_last:.1f}" r="3.2" fill="{color}"/>')

        y = legend_y + idx * 56
        parts.append(f'<line x1="{legend_x}" y1="{y}" x2="{legend_x + 26}" y2="{y}" stroke="{color}" stroke-width="3"/>')
        parts.append(f'<text x="{legend_x + 34}" y="{y + 4}" class="label">{html.escape(label)}</text>')
        parts.append(
            f'<text x="{legend_x + 34}" y="{y + 22}" class="small">profit {money_label(fnum(final["equity_units"]))}, maxDD {money_label(min(fnum(row["drawdown_units"]) for row in rows))}</text>'
        )

    parts.append(
        f'<text x="{left}" y="{height - 10}" class="small">Range: {min_date.date()} to {max_date.date()}; 512 units per issue.</text>'
    )
    parts.append("</svg>")
    output.write_text("\n".join(parts), encoding="utf-8")


def write_curve_csv(series: dict[str, list[dict[str, object]]], output: Path) -> None:
    rows = []
    for policy, label, _color in POLICIES:
        for row in series[policy]:
            rows.append(
                {
                    "policy": policy,
                    "label": label,
                    "issue": row["issue"],
                    "issue_close_ts": row["issue_close_ts"],
                    "profit_units": row["profit_units"],
                    "equity_units": row["equity_units"],
                    "drawdown_units": row["drawdown_units"],
                    "chosen_arm": row["chosen_arm"],
                    "state": row["state"],
                }
            )
    write_csv(output, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-profit",
        type=Path,
        default=Path("results/n7_dynamic_sleeve_allocator_20260628_timefix/dynamic_sleeve_issue_profit.csv"),
    )
    parser.add_argument(
        "--output-svg",
        type=Path,
        default=Path("docs/research/figures/n7_dynamic_sleeve_equity_timefix_2026-06-28.svg"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("docs/research/figures/n7_dynamic_sleeve_equity_timefix_2026-06-28.csv"),
    )
    args = parser.parse_args()
    series = build_series(read_csv(args.issue_profit))
    args.output_svg.parent.mkdir(parents=True, exist_ok=True)
    render_svg(series, args.output_svg)
    write_curve_csv(series, args.output_csv)
    print(f"Wrote {args.output_svg}")
    print(f"Wrote {args.output_csv}")


if __name__ == "__main__":
    main()
