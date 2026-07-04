#!/usr/bin/env python3
"""Dynamic allocation among fixed-256 protected N7/N5 ratio candidates."""
from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_high_n_fixed256_diversity import (
    annual_rows,
    fnum,
    full_loss,
    load_issue_calendar,
    max_dead_streak,
    max_drawdown_units,
    max_loss_streak,
    max_underwater,
    row_order,
    row_year,
    write_equity_svg,
)
from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


BASELINE = "grid_core192_n5ov64"
NORMAL = "grid_c144_p48_draw_top_ev_k1_n5ov64"
BALANCED = "grid_c128_p48_draw_top_ev_k1_n5ov80"
SAFE = "grid_c128_p16_draw_top_ev_k1_n5ov112"
ULTRA_SAFE = "grid_c128_p16_full_top_ev_k3_n5ov112"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv_all(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    first_keys = list(rows[0].keys())
    extra = sorted({key for row in rows for key in row.keys()} - set(first_keys))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=first_keys + extra)
        writer.writeheader()
        writer.writerows(rows)


def load_portfolios(path: Path, calendar: dict[str, dict[str, object]]) -> dict[str, dict[str, dict[str, object]]]:
    out: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in read_csv_rows(path):
        copied = dict(row)
        copied.update(calendar.get(str(row["issue"]), {}))
        out[str(row["portfolio"])][str(row["issue"])] = copied
    return dict(out)


def ordered_issues(rows_by_portfolio: dict[str, dict[str, dict[str, object]]], calendar: dict[str, dict[str, object]]) -> list[str]:
    base = rows_by_portfolio.get(BASELINE) or next(iter(rows_by_portfolio.values()))
    return sorted(base.keys(), key=lambda issue: int(calendar.get(issue, {}).get("issue_order", 10**9)))


def specs() -> list[dict[str, object]]:
    return [
        {"policy": f"fixed::{BASELINE}", "kind": "fixed", "normal": BASELINE},
        {"policy": f"fixed::{NORMAL}", "kind": "fixed", "normal": NORMAL},
        {"policy": f"fixed::{BALANCED}", "kind": "fixed", "normal": BALANCED},
        {"policy": f"fixed::{SAFE}", "kind": "fixed", "normal": SAFE},
        {
            "policy": "dd10_15_normal_balanced_safe",
            "kind": "dynamic",
            "normal": NORMAL,
            "balanced": BALANCED,
            "safe": SAFE,
            "dd_balanced": 10000.0,
            "dd_safe": 15000.0,
            "loss_balanced": 8,
            "loss_safe": 14,
            "dead_balanced": 4,
            "dead_safe": 7,
        },
        {
            "policy": "dd8_13_normal_balanced_safe",
            "kind": "dynamic",
            "normal": NORMAL,
            "balanced": BALANCED,
            "safe": SAFE,
            "dd_balanced": 8000.0,
            "dd_safe": 13000.0,
            "loss_balanced": 6,
            "loss_safe": 12,
            "dead_balanced": 3,
            "dead_safe": 6,
        },
        {
            "policy": "dd12_16_normal_balanced_safe",
            "kind": "dynamic",
            "normal": NORMAL,
            "balanced": BALANCED,
            "safe": SAFE,
            "dd_balanced": 12000.0,
            "dd_safe": 16000.0,
            "loss_balanced": 10,
            "loss_safe": 16,
            "dead_balanced": 5,
            "dead_safe": 8,
        },
        {
            "policy": "dd10_15_normal_balanced_ultra",
            "kind": "dynamic",
            "normal": NORMAL,
            "balanced": BALANCED,
            "safe": ULTRA_SAFE,
            "dd_balanced": 10000.0,
            "dd_safe": 15000.0,
            "loss_balanced": 8,
            "loss_safe": 14,
            "dead_balanced": 4,
            "dead_safe": 7,
        },
        {
            "policy": "loss_only_8_14",
            "kind": "dynamic",
            "normal": NORMAL,
            "balanced": BALANCED,
            "safe": SAFE,
            "dd_balanced": 10**9,
            "dd_safe": 10**9,
            "loss_balanced": 8,
            "loss_safe": 14,
            "dead_balanced": 4,
            "dead_safe": 7,
        },
        {
            "policy": "dd_only_10_15",
            "kind": "dynamic",
            "normal": NORMAL,
            "balanced": BALANCED,
            "safe": SAFE,
            "dd_balanced": 10000.0,
            "dd_safe": 15000.0,
            "loss_balanced": 10**9,
            "loss_safe": 10**9,
            "dead_balanced": 10**9,
            "dead_safe": 10**9,
        },
    ]


