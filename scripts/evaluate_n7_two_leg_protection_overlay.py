#!/usr/bin/env python3
"""Evaluate N7 multi-leg protection as extra capital overlays."""
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
from scripts.evaluate_n7_core_ticket_protection import (
    CORE_SELECTOR,
    SOURCE_STRATEGY,
    load_core_source_rows,
    protection_score,
    scaled_settled_row,
)
from scripts.evaluate_n7_highn_overlay_maxdd import CURRENT_PATH, CURRENT_PORTFOLIO, write_csv_all
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.evaluate_n7_protection_allocation_grid import max_underwater_profit_window
from scripts.evaluate_n7_same_ticket_leg_coverage import action_lookup, convert_ticket, parse_ticket, single_rows
from scripts.walkforward_beidan_strategy_eval import default_db_path, load_action_rows, md_table, settle_ticket, write_csv


SELECTED_TICKETS_PATH = Path("results/high_n_selector_20260628/high_n_selector_selected_tickets.csv")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_csv(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


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


def strategy_stem(*, cover_count: int, policy: str, mode: str, protect_count: int) -> str:
    if cover_count == 1 and protect_count > 1:
        shape = f"distributed{protect_count}"
    elif cover_count > 1 and protect_count == 1:
        shape = f"same_ticket{cover_count}"
    else:
        shape = f"c{cover_count}_k{protect_count}"
    return f"n7prot_{shape}_{policy}_{mode}"


def build_protection_rows(
    *,
    source_rows: list[dict[str, object]],
    actions,
    single,
    policy: str,
    mode: str,
    protect_count: int,
    cover_count: int,
    snapshot: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in source_rows:
        grouped[str(row["issue"])].append(row)

    strategy = strategy_stem(cover_count=cover_count, policy=policy, mode=mode, protect_count=protect_count)
    out: list[dict[str, object]] = []
    for _issue, rows in grouped.items():
        ranked = sorted(rows, key=lambda row: protection_score(row, mode), reverse=True)
        for row in ranked[:protect_count]:
            base_ticket = parse_ticket(row, actions)
            if base_ticket is None:
                continue
            base_raw = settle_ticket(base_ticket)
            source_scale = fnum(row.get("stake_units")) / fnum(base_raw.get("stake_units"), 1.0)
            converted = convert_ticket(
                base_ticket,
                strategy=strategy,
                policy=policy,
                cover_count=cover_count,
                single=single,
                actions=actions,
                snapshot=snapshot,
            )
            settled = scaled_settled_row(converted, row, strategy, source_scale, 1)
            settled["leg_cover_count"] = cover_count
            settled["protected_ticket_count_per_issue"] = protect_count
            settled["protection_policy"] = policy
            settled["protection_mode"] = mode
            settled["protection_shape"] = (
                "distributed" if cover_count == 1 and protect_count > 1 else "same_ticket"
            )
            out.append(settled)
    return out


def load_issue_arm_maps(rows: list[dict[str, object]], calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["strategy"])][str(row["issue"])] = copied
    return dict(out)


def short_arm(strategy: str) -> str:
    return strategy.removesuffix("__budget256_fractional")


def ordered_issues(calendar: dict[str, dict[str, object]], current: dict[str, dict[str, object]]) -> list[str]:
    return sorted(current, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def overlay_specs(arms: list[str], extras: list[float]) -> list[tuple[str, float, dict[str, float], str]]:
    specs: list[tuple[str, float, dict[str, float], str]] = [
        ("current_reference_256", ISSUE_BUDGET, {}, "current fixed-256 reference")
    ]
    arm_set = set(arms)
    for extra in extras:
        budget = ISSUE_BUDGET + extra
        for arm in arms:
            specs.append(
                (
                    f"b{int(budget)}_plus_{short_arm(arm)}",
                    budget,
                    {arm: extra},
                    f"current 256 + {extra:g} N7 protected overlay from {short_arm(arm)}",
                )
            )
        blend_defs: list[tuple[str, dict[str, float], str]] = []
        for depth in (2, 3, 4):
            blend_defs.extend(
                [
                    (
                        f"same{depth}_draw70_alt30",
                        {
                            f"n7prot_same_ticket{depth}_draw_top_ev__budget256_fractional": extra * 0.70,
                            f"n7prot_same_ticket{depth}_alt_top_ev__budget256_fractional": extra * 0.30,
                        },
                        f"same-ticket {depth}-leg protection, mostly draw with smaller alternative-side cover",
                    ),
                    (
                        f"same{depth}_draw50_alt25_full25",
                        {
                            f"n7prot_same_ticket{depth}_draw_top_ev__budget256_fractional": extra * 0.50,
                            f"n7prot_same_ticket{depth}_alt_top_ev__budget256_fractional": extra * 0.25,
                            f"n7prot_same_ticket{depth}_full_top_ev__budget256_fractional": extra * 0.25,
                        },
                        f"same-ticket {depth}-leg protection split across draw, alt, and full policies",
                    ),
                ]
            )
        for n_tickets in (2, 3, 4):
            blend_defs.append(
                (
                    f"dist{n_tickets}_draw50_alt25_full25",
                    {
                        f"n7prot_distributed{n_tickets}_draw_top_ev__budget256_fractional": extra * 0.50,
                        f"n7prot_distributed{n_tickets}_alt_top_ev__budget256_fractional": extra * 0.25,
                        f"n7prot_distributed{n_tickets}_full_top_ev__budget256_fractional": extra * 0.25,
                    },
                    f"distributed one-leg protection across {n_tickets} tickets, split across policies",
                )
            )
        blend_defs.extend(
            [
                (
                    "same2_70_same3_30_draw",
                    {
                        "n7prot_same_ticket2_draw_top_ev__budget256_fractional": extra * 0.70,
                        "n7prot_same_ticket3_draw_top_ev__budget256_fractional": extra * 0.30,
                    },
                    "blend two-leg and three-leg same-ticket draw protection",
                ),
                (
                    "same3_70_dist3_30_draw",
                    {
                        "n7prot_same_ticket3_draw_top_ev__budget256_fractional": extra * 0.70,
                        "n7prot_distributed3_draw_top_ev__budget256_fractional": extra * 0.30,
                    },
                    "mostly same-ticket three-leg draw protection plus distributed protection",
                ),
            ]
        )
        for label, allocation, rationale in blend_defs:
            if all(arm in arm_set for arm in allocation):
                specs.append((f"b{int(budget)}_plus_{label}", budget, allocation, rationale))
    return specs


def combine(
    *,
    name: str,
    budget: float,
    allocation: dict[str, float],
    rationale: str,
    issues: list[str],
    current: dict[str, dict[str, object]],
    arms: dict[str, dict[str, dict[str, object]]],
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
            row = arms.get(arm, {}).get(issue)
            if row is None:
                parts.append(f"cash:{short_arm(arm)}:{units:g}")
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
            "extra_budget": max(0.0, budget - ISSUE_BUDGET),
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
        "portfolio": str(ordered[0].get("portfolio", ordered[0].get("strategy", ""))) if ordered else "",
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
    action_rows = load_action_rows(args.db, args.min_year)
    actions = action_lookup(action_rows)
    single = single_rows(action_rows)
    source_rows = load_core_source_rows(args.selected_tickets)

    raw_rows: list[dict[str, object]] = []
    for policy in parse_csv(args.policies):
        for mode in parse_csv(args.modes):
            for protect_count in args.protect_counts:
                for cover_count in args.cover_counts:
                    if cover_count <= 0 or protect_count <= 0:
                        continue
                    raw_rows.extend(
                        build_protection_rows(
                            source_rows=source_rows,
                            actions=actions,
                            single=single,
                            policy=policy,
                            mode=mode,
                            protect_count=int(protect_count),
                            cover_count=int(cover_count),
                            snapshot=args.snapshot,
                        )
                    )

    budgeted = budgeted_ticket_rows(raw_rows, issue_budget_units=ISSUE_BUDGET, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    arm_maps = load_issue_arm_maps(issue_rows, calendar)
    issues = ordered_issues(calendar, current)

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}
    for name, budget, allocation, rationale in overlay_specs(sorted(arm_maps), args.extra_budgets):
        rows = combine(
            name=name,
            budget=budget,
            allocation=allocation,
            rationale=rationale,
            issues=issues,
            current=current,
            arms=arm_maps,
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
        + 80000.0 * summary_df["non_full_loss_rate"]
    )
    summary_df = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False])
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "multi_leg_protection_raw_tickets.csv", raw_rows)
    write_csv_all(args.output_dir / "multi_leg_protection_budgeted_tickets.csv", budgeted)
    write_csv(args.output_dir / "multi_leg_protection_issue_profit.csv", issue_rows)
    write_csv_all(args.output_dir / "multi_leg_protection_overlay_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "multi_leg_protection_overlay_summary.csv", index=False)
    write_csv(args.output_dir / "multi_leg_protection_overlay_annual.csv", annual)

    standalone_summary = []
    for strategy, vals in arm_maps.items():
        rows = list(vals.values())
        standalone_summary.append(summarize(rows, ISSUE_BUDGET, args.recent_min_year, args.recent_max_year) | {"strategy": strategy})
    standalone_df = pd.DataFrame(standalone_summary).sort_values(
        ["max_drawdown_units", "profit_units"], ascending=[False, False]
    )
    standalone_df.to_csv(args.output_dir / "multi_leg_protection_standalone_summary.csv", index=False)

    reference = summary_df[summary_df["portfolio"] == "current_reference_256"].iloc[0]
    better_abs = summary_df[summary_df["max_drawdown_units"] >= fnum(reference["max_drawdown_units"])].copy()
    top_abs = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(24)
    top_score = summary_df.sort_values(["dd_score", "profit_units"], ascending=[False, False]).head(24)
    top_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(24)
    selected_names = ["current_reference_256"]
    selected_names += [name for name in top_abs["portfolio"].head(9).tolist() if name not in selected_names]
    write_equity_svg(args.figure_path, {name: series[name] for name in selected_names if name in series}, calendar)

    report = [
        "# N7 Multi-Leg Protection Overlay",
        "",
        "## Scope",
        "",
        f"- Base: `{CURRENT_PORTFOLIO}` from `{args.current_path}`.",
        f"- Source N7 core tickets: `{args.selected_tickets}` / `{SOURCE_STRATEGY}` / `{CORE_SELECTOR}`.",
        "- No low-N route is added. Extra budget buys only N7 protected tickets.",
        f"- Extra budgets tested: `{','.join(f'{x:g}' for x in args.extra_budgets)}`.",
        f"- Policies: `{args.policies}`; modes: `{args.modes}`; protect-counts: `{','.join(str(x) for x in args.protect_counts)}`; cover-counts: `{','.join(str(x) for x in args.cover_counts)}`.",
        "- `same_ticketK` means one ticket protects K legs. `distributedK` means K tickets each protect one leg.",
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
                    "overlay_allocation",
                ]
            ].to_dict("records"),
            limit=40,
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
            limit=24,
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
            limit=24,
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
            limit=24,
        ),
        "",
        "## Standalone Protected Arms",
        "",
        md_table(
            standalone_df[
                [
                    "strategy",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_per_256",
                ]
            ].head(24).to_dict("records"),
            limit=24,
        ),
        "",
        "## Interpretation",
        "",
        "- If `same_ticket2` improves maxDD more than `distributed2`, the main issue is two vulnerable legs inside the same high-EV ticket.",
        "- If `distributed2` wins, protection should be spread across different tickets rather than concentrated on one ticket.",
        "- If both improve only as `+32/+64` sleeves and fail at larger budgets, two-leg protection is useful but should remain a small overlay.",
        f"- Figure: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")
    print(f"Wrote {len(raw_rows)} raw protected ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--current-path", type=Path, default=CURRENT_PATH)
    parser.add_argument("--selected-tickets", type=Path, default=SELECTED_TICKETS_PATH)
    parser.add_argument("--snapshot", choices=("10h", "1h", "final"), default="1h")
    parser.add_argument("--policies", default="draw,alt,full")
    parser.add_argument("--modes", default="top_ev,risk")
    parser.add_argument("--protect-counts", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--cover-counts", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--extra-budgets", type=float, nargs="+", default=[32.0, 64.0, 128.0, 256.0])
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_multi_leg_protection_overlay_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_multi_leg_protection_overlay_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_multi_leg_protection_overlay_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
