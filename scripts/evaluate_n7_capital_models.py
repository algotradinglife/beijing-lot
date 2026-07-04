#!/usr/bin/env python3
"""Evaluate capital allocation models from existing N=7 issue results.

This is a post-selection accounting layer. It does not change ticket selection,
does not retrain any predictor, and does not use future outcomes to decide
whether to bet. It consumes per-issue realized ROI from a previous backtest and
replays different bankroll policies on the same issue sequence.
"""
from __future__ import annotations

import argparse
import csv
import math
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, write_csv


@dataclass(frozen=True)
class IssueResult:
    issue: str
    strategy: str
    tickets: int
    hits: int
    stake_units: float
    profit_units: float
    roi: float


@dataclass
class EquityPoint:
    run: str
    strategy: str
    capital_model: str
    issue: str
    year: int
    active: int
    stake_units: float
    profit_units: float
    issue_roi: float
    bankroll_before: float
    bankroll_after: float
    drawdown_pct: float
    signal: int = 0
    stopped: int = 0


def parse_floats(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def issue_year(issue: str) -> int:
    return 2000 + int(issue[:2])


def issue_sort_key(issue: str) -> tuple[int, str]:
    return issue_year(issue), issue


def load_calendar_issues(result_dir: Path) -> list[str]:
    windows = result_dir / "ev_framework_windows.csv"
    if windows.exists():
        issues = [str(row["test_issue"]) for row in read_csv(windows)]
        return sorted(set(issues), key=issue_sort_key)

    issue_profit = result_dir / "ev_framework_issue_profit.csv"
    rows = read_csv(issue_profit)
    return sorted({str(row["issue"]) for row in rows}, key=issue_sort_key)


def load_issue_results(result_dir: Path) -> dict[str, dict[str, IssueResult]]:
    path = result_dir / "ev_framework_issue_profit.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing issue result file: {path}")
    out: dict[str, dict[str, IssueResult]] = defaultdict(dict)
    for row in read_csv(path):
        stake = float(row["stake_units"])
        profit = float(row["profit_units"])
        roi = float(row["roi"]) if row.get("roi") else (profit / stake if stake else 0.0)
        issue = str(row["issue"])
        strategy = str(row["strategy"])
        out[strategy][issue] = IssueResult(
            issue=issue,
            strategy=strategy,
            tickets=int(float(row.get("tickets", 0) or 0)),
            hits=int(float(row.get("hits", 0) or 0)),
            stake_units=stake,
            profit_units=profit,
            roi=roi,
        )
    return dict(out)


def infer_issue_budget(active_rows: dict[str, IssueResult], fallback: float) -> float:
    stakes = sorted(row.stake_units for row in active_rows.values() if row.stake_units > 0)
    if not stakes:
        return fallback
    mid = len(stakes) // 2
    if len(stakes) % 2:
        return stakes[mid]
    return 0.5 * (stakes[mid - 1] + stakes[mid])


def max_drawdown(equity_points: list[EquityPoint]) -> float:
    if not equity_points:
        return 0.0
    return min(point.drawdown_pct for point in equity_points)


def years_span(calendar_issues: list[str]) -> int:
    years = [issue_year(issue) for issue in calendar_issues]
    if not years:
        return 1
    return max(1, max(years) - min(years) + 1)