def choose_model(spec: dict[str, object], state: dict[str, object]) -> tuple[str, str]:
    if spec["kind"] == "fixed":
        return str(spec["normal"]), "fixed"
    dd = fnum(state.get("drawdown_depth_before_units"))
    loss = int(state.get("loss_streak", 0))
    dead = int(state.get("dead_streak", 0))
    if dd >= fnum(spec["dd_safe"]) or loss >= int(spec["loss_safe"]) or dead >= int(spec["dead_safe"]):
        return str(spec["safe"]), "safe"
    if dd >= fnum(spec["dd_balanced"]) or loss >= int(spec["loss_balanced"]) or dead >= int(spec["dead_balanced"]):
        return str(spec["balanced"]), "balanced"
    return str(spec["normal"]), "normal"


def replay(
    spec: dict[str, object],
    *,
    rows_by_portfolio: dict[str, dict[str, dict[str, object]]],
    issues: list[str],
) -> list[dict[str, object]]:
    equity = 0.0
    peak = 0.0
    loss_streak = 0
    dead_streak = 0
    out = []
    for issue in issues:
        state = {
            "equity_before": equity,
            "drawdown_depth_before_units": peak - equity,
            "loss_streak": loss_streak,
            "dead_streak": dead_streak,
        }
        model, state_label = choose_model(spec, state)
        source = rows_by_portfolio[model][issue]
        profit = fnum(source.get("profit_units"))
        row = dict(source)
        row.update(
            {
                "portfolio": str(spec["policy"]),
                "selected_model": model,
                "state": state_label,
                **state,
            }
        )
        equity += profit
        peak = max(peak, equity)
        row["equity_after"] = equity
        row["drawdown_after_units"] = equity - peak
        if fnum(row.get("profit_units")) <= 0:
            loss_streak += 1
        else:
            loss_streak = 0
        if full_loss(row):
            dead_streak += 1
        else:
            dead_streak = 0
        out.append(row)
    return out


def summarize_policy(rows: list[dict[str, object]], recent_min_year: int, recent_max_year: int) -> dict[str, object]:
    ordered = sorted(rows, key=row_order)
    stake = sum(fnum(row.get("stake_units")) for row in ordered)
    profit = sum(fnum(row.get("profit_units")) for row in ordered)
    best = max((fnum(row.get("profit_units")) for row in ordered), default=0.0)
    recent = [row for row in ordered if recent_min_year <= row_year(row) <= recent_max_year]
    recent_stake = sum(fnum(row.get("stake_units")) for row in recent)
    recent_profit = sum(fnum(row.get("profit_units")) for row in recent)
    recent_best = max((fnum(row.get("profit_units")) for row in recent), default=0.0)
    model_counts = Counter(str(row.get("selected_model")) for row in ordered)
    state_counts = Counter(str(row.get("state")) for row in ordered)
    out = {
        "portfolio": str(ordered[0]["portfolio"]) if ordered else "",
        "n_issues": len(ordered),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in ordered if fnum(row.get("profit_units")) > 0) / len(ordered)
        if ordered
        else math.nan,
        "non_full_loss_rate": sum(1 for row in ordered if not full_loss(row)) / len(ordered) if ordered else math.nan,
        "small_loss_rate": sum(
            1 for row in ordered if -fnum(row.get("stake_units")) < fnum(row.get("profit_units")) <= 0
        )
        / len(ordered)
        if ordered
        else math.nan,
        "max_drawdown_units": max_drawdown_units(ordered),
        "max_drawdown_full_loss_equiv": abs(max_drawdown_units(ordered)) / 256.0,
        "max_loss_streak": max_loss_streak(ordered),
        "max_dead_streak": max_dead_streak(ordered),
        "best_issue_profit_units": best,
        "roi_ex_best_issue": (profit - best) / (stake - 256.0) if stake > 256 else math.nan,
        "recent_profit_units": recent_profit,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_roi_ex_best_issue": (recent_profit - recent_best) / (recent_stake - 256.0)
        if recent_stake > 256
        else math.nan,
        "model_mix": ";".join(f"{key}:{value}" for key, value in sorted(model_counts.items())),
        "state_mix": ";".join(f"{key}:{value}" for key, value in sorted(state_counts.items())),
    }
    out.update(max_underwater(ordered))
    return out


