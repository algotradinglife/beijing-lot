#!/usr/bin/env python3
"""Blend independent N3 selectors with the N7 reference core."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_issue_cooldown import max_underwater
from scripts.evaluate_n3_independent_selector import BASE_MODEL, BASE_POLICY, fnum, full_loss, plot_equity, write_csv_all
from scripts.evaluate_n7_dynamic_sleeve_allocator import row_order, row_year
from scripts.evaluate_n7_same_ticket_leg_coverage import max_dead_streak, max_drawdown_units
from scripts.walkforward_beidan_strategy_eval import md_table


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_floats(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def load_base(path: Path, *, policy: str, model: str) -> list[dict[str, object]]:
    rows = [dict(row) for row in read_csv(path) if row.get("policy") == policy and row.get("model") == model]
    if not rows:
        raise SystemExit(f"missing N7 base rows: policy={policy} model={model}")
    rows.sort(key=row_order)
    return rows


def load_n3(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    out: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in read_csv(path):
        out[str(row["strategy"])][str(row["issue"])] = row
    return dict(out)


def blend_rows(
    *,
    base_rows: list[dict[str, object]],
    n3_by_issue: dict[str, dict[str, str]],
    n3_strategy: str,
    core_units: float,
    sleeve_units: float,
) -> list[dict[str, object]]:
    portfolio = (
        f"core{core_units:g}_n3{sleeve_units:g}_"
        f"{n3_strategy.removeprefix('n3_').removesuffix('__budget256_fractional')}"
    ).replace(".", "p")
    out = []
    for base in base_rows:
        issue = str(base["issue"])
        n3 = n3_by_issue.get(issue)
        if n3 is None:
            base_scale = 1.0
            sleeve_scale = 0.0
            n3_profit = 0.0
            n3_stake = 0.0
        else:
            base_scale = core_units / 512.0
            sleeve_scale = sleeve_units / 256.0
            n3_profit = fnum(n3.get("profit_units")) * sleeve_scale
            n3_stake = fnum(n3.get("stake_units")) * sleeve_scale
        base_profit = fnum(base.get("profit_units")) * base_scale
        base_stake = fnum(base.get("stake_units")) * base_scale
        profit = base_profit + n3_profit
        stake = base_stake + n3_stake
        copied = dict(base)
        copied.update(
            {
                "portfolio": portfolio,
                "core_units": core_units if n3 is not None else 512.0,
                "sleeve_units": sleeve_units if n3 is not None else 0.0,
                "n3_strategy": n3_strategy,
                "n3_active": int(n3 is not None),
                "base_profit_units": base_profit,
                "base_stake_units": base_stake,
                "n3_profit_units": n3_profit,
                "n3_stake_units": n3_stake,
                "profit_units": profit,
                "stake_units": stake,
                "roi": profit / stake if stake else math.nan,
            }
        )
        out.append(copied)
    return out


def summarize(rows: list[dict[str, object]], *, recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    rows = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in rows)
    profit = sum(fnum(row.get("profit_units")) for row in rows)
    best = max((fnum(row.get("profit_units")) for row in rows), default=0.0)
    recent = [row for row in rows if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    out = {
        "portfolio": str(rows[0]["portfolio"]) if rows else "",
        "core_units": rows[0].get("core_units", "") if rows else "",
        "sleeve_units": rows[0].get("sleeve_units", "") if rows else "",
        "n3_strategy": rows[0].get("n3_strategy", "") if rows else "",
        "n_issues": len(rows),
        "n3_active_issues": sum(int(fnum(row.get("n3_active"))) for row in rows),
        "stake_units": stake,
        "profit_units": profit,
        "profit_per_issue": profit / len(rows) if rows else math.nan,
        "roi_on_512_budget": profit / (len(rows) * 512.0) if rows else math.nan,
        "issue_win_rate": sum(1 for row in rows if fnum(row.get("profit_units")) > 0) / len(rows) if rows else math.nan,
        "non_full_loss_rate": sum(1 for row in rows if not full_loss(row)) / len(rows) if rows else math.nan,
        "max_drawdown_units": max_drawdown_units(rows),
        "max_dead_streak": max_dead_streak(rows),
        "best_issue_profit_units": best,
        "roi_ex_best_on_512_budget": (profit - best) / (len(rows) * 512.0) if rows else math.nan,
        "recent_profit_units": recent_profit,
        "recent_roi_on_512_budget": recent_profit / (len(recent) * 512.0) if recent else math.nan,
        "recent_roi_ex_best_on_512_budget": (recent_profit - recent_best) / (len(recent) * 512.0)
        if recent
        else math.nan,
    }
    out.update(max_underwater(rows))
    return out


def annual_rows(issue_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, int], list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        grouped[(str(row["portfolio"]), row_year(row))].append(row)
    out = []
    for (portfolio, year), vals in sorted(grouped.items()):
        vals = sorted(vals, key=row_order)
        stake = sum(fnum(row.get("stake_units")) for row in vals)
        profit = sum(fnum(row.get("profit_units")) for row in vals)
        out.append(
            {
                "portfolio": portfolio,
                "year": year,
                "n_issues": len(vals),
                "stake_units": stake,
                "profit_units": profit,
                "roi_on_512_budget": profit / (len(vals) * 512.0) if vals else math.nan,
                "issue_win_rate": sum(1 for row in vals if fnum(row.get("profit_units")) > 0) / len(vals)
                if vals
                else math.nan,
                "non_full_loss_rate": sum(1 for row in vals if not full_loss(row)) / len(vals) if vals else math.nan,
                "max_drawdown_units": max_drawdown_units(vals),
            }
        )
    return out


def curve_rows(portfolio_rows: list[dict[str, object]], portfolios: list[str]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in portfolio_rows:
        if str(row["portfolio"]) in portfolios:
            grouped[str(row["portfolio"])].append(row)
    out = []
    for portfolio, rows in sorted(grouped.items()):
        rows = sorted(rows, key=row_order)
        cum_roi = 0.0
        cum_profit = 0.0
        for idx, row in enumerate(rows, start=1):
            profit = fnum(row.get("profit_units"))
            stake = fnum(row.get("stake_units"))
            cum_profit += profit
            cum_roi += profit / stake if stake else 0.0
            out.append(
                {
                    "strategy": portfolio,
                    "issue": row.get("issue", ""),
                    "issue_close_ts": row.get("issue_close_ts", ""),
                    "issue_order": row.get("issue_order", ""),
                    "calendar_year": row_year(row),
                    "cum_profit_units": cum_profit,
                    "cum_issue_roi_units": cum_roi,
                    "n_points": idx,
                }
            )
    return out


def compact(rows: list[dict[str, object]], limit: int = 30) -> list[dict[str, object]]:
    keep = [
        "portfolio",
        "profit_units",
        "roi_on_512_budget",
        "issue_win_rate",
        "non_full_loss_rate",
        "max_drawdown_units",
        "max_dead_streak",
        "roi_ex_best_on_512_budget",
        "recent_profit_units",
        "recent_roi_on_512_budget",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    base_rows = load_base(args.base_issue_profit, policy=args.base_policy, model=args.base_model)
    n3_maps = load_n3(args.n3_issue_profit)
    all_rows = []
    summary = []

    baseline = []
    for row in base_rows:
        copied = dict(row)
        copied.update(
            {
                "portfolio": "N7_core512",
                "core_units": 512.0,
                "sleeve_units": 0.0,
                "n3_strategy": "",
                "n3_active": 0,
            }
        )
        baseline.append(copied)
    all_rows.extend(baseline)
    summary.append(summarize(baseline, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year))

    for n3_strategy, n3_by_issue in sorted(n3_maps.items()):
        for core_units in args.core_units:
            sleeve_units = 512.0 - core_units
            if sleeve_units <= 0:
                continue
            rows = blend_rows(
                base_rows=base_rows,
                n3_by_issue=n3_by_issue,
                n3_strategy=n3_strategy,
                core_units=core_units,
                sleeve_units=sleeve_units,
            )
            all_rows.extend(rows)
            summary.append(summarize(rows, recent_min_year=args.recent_min_year, recent_max_year=args.recent_max_year))

    summary.sort(
        key=lambda row: (
            fnum(row.get("roi_on_512_budget")),
            fnum(row.get("issue_win_rate")),
            fnum(row.get("max_drawdown_units")),
        ),
        reverse=True,
    )
    dd_sorted = sorted(
        [row for row in summary if fnum(row.get("profit_units")) > 150000],
        key=lambda row: (
            fnum(row.get("max_drawdown_units")),
            fnum(row.get("profit_units")),
        ),
        reverse=True,
    )
    plot_portfolios = []
    for row in [summary[0], *dd_sorted[:5]]:
        portfolio = str(row["portfolio"])
        if portfolio not in plot_portfolios:
            plot_portfolios.append(portfolio)
    if "N7_core512" not in plot_portfolios:
        plot_portfolios.insert(0, "N7_core512")
    curves = curve_rows(all_rows, plot_portfolios)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "n3_independent_sleeve_issue_profit.csv", all_rows)
    write_csv_all(args.output_dir / "n3_independent_sleeve_summary.csv", summary)
    write_csv_all(args.output_dir / "n3_independent_sleeve_annual.csv", annual_rows(all_rows))
    write_csv_all(args.output_dir / "n3_independent_sleeve_equity_curve.csv", curves)
    plot_equity(curves, args.figure_path)

    report = [
        "# Independent N3 sleeve combo",
        "",
        "- Same 512-unit issue budget.",
        "- If an N3 selector has no active candidate for an issue, the issue falls back to full N7 core.",
        "",
        "## Sorted By ROI",
        "",
        md_table(compact(summary, limit=25)),
        "",
        "## Best Drawdown Tradeoffs With Profit > 150k",
        "",
        md_table(compact(dd_sorted, limit=20)),
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-issue-profit",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--base-policy", default=BASE_POLICY)
    parser.add_argument("--base-model", default=BASE_MODEL)
    parser.add_argument(
        "--n3-issue-profit",
        type=Path,
        default=Path("results/n3_independent_selector_20260628/n3_independent_issue_profit.csv"),
    )
    parser.add_argument("--core-units", type=parse_floats, default=parse_floats("448,384,320,256"))
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_independent_sleeve_combo_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_independent_sleeve_combo_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_independent_sleeve_combo_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