def summarize_equity(
    *,
    run: str,
    strategy: str,
    capital_model: str,
    calendar_issues: list[str],
    active_results: dict[str, IssueResult],
    equity_points: list[EquityPoint],
    initial_bankroll: float,
    budget_basis_units: float,
) -> dict[str, object]:
    active_issues = sum(point.active for point in equity_points)
    signal_issues = sum(point.signal for point in equity_points)
    stopped_issues = sum(point.stopped for point in equity_points)
    deployed_stake = sum(point.stake_units for point in equity_points)
    profit = sum(point.profit_units for point in equity_points)
    final_bankroll = equity_points[-1].bankroll_after if equity_points else initial_bankroll
    issue_profits = [point.profit_units for point in equity_points if point.active]
    best_issue_profit = max(issue_profits) if issue_profits else 0.0
    worst_issue_profit = min(issue_profits) if issue_profits else 0.0
    worst_issue_roi = min((point.issue_roi for point in equity_points if point.active), default=0.0)
    best_issue_profit_share = (
        best_issue_profit / profit if profit > 0 and best_issue_profit > 0 else ""
    )
    span = years_span(calendar_issues)
    annualized = (
        (final_bankroll / initial_bankroll) ** (1.0 / span) - 1.0
        if initial_bankroll > 0 and final_bankroll > 0
        else float("nan")
    )
    return {
        "run": run,
        "strategy": strategy,
        "capital_model": capital_model,
        "calendar_issues": len(calendar_issues),
        "active_issues": active_issues,
        "deployment_rate": active_issues / len(calendar_issues) if calendar_issues else float("nan"),
        "signal_issues": signal_issues,
        "stopped_issues": stopped_issues,
        "stop_rate_vs_signal": stopped_issues / signal_issues if signal_issues else 0.0,
        "initial_bankroll": initial_bankroll,
        "final_bankroll": final_bankroll,
        "deployed_stake_units": deployed_stake,
        "budget_basis_units": budget_basis_units,
        "profit_units": profit,
        "roi_on_deployed_stake": profit / deployed_stake if deployed_stake > 0 else float("nan"),
        "roi_on_budget_basis": profit / budget_basis_units if budget_basis_units > 0 else float("nan"),
        "bankroll_return": (final_bankroll - initial_bankroll) / initial_bankroll
        if initial_bankroll > 0
        else float("nan"),
        "annualized_bankroll_return": annualized,
        "max_drawdown_pct": max_drawdown(equity_points),
        "min_bankroll": min((point.bankroll_after for point in equity_points), default=initial_bankroll),
        "ruined": 1 if any(point.bankroll_after <= 0 for point in equity_points) else 0,
        "best_issue_profit_units": best_issue_profit,
        "best_issue_profit_share": best_issue_profit_share,
        "worst_issue_profit_units": worst_issue_profit,
        "worst_issue_roi": worst_issue_roi,
        "active_source_issues": len(active_results),
    }


def replay_fixed_active(
    *,
    run: str,
    strategy: str,
    calendar_issues: list[str],
    active_results: dict[str, IssueResult],
    initial_bankroll: float,
) -> list[EquityPoint]:
    bankroll = initial_bankroll
    peak = bankroll
    points: list[EquityPoint] = []
    for issue in calendar_issues:
        before = bankroll
        result = active_results.get(issue)
        signal = 1 if result is not None else 0
        if result is None:
            stake = 0.0
            profit = 0.0
            roi = 0.0
            active = 0
        else:
            stake = result.stake_units
            profit = result.profit_units
            roi = result.roi
            active = 1
        bankroll += profit
        peak = max(peak, bankroll)
        drawdown = (bankroll - peak) / peak if peak > 0 else float("nan")
        points.append(
            EquityPoint(
                run=run,
                strategy=strategy,
                capital_model="fixed_active_issue_budget",
                issue=issue,
                year=issue_year(issue),
                active=active,
                stake_units=stake,
                profit_units=profit,
                issue_roi=roi,
                bankroll_before=before,
                bankroll_after=bankroll,
                drawdown_pct=drawdown,
                signal=signal,
            )
        )
    return points


def replay_fixed_drawdown_cooldown(
    *,
    run: str,
    strategy: str,
    capital_model: str,
    calendar_issues: list[str],
    active_results: dict[str, IssueResult],
    initial_bankroll: float,
    drawdown_threshold: float,
    cooldown_issues: int,
) -> list[EquityPoint]:
    bankroll = initial_bankroll
    peak = bankroll
    cooldown_remaining = 0
    points: list[EquityPoint] = []
    for issue in calendar_issues:
        before = bankroll
        result = active_results.get(issue)
        signal = 1 if result is not None else 0
        stopped = 0
        if result is None:
            stake = 0.0
            profit = 0.0
            roi = 0.0
            active = 0
        elif cooldown_remaining > 0:
            stake = 0.0
            profit = 0.0
            roi = result.roi
            active = 0
            stopped = 1
        else:
            stake = result.stake_units
            profit = result.profit_units
            roi = result.roi
            active = 1
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
        bankroll += profit
        peak = max(peak, bankroll)
        drawdown = (bankroll - peak) / peak if peak > 0 else float("nan")
        if active and drawdown <= -drawdown_threshold:
            cooldown_remaining = max(cooldown_remaining, cooldown_issues)
        points.append(
            EquityPoint(
                run=run,
                strategy=strategy,
                capital_model=capital_model,
                issue=issue,
                year=issue_year(issue),
                active=active,
                stake_units=stake,
                profit_units=profit,
                issue_roi=roi,
                bankroll_before=before,
                bankroll_after=bankroll,
                drawdown_pct=drawdown,
                signal=signal,
                stopped=stopped,
            )
        )
    return points