def run(args: argparse.Namespace) -> None:
    calendar = load_issue_calendar(args.db)
    rows_by_portfolio = load_portfolios(args.grid_issue_profit, calendar)
    issues = ordered_issues(rows_by_portfolio, calendar)

    all_rows = []
    series = {}
    for spec in specs():
        rows = replay(spec, rows_by_portfolio=rows_by_portfolio, issues=issues)
        all_rows.extend(rows)
        series[str(spec["policy"])] = rows
    summaries = [summarize_policy(rows, args.recent_min_year, args.recent_max_year) for rows in series.values()]
    summaries.sort(
        key=lambda row: (fnum(row["max_drawdown_units"]), fnum(row["profit_units"])),
        reverse=True,
    )
    annual = annual_rows(all_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "protection_dynamic_ratio_issue_profit.csv", all_rows)
    write_csv(args.output_dir / "protection_dynamic_ratio_summary.csv", summaries)
    write_csv(args.output_dir / "protection_dynamic_ratio_annual.csv", annual)

    summary_df = pd.DataFrame(summaries)
    top_dd = summary_df.sort_values(["max_drawdown_units", "profit_units"], ascending=[False, False]).head(12)
    top_profit = summary_df.sort_values(["profit_units", "max_drawdown_units"], ascending=[False, False]).head(12)
    plot_names = [
        f"fixed::{BASELINE}",
        f"fixed::{NORMAL}",
        f"fixed::{BALANCED}",
        f"fixed::{SAFE}",
        "dd10_15_normal_balanced_safe",
        "dd8_13_normal_balanced_safe",
        "dd_only_10_15",
    ]
    write_equity_svg(args.figure_path, {name: series[name] for name in plot_names if name in series}, calendar)

    best_profit_with_better_dd = summary_df[
        (summary_df["max_drawdown_units"] >= fnum(summary_df[summary_df["portfolio"] == f"fixed::{NORMAL}"].iloc[0]["max_drawdown_units"]))
        & (summary_df["profit_units"] >= fnum(summary_df[summary_df["portfolio"] == f"fixed::{NORMAL}"].iloc[0]["profit_units"]))
    ].sort_values(["profit_units"], ascending=False)

    report = [
        "# N7 Protected Dynamic Ratio",
        "",
        "## Scope",
        "",
        "- 每期仍固定 `256` units。",
        "- 不降仓，只在几个固定比例候选之间切换。",
        f"- Normal: `{NORMAL}`; balanced: `{BALANCED}`; safe: `{SAFE}`; ultra-safe: `{ULTRA_SAFE}`.",
        "- 动态选择只用当前 issue 前的组合 equity、drawdown depth、loss streak、dead streak。",
        "",
        "## Summary",
        "",
        md_table(
            summary_df[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "non_full_loss_rate",
                    "max_drawdown_units",
                    "max_drawdown_full_loss_equiv",
                    "max_dead_streak",
                    "max_loss_streak",
                    "recent_profit_units",
                    "recent_roi",
                    "roi_ex_best_issue",
                    "model_mix",
                    "state_mix",
                ]
            ].to_dict("records"),
            limit=40,
        ),
        "",
        "## Best Profit With No Worse MaxDD Than Fixed Normal",
        "",
        md_table(
            best_profit_with_better_dd[
                [
                    "portfolio",
                    "profit_units",
                    "roi",
                    "max_drawdown_units",
                    "max_dead_streak",
                    "recent_profit_units",
                    "roi_ex_best_issue",
                    "model_mix",
                ]
            ].head(12).to_dict("records"),
            limit=12,
        ),
        "",
        "## Interpretation",
        "",
        "- 如果动态组合不能同时提高 profit 并降低 maxDD，说明比例切换的信号还不够好；固定比例优先。",
        "- 若动态组合降低 maxDD 但牺牲明显 profit，可作为大回撤后的风控模式，而不是默认模式。",
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
    parser.add_argument(
        "--grid-issue-profit",
        type=Path,
        default=Path("results/n7_protection_allocation_grid_20260628/protection_allocation_grid_issue_profit.csv"),
    )
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_protection_dynamic_ratio_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n7_protection_dynamic_ratio_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n7_protection_dynamic_ratio_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
