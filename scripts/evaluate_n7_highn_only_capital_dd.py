#!/usr/bin/env python3
"""MaxDD-first capital scaling without lower-N sleeves.

This script keeps the experiment on high-N exposure only:

* N7 core tickets;
* N7 top-EV protected ticket sleeves;
* N7 broad/draw-free/topology selector sleeves.

The existing current strategy with N5 overlap is included only as a reference,
not as a candidate route.
"""
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
    N5_OVERLAP_PATH,
    N5_OVERLAP_STRATEGY,
    load_issue_arm,
    write_csv_all,
)
from scripts.evaluate_n7_protection_allocation_grid import CORE_ARM, load_strategy_maps, max_underwater_profit_window
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


PROTECTION_ISSUE_PATH = Path("results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_issue_profit.csv")
HIGH_N_ISSUE_PATH = Path("results/high_n_selector_20260628/high_n_selector_issue_profit.csv")
HIGH_N_SOURCE = "ev_m0p95_p0p8_full_opt__budget256_fractional"

PROTECT_ARMS = {
    "draw1": "core_tp_only_draw_top_ev_k1__budget256_fractional",
    "draw2": "core_tp_only_draw_top_ev_k2__budget256_fractional",
    "draw3": "core_tp_only_draw_top_ev_k3__budget256_fractional",
    "alt1": "core_tp_only_alt_top_ev_k1__budget256_fractional",
    "full1": "core_tp_only_full_top_ev_k1__budget256_fractional",
    "full3": "core_tp_only_full_top_ev_k3__budget256_fractional",
}

HIGH_N_SELECTORS = {
    "hn_all": "all",
    "hn_draw_free": "draw_free",
    "hn_core80_priority": "portfolio_realloc_80_core_neg0ge6_20_priority",
    "hn_core80_exact": "portfolio_realloc_80_core_neg0ge6_20_exact",
    "hn_core70_exact": "portfolio_realloc_70_core_neg0ge6_30_exact",
    "hn_priority_tail": "selector_v1_topology_priority",
}