def replay_fixed_loss_streak_cooldown(
    *,
    run: str,
    strategy: str,
    capital_model: str,
    calendar_issues: list[str],
    active_results: dict[str, IssueResult],
    initial_bankroll: float,
    loss_streak_trigger: int,
    cooldown_issues: int,
    big_loss_roi_threshold: float | None,
) -> list[EquityPoint]:
    bankroll = initial_bankroll
    peak = bankroll
    cooldown_remaining = 0
    loss_streak = 0
    points: list[EquityPoint] = []
    for issue in calendar_issues:
        before = bankroll
        result = active_results.get(issue)
        signal = 1 if result is not None else 0
        stopped = 0
        if result is None:
            stake = 0.0
            profit = 0.0
            roi = 0.0
            active = 0
        elif cooldown_remaining > 0:
            stake = 0.0
            profit = 0.0
            roi = result.roi
            active = 0
            stopped = 1
        else:
            stake = result.stake_units
            profit = result.profit_units
            roi = result.roi
            active = 1
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
        bankroll += profit
        peak = max(peak, bankroll)
        drawdown = (bankroll - peak) / peak if peak > 0 else float("nan")
        if active:
            is_loss = profit < 0
            if big_loss_roi_threshold is not None:
                is_loss = roi <= big_loss_roi_threshold
            if is_loss:
                loss_streak += 1
            else:
                loss_streak = 0
            if loss_streak >= loss_streak_trigger:
                cooldown_remaining = max(cooldown_remaining, cooldown_issues)
                loss_streak = 0
        points.append(
            EquityPoint(
                run=run,
                strategy=strategy,
                capital_model=capital_model,
                issue=issue,
                year=issue_year(issue),
                active=active,
                stake_units=stake,
                profit_units=profit,
                issue_roi=roi,
                bankroll_before=before,
                bankroll_after=bankroll,
                drawdown_pct=drawdown,
                signal=signal,
                stopped=stopped,
            )
        )
    return points


def replay_fractional(
    *,
    run: str,
    strategy: str,
    capital_model: str,
    calendar_issues: list[str],
    active_results: dict[str, IssueResult],
    initial_bankroll: float,
    fraction: float,
) -> list[EquityPoint]:
    bankroll = initial_bankroll
    peak = bankroll
    points: list[EquityPoint] = []
    for issue in calendar_issues:
        before = bankroll
        result = active_results.get(issue)
        signal = 1 if result is not None else 0
        if result is None or bankroll <= 0:
            stake = 0.0
            profit = 0.0
            roi = 0.0
            active = 0
        else:
            stake = bankroll * fraction
            roi = result.roi
            profit = stake * roi
            active = 1
        bankroll += profit
        peak = max(peak, bankroll)
        drawdown = (bankroll - peak) / peak if peak > 0 else float("nan")
        points.append(
            EquityPoint(
                run=run,
                strategy=strategy,
                capital_model=capital_model,
                issue=issue,
                year=issue_year(issue),
                active=active,
                stake_units=stake,
                profit_units=profit,
                issue_roi=roi,
                bankroll_before=before,
                bankroll_after=bankroll,
                drawdown_pct=drawdown,
                signal=signal,
            )
        )
    return points


def point_to_row(point: EquityPoint) -> dict[str, object]:
    return {
        "run": point.run,
        "strategy": point.strategy,
        "capital_model": point.capital_model,
        "issue": point.issue,
        "year": point.year,
        "active": point.active,
        "stake_units": point.stake_units,
        "profit_units": point.profit_units,
        "issue_roi": point.issue_roi,
        "bankroll_before": point.bankroll_before,
        "bankroll_after": point.bankroll_after,
        "drawdown_pct": point.drawdown_pct,
        "signal": point.signal,
        "stopped": point.stopped,
    }


def annual_rows(points: list[EquityPoint]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str, int], list[EquityPoint]] = defaultdict(list)
    for point in points:
        grouped[(point.run, point.strategy, point.capital_model, point.year)].append(point)

    rows: list[dict[str, object]] = []
    for (run, strategy, model, year), vals in sorted(grouped.items()):
        vals = sorted(vals, key=lambda point: issue_sort_key(point.issue))
        start = vals[0].bankroll_before
        end = vals[-1].bankroll_after
        stake = sum(point.stake_units for point in vals)
        profit = sum(point.profit_units for point in vals)
        rows.append(
            {
                "run": run,
                "strategy": strategy,
                "capital_model": model,
                "year": year,
                "calendar_issues": len(vals),
                "active_issues": sum(point.active for point in vals),
                "signal_issues": sum(point.signal for point in vals),
                "stopped_issues": sum(point.stopped for point in vals),
                "deployed_stake_units": stake,
                "profit_units": profit,
                "roi_on_deployed_stake": profit / stake if stake > 0 else float("nan"),
                "start_bankroll": start,
                "end_bankroll": end,
                "bankroll_return": (end - start) / start if start > 0 else float("nan"),
                "max_drawdown_pct": max_drawdown(vals),
            }
        )
    return rows


