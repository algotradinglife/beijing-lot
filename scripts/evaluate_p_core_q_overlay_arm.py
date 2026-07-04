#!/usr/bin/env python3
"""Evaluate a probability-first core plus high-q overlay N7 arm.

This is a ticket-level validation on the already-generated high-N ticket pool.
It does not rebuild the underlying leg generator.  The goal is to test whether
using predicted ticket hit probability for the main sleeve, and q/EV only for a
smaller overlay sleeve, improves drawdown and hit experience versus the current
q-first 384 arms.
"""
from __future__ import annotations

import argparse
import csv
import html
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TICKET_PATH = ROOT / "results/high_n_selector_plus2026_linefill_20260630/high_n_selector_enriched_source_tickets.csv"
DEFAULT_BASELINE_PATH = ROOT / "results/n7_sleeve_mix_capital_plus2026_linefill_20260630/sleeve_mix_issue_profit.csv"
DEFAULT_DB = ROOT / "data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite"
DEFAULT_OUT = ROOT / "results/p_core_q_overlay_384_20260701"
DEFAULT_REPORT = ROOT / "docs/research/p_core_q_overlay_384_2026-07-01.md"
DEFAULT_FIGURE = ROOT / "docs/research/figures/p_core_q_overlay_384_2026-07-01.svg"

SOURCE_STRATEGIES = (
    "ev_m0p95_p0p8_full_opt__budget256_fractional",
    "ev_m0p95_p0p85_full_opt__budget256_fractional",
)
BASELINE_PORTFOLIOS = ("b384_dd32_smooth100", "b384_dd32_smooth80_convex19", "current_reference_256")
ISSUE_BUDGET = 384.0
RECENT_MIN_YEAR = 2023
RECENT_MAX_YEAR = 2025


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


