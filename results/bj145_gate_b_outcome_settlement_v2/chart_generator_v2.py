#!/usr/bin/env python3
"""Render the complete #145 Gate-B v2 descriptive chart set as SVG."""

from __future__ import annotations

import argparse
import csv
import html
import statistics
from collections import defaultdict
from pathlib import Path


ARMS = ("PRIMARY_NO_GATE_K4", "SECONDARY_ESP300_GM290_K8")
M_GRID = tuple(range(16, 257, 16)) + (512, 1024, 1458, 2187)
COLORS = (
    "#2563eb",
    "#dc2626",
    "#059669",
    "#d97706",
    "#7c3aed",
    "#0891b2",
    "#be123c",
    "#4b5563",
    "#65a30d",
)


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[
        min(len(ordered) - 1, max(0, round((len(ordered) - 1) * probability)))
    ]


def svg_header(
    title: str, subtitle: str, width: int = 1180, height: int = 720
) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        "<style>text{font-family:Arial,sans-serif;fill:#111827}.grid{stroke:#e5e7eb;stroke-width:1}.axis{stroke:#374151;stroke-width:1}.line{fill:none;stroke-width:2}.band{fill-opacity:.16}.legend{font-size:11px}</style>",
        f'<text x="82" y="30" font-size="19" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="82" y="50" font-size="12">{html.escape(subtitle)}</text>',
    ]


def line_chart(
    title: str,
    subtitle: str,
    series: dict[tuple[str, str], dict[int, float]],
    output: Path,
    y_label: str,
    y_min: float | None = None,
    y_max: float | None = None,
) -> None:
    width, height, left, right, top, bottom, gap = 1180, 720, 82, 38, 80, 74, 54
    panel_h = (height - top - bottom - gap) / 2
    values = [value for data in series.values() for value in data.values()]
    low = min(values, default=-1.0) if y_min is None else y_min
    high = max(values, default=1.0) if y_max is None else y_max
    padding = max(0.05, (high - low) * 0.08)
    low, high = low - padding, high + padding
    plot_w = width - left - right

    def x(m: int) -> float:
        return left + M_GRID.index(m) / (len(M_GRID) - 1) * plot_w

    def y(value: float, panel: int) -> float:
        origin = top + panel * (panel_h + gap)
        return origin + (high - value) / (high - low) * panel_h

    bits = svg_header(title, subtitle, width, height)
    labels = sorted({label for _, label in series})
    color_map = {
        label: COLORS[index % len(COLORS)] for index, label in enumerate(labels)
    }
    for panel, arm in enumerate(ARMS):
        origin = top + panel * (panel_h + gap)
        bits.append(
            f'<text x="{left}" y="{origin - 10:.1f}" font-size="14" font-weight="bold">{html.escape(arm)}</text>'
        )
        for tick_index in range(5):
            value = low + (high - low) * tick_index / 4
            yy = y(value, panel)
            bits.append(
                f'<line class="grid" x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
            )
            bits.append(
                f'<text x="{left - 10}" y="{yy + 4:.1f}" text-anchor="end" font-size="10">{value:.2f}</text>'
            )
        zero = y(0, panel)
        if origin <= zero <= origin + panel_h:
            bits.append(
                f'<line x1="{left}" x2="{width - right}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="#111827" stroke-dasharray="4 4"/>'
            )
        bits.append(
            f'<line class="axis" x1="{left}" x2="{width - right}" y1="{origin + panel_h:.1f}" y2="{origin + panel_h:.1f}"/>'
        )
        for idx, m in enumerate(M_GRID):
            if idx % 2 == 0 or m in (512, 1024, 1458, 2187):
                bits.append(
                    f'<text x="{x(m):.1f}" y="{origin + panel_h + 18:.1f}" text-anchor="middle" font-size="9">{m}</text>'
                )
        for label in labels:
            data = series.get((arm, label), {})
            points = [
                f"{x(m):.1f},{y(data[m], panel):.1f}" for m in M_GRID if m in data
            ]
            if points:
                bits.append(
                    f'<polyline class="line" stroke="{color_map[label]}" points="{" ".join(points)}"/>'
                )
    cursor_x, cursor_y = left, height - 24
    for label in labels:
        if cursor_x > width - 180:
            cursor_x, cursor_y = left, cursor_y + 15
        bits.append(
            f'<line x1="{cursor_x}" x2="{cursor_x + 19}" y1="{cursor_y - 4}" y2="{cursor_y - 4}" stroke="{color_map[label]}" stroke-width="3"/>'
        )
        bits.append(
            f'<text class="legend" x="{cursor_x + 24}" y="{cursor_y}">{html.escape(label)}</text>'
        )
        cursor_x += max(120, 7 * len(label) + 45)
    bits.append(
        f'<text x="18" y="380" transform="rotate(-90 18 380)" font-size="12">{html.escape(y_label)}</text>'
    )
    bits.append("</svg>")
    output.write_text("\n".join(bits) + "\n", encoding="utf-8")


