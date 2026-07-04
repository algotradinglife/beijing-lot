#!/usr/bin/env python3
"""Mix N7 protection sleeves under larger capital budgets."""
from __future__ import annotations

import argparse
import csv
import math
import sys
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
from scripts.evaluate_n7_protection_allocation_grid import max_underwater_profit_window
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


CURRENT_PORTFOLIO = "current_reference_256"
CURRENT_ISSUE_PATH = Path(
    "results/n7_multi_leg_protection_overlay_large_20260629/"
    "multi_leg_protection_overlay_issue_profit.csv"
)
ARM_ISSUE_PATH = Path(
    "results/n7_multi_leg_protection_overlay_large_20260629/"
    "multi_leg_protection_issue_profit.csv"
)

DD_ARM = "n7prot_same_ticket2_alt_risk__budget256_fractional"
SMOOTH_ARM = "n7prot_same_ticket4_full_risk__budget256_fractional"
SMOOTH_DEEP_ARM = "n7prot_c4_k4_full_risk__budget256_fractional"
SMOOTH_SAFE_ARM = "n7prot_c4_k2_full_risk__budget256_fractional"
CONVEX_ARM = "n7prot_same_ticket2_draw_risk__budget256_fractional"
CONVEX_MID_ARM = "n7prot_c2_k2_draw_risk__budget256_fractional"
CONVEX_WIDE_ARM = "n7prot_c2_k3_draw_top_ev__budget256_fractional"


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
    out: dict[str, dict[str, object]] = {}
    for row in read_csv_rows(path):
        if row.get("portfolio") != CURRENT_PORTFOLIO:
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["issue"])] = copied
    if not out:
        raise SystemExit(f"missing current rows in {path}")
    return out


