#!/usr/bin/env python3
"""Create the non-promotional #145 Gate-B surface integration chart."""
from __future__ import annotations

import csv
import html
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = next(
    candidate for candidate in Path(__file__).resolve().parents
    if (candidate / "results").is_dir()
)
PACKAGE = ROOT / "results" / "bj145_gate_b_outcome_settlement_v1"
OUT = PACKAGE / "mechanism_surface_median.svg"
ARMS = ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8")
MECHANISMS = (
    ("WR_DUPLICATE_STAKE", "WR"),
    ("WOR_DISTINCT", "WOR"),
    ("RESIDUAL_SYSTEMATIC", "Residual"),
    ("CAPPED_REPEAT", "Capped"),
    ("DETERMINISTIC_TOP_MASS", "Top-mass"),
    ("FULL_ENUMERATED", "FULL"),
)
COLORS = ("#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed", "#111827")
M_GRID = tuple(range(16, 257, 16)) + (512, 1024, 1458, 2187)


def median_surface() -> dict[tuple[str, str, int], float]:
    values: defaultdict[tuple[str, str, int], list[float]] = defaultdict(list)
    with (PACKAGE / "mechanism_weight_surface_summary.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["scope"] != "ALL" or row["arm_id"] not in ARMS:
                continue
            values[(row["arm_id"], row["mechanism"], int(row["M"]))].append(float(row["no_tax_roi"]))
    return {key: statistics.median(items) for key, items in values.items()}


def chart() -> str:
    surface = median_surface()
    width, height = 1040, 660
    left, right, top, bottom = 78, 36, 74, 58
    panel_gap = 54
    panel_h = (height - top - bottom - panel_gap) / 2
    plot_w = width - left - right
    y_min, y_max = -1.0, 1.0

    def x(m: int) -> float:
        return left + (M_GRID.index(m) / (len(M_GRID) - 1)) * plot_w

    def y(value: float, panel: int) -> float:
        origin = top + panel * (panel_h + panel_gap)
        return origin + (y_max - max(y_min, min(y_max, value))) / (y_max - y_min) * panel_h

    bits = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,sans-serif;fill:#111827} .grid{stroke:#e5e7eb;stroke-width:1} .axis{stroke:#374151;stroke-width:1} .line{fill:none;stroke-width:2} .legend{font-size:12px}</style>',
        '<text x="78" y="28" font-size="18" font-weight="bold">#145 Gate-B descriptive surface: median pre-tax ROI</text>',
        '<text x="78" y="48" font-size="12">Median across frozen weight/cap/seed cells; no winner selection. Same-window historical settlement only.</text>',
    ]
    for panel, arm in enumerate(ARMS):
        origin = top + panel * (panel_h + panel_gap)
        bits.append(f'<text x="{left}" y="{origin - 12:.1f}" font-size="14" font-weight="bold">{html.escape(arm)}</text>')
        for tick in (-1.0, -0.5, 0.0, 0.5, 1.0):
            yy = y(tick, panel)
            bits.append(f'<line class="grid" x1="{left}" x2="{width-right}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
            bits.append(f'<text x="{left-10}" y="{yy+4:.1f}" text-anchor="end" font-size="11">{tick:.1f}</text>')
        bits.append(f'<line class="axis" x1="{left}" x2="{left}" y1="{origin:.1f}" y2="{origin+panel_h:.1f}"/>')
        bits.append(f'<line class="axis" x1="{left}" x2="{width-right}" y1="{origin+panel_h:.1f}" y2="{origin+panel_h:.1f}"/>')
        for idx, m in enumerate(M_GRID):
            xx = x(m)
            if idx % 2 == 0 or m in (512, 1024, 1458, 2187):
                bits.append(f'<text x="{xx:.1f}" y="{origin+panel_h+18:.1f}" text-anchor="middle" font-size="10">{m}</text>')
        for (mechanism, label), color in zip(MECHANISMS, COLORS):
            points = []
            for m in M_GRID:
                value = surface.get((arm, mechanism, m))
                if value is not None:
                    points.append(f'{x(m):.1f},{y(value, panel):.1f}')
            if points:
                bits.append(f'<polyline class="line" stroke="{color}" points="{" ".join(points)}"/>')
    legend_y = height - 14
    cursor = left
    for (mechanism, label), color in zip(MECHANISMS, COLORS):
        bits.append(f'<line x1="{cursor}" x2="{cursor+22}" y1="{legend_y-4}" y2="{legend_y-4}" stroke="{color}" stroke-width="3"/>')
        bits.append(f'<text class="legend" x="{cursor+28}" y="{legend_y}">{html.escape(label)}</text>')
        cursor += 136
    bits.append('<text x="18" y="370" transform="rotate(-90 18 370)" font-size="12">pre-tax no_tax_roi</text>')
    bits.append('</svg>')
    return "\n".join(bits) + "\n"


if __name__ == "__main__":
    OUT.write_text(chart(), encoding="utf-8")
    print(OUT)