def uncertainty_chart(bootstrap: list[dict[str, str]], output: Path) -> None:
    grouped: defaultdict[tuple[str, int], list[tuple[float, float, float]]] = (
        defaultdict(list)
    )
    for row in bootstrap:
        if row["metric"] == "no_tax_roi_delta" and row["point_estimate"]:
            grouped[(row["arm_id"], int(row["M"]))].append(
                (
                    float(row["point_estimate"]),
                    float(row["ci95_low"]),
                    float(row["ci95_high"]),
                )
            )
    width, height, left, right, top, bottom, gap = 1180, 720, 82, 38, 80, 70, 54
    panel_h = (height - top - bottom - gap) / 2
    plot_w = width - left - right
    stats = {
        (arm, m): (
            statistics.median(v[0] for v in values),
            percentile([v[1] for v in values], 0.25),
            percentile([v[2] for v in values], 0.75),
        )
        for (arm, m), values in grouped.items()
    }
    all_values = [value for triple in stats.values() for value in triple]
    low, high = min(all_values, default=-1.0), max(all_values, default=1.0)
    padding = max(0.05, (high - low) * 0.08)
    low -= padding
    high += padding

    def x(m: int) -> float:
        return left + M_GRID.index(m) / (len(M_GRID) - 1) * plot_w

    def y(value: float, panel: int) -> float:
        origin = top + panel * (panel_h + gap)
        return origin + (high - value) / (high - low) * panel_h

    bits = svg_header(
        "#145 Gate-B bootstrap uncertainty and stability",
        "Median point estimate; shaded band is the cross-cell IQR of issue-bootstrap 95% bounds. Descriptive only.",
        width,
        height,
    )
    for panel, arm in enumerate(ARMS):
        origin = top + panel * (panel_h + gap)
        bits.append(
            f'<text x="{left}" y="{origin - 10:.1f}" font-size="14" font-weight="bold">{arm}</text>'
        )
        for tick_index in range(5):
            value = low + (high - low) * tick_index / 4
            yy = y(value, panel)
            bits.append(
                f'<line class="grid" x1="{left}" x2="{width - right}" y1="{yy:.1f}" y2="{yy:.1f}"/>'
            )
            bits.append(
                f'<text x="{left - 10}" y="{yy + 4:.1f}" text-anchor="end" font-size="10">{value:.2f}</text>'
            )
        zero = y(0, panel)
        bits.append(
            f'<line x1="{left}" x2="{width - right}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="#111827" stroke-dasharray="4 4"/>'
        )
        points = [(m, stats[(arm, m)]) for m in M_GRID if (arm, m) in stats]
        upper = " ".join(f"{x(m):.1f},{y(v[2], panel):.1f}" for m, v in points)
        lower = " ".join(
            f"{x(m):.1f},{y(v[1], panel):.1f}" for m, v in reversed(points)
        )
        bits.append(f'<polygon class="band" fill="#2563eb" points="{upper} {lower}"/>')
        bits.append(
            f'<polyline class="line" stroke="#1d4ed8" points="{" ".join(f"{x(m):.1f},{y(v[0], panel):.1f}" for m, v in points)}"/>'
        )
        for idx, m in enumerate(M_GRID):
            if idx % 2 == 0 or m in (512, 1024, 1458, 2187):
                bits.append(
                    f'<text x="{x(m):.1f}" y="{origin + panel_h + 18:.1f}" text-anchor="middle" font-size="9">{m}</text>'
                )
    bits.append(
        '<text x="18" y="380" transform="rotate(-90 18 380)" font-size="12">pre-tax ROI delta vs matched FULL</text>'
    )
    bits.append("</svg>")
    output.write_text("\n".join(bits) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    package = args.package.resolve()
    summary = rows(package / "mechanism_weight_surface_summary.csv")
    full = rows(package / "full_control_deltas.csv")
    bootstrap = rows(package / "issue_bootstrap.csv")
    roi_values: defaultdict[tuple[str, str, int], list[float]] = defaultdict(list)
    for row in summary:
        if row["scope"] != "ALL" or not row["no_tax_roi"]:
            continue
        label = (
            row["mechanism"]
            if row["mechanism"] != "CAPPED_REPEAT"
            else f"CAPPED cap={row['cap']}"
        )
        roi_values[(row["arm_id"], label, int(row["M"]))].append(
            float(row["no_tax_roi"])
        )
    roi_series = {
        (arm, label): {
            m: statistics.median(values)
            for (a, series_label, m), values in roi_values.items()
            if a == arm and series_label == label
        }
        for arm, label, _ in roi_values
    }
    line_chart(
        "#145 Gate-B pre-tax ROI by M and cap",
        "Median across frozen weight/seed cells; capped-repeat arms are separated by cap.",
        roi_series,
        package / "roi_vs_m_cap.svg",
        "pre-tax no_tax_roi",
    )
    delta_values: defaultdict[tuple[str, str, int], list[float]] = defaultdict(list)
    for row in full:
        if row["scope"] == "ALL" and row["no_tax_roi_delta"]:
            label = (
                row["mechanism"]
                if row["mechanism"] != "CAPPED_REPEAT"
                else f"CAPPED cap={row['cap']}"
            )
            delta_values[(row["arm_id"], label, int(row["M"]))].append(
                float(row["no_tax_roi_delta"])
            )
    delta_series = {
        (arm, label): {
            m: statistics.median(values)
            for (a, series_label, m), values in delta_values.items()
            if a == arm and series_label == label
        }
        for arm, label, _ in delta_values
    }
    line_chart(
        "#145 matched pre-tax comparison versus FULL",
        "Median candidate-minus-FULL ROI on identical arm/weight/scope support; zero means matched FULL parity.",
        delta_series,
        package / "matched_pre_tax_comparison.svg",
        "pre-tax ROI delta vs FULL",
    )
    uncertainty_chart(bootstrap, package / "uncertainty_stability.svg")
    print(
        "\n".join(
            str(package / name)
            for name in (
                "roi_vs_m_cap.svg",
                "matched_pre_tax_comparison.svg",
                "uncertainty_stability.svg",
            )
        )
    )


if __name__ == "__main__":
    main()
