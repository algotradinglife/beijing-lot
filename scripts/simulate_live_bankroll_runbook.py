#!/usr/bin/env python3
"""Simulate the 10000-bankroll live runbook on historical N7 issue PnL."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_384_drawdown_dynamic import (
    SELECTED_PORTFOLIO,
    fnum,
    row_order,
    row_year,
)
from scripts.evaluate_n7_384_weak_quality_dynamic import write_equity_svg
from scripts.walkforward_beidan_strategy_eval import md_table


BASE_PORTFOLIO = SELECTED_PORTFOLIO
BASE_STAKE = 384.0
STARTING_BANKROLL = 10000.0
DEFAULT_INITIAL_CAP = 256.0
LOCK_STEP = 2000.0
LOCK_AMOUNT = 1000.0

MODE_FIXED_256 = "fixed_256"
MODE_LADDER_NO_STOP = "ladder_no_stop"
MODE_RUNBOOK_RESTART20 = "runbook_restart20"
MODES = [MODE_FIXED_256, MODE_LADDER_NO_STOP, MODE_RUNBOOK_RESTART20]


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


def load_base_issue_rows(path: Path) -> list[dict[str, object]]:
    rows = [dict(row) for row in read_csv_rows(path) if row.get("portfolio") == BASE_PORTFOLIO]
    if not rows:
        raise SystemExit(f"missing portfolio {BASE_PORTFOLIO} in {path}")
    return sorted(rows, key=row_order)


def cap_from_state(
    *,
    equity: float,
    high_watermark: float,
    previous_cap: float,
    clean_issues_since_downshift: int,
    clean_issues_at_320: int,
    last_issue_full_loss: bool,
    hard_stop: bool,
) -> tuple[float, str]:
    drawdown = max(0.0, high_watermark - equity)
    if hard_stop and (drawdown >= 3200.0 or equity < 6800.0):
        return 0.0, "hard_stop"
    if drawdown >= 3200.0 or equity < 6800.0:
        return 64.0, "red_zone_review_64"
    if drawdown >= 2500.0 or equity < 7500.0:
        return 64.0, "dd_ge2500_or_equity_lt7500"
    if drawdown >= 1800.0 or equity < 8200.0:
        return 128.0, "dd_ge1800_or_equity_lt8200"
    if drawdown >= 1000.0 or equity < 9000.0:
        return 192.0, "dd_ge1000_or_equity_lt9000"

    cap = DEFAULT_INITIAL_CAP
    reason = "normal_256"
    if equity > 15000.0 and drawdown < 750.0 and clean_issues_at_320 >= 40:
        cap = 384.0
        reason = "upsize_384"
    elif equity > 12000.0 and drawdown < 500.0 and clean_issues_since_downshift >= 40:
        cap = 320.0
        reason = "upsize_320"

    if last_issue_full_loss and cap > previous_cap:
        return previous_cap, "no_upsize_after_full_loss"
    if previous_cap < cap and cap - previous_cap > 64.0:
        return previous_cap + 64.0, "one_step_up"
    return cap, reason


def scaled_profit(base_profit: float, cap: float) -> float:
    return base_profit * cap / BASE_STAKE if cap > 0 else 0.0


def apply_profit_locks(
    *,
    equity: float,
    locked_profit: float,
    next_lock_total_wealth: float,
    high_watermark: float,
) -> tuple[float, float, float, float, float]:
    locked_now = 0.0
    total_wealth = equity + locked_profit
    while total_wealth >= next_lock_total_wealth:
        equity -= LOCK_AMOUNT
        locked_profit += LOCK_AMOUNT
        locked_now += LOCK_AMOUNT
        next_lock_total_wealth += LOCK_STEP
        total_wealth = equity + locked_profit
        # Locked capital is removed from risk capital. Reset the risk high-water
        # mark to avoid treating an intentional transfer as strategy drawdown.
        high_watermark = equity
    return equity, locked_profit, next_lock_total_wealth, high_watermark, locked_now


def simulate_mode(
    *,
    mode: str,
    base_rows: list[dict[str, object]],
    starting_bankroll: float,
    initial_cap: float,
    restart_skip_issues: int,
) -> list[dict[str, object]]:
    equity = starting_bankroll
    locked_profit = 0.0
    high_watermark = starting_bankroll
    next_lock_total_wealth = starting_bankroll + LOCK_STEP
    previous_cap = initial_cap
    clean_issues_since_downshift = 0
    clean_issues_at_320 = 0
    last_issue_full_loss = False
    stopped_remaining = 0
    review_restart_pending = False
    stop_events = 0
    live_issue_index = 0
    out: list[dict[str, object]] = []

    for idx, base in enumerate(base_rows):
        before_equity = equity
        before_locked = locked_profit
        before_total_wealth = before_equity + before_locked
        before_high_watermark = high_watermark
        before_drawdown = max(0.0, before_high_watermark - before_equity)
        base_profit = fnum(base.get("profit_units"))

        if mode == MODE_FIXED_256:
            cap = initial_cap
            cap_reason = "fixed_256"
            paper_only = False
        elif mode == MODE_LADDER_NO_STOP:
            cap, cap_reason = cap_from_state(
                equity=before_equity,
                high_watermark=before_high_watermark,
                previous_cap=previous_cap,
                clean_issues_since_downshift=clean_issues_since_downshift,
                clean_issues_at_320=clean_issues_at_320,
                last_issue_full_loss=last_issue_full_loss,
                hard_stop=False,
            )
            paper_only = False
        elif mode == MODE_RUNBOOK_RESTART20:
            if stopped_remaining > 0:
                cap = 0.0
                cap_reason = "paper_cooling"
                paper_only = True
                stopped_remaining -= 1
            elif review_restart_pending:
                # A written review can restart live betting at no more than 64.
                # Reset the risk high-water mark to the reviewed bankroll;
                # otherwise the same historical drawdown would immediately
                # trigger another hard stop without placing a ticket.
                before_high_watermark = before_equity
                before_drawdown = 0.0
                high_watermark = before_equity
                cap = 64.0
                cap_reason = "review_restart_64"
                paper_only = False
                review_restart_pending = False
                clean_issues_since_downshift = 0
                clean_issues_at_320 = 0
                previous_cap = 64.0
            else:
                cap, cap_reason = cap_from_state(
                    equity=before_equity,
                    high_watermark=before_high_watermark,
                    previous_cap=previous_cap,
                    clean_issues_since_downshift=clean_issues_since_downshift,
                    clean_issues_at_320=clean_issues_at_320,
                    last_issue_full_loss=last_issue_full_loss,
                    hard_stop=True,
                )
                paper_only = cap <= 0
                if paper_only:
                    stop_events += 1
                    stopped_remaining = restart_skip_issues
                    review_restart_pending = True
                    previous_cap = 64.0
        else:
            raise ValueError(f"unknown mode: {mode}")

        if mode == MODE_RUNBOOK_RESTART20 and cap <= 0 and cap_reason == "hard_stop":
            profit = 0.0
            stake = 0.0
        elif mode == MODE_RUNBOOK_RESTART20 and cap <= 0 and cap_reason == "paper_cooling":
            profit = 0.0
            stake = 0.0
        else:
            stake = cap
            profit = scaled_profit(base_profit, cap)

        equity += profit
        full_loss = stake > 0 and profit <= -0.999 * stake
        win = stake > 0 and profit > 0
        if stake > 0:
            live_issue_index += 1
            if cap < previous_cap:
                clean_issues_since_downshift = 0
                clean_issues_at_320 = 0
            else:
                clean_issues_since_downshift += 1
                if cap >= 320:
                    clean_issues_at_320 += 1
                else:
                    clean_issues_at_320 = 0
            previous_cap = cap
            last_issue_full_loss = full_loss
        else:
            last_issue_full_loss = False

        high_watermark = max(high_watermark, equity)
        equity, locked_profit, next_lock_total_wealth, high_watermark, locked_now = apply_profit_locks(
            equity=equity,
            locked_profit=locked_profit,
            next_lock_total_wealth=next_lock_total_wealth,
            high_watermark=high_watermark,
        )
        after_total_wealth = equity + locked_profit
        after_drawdown = max(0.0, high_watermark - equity)

        row = {
            "mode": mode,
            "issue": base.get("issue", ""),
            "issue_order": base.get("issue_order", ""),
            "calendar_year": base.get("calendar_year", ""),
            "issue_start_ts": base.get("issue_start_ts", ""),
            "issue_close_ts": base.get("issue_close_ts", ""),
            "sequence_index": idx + 1,
            "live_issue_index": live_issue_index if stake > 0 else "",
            "paper_only": int(paper_only),
            "issue_cap": cap,
            "cap_reason": cap_reason,
            "stake_units": stake,
            "base384_profit_units": base_profit,
            "profit_units": profit,
            "roi": profit / stake if stake else "",
            "win": int(win),
            "full_loss": int(full_loss),
            "equity_before": before_equity,
            "locked_profit_before": before_locked,
            "total_wealth_before": before_total_wealth,
            "high_watermark_before": before_high_watermark,
            "drawdown_before": before_drawdown,
            "equity_after": equity,
            "locked_profit_after": locked_profit,
            "total_wealth_after": after_total_wealth,
            "high_watermark_after": high_watermark,
            "drawdown_after": after_drawdown,
            "locked_now": locked_now,
            "pending_exposure_before": 0.0,
            "pending_exposure_after": 0.0,
            "stop_events_so_far": stop_events,
            "stopped_remaining": stopped_remaining,
        }
        out.append(row)
    return out


def max_drawdown_from_values(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def max_streak(rows: list[dict[str, object]], predicate) -> int:
    cur = 0
    best = 0
    for row in rows:
        if predicate(row):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def summarize_mode(rows: list[dict[str, object]], starting_bankroll: float) -> dict[str, object]:
    live = [row for row in rows if fnum(row.get("stake_units")) > 0]
    final = rows[-1] if rows else {}
    stake = sum(fnum(row.get("stake_units")) for row in live)
    profit = sum(fnum(row.get("profit_units")) for row in live)
    final_total = fnum(final.get("total_wealth_after"), starting_bankroll)
    caps = Counter(str(int(fnum(row.get("issue_cap")))) for row in live)
    recent = [row for row in live if 2023 <= row_year(row) <= 2025]
    years = sorted({row_year(row) for row in rows if row_year(row) > 0})
    return {
        "mode": rows[0].get("mode", "") if rows else "",
        "issues": len(rows),
        "live_issues": len(live),
        "skipped_issues": len(rows) - len(live),
        "stake_units": stake,
        "profit_units": profit,
        "final_equity": fnum(final.get("equity_after"), starting_bankroll),
        "locked_profit": fnum(final.get("locked_profit_after")),
        "final_total_wealth": final_total,
        "net_profit": final_total - starting_bankroll,
        "roi_on_stake": profit / stake if stake else math.nan,
        "wealth_return": final_total / starting_bankroll - 1.0,
        "min_equity": min((fnum(row.get("equity_after")) for row in rows), default=starting_bankroll),
        "max_drawdown_equity": max_drawdown_from_values(
            [starting_bankroll] + [fnum(row.get("equity_after")) for row in rows]
        ),
        "max_drawdown_total_wealth": max_drawdown_from_values(
            [starting_bankroll] + [fnum(row.get("total_wealth_after")) for row in rows]
        ),
        "issue_win_rate": sum(1 for row in live if fnum(row.get("profit_units")) > 0) / len(live)
        if live
        else math.nan,
        "full_loss_rate": sum(1 for row in live if int(fnum(row.get("full_loss"))) == 1) / len(live)
        if live
        else math.nan,
        "max_loss_streak": max_streak(live, lambda row: fnum(row.get("profit_units")) <= 0),
        "max_dead_streak": max_streak(live, lambda row: int(fnum(row.get("full_loss"))) == 1),
        "stop_events": max((int(fnum(row.get("stop_events_so_far"))) for row in rows), default=0),
        "max_cap": max((fnum(row.get("issue_cap")) for row in live), default=0.0),
        "avg_cap": sum(fnum(row.get("issue_cap")) for row in live) / len(live) if live else 0.0,
        "cap_64_issues": caps.get("64", 0),
        "cap_128_issues": caps.get("128", 0),
        "cap_192_issues": caps.get("192", 0),
        "cap_256_issues": caps.get("256", 0),
        "cap_320_issues": caps.get("320", 0),
        "cap_384_issues": caps.get("384", 0),
        "recent_live_issues": len(recent),
        "recent_profit_units": sum(fnum(row.get("profit_units")) for row in recent),
        "recent_roi_on_stake": (
            sum(fnum(row.get("profit_units")) for row in recent)
            / sum(fnum(row.get("stake_units")) for row in recent)
        )
        if recent and sum(fnum(row.get("stake_units")) for row in recent)
        else math.nan,
        "start_year": min(years) if years else "",
        "end_year": max(years) if years else "",
    }


def annual_rows(rows_by_mode: dict[str, list[dict[str, object]]], starting_bankroll: float) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for mode, rows in rows_by_mode.items():
        for year in sorted({row_year(row) for row in rows if row_year(row) > 0}):
            sub = [row for row in rows if row_year(row) == year]
            live = [row for row in sub if fnum(row.get("stake_units")) > 0]
            stake = sum(fnum(row.get("stake_units")) for row in live)
            profit = sum(fnum(row.get("profit_units")) for row in live)
            out.append(
                {
                    "mode": mode,
                    "year": year,
                    "issues": len(sub),
                    "live_issues": len(live),
                    "skipped_issues": len(sub) - len(live),
                    "stake_units": stake,
                    "profit_units": profit,
                    "roi_on_stake": profit / stake if stake else math.nan,
                    "issue_win_rate": sum(1 for row in live if fnum(row.get("profit_units")) > 0) / len(live)
                    if live
                    else math.nan,
                    "full_loss_rate": sum(1 for row in live if int(fnum(row.get("full_loss"))) == 1) / len(live)
                    if live
                    else math.nan,
                    "max_equity_drawdown_within_year": max_drawdown_from_values(
                        [fnum(sub[0].get("equity_before"), starting_bankroll)]
                        + [fnum(row.get("equity_after")) for row in sub]
                    )
                    if sub
                    else 0.0,
                    "end_equity": fnum(sub[-1].get("equity_after")) if sub else "",
                    "end_locked_profit": fnum(sub[-1].get("locked_profit_after")) if sub else "",
                    "end_total_wealth": fnum(sub[-1].get("total_wealth_after")) if sub else "",
                }
            )
    return out


def quantile(values: Iterable[float], q: float) -> float:
    ordered = sorted(value for value in values if math.isfinite(value))
    if not ordered:
        return math.nan
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def rolling_start_rows(
    *,
    base_rows: list[dict[str, object]],
    starting_bankroll: float,
    initial_cap: float,
    restart_skip_issues: int,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for start_idx in range(len(base_rows)):
        suffix = base_rows[start_idx:]
        start = suffix[0]
        for mode in MODES:
            rows = simulate_mode(
                mode=mode,
                base_rows=suffix,
                starting_bankroll=starting_bankroll,
                initial_cap=initial_cap,
                restart_skip_issues=restart_skip_issues,
            )
            summary = summarize_mode(rows, starting_bankroll)
            out.append(
                {
                    "mode": mode,
                    "start_index": start_idx + 1,
                    "start_issue": start.get("issue", ""),
                    "start_year": row_year(start),
                    "remaining_issues": len(suffix),
                    "net_profit": summary["net_profit"],
                    "final_total_wealth": summary["final_total_wealth"],
                    "min_equity": summary["min_equity"],
                    "max_drawdown_equity": summary["max_drawdown_equity"],
                    "max_drawdown_total_wealth": summary["max_drawdown_total_wealth"],
                    "live_issues": summary["live_issues"],
                    "skipped_issues": summary["skipped_issues"],
                    "stake_units": summary["stake_units"],
                    "roi_on_stake": summary["roi_on_stake"],
                    "stop_events": summary["stop_events"],
                    "profitable": int(fnum(summary["net_profit"]) > 0),
                    "breached_6800": int(fnum(summary["min_equity"]) < 6800),
                    "breached_7500": int(fnum(summary["min_equity"]) < 7500),
                }
            )
    return out


def summarize_rolling_starts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    periods = [
        ("all_starts", lambda row: True),
        ("start_2014_2022", lambda row: 2014 <= int(fnum(row.get("start_year"))) <= 2022),
        ("start_2023_2025", lambda row: 2023 <= int(fnum(row.get("start_year"))) <= 2025),
    ]
    for mode in MODES:
        mode_rows = [row for row in rows if row.get("mode") == mode]
        for period, predicate in periods:
            sub = [row for row in mode_rows if predicate(row)]
            if not sub:
                continue
            net = [fnum(row.get("net_profit")) for row in sub]
            dd = [fnum(row.get("max_drawdown_total_wealth")) for row in sub]
            min_equity = [fnum(row.get("min_equity")) for row in sub]
            out.append(
                {
                    "mode": mode,
                    "period": period,
                    "n_starts": len(sub),
                    "profitable_rate": sum(1 for row in sub if int(fnum(row.get("profitable"))) == 1) / len(sub),
                    "breached_7500_rate": sum(1 for row in sub if int(fnum(row.get("breached_7500"))) == 1) / len(sub),
                    "breached_6800_rate": sum(1 for row in sub if int(fnum(row.get("breached_6800"))) == 1) / len(sub),
                    "stop_event_rate": sum(1 for row in sub if fnum(row.get("stop_events")) > 0) / len(sub),
                    "median_net_profit": quantile(net, 0.50),
                    "p25_net_profit": quantile(net, 0.25),
                    "p10_net_profit": quantile(net, 0.10),
                    "worst_net_profit": min(net),
                    "best_net_profit": max(net),
                    "median_maxdd_total_wealth": quantile(dd, 0.50),
                    "p10_maxdd_total_wealth": quantile(dd, 0.10),
                    "worst_maxdd_total_wealth": min(dd),
                    "median_min_equity": quantile(min_equity, 0.50),
                    "worst_min_equity": min(min_equity),
                }
            )
    return out


def rows_for_equity_svg(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    previous = fnum(rows[0].get("total_wealth_before"), STARTING_BANKROLL) if rows else STARTING_BANKROLL
    for row in rows:
        total = fnum(row.get("total_wealth_after"), previous)
        copied = {
            "issue": row.get("issue", ""),
            "issue_order": row.get("issue_order", ""),
            "calendar_year": row.get("calendar_year", ""),
            "profit_units": total - previous,
        }
        out.append(copied)
        previous = total
    return out


def check_next_cap(args: argparse.Namespace) -> None:
    high_watermark = args.high_watermark if args.high_watermark is not None else args.equity
    cap, reason = cap_from_state(
        equity=args.equity,
        high_watermark=high_watermark,
        previous_cap=args.previous_cap,
        clean_issues_since_downshift=args.clean_issues_since_downshift,
        clean_issues_at_320=args.clean_issues_at_320,
        last_issue_full_loss=args.last_issue_full_loss,
        hard_stop=False,
    )
    pending_limit = min(3 * cap, args.equity * 0.08) if cap > 0 else 0.0
    allowed_new_stake = max(0.0, pending_limit - args.pending_exposure)
    payload = {
        "equity": args.equity,
        "high_watermark": high_watermark,
        "drawdown": max(0.0, high_watermark - args.equity),
        "previous_cap": args.previous_cap,
        "next_issue_cap": cap,
        "cap_reason": reason,
        "pending_exposure": args.pending_exposure,
        "pending_limit_after_new_issue": pending_limit,
        "allowed_new_stake_by_pending_limit": allowed_new_stake,
        "paper_only": cap <= 0,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def run(args: argparse.Namespace) -> None:
    base_rows = load_base_issue_rows(args.issue_profit)
    rows_by_mode = {
        mode: simulate_mode(
            mode=mode,
            base_rows=base_rows,
            starting_bankroll=args.starting_bankroll,
            initial_cap=args.initial_cap,
            restart_skip_issues=args.restart_skip_issues,
        )
        for mode in MODES
    }
    summary = [summarize_mode(rows, args.starting_bankroll) for rows in rows_by_mode.values()]
    annual = annual_rows(rows_by_mode, args.starting_bankroll)
    ledger_rows = [row for rows in rows_by_mode.values() for row in rows]
    rolling_rows = rolling_start_rows(
        base_rows=base_rows,
        starting_bankroll=args.starting_bankroll,
        initial_cap=args.initial_cap,
        restart_skip_issues=args.restart_skip_issues,
    )
    rolling_summary = summarize_rolling_starts(rolling_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "historical_live_ledger.csv", ledger_rows)
    write_csv_all(args.output_dir / "historical_live_summary.csv", summary)
    write_csv_all(args.output_dir / "historical_live_annual.csv", annual)
    write_csv_all(args.output_dir / "rolling_start_rows.csv", rolling_rows)
    write_csv_all(args.output_dir / "rolling_start_summary.csv", rolling_summary)
    write_csv_all(
        args.output_dir / "live_ledger_template.csv",
        [
            {
                "issue": "",
                "issue_close_ts": "",
                "mode": "production",
                "equity_before": "",
                "locked_profit_before": "",
                "high_watermark_before": "",
                "drawdown_before": "",
                "issue_cap": "",
                "stake_units": "",
                "pending_exposure_before": "",
                "pending_exposure_after": "",
                "generated_plan_path": "",
                "submitted_ticket_ref": "",
                "profit_units": "",
                "equity_after": "",
                "locked_profit_after": "",
                "high_watermark_after": "",
                "drawdown_after": "",
                "cap_reason": "",
                "rule_violation": "",
                "notes": "",
            }
        ],
    )
    write_equity_svg(
        args.figure_path,
        {mode: rows_for_equity_svg(rows) for mode, rows in rows_by_mode.items()},
    )

    summary_cols = [
        "mode",
        "live_issues",
        "skipped_issues",
        "stake_units",
        "profit_units",
        "final_equity",
        "locked_profit",
        "final_total_wealth",
        "net_profit",
        "roi_on_stake",
        "wealth_return",
        "min_equity",
        "max_drawdown_equity",
        "max_drawdown_total_wealth",
        "issue_win_rate",
        "full_loss_rate",
        "max_loss_streak",
        "max_dead_streak",
        "stop_events",
        "max_cap",
        "avg_cap",
        "recent_profit_units",
        "recent_roi_on_stake",
    ]
    cap_cols = [
        "mode",
        "cap_64_issues",
        "cap_128_issues",
        "cap_192_issues",
        "cap_256_issues",
        "cap_320_issues",
        "cap_384_issues",
    ]
    annual_cols = [
        "mode",
        "year",
        "live_issues",
        "skipped_issues",
        "stake_units",
        "profit_units",
        "roi_on_stake",
        "issue_win_rate",
        "full_loss_rate",
        "max_equity_drawdown_within_year",
        "end_total_wealth",
    ]
    rolling_cols = [
        "mode",
        "period",
        "n_starts",
        "profitable_rate",
        "breached_7500_rate",
        "breached_6800_rate",
        "stop_event_rate",
        "median_net_profit",
        "p25_net_profit",
        "p10_net_profit",
        "worst_net_profit",
        "best_net_profit",
        "median_maxdd_total_wealth",
        "p10_maxdd_total_wealth",
        "worst_maxdd_total_wealth",
        "median_min_equity",
        "worst_min_equity",
    ]
    report = [
        "# Live Bankroll Runbook Historical Simulation",
        "",
        f"Starting bankroll: `{args.starting_bankroll:g}`.",
        f"Initial issue cap: `{args.initial_cap:g}`.",
        "",
        "## Modes",
        "",
        "- `fixed_256`: always scale the 384 production profile to 256.",
        "- `ladder_no_stop`: use the runbook drawdown ladder, but keep betting at the 64 floor instead of hard stopping.",
        f"- `runbook_restart20`: hard stop at the runbook threshold, skip `{args.restart_skip_issues}` issues as paper, then resume from 64.",
        "",
        "Historical pending exposure is modeled as zero because this replay is sequential by settled issue. Live execution must still enforce the pending exposure rule in the runbook.",
        "",
        "## Summary",
        "",
        md_table([{col: row.get(col, "") for col in summary_cols} for row in summary], limit=20),
        "",
        "## Cap Usage",
        "",
        md_table([{col: row.get(col, "") for col in cap_cols} for row in summary], limit=20),
        "",
        "## Annual Results",
        "",
        md_table([{col: row.get(col, "") for col in annual_cols} for row in annual], limit=80),
        "",
        "## Rolling Start Stress Test",
        "",
        "Each historical issue is also treated as a fresh 10000-bankroll start. This is stricter than the single 2014 start path and is closer to asking whether the runbook can survive an arbitrary live launch date.",
        "",
        md_table([{col: row.get(col, "") for col in rolling_cols} for row in rolling_summary], limit=20),
        "",
        "## Interpretation",
        "",
        "- The simulation uses the production 384 profile only, linearly scaled to the active issue cap.",
        "- Profit locks remove capital from the live bankroll and reset the risk high-watermark.",
        "- On the single 2014-start path, `ladder_no_stop` cuts total-wealth maxDD from roughly `-10051` to `-4387`, while preserving a large positive long-run result.",
        "- `runbook_restart20` is not a good automatic financial-stop rule in this replay. It frequently misses convex rebound issues after the cooling period and ends negative on the single 2014-start path.",
        "- Rolling-start stress is stricter: starts during 2023-2025 are fragile for every mode. The ladder reduces severe breach frequency versus fixed 256, but it does not make recent-regime launches risk-free.",
        "- Operationally, a pure PnL drawdown should prefer a 64-unit red-zone floor plus review. Hard stop should be reserved for data, execution, settlement, or rule-integrity failures unless capital preservation is more important than preserving convex exposure.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'historical_live_ledger.csv'}`",
        f"- `{args.output_dir / 'historical_live_summary.csv'}`",
        f"- `{args.output_dir / 'historical_live_annual.csv'}`",
        f"- `{args.output_dir / 'rolling_start_rows.csv'}`",
        f"- `{args.output_dir / 'rolling_start_summary.csv'}`",
        f"- `{args.output_dir / 'live_ledger_template.csv'}`",
        f"- `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.output_dir / 'historical_live_summary.csv'}")
    print(f"Wrote {args.figure_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issue-profit",
        type=Path,
        default=Path("results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/live_bankroll_runbook_10000_20260629"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/live_bankroll_runbook_10000_simulation_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/live_bankroll_runbook_10000_simulation_2026-06-29.svg"),
    )
    parser.add_argument("--starting-bankroll", type=float, default=STARTING_BANKROLL)
    parser.add_argument("--initial-cap", type=float, default=DEFAULT_INITIAL_CAP)
    parser.add_argument("--restart-skip-issues", type=int, default=20)
    parser.add_argument("--check-next-cap", action="store_true")
    parser.add_argument("--equity", type=float, default=STARTING_BANKROLL)
    parser.add_argument("--high-watermark", type=float)
    parser.add_argument("--previous-cap", type=float, default=DEFAULT_INITIAL_CAP)
    parser.add_argument("--pending-exposure", type=float, default=0.0)
    parser.add_argument("--clean-issues-since-downshift", type=int, default=40)
    parser.add_argument("--clean-issues-at-320", type=int, default=0)
    parser.add_argument("--last-issue-full-loss", action="store_true")
    args = parser.parse_args()

    if args.check_next_cap:
        check_next_cap(args)
        return
    if not args.issue_profit.exists():
        raise SystemExit(f"missing input: {args.issue_profit}")
    run(args)


if __name__ == "__main__":
    main()
