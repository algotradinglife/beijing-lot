#!/usr/bin/env python3
"""Test extra-capital overlays that buy only protected N7 tickets."""
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
    write_equity_svg,
)
from scripts.evaluate_n7_highn_overlay_maxdd import CURRENT_PATH, CURRENT_PORTFOLIO, write_csv_all
from scripts.evaluate_n7_protection_allocation_grid import max_underwater_profit_window
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


PROTECTED_PATH = Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_issue_profit.csv")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_current(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    rows = {}
    for row in read_csv_rows(path):
        if row.get("portfolio") != CURRENT_PORTFOLIO:
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        rows[str(row["issue"])] = copied
    if not rows:
        raise SystemExit(f"missing current rows: {path} / {CURRENT_PORTFOLIO}")
    return rows


def load_protected(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        strategy = str(row.get("strategy", ""))
        if not strategy.startswith("core_tp_only_"):
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[strategy][str(row["issue"])] = copied
    if not out:
        raise SystemExit(f"missing core_tp_only protected rows: {path}")
    return dict(out)


def ordered_issues(calendar: dict[str, dict[str, object]], current: dict[str, dict[str, object]]) -> list[str]:
    return sorted(current, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def short_arm(strategy: str) -> str:
    return strategy.removeprefix("core_tp_only_").removesuffix("__budget256_fractional")


def overlay_specs(arms: list[str]) -> list[tuple[str, float, dict[str, float], str]]:
    specs: list[tuple[str, float, dict[str, float], str]] = [
        ("current_reference_256", ISSUE_BUDGET, {}, "current fixed-256 reference")
    ]
    extras = [32.0, 64.0, 128.0, 256.0]
    priority = [
        "core_tp_only_draw_top_ev_k1__budget256_fractional",
        "core_tp_only_draw_risk_k1__budget256_fractional",
        "core_tp_only_alt_top_ev_k1__budget256_fractional",
        "core_tp_only_full_top_ev_k1__budget256_fractional",
        "core_tp_only_full_top_ev_k3__budget256_fractional",
        "core_tp_only_draw_top_ev_k2__budget256_fractional",
        "core_tp_only_draw_top_ev_k3__budget256_fractional",
        "core_tp_only_draw_low_hit_k1__budget256_fractional",
    ]
    selected = [arm for arm in priority if arm in arms]
    for extra in extras:
        budget = ISSUE_BUDGET + extra
        for arm in selected:
            label = short_arm(arm)
            specs.append(
                (
                    f"b{int(budget)}_plus_{label}",
                    budget,
                    {arm: extra},
                    f"current 256 + {extra:g} protected N7 overlay from {label}",
                )
            )
        blends = [
            (
                "draw70_full30",
                {
                    "core_tp_only_draw_top_ev_k1__budget256_fractional": extra * 0.70,
                    "core_tp_only_full_top_ev_k3__budget256_fractional": extra * 0.30,
                },
                "top-EV draw protection plus smaller full-cover protection",
            ),
            (
                "draw50_alt25_full25",
                {
                    "core_tp_only_draw_top_ev_k1__budget256_fractional": extra * 0.50,
                    "core_tp_only_alt_top_ev_k1__budget256_fractional": extra * 0.25,
                    "core_tp_only_full_top_ev_k1__budget256_fractional": extra * 0.25,
                },
                "split protected overlay across draw, alternative side, and full cover",
            ),
            (
                "draw80_lowhit20",
                {
                    "core_tp_only_draw_top_ev_k1__budget256_fractional": extra * 0.80,
                    "core_tp_only_draw_low_hit_k1__budget256_fractional": extra * 0.20,
                },
                "mostly top-EV draw protection with a small convex low-hit tail",
            ),
        ]
        for blend, allocation, rationale in blends:
            if all(arm in arms for arm in allocation):
                specs.append((f"b{int(budget)}_plus_{blend}", budget, allocation, rationale))
    return specs


def combine(
    *,
    name: str,
    budget: float,
    allocation: dict[str, float],
    rationale: str,
    issues: list[str],
    current: dict[str, dict[str, object]],
    protected: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    out = []
    for issue in issues:
        cur = current[issue]
        profit = fnum(cur.get("profit_units"))
        tickets = fnum(cur.get("tickets"))
        hits = fnum(cur.get("hits"))
        parts = ["current:256"]
        for arm, units in allocation.items():
            row = protected.get(arm, {}).get(issue)
            if row is None:
                profit -= units
                tickets += 1.0
                parts.append(f"missing:{short_arm(arm)}:{units:g}")
                continue
            row_stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = units / row_stake if row_stake else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{short_arm(arm)}:{units:g}")
        combined = {
            "portfolio": name,
            "issue": issue,
            "stake_units": budget,
            "profit_units": profit,
            "roi": profit / budget if budget else math.nan,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
            "state": "static",
            "issue_budget": budget,
            "budget_multiplier": budget / ISSUE_BUDGET,
            "overlay_allocation": "; ".join(f"{short_arm(k)}={v:g}" for k, v in allocation.items()),
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
        "extra_budget": max(0.0, budget - ISSUE_BUDGET),
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
    protected = load_protected(args.protected_path, calendar)
    issues = ordered_issues(calendar, current)

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}
    for name, budget, allocation, rationale in overlay_specs(sorted(protected)):
        rows = combine(
            name=name,
            budget=budget,
            allocation=allocation,
            rationale=rationale,
            issues=issues,
            current=current,
            protected=protected,
            calendar=calendar,
        )
        all_rows.extend(rows)
        series[name] = rows
        meta[name] = {
            "overlay_allocation": "; ".join(f"{short_arm(k)}={v:g}" for k, v in allocation.items()),
            "rationale": rationale,
        }

    summaries = []
    for name, rows in series.items():
        budget = fnum(rows[0].get("issue_budget"), ISSUE_BUDGET) if rows else ISSUE_BUDGET
        summary = summarize(rows, budget, args.recent_min_year, args.recent_max_year)
        summary.update(meta[name])
        summaries.append(summary)
    summary_df = pd.DataFrame(summaries)
    summary_df["dd_score"] = (
        3.0 * summary_df["max_drawdown_units"]
        + 0.10 * summary_df["profit_units"]
        + 50000.0 * summary_df["issue_win_rate"]
        + 70000.0 * summary_df["non_full_loss_rate"]
    )
    summary_df = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False])
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "protected_overlay_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "protected_overlay_summary.csv", index=False)
    write_csv(args.output_dir / "protected_overlay_annual.csv", annual)

    reference = summary_df[summary_df["portfolio"] == "current_reference_256"].iloc[0]
    better_abs = summary_df[summary_df["max_drawdown_units"] >= fnum(reference["max_drawdown_units"])].copy()
    top_abs = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(20)
    top_score = summary_df.sort_values(["dd_score", "profit_units"], ascending=[False, False]).head(20)
    top_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(20)
    selected_names = ["current_reference_256"]
    selected_names += [name for name in top_abs["portfolio"].head(8).tolist() if name not in selected_names]
    write_equity_svg(args.figure_path, {name: series[name] for name in selected_names if name in series}, calendar)

    report = [
        "# N7 Protected Overlay Capital Test",
        "",
        "## Scope",
        "",
        f"- Base: `{CURRENT_PORTFOLIO}` from `{args.current_path}`.",
        f"- Overlay source: `core_tp_only_*` protected N7 tickets from `{args.protected_path}`.",
        "- Overlay uses only N7 protected tickets; no N3/N4/N5 is added as new capital.",
        "- Tested extra budgets: `+32`, `+64`, `+128`, `+256` units per issue.",
        "",
        "## Absolute MaxDD Not Worse Than Current",
        "",
        md_table(
            better_abs[
                [
                    "portfolio",
                    "issue_budget",
                    "extra_budget",
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
            limit=30,
        ),
        "",
        "## Top Absolute MaxDD",
        "",
        md_table(
            top_abs[
                [
                    "portfolio",
                    "issue_budget",
                    "extra_budget",
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
                    "overlay_allocation",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Top Score",
        "",
        md_table(
            top_score[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "overlay_allocation",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Top Profit",
        "",
        md_table(
            top_profit[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_units",
                    "profit_per_256",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "overlay_allocation",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Interpretation",
        "",
        "- If only tiny `+32` overlays improve absolute maxDD, that suggests protection is useful but should remain a sleeve, not a full doubling.",
        "- If no protected overlay improves absolute maxDD, then extra high-N capital is not acting as a hedge; it is still mostly extra exposure.",
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
    parser.add_argument("--protected-path", type=Path, default=PROTECTED_PATH)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_protected_overlay_capital_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_protected_overlay_capital_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_protected_overlay_capital_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