FALLBACK_HIGH_N = "hn_all"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_high_n_maps(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    selector_to_arm = {selector: arm for arm, selector in HIGH_N_SELECTORS.items()}
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        if row.get("source_strategy") != HIGH_N_SOURCE:
            continue
        arm = selector_to_arm.get(str(row.get("selector", "")))
        if arm is None:
            continue
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        copied["arm"] = arm
        out[arm][str(row["issue"])] = copied
    return dict(out)


def ordered_issues(calendar: dict[str, dict[str, object]], arms: dict[str, dict[str, dict[str, object]]]) -> list[str]:
    issues = set()
    for arm in (FALLBACK_HIGH_N, CORE_ARM, PROTECT_ARMS["draw1"]):
        issues.update(arms.get(arm, {}).keys())
    return sorted(issues, key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def combine_portfolio(
    *,
    portfolio: str,
    issue_budget: float,
    issues: list[str],
    arms: dict[str, dict[str, dict[str, object]]],
    allocation: dict[str, float],
    calendar: dict[str, dict[str, object]],
    fallback_arm: str,
) -> list[dict[str, object]]:
    out = []
    for issue in issues:
        profit = 0.0
        tickets = 0.0
        hits = 0.0
        parts = []
        missing_units = 0.0
        for arm, units in allocation.items():
            if units <= 0:
                continue
            row = arms.get(arm, {}).get(issue)
            if row is None:
                missing_units += units
                continue
            stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = units / stake if stake else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{arm}:{units:g}")
        if missing_units:
            row = arms.get(fallback_arm, {}).get(issue)
            if row is None:
                raise SystemExit(f"missing fallback {fallback_arm} for issue {issue}")
            stake = fnum(row.get("stake_units"), ISSUE_BUDGET)
            scale = missing_units / stake if stake else 0.0
            profit += fnum(row.get("profit_units")) * scale
            tickets += fnum(row.get("tickets")) * scale
            hits += fnum(row.get("hits")) * scale
            parts.append(f"{fallback_arm}_fallback:{missing_units:g}")
        row = {
            "portfolio": portfolio,
            "issue": issue,
            "stake_units": issue_budget,
            "profit_units": profit,
            "roi": profit / issue_budget if issue_budget else math.nan,
            "tickets": tickets,
            "hits": hits,
            "parts": ";".join(parts),
            "state": "static",
        }
        row.update(calendar.get(issue, {}))
        out.append(row)
    return out


def units_from_shares(budget: float, shares: dict[str, float]) -> dict[str, float]:
    total = sum(shares.values())
    if total <= 0:
        raise ValueError("empty shares")
    units = {arm: budget * share / total for arm, share in shares.items() if share > 0}
    drift = budget - sum(units.values())
    if abs(drift) > 1e-6:
        first = next(iter(units))
        units[first] += drift
    return units


def scaling_specs() -> list[tuple[str, float, dict[str, float], str, bool]]:
    templates: dict[str, tuple[dict[str, float], str]] = {
        "replace_n5_with_broad": (
            {
                CORE_ARM: 144,
                PROTECT_ARMS["draw1"]: 48,
                "hn_draw_free": 64,
            },
            "current core/draw sleeve, N5 replaced by N7 draw-free broad sleeve",
        ),
        "protect_heavy": (
            {
                CORE_ARM: 0.18,
                PROTECT_ARMS["draw1"]: 0.22,
                PROTECT_ARMS["draw2"]: 0.15,
                PROTECT_ARMS["alt1"]: 0.13,
                PROTECT_ARMS["full1"]: 0.20,
                PROTECT_ARMS["full3"]: 0.12,
            },
            "high-N only, extra capital goes mostly to protected N7 tickets",
        ),
        "full_smooth": (
            {
                CORE_ARM: 0.16,
                PROTECT_ARMS["draw1"]: 0.18,
                PROTECT_ARMS["alt1"]: 0.12,
                PROTECT_ARMS["full1"]: 0.27,
                PROTECT_ARMS["full3"]: 0.17,
                "hn_draw_free": 0.10,
            },
            "max protection depth; uses full-cover N7 sleeves as drawdown dampener",
        ),
        "broad_smooth": (
            {
                CORE_ARM: 0.18,
                PROTECT_ARMS["draw1"]: 0.16,
                PROTECT_ARMS["alt1"]: 0.10,
                PROTECT_ARMS["full1"]: 0.16,
                "hn_draw_free": 0.25,
                "hn_all": 0.15,
            },
            "adds many N7 broad tickets instead of lower-N sleeves",
        ),
        "hybrid_dd": (
            {
                CORE_ARM: 0.20,
                PROTECT_ARMS["draw1"]: 0.18,
                PROTECT_ARMS["draw2"]: 0.10,
                PROTECT_ARMS["alt1"]: 0.12,
                PROTECT_ARMS["full1"]: 0.16,
                PROTECT_ARMS["full3"]: 0.08,
                "hn_draw_free": 0.16,
            },
            "balanced protection plus N7 broad sleeve",
        ),
        "topology_diverse": (
            {
                CORE_ARM: 0.22,
                PROTECT_ARMS["draw1"]: 0.18,
                PROTECT_ARMS["alt1"]: 0.10,
                PROTECT_ARMS["full1"]: 0.12,
                "hn_draw_free": 0.14,
                "hn_core80_priority": 0.12,
                "hn_core80_exact": 0.08,
                "hn_priority_tail": 0.04,
            },
            "adds high-N topology diversity; keeps tail small",
        ),
    }
    specs: list[tuple[str, float, dict[str, float], str, bool]] = []
    for multiplier in (1, 2, 4, 8):
        budget = ISSUE_BUDGET * multiplier
        for label, (shares, rationale) in templates.items():
            if label == "replace_n5_with_broad":
                allocation = {arm: units * multiplier for arm, units in shares.items()}
            else:
                allocation = units_from_shares(budget, shares)
            specs.append((f"x{multiplier}_{label}", budget, allocation, rationale, False))
        specs.append(
            (
                f"x{multiplier}_current_with_n5_reference",
                budget,
                {
                    CORE_ARM: 144.0 * multiplier,
                    PROTECT_ARMS["draw1"]: 48.0 * multiplier,
                    "n5_overlap": 64.0 * multiplier,
                },
                "reference only: existing current strategy with N5 overlap",
                True,
            )
        )
    return specs


def quantile(values: list[float], q: float) -> float:
    if not values:
        return math.nan
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def summarize(rows: list[dict[str, object]], budget: float, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    profits = [fnum(row.get("profit_units")) for row in ordered]
    recent = [row for row in ordered if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    years = sorted({row_year(row) for row in ordered if row_year(row) > 0})
    maxdd = max_drawdown_units(ordered)
    full_losses = [row for row in ordered if full_loss(row)]
    out = {
        "portfolio": str(ordered[0]["portfolio"]) if ordered else "",
        "issue_budget": budget,
        "budget_multiplier": budget / ISSUE_BUDGET,
        "n_issues": len(ordered),
        "years": f"{min(years)}-{max(years)}" if years else "",
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_256": profit / (budget / ISSUE_BUDGET) if budget else math.nan,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered)
        if ordered
        else math.nan,
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered) if ordered else math.nan,
        "full_loss_rate": len(full_losses) / len(ordered) if ordered else math.nan,
        "small_loss_rate": sum(
            1 for row in ordered if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
        )
        / len(ordered)
        if ordered
        else math.nan,
        "median_issue_profit": quantile(profits, 0.5),
        "p10_issue_profit": quantile(profits, 0.10),
        "p25_issue_profit": quantile(profits, 0.25),
        "max_drawdown_units": maxdd,
        "max_drawdown_per_256": maxdd / (budget / ISSUE_BUDGET) if budget else math.nan,
        "max_drawdown_budget_equiv": abs(maxdd) / budget if budget else math.nan,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "best_issue_profit_per_256": best / (budget / ISSUE_BUDGET) if budget else math.nan,
        "roi_ex_best_issue": (profit - best) / (stake - budget) if stake > budget else math.nan,
        "recent_issues": len(recent),
        "recent_profit_units": recent_profit,
        "recent_profit_per_256": recent_profit / (budget / ISSUE_BUDGET) if budget else math.nan,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "avg_tickets_per_issue": sum(fnum(row.get("tickets")) for row in ordered) / len(ordered) if ordered else math.nan,
    }
    out.update(max_underwater_profit_window(ordered))
    out["profit_to_dd"] = profit / abs(maxdd) if maxdd else math.nan
    return out


def normalized_rows(rows: list[dict[str, object]], divisor: float) -> list[dict[str, object]]:
    out = []
    for row in rows:
        copied = dict(row)
        copied["stake_units"] = fnum(row.get("stake_units")) / divisor
        copied["profit_units"] = fnum(row.get("profit_units")) / divisor
        copied["portfolio"] = f"{row.get('portfolio')}_norm256"
        out.append(copied)
    return out


def allocation_text(allocation: dict[str, float]) -> str:
    return "; ".join(f"{arm}={units:.1f}" for arm, units in allocation.items() if units > 0)


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    arms = load_strategy_maps(args.protection_issue_profit, calendar)
    arms.update(load_high_n_maps(args.high_n_issue_profit, calendar))
    arms["n5_overlap"] = load_issue_arm(N5_OVERLAP_PATH, N5_OVERLAP_STRATEGY, "n5_overlap", calendar)
    issues = ordered_issues(calendar, arms)

    all_rows: list[dict[str, object]] = []
    norm_rows: list[dict[str, object]] = []
    series: dict[str, list[dict[str, object]]] = {}
    norm_series: dict[str, list[dict[str, object]]] = {}
    meta: dict[str, dict[str, object]] = {}
    for name, budget, allocation, rationale, is_reference in scaling_specs():
        if abs(sum(allocation.values()) - budget) > 1e-6:
            raise SystemExit(f"{name} allocation sum {sum(allocation.values())}, expected {budget}")
        rows = combine_portfolio(
            portfolio=name,
            issue_budget=budget,
            issues=issues,
            arms=arms,
            allocation=allocation,
            calendar=calendar,
            fallback_arm=FALLBACK_HIGH_N,
        )
        for row in rows:
            row.update(
                {
                    "issue_budget": budget,
                    "budget_multiplier": budget / ISSUE_BUDGET,
                    "allocation": allocation_text(allocation),
                    "rationale": rationale,
                    "is_reference": int(is_reference),
                }
            )
        all_rows.extend(rows)
        series[name] = rows
        norm = normalized_rows(rows, budget / ISSUE_BUDGET)
        norm_rows.extend(norm)
        norm_series[name] = norm
        meta[name] = {
            "issue_budget": budget,
            "budget_multiplier": budget / ISSUE_BUDGET,
            "allocation": allocation_text(allocation),
            "rationale": rationale,
            "is_reference": int(is_reference),
        }

    summaries = []
    for name, rows in series.items():
        summary = summarize(rows, fnum(meta[name]["issue_budget"]), args.recent_min_year, args.recent_max_year)
        summary.update(meta[name])
        summaries.append(summary)
    summary_df = pd.DataFrame(summaries)
    summary_df["dd_first_score"] = (
        2.2 * summary_df["max_drawdown_per_256"]
        + 42000.0 * summary_df["non_full_loss_rate"]
        + 25000.0 * summary_df["issue_win_rate"]
        - 300.0 * summary_df["max_dead_streak"]
        + 30000.0 * summary_df["roi"].clip(lower=0.0, upper=1.0)
        + 0.12 * summary_df["profit_per_256"]
    )
    summary_df = summary_df.sort_values(
        ["budget_multiplier", "is_reference", "dd_first_score"],
        ascending=[True, True, False],
    )
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "highn_only_capital_dd_issue_profit.csv", all_rows)
    write_csv_all(args.output_dir / "highn_only_capital_dd_issue_profit_norm256.csv", norm_rows)
    summary_df.to_csv(args.output_dir / "highn_only_capital_dd_summary.csv", index=False)
    write_csv(args.output_dir / "highn_only_capital_dd_annual.csv", annual)

    candidates = summary_df[summary_df["is_reference"] == 0]
    best_by_budget = (
        candidates.sort_values(["budget_multiplier", "dd_first_score"], ascending=[True, False])
        .groupby("budget_multiplier", as_index=False)
        .head(1)
    )
    best_dd_by_budget = (
        candidates.sort_values(["budget_multiplier", "max_drawdown_per_256"], ascending=[True, False])
        .groupby("budget_multiplier", as_index=False)
        .head(1)
    )
    refs = summary_df[summary_df["is_reference"] == 1]
    selected_names = set(best_by_budget["portfolio"].tolist() + best_dd_by_budget["portfolio"].tolist())
    selected_names.update(refs["portfolio"].tolist())
    selected = summary_df[summary_df["portfolio"].isin(selected_names)].copy()

    plot_names = []
    for frame in (refs, best_by_budget, best_dd_by_budget):
        for name in frame["portfolio"].tolist():
            if name not in plot_names:
                plot_names.append(name)
    write_equity_svg(args.figure_path, {name: series[name] for name in plot_names[:10]}, calendar)
    write_equity_svg(args.norm_figure_path, {name: norm_series[name] for name in plot_names[:10]}, calendar)

    top_dd = candidates.sort_values(["max_drawdown_per_256", "profit_per_256"], ascending=[False, False]).head(12)
    top_score = candidates.sort_values(["dd_first_score"], ascending=False).head(12)
    min_roi = candidates[candidates["roi"] >= args.min_roi].copy()
    top_dd_roi = min_roi.sort_values(["max_drawdown_per_256", "profit_per_256"], ascending=[False, False]).head(12)
    report = [
        "# N7 High-N-Only Capital Scaling MaxDD Grid",
        "",
        "## Scope",
        "",
        "- 新候选方案不使用 N3/N4/N5。",
        "- 可用 arm：N7 core、N7 top-EV draw/alt/full protected sleeves、N7 broad/draw-free/topology sleeves。",
        "- `current_with_n5_reference` 只作历史基线，不参与候选排序。",
        f"- High-N missing issue fallback: `{FALLBACK_HIGH_N}`.",
        f"- Minimum ROI reference for DD table: `{args.min_roi}`.",
        "",
        "## Best DD-First By Budget",
        "",
        md_table(
            best_by_budget[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "roi_ex_best_issue",
                    "dd_first_score",
                ]
            ].to_dict("records"),
            limit=10,
        ),
        "",
        "## Lowest MaxDD Per 256",
        "",
        md_table(
            top_dd[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
                    "max_drawdown_per_256",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        f"## Lowest MaxDD Per 256 With ROI >= {args.min_roi}",
        "",
        md_table(
            top_dd_roi[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
                    "max_drawdown_per_256",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "roi_ex_best_issue",
                ]
            ].to_dict("records"),
            limit=12,
        ),
        "",
        "## Selected Vs Current Reference",
        "",
        md_table(
            selected[
                [
                    "portfolio",
                    "is_reference",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
                    "max_drawdown_per_256",
                    "max_drawdown_budget_equiv",
                    "max_dead_streak",
                    "recent_profit_per_256",
                    "avg_tickets_per_issue",
                ]
            ].sort_values(["issue_budget", "is_reference", "max_drawdown_per_256"], ascending=[True, True, False]).to_dict("records"),
            limit=40,
        ),
        "",
        "## Top DD-First Score",
        "",
        md_table(
            top_score[
                [
                    "portfolio",
                    "issue_budget",
                    "profit_per_256",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "full_loss_rate",
                    "max_drawdown_per_256",
                    "max_dead_streak",
                    "dd_first_score",
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
                    "is_reference",
                    "issue_budget",
                    "allocation",
                    "rationale",
                ]
            ].sort_values(["issue_budget", "is_reference", "portfolio"]).to_dict("records"),
            limit=80,
        ),
        "",
        "## Interpretation",
        "",
        "- 如果 high-N-only 方案的 `max_drawdown_per_256` 低于 current reference，说明增加资金用于 N7 多样性/保护本身能降低单位预算回撤。",
        "- 如果只能靠 reference 里的 N5 才能明显降 DD，说明高 N 内部保护还不够，需要继续从 near-miss 规则里做更精准保护，而不是扩大 broad sleeve。",
        f"- Absolute figure: `{args.figure_path}`",
        f"- Normalized figure: `{args.norm_figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.figure_path}")
    print(f"Wrote {args.norm_figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--protection-issue-profit", type=Path, default=PROTECTION_ISSUE_PATH)
    parser.add_argument("--high-n-issue-profit", type=Path, default=HIGH_N_ISSUE_PATH)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--min-roi", type=float, default=0.5)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_highn_only_capital_dd_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_highn_only_capital_dd_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_highn_only_capital_dd_absolute_2026-06-28.svg"),
    )
    parser.add_argument(
        "--norm-figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_highn_only_capital_dd_norm256_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