def load_issue_calendar(db_path: Path) -> dict[str, dict[str, object]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT
            issue,
            MIN(kickoff_ts) AS issue_start_ts,
            MAX(kickoff_ts) AS issue_close_ts,
            MAX(season_year) AS season_year
        FROM action_candidates
        WHERE has_winning_sp = 1
          AND kickoff_ts IS NOT NULL
        GROUP BY issue
        ORDER BY issue_close_ts, issue
        """
    ).fetchall()
    conn.close()
    return {
        str(row["issue"]): {
            "issue_start_ts": str(row["issue_start_ts"] or ""),
            "issue_close_ts": str(row["issue_close_ts"] or ""),
            "issue_order": idx,
            "calendar_year": int(str(row["issue_close_ts"])[:4]) if row["issue_close_ts"] else issue_year(row["issue"]),
            "season_year": int(row["season_year"]) if row["season_year"] is not None else issue_year(row["issue"]),
        }
        for idx, row in enumerate(rows)
    }


def row_year(row: dict[str, object]) -> int:
    if row.get("calendar_year") not in ("", None):
        return int(float(str(row["calendar_year"])))
    close_ts = str(row.get("issue_close_ts", ""))
    if len(close_ts) >= 4 and close_ts[:4].isdigit():
        return int(close_ts[:4])
    return issue_year(row.get("issue", ""))


def row_order(row: dict[str, object]) -> tuple[int, str]:
    if row.get("issue_order") not in ("", None):
        return int(float(str(row["issue_order"]))), str(row.get("issue", ""))
    return 10**9 + issue_year(row.get("issue", "")), str(row.get("issue", ""))


def read_csv_rows(path: Path) -> Iterable[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_tickets(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, list[dict[str, object]]]]:
    out: dict[str, dict[str, list[dict[str, object]]]] = {source: defaultdict(list) for source in SOURCE_STRATEGIES}
    for row in read_csv_rows(path):
        source = str(row.get("strategy", ""))
        if source not in out:
            continue
        copied: dict[str, object] = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[source][str(row["issue"])].append(copied)
    return {source: dict(by_issue) for source, by_issue in out.items()}


def load_baseline_issue_rows(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    out: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in read_csv_rows(path):
        portfolio = str(row.get("portfolio", ""))
        if portfolio not in BASELINE_PORTFOLIOS:
            continue
        copied: dict[str, object] = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[portfolio].append(copied)
    return dict(out)


def scale_ticket_rows(rows: list[dict[str, object]], units: float) -> tuple[float, float, float]:
    raw_stake = sum(fnum(row.get("stake_units")) for row in rows)
    if raw_stake <= 0 or units <= 0:
        return 0.0, 0.0, 0.0
    scale = units / raw_stake
    profit = sum(fnum(row.get("profit_units")) * scale for row in rows)
    hits = sum(fnum(row.get("hit")) for row in rows)
    return units, profit, hits


def ticket_key(row: dict[str, object]) -> str:
    return str(row.get("ticket_idx") or row.get("legs") or id(row))


def select_rows(
    rows: list[dict[str, object]],
    *,
    core_k: int,
    overlay_k: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    core = sorted(
        rows,
        key=lambda row: (
            fnum(row.get("pred_hit_prob")),
            fnum(row.get("avg_conf_weight")),
            fnum(row.get("pred_ev_per_stake")),
            fnum(row.get("avg_q_score")),
        ),
        reverse=True,
    )[:core_k]
    used = {ticket_key(row) for row in core}
    overlay_pool = [row for row in rows if ticket_key(row) not in used]
    overlay = sorted(
        overlay_pool,
        key=lambda row: (
            fnum(row.get("pred_ev_per_stake")),
            fnum(row.get("avg_q_score")),
            fnum(row.get("pred_hit_prob")),
        ),
        reverse=True,
    )[:overlay_k]
    return core, overlay


def replay_variant(
    *,
    name: str,
    source: str,
    by_issue: dict[str, list[dict[str, object]]],
    calendar: dict[str, dict[str, object]],
    core_weight: float,
    core_k: int,
    overlay_k: int,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    core_units = ISSUE_BUDGET * core_weight
    overlay_units = ISSUE_BUDGET - core_units
    for issue in sorted(by_issue, key=lambda item: int(calendar.get(item, {}).get("issue_order", 10**9))):
        tickets = by_issue[issue]
        core, overlay = select_rows(tickets, core_k=core_k, overlay_k=overlay_k)
        if not core:
            continue
        # If overlay is unavailable, do not leave cash idle in this test; move it to core.
        effective_core_units = core_units + (overlay_units if not overlay else 0.0)
        effective_overlay_units = overlay_units if overlay else 0.0
        core_stake, core_profit, core_hits = scale_ticket_rows(core, effective_core_units)
        overlay_stake, overlay_profit, overlay_hits = scale_ticket_rows(overlay, effective_overlay_units)
        stake = core_stake + overlay_stake
        profit = core_profit + overlay_profit
        selected = core + overlay
        avg_hit = sum(fnum(row.get("pred_hit_prob")) for row in selected) / len(selected)
        avg_ev = sum(fnum(row.get("pred_ev_per_stake")) for row in selected) / len(selected)
        avg_q = sum(fnum(row.get("avg_q_score")) for row in selected) / len(selected)
        avg_conf = sum(fnum(row.get("avg_conf_weight")) for row in selected) / len(selected)
        out = {
            "portfolio": name,
            "source_strategy": source,
            "issue": issue,
            "stake_units": stake,
            "profit_units": profit,
            "roi": profit / stake if stake else math.nan,
            "tickets": len(selected),
            "hits": core_hits + overlay_hits,
            "core_tickets": len(core),
            "overlay_tickets": len(overlay),
            "core_units": effective_core_units,
            "overlay_units": effective_overlay_units,
            "core_weight": core_weight,
            "core_k": core_k,
            "overlay_k": overlay_k,
            "avg_pred_hit_prob": avg_hit,
            "avg_pred_ev_per_stake": avg_ev,
            "avg_q_score": avg_q,
            "avg_conf_weight": avg_conf,
            "parts": f"p_core_top{core_k}:{effective_core_units:g};q_overlay_top{overlay_k}:{effective_overlay_units:g}",
        }
        out.update(calendar.get(issue, {}))
        rows.append(out)
    return rows


def full_loss(row: dict[str, object]) -> bool:
    return fnum(row.get("profit_units")) <= -0.999 * fnum(row.get("stake_units"))


def max_drawdown(rows: list[dict[str, object]]) -> tuple[float, str, str, int]:
    equity = 0.0
    peak = 0.0
    peak_issue = ""
    max_dd = 0.0
    start_issue = ""
    end_issue = ""
    start_idx = 0
    end_idx = 0
    for idx, row in enumerate(sorted(rows, key=row_order)):
        equity += fnum(row.get("profit_units"))
        if equity > peak:
            peak = equity
            peak_issue = str(row.get("issue", ""))
            start_idx = idx
        dd = equity - peak
        if dd < max_dd:
            max_dd = dd
            start_issue = peak_issue
            end_issue = str(row.get("issue", ""))
            end_idx = idx
    return max_dd, start_issue, end_issue, max(0, end_idx - start_idx + 1)


def max_loss_streak(rows: list[dict[str, object]]) -> int:
    streak = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if fnum(row.get("profit_units")) < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def max_dead_streak(rows: list[dict[str, object]]) -> int:
    streak = 0
    best = 0
    for row in sorted(rows, key=row_order):
        if full_loss(row):
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def summarize(rows: list[dict[str, object]], portfolio: str) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    recent = [row for row in ordered if RECENT_MIN_YEAR <= row_year(row) <= RECENT_MAX_YEAR]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    maxdd, dd_start, dd_end, dd_issues = max_drawdown(ordered)
    budget = fnum(ordered[0].get("stake_units"), ISSUE_BUDGET) if ordered else ISSUE_BUDGET
    return {
        "portfolio": portfolio,
        "source_strategy": str(ordered[0].get("source_strategy", "")) if ordered else "",
        "issues": len(ordered),
        "issue_budget": budget,
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (budget / 256.0) if budget else math.nan,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered),
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered),
        "full_loss_rate": sum(1 for row in ordered if full_loss(row)) / len(ordered),
        "max_drawdown_units": maxdd,
        "max_drawdown_per_256": maxdd / (budget / 256.0) if budget else math.nan,
        "max_drawdown_budget_equiv": abs(maxdd) / budget if budget else math.nan,
        "maxdd_window_start_issue": dd_start,
        "maxdd_window_end_issue": dd_end,
        "maxdd_window_issues": dd_issues,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / (stake - budget) if stake > budget else math.nan,
        "recent_profit_units": recent_profit,
        "recent_profit_per_256": recent_profit / (budget / 256.0) if budget else math.nan,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in ordered) / len(ordered),
        "avg_pred_hit_prob": sum(fnum(row.get("avg_pred_hit_prob")) for row in ordered) / len(ordered),
        "avg_pred_ev_per_stake": sum(fnum(row.get("avg_pred_ev_per_stake")) for row in ordered) / len(ordered),
        "avg_q_score": sum(fnum(row.get("avg_q_score")) for row in ordered) / len(ordered),
        "avg_conf_weight": sum(fnum(row.get("avg_conf_weight")) for row in ordered) / len(ordered),
        "parts": str(ordered[0].get("parts", "")) if ordered else "",
    }


def annual_rows(rows_by_portfolio: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for portfolio, rows in rows_by_portfolio.items():
        grouped: dict[int, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            grouped[row_year(row)].append(row)
        for year, vals in sorted(grouped.items()):
            stake = sum(fnum(row.get("stake_units")) for row in vals)
            profit = sum(fnum(row.get("profit_units")) for row in vals)
            maxdd, _, _, _ = max_drawdown(vals)
            out.append({
                "portfolio": portfolio,
                "year": year,
                "issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi": profit / stake if stake else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals),
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals),
                "max_drawdown_units": maxdd,
            })
    return out


def md_table(rows: list[dict[str, object]], cols: list[str], limit: int = 20) -> str:
    clipped = rows[:limit]
    if not clipped:
        return "_none_"
    lines = ["|" + "|".join(cols) + "|", "|" + "|".join(["---"] * len(cols)) + "|"]
    for row in clipped:
        vals = []
        for col in cols:
            value = row.get(col, "")
            if isinstance(value, float):
                if math.isnan(value):
                    text = ""
                elif "rate" in col or col == "roi" or col.endswith("_roi"):
                    text = f"{value:.3f}"
                else:
                    text = f"{value:,.1f}"
            else:
                text = str(value)
            vals.append(text)
        lines.append("|" + "|".join(vals) + "|")
    return "\n".join(lines)


def write_equity_svg(path: Path, series: dict[str, list[dict[str, object]]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1160, 620
    left, right, top, bottom = 72, 28, 44, 58
    curves: dict[str, list[tuple[int, float]]] = {}
    min_y = 0.0
    max_y = 0.0
    max_x = 0
    for name, rows in series.items():
        equity = 0.0
        pts = [(0, 0.0)]
        for idx, row in enumerate(sorted(rows, key=row_order), start=1):
            equity += fnum(row.get("profit_units"))
            pts.append((idx, equity))
            min_y = min(min_y, equity)
            max_y = max(max_y, equity)
            max_x = max(max_x, idx)
        curves[name] = pts
    if max_y <= min_y:
        max_y = min_y + 1.0
    plot_w = width - left - right
    plot_h = height - top - bottom

    def sx(x: int) -> float:
        return left + (x / max(max_x, 1)) * plot_w

    def sy(y: float) -> float:
        return top + (max_y - y) / (max_y - min_y) * plot_h

    colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2"]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Arial,sans-serif;font-size:12px;fill:#334155}.title{font-size:18px;font-weight:700}.axis{stroke:#94a3b8;stroke-width:1}.grid{stroke:#e2e8f0;stroke-width:1}.legend{font-size:12px}</style>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{left}" y="26" class="title">p-core / q-overlay 384 equity</text>',
    ]
    for i in range(6):
        y = min_y + (max_y - min_y) * i / 5
        py = sy(y)
        parts.append(f'<line x1="{left}" y1="{py:.2f}" x2="{width-right}" y2="{py:.2f}" class="grid"/>')
        parts.append(f'<text x="8" y="{py+4:.2f}">{y:,.0f}</text>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{height-bottom}" class="axis"/>')
    parts.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" class="axis"/>')
    for idx, (name, pts) in enumerate(curves.items()):
        color = colors[idx % len(colors)]
        point_text = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in pts)
        parts.append(f'<polyline points="{point_text}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
        ly = 52 + idx * 18
        parts.append(f'<line x1="{width-360}" y1="{ly-4}" x2="{width-336}" y2="{ly-4}" stroke="{color}" stroke-width="2.6"/>')
        parts.append(f'<text x="{width-328}" y="{ly}" class="legend">{html.escape(name)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    tickets = load_tickets(args.ticket_path, calendar)
    baselines = load_baseline_issue_rows(args.baseline_path, calendar)

    rows_by_portfolio: dict[str, list[dict[str, object]]] = {name: rows for name, rows in baselines.items()}
    variants: list[dict[str, object]] = []
    all_issue_rows: list[dict[str, object]] = []
    for source, by_issue in tickets.items():
        source_short = "p08" if "p0p8_" in source else "p085"
        for core_weight in (0.70, 0.80, 0.90, 1.0):
            for core_k in (4, 6, 8, 12):
                overlay_values = (0,) if core_weight >= 0.999 else (2, 4, 6)
                for overlay_k in overlay_values:
                    name = f"p_core_q_overlay_384_{source_short}_w{int(core_weight*100)}_c{core_k}_o{overlay_k}"
                    rows = replay_variant(
                        name=name,
                        source=source,
                        by_issue=by_issue,
                        calendar=calendar,
                        core_weight=core_weight,
                        core_k=core_k,
                        overlay_k=overlay_k,
                    )
                    rows_by_portfolio[name] = rows
                    all_issue_rows.extend(rows)
                    summary = summarize(rows, name)
                    variants.append(summary)

    baseline_summaries = [summarize(rows, name) for name, rows in baselines.items()]
    summaries = baseline_summaries + variants
    for row in summaries:
        row["utility_drawdown_first"] = (
            2.0 * fnum(row.get("max_drawdown_units"))
            + 0.10 * fnum(row.get("profit_units"))
            + 65000.0 * fnum(row.get("non_full_loss_rate"))
            + 35000.0 * fnum(row.get("issue_win_rate"))
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "p_core_q_overlay_issue_profit.csv", all_issue_rows)
    write_csv(args.output_dir / "p_core_q_overlay_summary.csv", sorted(summaries, key=lambda r: fnum(r.get("utility_drawdown_first")), reverse=True))
    write_csv(args.output_dir / "p_core_q_overlay_annual.csv", annual_rows({k: v for k, v in rows_by_portfolio.items() if k in {r["portfolio"] for r in summaries}}))

    viable = [
        row for row in variants
        if fnum(row.get("profit_units")) > 0 and fnum(row.get("recent_profit_units")) > 0
    ]
    best_by_utility = sorted(viable, key=lambda r: fnum(r.get("utility_drawdown_first")), reverse=True)[:12]
    best_by_dd = sorted(viable, key=lambda r: (fnum(r.get("max_drawdown_units")), fnum(r.get("profit_units"))), reverse=True)[:12]
    best_by_profit = sorted(viable, key=lambda r: fnum(r.get("profit_units")), reverse=True)[:12]
    focused_names = [
        "b384_dd32_smooth100",
        "b384_dd32_smooth80_convex19",
    ] + [str(row["portfolio"]) for row in best_by_utility[:4]]
    write_equity_svg(args.figure_path, {name: rows_by_portfolio[name] for name in focused_names if name in rows_by_portfolio})

    cols = [
        "portfolio",
        "profit_units",
        "roi",
        "issue_win_rate",
        "non_full_loss_rate",
        "max_drawdown_units",
        "max_loss_streak",
        "max_dead_streak",
        "recent_profit_units",
        "recent_roi",
        "avg_tickets_per_issue",
        "avg_pred_hit_prob",
        "avg_pred_ev_per_stake",
        "parts",
    ]
    report = [
        "# p-core / q-overlay 384 arm validation",
        "",
        "## Setup",
        "",
        "- Budget is fixed at 384 units per issue.",
        "- Core sleeve ranks existing N7 tickets by `pred_hit_prob` first, then confidence/EV.",
        "- Overlay sleeve ranks remaining tickets by `pred_ev_per_stake`, `avg_q_score`, then hit probability.",
        "- This is ticket-level validation on the existing high-N pool; it does not yet rebuild the leg generator around p-first single-leg selection.",
        "",
        "## Current 384 baselines",
        "",
        md_table(baseline_summaries, cols, limit=10),
        "",
        "## Best drawdown-first viable variants",
        "",
        md_table(best_by_utility, cols + ["utility_drawdown_first"], limit=12),
        "",
        "## Best absolute maxDD viable variants",
        "",
        md_table(best_by_dd, cols, limit=12),
        "",
        "## Best profit viable variants",
        "",
        md_table(best_by_profit, cols, limit=12),
        "",
        "## Interpretation",
        "",
        "- The arm is useful only if it materially improves maxDD / loss streak / non-full-loss rate while keeping long-run and 2023-2025 profit positive.",
        "- If ticket-level p-core does not improve enough, the next step is lower-level regeneration: select legs by single-leg probability, then reserve high-q outcomes for overlay depth.",
        f"- Equity figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.output_dir / 'p_core_q_overlay_summary.csv'}")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ticket-path", type=Path, default=DEFAULT_TICKET_PATH)
    parser.add_argument("--baseline-path", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--figure-path", type=Path, default=DEFAULT_FIGURE)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
