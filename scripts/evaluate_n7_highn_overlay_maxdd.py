#!/usr/bin/env python3
"""Add high-N-only overlays to the current strategy and test absolute maxDD."""
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
    with_calendar,
    write_equity_svg,
)
from scripts.evaluate_n7_protection_allocation_grid import max_underwater_profit_window
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


CURRENT_PATH = Path("results/n7_protection_allocation_grid_20260628/protection_allocation_grid_issue_profit.csv")
CURRENT_PORTFOLIO = "grid_c144_p48_draw_top_ev_k1_n5ov64"
CAP40_PATH = Path("results/high_n_selector_cap40_budget512_20260628/high_n_selector_issue_profit.csv")
CAP80_PATH = Path("results/high_n_selector_cap80_budget1024_20260628/high_n_selector_issue_profit.csv")
CAP40_SOURCE = "ev_m0p95_p0p8_full_opt__budget512_fractional"
CAP80_SOURCE = "ev_m0p95_p0p8_full_opt__budget1024_fractional"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
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


def load_current(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    rows = {}
    for row in read_csv_rows(path):
        if row.get("portfolio") != CURRENT_PORTFOLIO:
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        rows[str(row["issue"])] = copied
    if not rows:
        raise SystemExit(f"missing current portfolio rows: {path}")
    return rows


def load_selector_maps(
    path: Path,
    source: str,
    calendar: dict[str, dict[str, object]],
) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        if row.get("source_strategy") != source:
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["selector"])][str(row["issue"])] = copied
    return dict(out)


