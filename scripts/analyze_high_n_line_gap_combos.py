#!/usr/bin/env python3
"""Analyze line_gap combinations inside the high-N ticket pool.

This consumes ``high_n_selector_enriched_source_tickets.csv`` from
``evaluate_high_n_selector.py`` and reports:

* line_gap support-net buckets;
* topology x line_gap support-net combinations;
* exact 6n0+1p3 line_gap sensitivity;
* same-budget active-issue replay for candidate combinations.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table


SOURCE = "ev_m0p95_p0p8_full_opt__budget256_fractional"


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


def support_bucket(value: object) -> str:
    v = fnum(value)
    if v <= -3:
        return "<=-3"
    if v <= -1:
        return "-2:-1"
    if v == 0:
        return "0"
    if v <= 2:
        return "1:2"
    return ">=3"


def abs_gap_bucket(value: object) -> str:
    v = fnum(value)
    if v < 0.20:
        return "<0.20"
    if v < 0.30:
        return "0.20-0.30"
    if v < 0.40:
        return "0.30-0.40"
    return ">=0.40"


def gap_shape(row: pd.Series) -> str:
    pos = int(fnum(row.get("line_gap_positive_legs")))
    neg = int(fnum(row.get("line_gap_negative_legs")))
    flat = int(fnum(row.get("line_gap_flat_legs")))
    if pos == 0 and neg == 0:
        return "all_flat"
    if pos > 0 and neg == 0:
        return "positive_only"
    if neg > 0 and pos == 0:
        return "negative_only"
    if pos == neg:
        return "balanced_pos_neg"
    return "pos_dominant" if pos > neg else "neg_dominant"


def max_drawdown(profits: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def raw_summary(df: pd.DataFrame, group_cols: list[str], min_tickets: int) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_cols, observed=True, dropna=False):
        if len(group) < min_tickets:
            continue
        if not isinstance(key, tuple):
            key = (key,)
        stake = float(pd.to_numeric(group["stake_units"], errors="coerce").sum())
        profit = float(pd.to_numeric(group["profit_units"], errors="coerce").sum())
        hits = float(pd.to_numeric(group["hit"], errors="coerce").sum())
        row = {col: value for col, value in zip(group_cols, key)}
        row.update(
            {
                "tickets": len(group),
                "issues": group["issue"].nunique(),
                "hit_rate": hits / len(group) if len(group) else math.nan,
                "stake_units": stake,
                "profit_units": profit,
                "raw_roi": profit / stake if stake else math.nan,
                "avg_abs_line_gap": float(pd.to_numeric(group["avg_abs_line_gap"], errors="coerce").mean()),
                "avg_ll_good_count": float(pd.to_numeric(group["ll_good_count"], errors="coerce").mean()),
                "avg_ll_bad_count": float(pd.to_numeric(group["ll_bad_count"], errors="coerce").mean()),
                "avg_pred_ev_per_stake": float(pd.to_numeric(group["pred_ev_per_stake"], errors="coerce").mean()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("profit_units", ascending=False)


def replay_filter(
    df: pd.DataFrame,
    *,
    name: str,
    mask: pd.Series,
    issue_budget: float,
) -> dict[str, object]:
    selected = df[mask].copy()
    issue_rows = []
    for issue, group in selected.groupby("issue", sort=True):
        stake = float(pd.to_numeric(group["stake_units"], errors="coerce").sum())
        if stake <= 0:
            continue
        scale = issue_budget / stake
        profit = float((pd.to_numeric(group["profit_units"], errors="coerce") * scale).sum())
        issue_rows.append(
            {
                "issue": str(issue),
                "year": issue_year(issue),
                "tickets": len(group),
                "hits": int(pd.to_numeric(group["hit"], errors="coerce").sum()),
                "profit_units": profit,
                "stake_units": issue_budget,
            }
        )
    if not issue_rows:
        return {
            "combo": name,
            "issues": 0,
            "tickets": 0,
            "stake_units": 0.0,
            "profit_units": 0.0,
            "roi": math.nan,
        }
    profits = [fnum(row["profit_units"]) for row in issue_rows]
    stake = issue_budget * len(issue_rows)
    profit = sum(profits)
    best = max(profits)
    ex_best_profit = profit - best
    ex_best_stake = stake - issue_budget if best > 0 else stake
    recent = [row for row in issue_rows if 2023 <= int(row["year"]) <= 2025]
    recent_profit = sum(fnum(row["profit_units"]) for row in recent)
    recent_stake = issue_budget * len(recent)
    return {
        "combo": name,
        "issues": len(issue_rows),
        "tickets": sum(int(row["tickets"]) for row in issue_rows),
        "stake_units": stake,
        "profit_units": profit,
        "roi": profit / stake if stake else math.nan,
        "issue_win_rate": sum(1 for row in issue_rows if fnum(row["profit_units"]) > 0) / len(issue_rows),
        "max_drawdown_units": max_drawdown(profits),
        "best_issue_profit": best,
        "best_issue_profit_share": best / profit if profit > 0 else math.nan,
        "ex_best_roi": ex_best_profit / ex_best_stake if ex_best_stake > 0 else math.nan,
        "recent_issues": len(recent),
        "recent_profit_units": recent_profit,
        "recent_roi": recent_profit / recent_stake if recent_stake else math.nan,
        "recent_max_drawdown_units": max_drawdown([fnum(row["profit_units"]) for row in recent]),
    }


def replay_combos(df: pd.DataFrame, issue_budget: float) -> pd.DataFrame:
    combos: list[tuple[str, pd.Series]] = []
    combos.append(("all", pd.Series(True, index=df.index)))
    combos.append(("net_0", df["linegap_net_bucket"] == "0"))
    combos.append(("net_positive_1plus", df["line_gap_support_net"] >= 1))
    combos.append(("net_negative_1plus", df["line_gap_support_net"] <= -1))
    combos.append(("net_abs_ge3", df["line_gap_support_net"].abs() >= 3))
    combos.append(("flat_shape", df["linegap_shape"] == "all_flat"))
    combos.append(("exact_6n0_1p3_net0", (df["topology"] == "neg0_6_pos3_1_draw_0") & (df["linegap_net_bucket"] == "0")))
    combos.append(("exact_6n0_1p3_net_pos", (df["topology"] == "neg0_6_pos3_1_draw_0") & (df["line_gap_support_net"] >= 1)))
    combos.append(("exact_6n0_1p3_net_neg", (df["topology"] == "neg0_6_pos3_1_draw_0") & (df["line_gap_support_net"] <= -1)))
    combos.append(("neg0_7_net0", (df["topology"] == "neg0_7_pos3_0_draw_0") & (df["linegap_net_bucket"] == "0")))
    combos.append(("neg0_7_net_pos", (df["topology"] == "neg0_7_pos3_0_draw_0") & (df["line_gap_support_net"] >= 1)))
    combos.append(("neg0_7_net_neg", (df["topology"] == "neg0_7_pos3_0_draw_0") & (df["line_gap_support_net"] <= -1)))
    combos.append(("neg0_4_pos3_3_net_pos", (df["topology"] == "neg0_4_pos3_3_draw_0") & (df["line_gap_support_net"] >= 1)))
    combos.append(("neg0_4_pos3_3_net0", (df["topology"] == "neg0_4_pos3_3_draw_0") & (df["linegap_net_bucket"] == "0")))
    return pd.DataFrame(
        [replay_filter(df, name=name, mask=mask, issue_budget=issue_budget) for name, mask in combos]
    ).sort_values("recent_profit_units", ascending=False)


def run(args: argparse.Namespace) -> None:
    tickets = pd.read_csv(args.enriched_ticket_path)
    tickets = tickets[tickets["strategy"] == args.source_strategy].copy()
    tickets["year"] = tickets["issue"].map(issue_year)
    tickets["linegap_net_bucket"] = tickets["line_gap_support_net"].map(support_bucket)
    tickets["abs_gap_bucket"] = tickets["avg_abs_line_gap"].map(abs_gap_bucket)
    tickets["linegap_shape"] = tickets.apply(gap_shape, axis=1)

    recent = tickets[tickets["year"].between(2023, 2025)].copy()
    all_net = raw_summary(tickets, ["linegap_net_bucket"], args.min_tickets)
    recent_net = raw_summary(recent, ["linegap_net_bucket"], args.min_tickets)
    recent_topology_net = raw_summary(recent, ["topology", "linegap_net_bucket"], args.min_topology_tickets)
    recent_shape = raw_summary(recent, ["linegap_shape"], args.min_tickets)
    recent_abs_gap = raw_summary(recent, ["abs_gap_bucket"], args.min_tickets)
    replay = replay_combos(tickets, args.issue_budget)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_net.to_csv(args.output_dir / "linegap_all_net_bucket.csv", index=False)
    recent_net.to_csv(args.output_dir / "linegap_recent_net_bucket.csv", index=False)
    recent_topology_net.to_csv(args.output_dir / "linegap_recent_topology_net.csv", index=False)
    recent_shape.to_csv(args.output_dir / "linegap_recent_shape.csv", index=False)
    recent_abs_gap.to_csv(args.output_dir / "linegap_recent_abs_gap.csv", index=False)
    replay.to_csv(args.output_dir / "linegap_same_budget_combo_replay.csv", index=False)

    report = [
        "# High-N line_gap combo audit",
        "",
        "## Scope",
        "",
        f"- Source strategy: `{args.source_strategy}`",
        f"- Input: `{args.enriched_ticket_path}`",
        "- `line_gap = -beidan_handicap - asian_handicap_1h` is already joined in the enriched ticket file.",
        "- Positive support net means the chosen outcomes are more aligned with the line_gap direction; `0` means mostly flat/neutral or balanced.",
        "",
        "## Same-Budget Combo Replay",
        "",
        md_table(
            replay[
                [
                    "combo",
                    "issues",
                    "tickets",
                    "profit_units",
                    "roi",
                    "issue_win_rate",
                    "max_drawdown_units",
                    "ex_best_roi",
                    "recent_issues",
                    "recent_profit_units",
                    "recent_roi",
                    "recent_max_drawdown_units",
                ]
            ].to_dict("records"),
            limit=40,
        ),
        "",
        "## Recent line_gap Net Buckets",
        "",
        md_table(
            recent_net[
                [
                    "linegap_net_bucket",
                    "tickets",
                    "issues",
                    "hit_rate",
                    "profit_units",
                    "raw_roi",
                    "avg_abs_line_gap",
                    "avg_ll_good_count",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Recent Topology x line_gap Net",
        "",
        md_table(
            recent_topology_net[
                [
                    "topology",
                    "linegap_net_bucket",
                    "tickets",
                    "issues",
                    "hit_rate",
                    "profit_units",
                    "raw_roi",
                    "avg_abs_line_gap",
                    "avg_ll_good_count",
                ]
            ].head(50).to_dict("records"),
            limit=50,
        ),
        "",
        "## Recent line_gap Shape",
        "",
        md_table(
            recent_shape[
                [
                    "linegap_shape",
                    "tickets",
                    "issues",
                    "hit_rate",
                    "profit_units",
                    "raw_roi",
                    "avg_abs_line_gap",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Recent Average Absolute Gap",
        "",
        md_table(
            recent_abs_gap[
                [
                    "abs_gap_bucket",
                    "tickets",
                    "issues",
                    "hit_rate",
                    "profit_units",
                    "raw_roi",
                    "avg_abs_line_gap",
                ]
            ].to_dict("records"),
            limit=20,
        ),
        "",
        "## Read",
        "",
        "- The best recent line_gap niche is not strong positive support. It is the exact `6n0+1p3` topology with `support_net = 0`.",
        "- Positive support helps some `neg0_7` and `neg0_4_pos3_3` pockets, but the effect is small and not enough to become the main selector.",
        "- Strong absolute line_gap generally looks dangerous in this ticket pool; the high-payoff hits cluster more around neutral/balanced line_gap states.",
        "- Keep line_gap as a diagnostic/risk tag for now. Do not promote it to a hard gate ahead of topology.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'linegap_same_budget_combo_replay.csv'}`",
        f"- `{args.output_dir / 'linegap_recent_topology_net.csv'}`",
        f"- `{args.output_dir / 'linegap_recent_net_bucket.csv'}`",
        f"- `{args.output_dir / 'linegap_recent_shape.csv'}`",
        f"- `{args.output_dir / 'linegap_recent_abs_gap.csv'}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--enriched-ticket-path",
        type=Path,
        default=Path("results/high_n_selector_20260628/high_n_selector_enriched_source_tickets.csv"),
    )
    parser.add_argument("--source-strategy", default=SOURCE)
    parser.add_argument("--issue-budget", type=float, default=256.0)
    parser.add_argument("--min-tickets", type=int, default=80)
    parser.add_argument("--min-topology-tickets", type=int, default=40)
    parser.add_argument("--output-dir", type=Path, default=Path("results/high_n_linegap_combos_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/high_n_linegap_combos_2026-06-28.md"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