def load_arms(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = {}
    for row in read_csv_rows(path):
        strategy = str(row.get("strategy"))
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out.setdefault(strategy, {})[str(row["issue"])] = copied
    return out


def ordered_issues(calendar: dict[str, dict[str, object]], current: dict[str, dict[str, object]]) -> list[str]:
    return sorted(current, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def short_arm(name: str) -> str:
    return name.removesuffix("__budget256_fractional").removeprefix("n7prot_")


def allocation_specs(total_budgets: list[float]) -> list[tuple[str, float, dict[str, float], str]]:
    specs: list[tuple[str, float, dict[str, float], str]] = [
        ("current_reference_256", ISSUE_BUDGET, {}, "current fixed-256 reference")
    ]
    for total in total_budgets:
        if total <= ISSUE_BUDGET:
            continue
        extra = total - ISSUE_BUDGET
        dd32 = min(32.0, extra)
        dd64 = min(64.0, extra)
        for dd_units in (0.0, dd32, dd64):
            remaining = extra - dd_units
            if remaining < -1e-9:
                continue
            prefix = f"b{int(total)}_dd{int(dd_units)}"
            dd_alloc = {DD_ARM: dd_units} if dd_units > 0 else {}
            # Smooth-only reference for each budget.
            specs.append(
                (
                    f"{prefix}_smooth100",
                    total,
                    {**dd_alloc, SMOOTH_ARM: remaining},
                    "DD sleeve plus same-ticket four-leg full/risk smoothing sleeve",
                )
            )
            specs.append(
                (
                    f"{prefix}_deep_smooth100",
                    total,
                    {**dd_alloc, SMOOTH_DEEP_ARM: remaining},
                    "DD sleeve plus c4/k4 full/risk smoothing sleeve",
                )
            )
            # Convex-only and convex/smooth mixes.
            specs.append(
                (
                    f"{prefix}_convex100",
                    total,
                    {**dd_alloc, CONVEX_ARM: remaining},
                    "DD sleeve plus same-ticket two-leg draw/risk convex sleeve",
                )
            )
            for smooth_arm, smooth_label in (
                (SMOOTH_ARM, "smooth"),
                (SMOOTH_DEEP_ARM, "deep"),
                (SMOOTH_SAFE_ARM, "safe"),
            ):
                for convex_arm, convex_label in (
                    (CONVEX_ARM, "convex"),
                    (CONVEX_MID_ARM, "midconvex"),
                    (CONVEX_WIDE_ARM, "wideconvex"),
                ):
                    for smooth_share in (0.2, 0.35, 0.5, 0.65, 0.8):
                        smooth_units = remaining * smooth_share
                        convex_units = remaining - smooth_units
                        specs.append(
                            (
                                (
                                    f"{prefix}_{smooth_label}{int(smooth_share * 100)}_"
                                    f"{convex_label}{int((1 - smooth_share) * 100)}"
                                ),
                                total,
                                {**dd_alloc, smooth_arm: smooth_units, convex_arm: convex_units},
                                "DD sleeve plus blended smoothing and convex sleeves",
                            )
                        )
    return specs


def combine_rows(
    *,
    name: str,
    total_budget: float,
    allocation: dict[str, float],
    rationale: str,
    issues: list[str],
    current: dict[str, dict[str, object]],
    arms: dict[str, dict[str, dict[str, object]]],
    calendar: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for issue in issues:
        cur = current[issue]
        profit = fnum(cur.get("profit_units"))
        tickets = fnum(cur.get("tickets"))
        hits = fnum(cur.get("hits"))
        parts = ["current:256"]
        for arm, units in allocation.items():
            if units <= 1e-9:
                continue
            row = arms.get(arm, {}).get(issue)
            if row is None:
                parts.append(f"cash:{short_arm(arm)}:{units:g}")
                continue
            stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = units / stake if stake > 0 else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{short_arm(arm)}:{units:g}")
        row_out = {
            "portfolio": name,
            "issue": issue,
            "stake_units": total_budget,
            "profit_units": profit,
            "roi": profit / total_budget if total_budget else math.nan,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
            "state": "static",
            "issue_budget": total_budget,
            "extra_budget": max(0.0, total_budget - ISSUE_BUDGET),
            "allocation": "; ".join(f"{short_arm(k)}={v:g}" for k, v in allocation.items() if v > 1e-9),
            "rationale": rationale,
        }
        row_out.update(calendar.get(issue, {}))
        out.append(row_out)
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
    current = load_current(args.current_issue_path, calendar)
    arms = load_arms(args.arm_issue_path, calendar)
    missing = [
        arm
        for arm in (DD_ARM, SMOOTH_ARM, SMOOTH_DEEP_ARM, SMOOTH_SAFE_ARM, CONVEX_ARM, CONVEX_MID_ARM, CONVEX_WIDE_ARM)
        if arm not in arms
    ]
    if missing:
        raise SystemExit(f"missing arm rows: {missing}")
    issues = ordered_issues(calendar, current)

    all_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}
    for name, total_budget, allocation, rationale in allocation_specs(args.total_budgets):
        rows = combine_rows(
            name=name,
            total_budget=total_budget,
            allocation=allocation,
            rationale=rationale,
            issues=issues,
            current=current,
            arms=arms,
            calendar=calendar,
        )
        all_rows.extend(rows)
        series[name] = rows
        meta[name] = {
            "allocation": "; ".join(f"{short_arm(k)}={v:g}" for k, v in allocation.items() if v > 1e-9),
            "rationale": rationale,
        }

    summaries = []
    for name, rows in series.items():
        budget = fnum(rows[0].get("issue_budget"), ISSUE_BUDGET) if rows else ISSUE_BUDGET
        row = summarize(rows, budget, args.recent_min_year, args.recent_max_year)
        row.update(meta[name])
        summaries.append(row)
    summary_df = pd.DataFrame(summaries)
    summary_df["utility_score"] = (
        1.6 * summary_df["max_drawdown_units"]
        + 0.12 * summary_df["profit_units"]
        + 55000.0 * summary_df["issue_win_rate"]
        + 75000.0 * summary_df["non_full_loss_rate"]
        + 25000.0 * summary_df["roi"]
    )
    summary_df = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False])
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "sleeve_mix_issue_profit.csv", all_rows)
    summary_df.to_csv(args.output_dir / "sleeve_mix_summary.csv", index=False)
    write_csv(args.output_dir / "sleeve_mix_annual.csv", annual)

    reference = summary_df[summary_df["portfolio"] == "current_reference_256"].iloc[0]
    better_abs = summary_df[summary_df["max_drawdown_units"] >= fnum(reference["max_drawdown_units"])].copy()
    best_abs_by_budget = (
        summary_df.sort_values(["issue_budget", "max_drawdown_units", "profit_units"], ascending=[True, False, False])
        .groupby("issue_budget")
        .head(1)
    )
    best_rel_by_budget = (
        summary_df.sort_values(["issue_budget", "max_drawdown_budget_equiv", "profit_units"], ascending=[True, True, False])
        .groupby("issue_budget")
        .head(1)
    )
    best_roi_ge1 = summary_df[(summary_df["issue_budget"] > ISSUE_BUDGET) & (summary_df["roi"] >= 1.0)].sort_values(
        ["issue_budget", "max_drawdown_units", "profit_units"],
        ascending=[True, False, False],
    )
    best_score = summary_df.sort_values(["utility_score", "profit_units"], ascending=[False, False]).head(20)
    top_abs = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(24)
    selected_names = ["current_reference_256"]
    selected_names += [name for name in top_abs["portfolio"].head(9).tolist() if name not in selected_names]
    write_equity_svg(args.figure_path, {name: series[name] for name in selected_names if name in series}, calendar)

    cols = [
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
        "max_drawdown_budget_equiv",
        "max_dead_streak",
        "recent_profit_per_256",
        "allocation",
    ]
    report = [
        "# N7 Sleeve Mix Capital Test",
        "",
        "## Scope",
        "",
        "- Base stays as current fixed-256 strategy.",
        "- No low-N route is added. Extra capital is split across N7 sleeves only.",
        f"- Total budgets tested: `{','.join(f'{x:g}' for x in args.total_budgets)}`.",
        "- Sleeve families: DD sleeve (`same_ticket2_alt_risk`), smoothing sleeve (`same_ticket4/full_risk` variants), convex sleeve (`draw_risk` variants).",
        "",
        "## Absolute MaxDD Not Worse Than Current",
        "",
        md_table(better_abs[cols].to_dict("records"), limit=40),
        "",
        "## Best Absolute MaxDD By Budget",
        "",
        md_table(best_abs_by_budget[cols].to_dict("records"), limit=40),
        "",
        "## Best Relative DD By Budget",
        "",
        md_table(best_rel_by_budget[cols].to_dict("records"), limit=40),
        "",
        "## Best ROI>=1 By Budget",
        "",
        md_table(best_roi_ge1[cols].groupby("issue_budget").head(3).to_dict("records"), limit=60),
        "",
        "## Top Utility Score",
        "",
        md_table(best_score[cols + ["utility_score"]].to_dict("records"), limit=20),
        "",
        "## Interpretation",
        "",
        "- A useful large sleeve mix should beat the single-sleeve large test on absolute maxDD, not only on DD/budget.",
        "- If ROI>=1 mixes have much worse absolute maxDD, they are convex-growth allocations, not drawdown-control allocations.",
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
    parser.add_argument("--current-issue-path", type=Path, default=CURRENT_ISSUE_PATH)
    parser.add_argument("--arm-issue-path", type=Path, default=ARM_ISSUE_PATH)
    parser.add_argument(
        "--total-budgets",
        type=float,
        nargs="+",
        default=[288.0, 320.0, 384.0, 512.0, 768.0, 1024.0, 1280.0, 2048.0, 2304.0, 4352.0],
    )
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_sleeve_mix_capital_20260629"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_sleeve_mix_capital_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_sleeve_mix_capital_2026-06-29.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