def ordered_issues(calendar: dict[str, dict[str, object]], current: dict[str, dict[str, object]]) -> list[str]:
    return sorted(current, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def overlay_specs() -> list[tuple[str, float, str, dict[str, float], str]]:
    selectors = [
        "all",
        "draw_free",
        "portfolio_realloc_70_core_neg0ge6_30_exact",
        "portfolio_realloc_80_core_neg0ge6_20_exact",
        "topology_neg0_ge6_d0",
    ]
    specs: list[tuple[str, float, str, dict[str, float], str]] = []
    for budget, cap_label, extra in [(512.0, "cap40", 256.0), (1024.0, "cap80", 768.0), (2048.0, "cap80", 1792.0)]:
        multiplier = int(budget / ISSUE_BUDGET)
        for selector in selectors:
            specs.append(
                (
                    f"x{multiplier}_current_plus_{cap_label}_{selector}",
                    budget,
                    cap_label,
                    {selector: extra},
                    f"current 256 + {extra:g} high-N-only overlay from {cap_label}/{selector}",
                )
            )
        specs.extend(
            [
                (
                    f"x{multiplier}_current_plus_{cap_label}_all70_port30",
                    budget,
                    cap_label,
                    {
                        "all": extra * 0.70,
                        "portfolio_realloc_70_core_neg0ge6_30_exact": extra * 0.30,
                    },
                    "broad all overlay with smaller convex topology sleeve",
                ),
                (
                    f"x{multiplier}_current_plus_{cap_label}_all50_drawfree30_port20",
                    budget,
                    cap_label,
                    {
                        "all": extra * 0.50,
                        "draw_free": extra * 0.30,
                        "portfolio_realloc_70_core_neg0ge6_30_exact": extra * 0.20,
                    },
                    "broad all + draw-free + topology overlay",
                ),
                (
                    f"x{multiplier}_current_plus_{cap_label}_all80_drawfree20",
                    budget,
                    cap_label,
                    {
                        "all": extra * 0.80,
                        "draw_free": extra * 0.20,
                    },
                    "mostly broad all overlay, small draw-free sleeve",
                ),
            ]
        )
    specs.insert(
        0,
        (
            "x1_current_reference",
            256.0,
            "none",
            {},
            "current fixed-256 reference",
        ),
    )
    return specs


def combine(
    *,
    name: str,
    issue_budget: float,
    cap_label: str,
    overlay: dict[str, float],
    rationale: str,
    issues: list[str],
    current: dict[str, dict[str, object]],
    cap40: dict[str, dict[str, dict[str, object]]],
    cap80: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    source_maps = cap40 if cap_label == "cap40" else cap80
    out = []
    for issue in issues:
        cur = current[issue]
        profit = fnum(cur.get("profit_units"))
        tickets = fnum(cur.get("tickets"))
        hits = fnum(cur.get("hits"))
        parts = ["current:256"]
        missing = 0.0
        for selector, units in overlay.items():
            row = source_maps.get(selector, {}).get(issue)
            if row is None:
                missing += units
                continue
            row_stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = units / row_stake if row_stake else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{cap_label}:{selector}:{units:g}")
        if missing:
            row = source_maps.get("all", {}).get(issue)
            if row is None:
                raise SystemExit(f"missing all fallback for {cap_label} issue {issue}")
            row_stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = missing / row_stake if row_stake else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{cap_label}:all_fallback:{missing:g}")
        combined = {
            "portfolio": name,
            "issue": issue,
            "stake_units": issue_budget,
            "profit_units": profit,
            "roi": profit / issue_budget if issue_budget else math.nan,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
            "state": "static",
            "issue_budget": issue_budget,
            "budget_multiplier": issue_budget / ISSUE_BUDGET,
            "cap_label": cap_label,
            "overlay_allocation": "; ".join(f"{k}={v:g}" for k, v in overlay.items()),
            "rationale": rationale,
        }
        combined.update(calendar.get(issue, {}))
        out.append(combined)
    return out


def summarize(rows: list[dict[str, object]], budget: float, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    recent = [row for row in ordered if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    maxdd = max_drawdown_units(ordered)
    out = {
        "portfolio": str(ordered[0]["portfolio"]) if ordered else "",
        "issue_budget": budget,
        "budget_multiplier": budget / ISSUE_BUDGET,
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (budget / ISSUE_BUDGET),
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered),
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered),
        "full_loss_rate": sum(1 for row in ordered if full_loss(row)) / len(ordered),
        "max_drawdown_units": maxdd,
        "max_drawdown_per_256": maxdd / (budget / ISSUE_BUDGET),
        "max_drawdown_budget_equiv": abs(maxdd) / budget,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / (stake - budget) if stake > budget else math.nan,
        "recent_profit_units": recent_profit,
        "recent_profit_per_256": recent_profit / (budget / ISSUE_BUDGET),
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in ordered) / len(ordered),
    }
    out.update(max_underwater_profit_window(ordered))
    return out


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    current = load_current(args.current_path, calendar)
    cap40 = load_selector_maps(args.cap40_path, CAP40_SOURCE, calendar)
    cap80 = load_selector_maps(args.cap80_path, CAP80_SOURCE, calendar)
    issues = ordered_issues(calendar, current)

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}
    for name, budget, cap_label, overlay, rationale in overlay_specs():
        rows = combine(
            name=name,
            issue_budget=budget,
            cap_label=cap_label,
            overlay=overlay,
            rationale=rationale,
            issues=issues,
            current=current,
            cap40=cap40,
            cap80=cap80,
            calendar=calendar,
        )
        all_rows.extend(rows)
        series[name] = rows
        meta[name] = {
            "cap_label": cap_label,
            "overlay_allocation": "; ".join(f"{k}={v:g}" for k, v in overlay.items()),
            "rationale": rationale,
        }

    summaries = []
    for name, rows in series.items():
        budget = fnum(rows[0].get("issue_budget")) if rows else ISSUE_BUDGET
        summary = summarize(rows, budget, args.recent_min_year, args.recent_max_year)
        summary.update(meta[name])
        summaries.append(summary)
    summary_df = pd.DataFrame(summaries)
    summary_df["dd_score"] = (
        2.0 * summary_df["max_drawdown_units"]
        + 0.15 * summary_df["profit_units"]
        + 40000 * summary_df["issue_win_rate"]
        + 60000 * summary_df["non_full_loss_rate"]
    )
    summary_df = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False])
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "highn_overlay_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "highn_overlay_summary.csv", index=False)
    write_csv(args.output_dir / "highn_overlay_annual.csv", annual)

    reference = summary_df[summary_df["portfolio"] == "x1_current_reference"].iloc[0]
    better_abs = summary_df[summary_df["max_drawdown_units"] >= fnum(reference["max_drawdown_units"])].copy()
    top_abs = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(12)
    top_budget_equiv = summary_df.sort_values(["max_drawdown_budget_equiv", "profit_units"], ascending=[True, False]).head(12)
    selected_names = ["x1_current_reference"]
    selected_names += [x for x in top_abs["portfolio"].head(7).tolist() if x not in selected_names]
    write_equity_svg(args.figure_path, {name: series[name] for name in selected_names if name in series}, calendar)

    report = [
        "# N7 High-N Overlay MaxDD Test",
        "",
        "## Scope",
        "",
        "- Base stays as current fixed-256 strategy.",
        "- Extra capital is high-N only: cap40/cap80 N7 selector overlays.",
        "- No N3/N4/N5 is added in the overlay.",
        "",
        "## Absolute MaxDD Not Worse Than Current",
        "",
        md_table(
            better_abs[
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
                    "max_dead_streak",
                    "recent_profit_per_256",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Top Absolute MaxDD",
        "",
        md_table(
            top_abs[
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
                    "max_dead_streak",
                    "recent_profit_per_256",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Lowest DD / Budget",
        "",
        md_table(
            top_budget_equiv[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_units",
                    "profit_per_256",
                    "roi",
                    "max_drawdown_units",
                    "max_drawdown_budget_equiv",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
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
                    "cap_label",
                    "overlay_allocation",
                    "rationale",
                ]
            ].sort_values(["issue_budget", "portfolio"]).to_dict("records"),
            limit=80,
        ),
        "",
        "## Interpretation",
        "",
        "- If `Absolute MaxDD Not Worse Than Current` only contains the reference, high-N overlays did not reduce absolute maxDD.",
        "- A lower `max_drawdown_budget_equiv` means extra capital makes drawdown smaller relative to total stake, but this is weaker than reducing absolute DD.",
        f"- Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--current-path", type=Path, default=CURRENT_PATH)
    parser.add_argument("--cap40-path", type=Path, default=CAP40_PATH)
    parser.add_argument("--cap80-path", type=Path, default=CAP80_PATH)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_highn_overlay_maxdd_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_highn_overlay_maxdd_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_highn_overlay_maxdd_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
