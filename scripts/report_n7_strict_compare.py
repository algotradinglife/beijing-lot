#!/usr/bin/env python3
"""Build a strict comparison report for selected N=7 draw-cover strategies."""
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

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


STRATEGIES = (
    "draw_cover_none",
    "draw_cover_model_draw_ratio_k2",
    "draw_cover_form_low_abs_gd_10_k2",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def f(row: dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        value = float(row.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def i(row: dict[str, object], key: str, default: int = 0) -> int:
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def pct(value: float) -> str:
    return f"{100 * value:.2f}%"


def money(value: float) -> str:
    return f"{value:.2f}"


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def max_drawdown(profits: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for profit in profits:
        equity += profit
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def longest_streak(values: list[bool]) -> int:
    best = cur = 0
    for value in values:
        if value:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def year_from_issue(issue: str) -> str:
    if len(issue) >= 2 and issue[:2].isdigit():
        return f"20{issue[:2]}"
    return "unknown"


def aggregate_tickets(ticket_rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    out = defaultdict(lambda: {"tickets": 0, "hits": 0, "stake": 0.0, "profit": 0.0})
    for row in ticket_rows:
        strategy = str(row["strategy"])
        if strategy not in STRATEGIES:
            continue
        vals = out[strategy]
        vals["tickets"] += 1
        vals["hits"] += i(row, "hit")
        vals["stake"] += f(row, "stake_units")
        vals["profit"] += f(row, "profit_units")
    return dict(out)


def aggregate_issues(issue_rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    out = defaultdict(list)
    for row in issue_rows:
        strategy = str(row["strategy"])
        if strategy in STRATEGIES:
            out[strategy].append(row)
    for rows in out.values():
        rows.sort(key=lambda r: str(r["issue"]))
    return dict(out)


def strict_summary(
    summary_rows: list[dict[str, str]],
    ticket_stats: dict[str, dict[str, float]],
    issues_by_strategy: dict[str, list[dict[str, str]]],
) -> list[dict[str, object]]:
    summary_by_strategy = {str(row["strategy"]): row for row in summary_rows}
    rows: list[dict[str, object]] = []
    for strategy in STRATEGIES:
        base = summary_by_strategy[strategy]
        tickets = ticket_stats[strategy]
        issue_rows = issues_by_strategy[strategy]
        profits = [f(row, "profit_units") for row in issue_rows]
        rois = [f(row, "roi") for row in issue_rows]
        sorted_positive = sorted((p for p in profits if p > 0), reverse=True)
        total_profit = sum(profits)
        top3_share = sum(sorted_positive[:3]) / total_profit if total_profit > 0 else float("nan")
        rows.append(
            {
                "strategy": strategy,
                "stake": tickets["stake"],
                "profit": tickets["profit"],
                "roi": tickets["profit"] / tickets["stake"] if tickets["stake"] else float("nan"),
                "hit_rate": tickets["hits"] / tickets["tickets"] if tickets["tickets"] else float("nan"),
                "hit_issues": sum(1 for row in issue_rows if i(row, "hits") > 0),
                "profitable_issues": sum(1 for row in issue_rows if f(row, "profit_units") > 0),
                "median_issue_profit": percentile(profits, 0.50),
                "p25_issue_profit": percentile(profits, 0.25),
                "p75_issue_profit": percentile(profits, 0.75),
                "worst_issue_profit": min(profits) if profits else float("nan"),
                "best_issue_profit": max(profits) if profits else float("nan"),
                "top1_profit_share": f(base, "best_issue_profit_share"),
                "top3_profit_share": top3_share,
                "issue_max_drawdown_units": max_drawdown(profits),
                "issue_max_drawdown_pct_on_10000": max_drawdown(profits) / 10000.0,
                "longest_loss_issue_streak": longest_streak([p < 0 for p in profits]),
                "longest_no_hit_issue_streak": longest_streak([i(row, "hits") == 0 for row in issue_rows]),
                "max_ticket_loss_streak": i(base, "max_ticket_loss_streak"),
                "avg_issue_stake": f(base, "avg_issue_stake_units"),
                "avg_double_cover": f(base, "avg_double_cover_per_ticket"),
            }
        )
    return rows


def year_rows(issues_by_strategy: dict[str, list[dict[str, str]]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for strategy in STRATEGIES:
        grouped = defaultdict(list)
        for row in issues_by_strategy[strategy]:
            grouped[year_from_issue(str(row["issue"]))].append(row)
        for year, group in sorted(grouped.items()):
            stake = sum(f(row, "stake_units") for row in group)
            profit = sum(f(row, "profit_units") for row in group)
            rows.append(
                {
                    "strategy": strategy,
                    "year": year,
                    "issues": len(group),
                    "stake": stake,
                    "profit": profit,
                    "roi": profit / stake if stake else float("nan"),
                    "hit_issues": sum(1 for row in group if i(row, "hits") > 0),
                    "profitable_issues": sum(1 for row in group if f(row, "profit_units") > 0),
                    "worst_issue_profit": min(f(row, "profit_units") for row in group),
                    "best_issue_profit": max(f(row, "profit_units") for row in group),
                }
            )
    return rows


def incremental_rows(summary: list[dict[str, object]]) -> list[dict[str, object]]:
    base = next(row for row in summary if row["strategy"] == "draw_cover_none")
    rows = []
    for row in summary:
        if row["strategy"] == "draw_cover_none":
            continue
        extra_stake = f(row, "stake") - f(base, "stake")
        extra_profit = f(row, "profit") - f(base, "profit")
        rows.append(
            {
                "strategy": row["strategy"],
                "extra_stake": extra_stake,
                "extra_profit": extra_profit,
                "incremental_roi": extra_profit / extra_stake if extra_stake else float("nan"),
                "hit_rate_lift_pp": 100 * (f(row, "hit_rate") - f(base, "hit_rate")),
                "hit_issue_lift": i(row, "hit_issues") - i(base, "hit_issues"),
                "profitable_issue_lift": i(row, "profitable_issues") - i(base, "profitable_issues"),
                "drawdown_delta_pct_on_10000": f(row, "issue_max_drawdown_pct_on_10000") - f(base, "issue_max_drawdown_pct_on_10000"),
                "ticket_loss_streak_delta": i(row, "max_ticket_loss_streak") - i(base, "max_ticket_loss_streak"),
                "issue_loss_streak_delta": i(row, "longest_loss_issue_streak") - i(base, "longest_loss_issue_streak"),
            }
        )
    return rows


def display_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "strategy",
        "stake",
        "profit",
        "roi",
        "hit_rate",
        "hit_issues",
        "profitable_issues",
        "median_issue_profit",
        "worst_issue_profit",
        "best_issue_profit",
        "top1_profit_share",
        "top3_profit_share",
        "issue_max_drawdown_pct_on_10000",
        "longest_loss_issue_streak",
        "max_ticket_loss_streak",
    ]
    out = []
    for row in rows:
        out.append(
            {
                key: (
                    pct(f(row, key))
                    if key in {"roi", "hit_rate", "top1_profit_share", "top3_profit_share", "issue_max_drawdown_pct_on_10000"}
                    else money(f(row, key))
                    if key in {"stake", "profit", "median_issue_profit", "worst_issue_profit", "best_issue_profit"}
                    else row[key]
                )
                for key in keep
            }
        )
    return out


def display_year(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        out.append(
            {
                "strategy": row["strategy"],
                "year": row["year"],
                "issues": row["issues"],
                "stake": money(f(row, "stake")),
                "profit": money(f(row, "profit")),
                "roi": pct(f(row, "roi")),
                "hit_issues": row["hit_issues"],
                "profitable_issues": row["profitable_issues"],
            }
        )
    return out


def display_incremental(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        out.append(
            {
                "strategy": row["strategy"],
                "extra_stake": money(f(row, "extra_stake")),
                "extra_profit": money(f(row, "extra_profit")),
                "incremental_roi": pct(f(row, "incremental_roi")),
                "hit_rate_lift_pp": f"{f(row, 'hit_rate_lift_pp'):.2f}",
                "hit_issue_lift": row["hit_issue_lift"],
                "profitable_issue_lift": row["profitable_issue_lift"],
                "drawdown_delta_pct_on_10000": pct(f(row, "drawdown_delta_pct_on_10000")),
                "ticket_loss_streak_delta": row["ticket_loss_streak_delta"],
                "issue_loss_streak_delta": row["issue_loss_streak_delta"],
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    out = args.results_dir
    summary_rows = read_csv(out / "draw_cover_summary.csv")
    issue_rows = read_csv(out / "draw_cover_issue_profit.csv")
    ticket_rows = read_csv(out / "draw_cover_tickets.csv")

    ticket_stats = aggregate_tickets(ticket_rows)
    issues_by_strategy = aggregate_issues(issue_rows)
    summary = strict_summary(summary_rows, ticket_stats, issues_by_strategy)
    years = year_rows(issues_by_strategy)
    incremental = incremental_rows(summary)

    write_csv(out / "strict_compare_summary.csv", summary)
    write_csv(out / "strict_compare_year.csv", years)
    write_csv(out / "strict_compare_incremental.csv", incremental)

    report = [
        "# N=7 strict strategy comparison",
        "",
        f"- Source directory: `{out}`",
        f"- Strategies: `{', '.join(STRATEGIES)}`",
        "- Evaluation: same walk-forward windows, same base N=7 ticket set, no hindsight labels in selection.",
        "",
        "## Overall",
        md_table(display_summary(summary)),
        "## Incremental vs No Cover",
        md_table(display_incremental(incremental)),
        "## Year Split",
        md_table(display_year(years)),
        "",
        "## Notes",
        "",
        "- `draw_cover_none` keeps the highest realized ROI but has the lowest ticket hit rate and fewest hit/profitable issues.",
        "- `draw_cover_model_draw_ratio_k2` has the highest total profit among the two cover variants.",
        "- `draw_cover_form_low_abs_gd_10_k2` has the best hit spread and slightly better issue/ticket loss streak profile, with slightly lower total profit.",
        "",
        "## Files",
        "",
        "- `strict_compare_summary.csv`",
        "- `strict_compare_year.csv`",
        "- `strict_compare_incremental.csv`",
        "",
    ]
    (out / "strict_compare_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'strict_compare_report.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results/n7_strict_compare"))
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