def compact_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    keep = [
        "run",
        "strategy",
        "capital_model",
        "calendar_issues",
        "active_issues",
        "deployment_rate",
        "signal_issues",
        "stopped_issues",
        "stop_rate_vs_signal",
        "initial_bankroll",
        "final_bankroll",
        "deployed_stake_units",
        "profit_units",
        "roi_on_deployed_stake",
        "roi_on_budget_basis",
        "bankroll_return",
        "annualized_bankroll_return",
        "max_drawdown_pct",
        "best_issue_profit_share",
        "ruined",
    ]
    return [{key: row.get(key, "") for key in keep} for row in rows]


def model_label_for_fraction(fraction: float) -> str:
    pct = f"{fraction * 100:g}".replace(".", "p")
    return f"fractional_bankroll_{pct}pct"


def pct_label(value: float) -> str:
    return f"{value * 100:g}pct".replace(".", "p")


def run(args: argparse.Namespace) -> None:
    pattern = re.compile(args.strategy_regex) if args.strategy_regex else None
    all_summary: list[dict[str, object]] = []
    all_points: list[EquityPoint] = []

    for result_dir in args.result_dirs:
        result_dir = result_dir.resolve()
        run_label = result_dir.name
        calendar_issues = load_calendar_issues(result_dir)
        by_strategy = load_issue_results(result_dir)
        for strategy, active_results in sorted(by_strategy.items()):
            if pattern is not None and pattern.search(strategy) is None:
                continue
            issue_budget = infer_issue_budget(active_results, args.calendar_budget_units)

            fixed_points = replay_fixed_active(
                run=run_label,
                strategy=strategy,
                calendar_issues=calendar_issues,
                active_results=active_results,
                initial_bankroll=args.initial_bankroll,
            )
            all_points.extend(fixed_points)
            all_summary.append(
                summarize_equity(
                    run=run_label,
                    strategy=strategy,
                    capital_model="fixed_active_issue_budget",
                    calendar_issues=calendar_issues,
                    active_results=active_results,
                    equity_points=fixed_points,
                    initial_bankroll=args.initial_bankroll,
                    budget_basis_units=sum(point.stake_units for point in fixed_points),
                )
            )
            all_summary.append(
                summarize_equity(
                    run=run_label,
                    strategy=strategy,
                    capital_model="fixed_calendar_issue_budget",
                    calendar_issues=calendar_issues,
                    active_results=active_results,
                    equity_points=fixed_points,
                    initial_bankroll=args.initial_bankroll,
                    budget_basis_units=len(calendar_issues) * issue_budget,
                )
            )

            for drawdown in args.stop_drawdowns:
                for cooldown in args.stop_cooldowns:
                    label = f"fixed_stop_dd{pct_label(drawdown)}_cool{cooldown}"
                    stop_points = replay_fixed_drawdown_cooldown(
                        run=run_label,
                        strategy=strategy,
                        capital_model=label,
                        calendar_issues=calendar_issues,
                        active_results=active_results,
                        initial_bankroll=args.initial_bankroll,
                        drawdown_threshold=drawdown,
                        cooldown_issues=cooldown,
                    )
                    all_points.extend(stop_points)
                    all_summary.append(
                        summarize_equity(
                            run=run_label,
                            strategy=strategy,
                            capital_model=label,
                            calendar_issues=calendar_issues,
                            active_results=active_results,
                            equity_points=stop_points,
                            initial_bankroll=args.initial_bankroll,
                            budget_basis_units=sum(point.stake_units for point in stop_points),
                        )
                    )

            for streak in args.stop_loss_streaks:
                for cooldown in args.stop_cooldowns:
                    label = f"fixed_stop_loss{streak}_cool{cooldown}"
                    stop_points = replay_fixed_loss_streak_cooldown(
                        run=run_label,
                        strategy=strategy,
                        capital_model=label,
                        calendar_issues=calendar_issues,
                        active_results=active_results,
                        initial_bankroll=args.initial_bankroll,
                        loss_streak_trigger=streak,
                        cooldown_issues=cooldown,
                        big_loss_roi_threshold=None,
                    )
                    all_points.extend(stop_points)
                    all_summary.append(
                        summarize_equity(
                            run=run_label,
                            strategy=strategy,
                            capital_model=label,
                            calendar_issues=calendar_issues,
                            active_results=active_results,
                            equity_points=stop_points,
                            initial_bankroll=args.initial_bankroll,
                            budget_basis_units=sum(point.stake_units for point in stop_points),
                        )
                    )
                    label = f"fixed_stop_bigloss{streak}_cool{cooldown}"
                    stop_points = replay_fixed_loss_streak_cooldown(
                        run=run_label,
                        strategy=strategy,
                        capital_model=label,
                        calendar_issues=calendar_issues,
                        active_results=active_results,
                        initial_bankroll=args.initial_bankroll,
                        loss_streak_trigger=streak,
                        cooldown_issues=cooldown,
                        big_loss_roi_threshold=args.big_loss_roi_threshold,
                    )
                    all_points.extend(stop_points)
                    all_summary.append(
                        summarize_equity(
                            run=run_label,
                            strategy=strategy,
                            capital_model=label,
                            calendar_issues=calendar_issues,
                            active_results=active_results,
                            equity_points=stop_points,
                            initial_bankroll=args.initial_bankroll,
                            budget_basis_units=sum(point.stake_units for point in stop_points),
                        )
                    )

            for fraction in args.fractions:
                label = model_label_for_fraction(fraction)
                frac_points = replay_fractional(
                    run=run_label,
                    strategy=strategy,
                    capital_model=label,
                    calendar_issues=calendar_issues,
                    active_results=active_results,
                    initial_bankroll=args.initial_bankroll,
                    fraction=fraction,
                )
                all_points.extend(frac_points)
                all_summary.append(
                    summarize_equity(
                        run=run_label,
                        strategy=strategy,
                        capital_model=label,
                        calendar_issues=calendar_issues,
                        active_results=active_results,
                        equity_points=frac_points,
                        initial_bankroll=args.initial_bankroll,
                        budget_basis_units=sum(point.stake_units for point in frac_points),
                    )
                )

    all_summary.sort(
        key=lambda row: (
            str(row["strategy"]),
            str(row["capital_model"]),
            str(row["run"]),
        )
    )
    point_rows = [point_to_row(point) for point in all_points]
    ann = annual_rows(all_points)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "capital_model_summary.csv", all_summary)
    write_csv(out / "capital_model_equity_curve.csv", point_rows)
    write_csv(out / "capital_model_annual_summary.csv", ann)

    report = [
        "# N=7 capital model replay",
        "",
        "This report replays existing per-issue strategy returns under different",
        "capital allocation models. It does not change the selector.",
        "",
        f"- Initial bankroll: `{args.initial_bankroll}`",
        f"- Calendar budget fallback: `{args.calendar_budget_units}`",
        f"- Fractional bankroll rates: `{','.join(str(x) for x in args.fractions)}`",
        f"- Stop drawdowns: `{','.join(str(x) for x in args.stop_drawdowns)}`",
        f"- Stop loss streaks: `{','.join(str(x) for x in args.stop_loss_streaks)}`",
        f"- Stop cooldown issues: `{','.join(str(x) for x in args.stop_cooldowns)}`",
        f"- Big loss ROI threshold: `{args.big_loss_roi_threshold}`",
        f"- Strategy regex: `{args.strategy_regex}`",
        "",
        "## Summary",
        "",
        md_table(compact_summary(all_summary), limit=200),
        "## Files",
        "",
        "- `capital_model_summary.csv`",
        "- `capital_model_equity_curve.csv`",
        "- `capital_model_annual_summary.csv`",
        "",
    ]
    (out / "capital_model_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'capital_model_report.md'}")
    print(f"Wrote {len(all_summary)} summary rows and {len(point_rows)} equity rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dirs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_capital_models"))
    parser.add_argument("--strategy-regex", default=r"^ev_")
    parser.add_argument("--initial-bankroll", type=float, default=10000.0)
    parser.add_argument("--calendar-budget-units", type=float, default=256.0)
    parser.add_argument("--fractions", type=parse_floats, default=parse_floats("0.005,0.01,0.02,0.05"))
    parser.add_argument("--stop-drawdowns", type=parse_floats, default=parse_floats("0.3,0.5"))
    parser.add_argument("--stop-loss-streaks", type=parse_ints, default=parse_ints("3,5"))
    parser.add_argument("--stop-cooldowns", type=parse_ints, default=parse_ints("3,6,12"))
    parser.add_argument("--big-loss-roi-threshold", type=float, default=-0.75)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
