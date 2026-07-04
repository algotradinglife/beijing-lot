#!/usr/bin/env python3
"""Evaluate less conservative live position-management rules for N7."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_384_drawdown_dynamic import SELECTED_PORTFOLIO, fnum, row_order, row_year
from scripts.evaluate_n7_384_weak_quality_dynamic import write_equity_svg
from scripts.simulate_live_bankroll_runbook import (
    BASE_STAKE,
    DEFAULT_INITIAL_CAP,
    STARTING_BANKROLL,
    max_drawdown_from_values,
    max_streak,
)
from scripts.walkforward_beidan_strategy_eval import md_table


BASE_PORTFOLIO = SELECTED_PORTFOLIO


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


class RuleState:
    def __init__(
        self,
        *,
        equity: float,
        locked_profit: float,
        total_wealth_highwater: float,
        high_watermark: float,
        loss_streak: int,
        dead_streak: int,
        previous_cap: float,
    ) -> None:
        self.equity = equity
        self.locked_profit = locked_profit
        self.total_wealth = equity + locked_profit
        self.total_wealth_highwater = total_wealth_highwater
        self.high_watermark = high_watermark
        self.drawdown = max(0.0, high_watermark - equity)
        self.loss_streak = loss_streak
        self.dead_streak = dead_streak
        self.previous_cap = previous_cap


RuleFn = Callable[[RuleState], tuple[float, str]]


def fixed_256_rule(_state: RuleState) -> tuple[float, str]:
    return 256.0, "fixed_256"


def profit_tier_live_equity_rule(state: RuleState) -> tuple[float, str]:
    if state.equity >= 15000.0:
        return 384.0, "live_equity_ge15000_384"
    if state.equity >= 12000.0:
        return 320.0, "live_equity_ge12000_320"
    return 256.0, "live_equity_base_256"


def profit_tier_equity_copy_rule(state: RuleState) -> tuple[float, str]:
    if state.total_wealth >= 15000.0:
        return 384.0, "equity_copy_ge15000_384"
    if state.total_wealth >= 12000.0:
        return 320.0, "equity_copy_ge12000_320"
    return 256.0, "equity_copy_base_256"


def profit_tier_ratchet_rule(state: RuleState) -> tuple[float, str]:
    if state.total_wealth_highwater >= 15000.0:
        return 384.0, "ratchet_total_hwm_ge15000_384"
    if state.total_wealth_highwater >= 12000.0:
        return 320.0, "ratchet_total_hwm_ge12000_320"
    return 256.0, "ratchet_base_256"


def profit_tier_aggressive_rule(state: RuleState) -> tuple[float, str]:
    if state.total_wealth_highwater >= 20000.0:
        return 512.0, "aggr_total_hwm_ge20000_512"
    if state.total_wealth_highwater >= 15000.0:
        return 384.0, "aggr_total_hwm_ge15000_384"
    if state.total_wealth_highwater >= 12000.0:
        return 320.0, "aggr_total_hwm_ge12000_320"
    return 256.0, "aggr_base_256"


def profit_tier_guarded_rule(state: RuleState) -> tuple[float, str]:
    if state.total_wealth_highwater >= 15000.0 and state.equity >= 11000.0:
        return 384.0, "guarded_hwm15000_equity11000_384"
    if state.total_wealth_highwater >= 12000.0 and state.equity >= 9000.0:
        return 320.0, "guarded_hwm12000_equity9000_320"
    return 256.0, "guarded_base_256"


RULES: list[tuple[str, str, RuleFn]] = [
    ("fixed_256", "always target 256; no drawdown reduction", fixed_256_rule),
    ("profit_live_equity", "256 base; 320 at live equity 12000; 384 at live equity 15000", profit_tier_live_equity_rule),
    ("profit_equity_copy", "256 base; same thresholds as live equity; retained for no-locking comparison", profit_tier_equity_copy_rule),
    ("profit_ratchet", "256 base; ratchet to 320/384 after total wealth high-water marks", profit_tier_ratchet_rule),
    ("profit_aggressive", "256 base; ratchet to 320/384/512 after total wealth high-water marks", profit_tier_aggressive_rule),
    ("profit_guarded", "256 base; ratchet up only if total wealth and live equity both support it", profit_tier_guarded_rule),
]


def scaled_profit(base_profit: float, cap: float) -> float:
    return base_profit * cap / BASE_STAKE if cap > 0 else 0.0


def executable_cap(target_cap: float, equity: float) -> float:
    if target_cap <= 0 or equity <= 0:
        return 0.0
    return min(target_cap, equity)


def simulate_rule(
    *,
    rule_name: str,
    rule_desc: str,
    rule_fn: RuleFn,
    base_rows: list[dict[str, object]],
    starting_bankroll: float,
) -> list[dict[str, object]]:
    equity = starting_bankroll
    locked_profit = 0.0
    high_watermark = starting_bankroll
    total_wealth_highwater = starting_bankroll
    loss_streak = 0
    dead_streak = 0
    previous_cap = DEFAULT_INITIAL_CAP
    live_issue_index = 0
    ruined = False
    out: list[dict[str, object]] = []

    for idx, base in enumerate(base_rows):
        before_equity = equity
        before_locked = locked_profit
        before_total_wealth = before_equity + before_locked
        total_wealth_highwater = max(total_wealth_highwater, before_total_wealth)
        before_total_wealth_highwater = total_wealth_highwater
        before_high_watermark = high_watermark
        before_drawdown = max(0.0, before_high_watermark - before_equity)

        if ruined:
            target_cap, cap_reason = 0.0, "ruined"
        else:
            target_cap, cap_reason = rule_fn(
                RuleState(
                    equity=before_equity,
                    locked_profit=before_locked,
                    total_wealth_highwater=total_wealth_highwater,
                    high_watermark=before_high_watermark,
                    loss_streak=loss_streak,
                    dead_streak=dead_streak,
                    previous_cap=previous_cap,
                )
            )
        cap = executable_cap(target_cap, before_equity)
        constrained_by_equity = int(cap < target_cap and target_cap > 0)
        base_profit = fnum(base.get("profit_units"))
        profit = scaled_profit(base_profit, cap)
        stake = cap
        if stake > 0:
            live_issue_index += 1
        equity += profit
        if equity <= 1e-9 and not ruined:
            equity = max(0.0, equity)
            ruined = True

        full_loss = stake > 0 and profit <= -0.999 * stake
        win = stake > 0 and profit > 0
        if stake > 0:
            if win:
                loss_streak = 0
                dead_streak = 0
            else:
                loss_streak += 1
                dead_streak = dead_streak + 1 if full_loss else 0
            previous_cap = cap

        high_watermark = max(high_watermark, equity)
        locked_now = 0.0
        after_total_wealth = equity + locked_profit
        total_wealth_highwater = max(total_wealth_highwater, after_total_wealth)
        after_drawdown = max(0.0, high_watermark - equity)

        out.append(
            {
                "rule": rule_name,
                "rule_desc": rule_desc,
                "issue": base.get("issue", ""),
                "issue_order": base.get("issue_order", ""),
                "calendar_year": base.get("calendar_year", ""),
                "issue_start_ts": base.get("issue_start_ts", ""),
                "issue_close_ts": base.get("issue_close_ts", ""),
                "sequence_index": idx + 1,
                "live_issue_index": live_issue_index if stake > 0 else "",
                "target_cap": target_cap,
                "issue_cap": cap,
                "cap_reason": cap_reason,
                "constrained_by_equity": constrained_by_equity,
                "stake_units": stake,
                "base384_profit_units": base_profit,
                "profit_units": profit,
                "roi": profit / stake if stake else "",
                "win": int(win),
                "full_loss": int(full_loss),
                "loss_streak_after": loss_streak,
                "dead_streak_after": dead_streak,
                "ruined": int(ruined),
                "equity_before": before_equity,
                "locked_profit_before": before_locked,
                "total_wealth_before": before_total_wealth,
                "high_watermark_before": before_high_watermark,
                "total_wealth_highwater_before": before_total_wealth_highwater,
                "drawdown_before": before_drawdown,
                "equity_after": equity,
                "locked_profit_after": locked_profit,
                "total_wealth_after": after_total_wealth,
                "high_watermark_after": high_watermark,
                "total_wealth_highwater_after": total_wealth_highwater,
                "drawdown_after": after_drawdown,
                "locked_now": locked_now,
            }
        )
    return out


def summarize_rule(rows: list[dict[str, object]], starting_bankroll: float) -> dict[str, object]:
    live = [row for row in rows if fnum(row.get("stake_units")) > 0]
    final = rows[-1] if rows else {}
    stake = sum(fnum(row.get("stake_units")) for row in live)
    profit = sum(fnum(row.get("profit_units")) for row in live)
    final_total = fnum(final.get("total_wealth_after"), starting_bankroll)
    caps = Counter(int(round(fnum(row.get("issue_cap")))) for row in live)
    recent = [row for row in live if 2023 <= row_year(row) <= 2025]
    return {
        "rule": rows[0].get("rule", "") if rows else "",
        "rule_desc": rows[0].get("rule_desc", "") if rows else "",
        "issues": len(rows),
        "live_issues": len(live),
        "skipped_after_ruin": len(rows) - len(live),
        "stake_units": stake,
        "profit_units": profit,
        "final_equity": fnum(final.get("equity_after"), starting_bankroll),
        "locked_profit": fnum(final.get("locked_profit_after")),
        "final_total_wealth": final_total,
        "net_profit": final_total - starting_bankroll,
        "roi_on_stake": profit / stake if stake else math.nan,
        "wealth_return": final_total / starting_bankroll - 1.0,
        "min_equity": min((fnum(row.get("equity_after")) for row in rows), default=starting_bankroll),
        "max_drawdown_total_wealth": max_drawdown_from_values(
            [starting_bankroll] + [fnum(row.get("total_wealth_after")) for row in rows]
        ),
        "max_drawdown_equity": max_drawdown_from_values(
            [starting_bankroll] + [fnum(row.get("equity_after")) for row in rows]
        ),
        "issue_win_rate": sum(1 for row in live if fnum(row.get("profit_units")) > 0) / len(live)
        if live
        else math.nan,
        "full_loss_rate": sum(1 for row in live if int(fnum(row.get("full_loss"))) == 1) / len(live)
        if live
        else math.nan,
        "max_loss_streak": max_streak(live, lambda row: fnum(row.get("profit_units")) <= 0),
        "max_dead_streak": max_streak(live, lambda row: int(fnum(row.get("full_loss"))) == 1),
        "ruined": int(any(int(fnum(row.get("ruined"))) == 1 for row in rows)),
        "equity_constrained_issues": sum(int(fnum(row.get("constrained_by_equity"))) for row in live),
        "avg_cap": sum(fnum(row.get("issue_cap")) for row in live) / len(live) if live else 0.0,
        "cap_64_or_less_issues": sum(count for cap, count in caps.items() if cap <= 64),
        "cap_128_issues": caps.get(128, 0),
        "cap_192_issues": caps.get(192, 0),
        "cap_256_issues": caps.get(256, 0),
        "cap_320_issues": caps.get(320, 0),
        "cap_384_issues": caps.get(384, 0),
        "cap_512_issues": caps.get(512, 0),
        "recent_live_issues": len(recent),
        "recent_profit_units": sum(fnum(row.get("profit_units")) for row in recent),
        "recent_roi_on_stake": (
            sum(fnum(row.get("profit_units")) for row in recent)
            / sum(fnum(row.get("stake_units")) for row in recent)
        )
        if recent and sum(fnum(row.get("stake_units")) for row in recent)
        else math.nan,
    }


def annual_rows(rows_by_rule: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for rule, rows in rows_by_rule.items():
        for year in sorted({row_year(row) for row in rows if row_year(row) > 0}):
            sub = [row for row in rows if row_year(row) == year]
            live = [row for row in sub if fnum(row.get("stake_units")) > 0]
            stake = sum(fnum(row.get("stake_units")) for row in live)
            profit = sum(fnum(row.get("profit_units")) for row in live)
            out.append(
                {
                    "rule": rule,
                    "year": year,
                    "issues": len(sub),
                    "live_issues": len(live),
                    "stake_units": stake,
                    "profit_units": profit,
                    "roi_on_stake": profit / stake if stake else math.nan,
                    "end_total_wealth": fnum(sub[-1].get("total_wealth_after")) if sub else "",
                    "max_drawdown_total_wealth_in_year": max_drawdown_from_values(
                        [fnum(sub[0].get("total_wealth_before"), STARTING_BANKROLL)]
                        + [fnum(row.get("total_wealth_after")) for row in sub]
                    )
                    if sub
                    else 0.0,
                    "ruined": int(any(int(fnum(row.get("ruined"))) == 1 for row in sub)),
                }
            )
    return out


def rolling_start_rows(
    *,
    base_rows: list[dict[str, object]],
    starting_bankroll: float,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for start_idx in range(len(base_rows)):
        suffix = base_rows[start_idx:]
        start = suffix[0]
        for rule_name, rule_desc, rule_fn in RULES:
            rows = simulate_rule(
                rule_name=rule_name,
                rule_desc=rule_desc,
                rule_fn=rule_fn,
                base_rows=suffix,
                starting_bankroll=starting_bankroll,
            )
            summary = summarize_rule(rows, starting_bankroll)
            out.append(
                {
                    "rule": rule_name,
                    "start_index": start_idx + 1,
                    "start_issue": start.get("issue", ""),
                    "start_year": row_year(start),
                    "remaining_issues": len(suffix),
                    "net_profit": summary["net_profit"],
                    "final_total_wealth": summary["final_total_wealth"],
                    "min_equity": summary["min_equity"],
                    "max_drawdown_total_wealth": summary["max_drawdown_total_wealth"],
                    "max_drawdown_equity": summary["max_drawdown_equity"],
                    "live_issues": summary["live_issues"],
                    "stake_units": summary["stake_units"],
                    "roi_on_stake": summary["roi_on_stake"],
                    "ruined": summary["ruined"],
                    "profitable": int(fnum(summary["net_profit"]) > 0),
                    "breached_7500": int(fnum(summary["min_equity"]) < 7500),
                    "breached_6800": int(fnum(summary["min_equity"]) < 6800),
                    "breached_5000": int(fnum(summary["min_equity"]) < 5000),
                }
            )
    return out


def q(values: Iterable[float], pct: float) -> float:
    vals = sorted(value for value in values if math.isfinite(value))
    if not vals:
        return math.nan
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * pct
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def summarize_rolling(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    periods = [
        ("all_starts", lambda row: True),
        ("start_2014_2022", lambda row: 2014 <= int(fnum(row.get("start_year"))) <= 2022),
        ("start_2023_2025", lambda row: 2023 <= int(fnum(row.get("start_year"))) <= 2025),
    ]
    out: list[dict[str, object]] = []
    for rule, _desc, _fn in RULES:
        rule_rows = [row for row in rows if row.get("rule") == rule]
        for period, predicate in periods:
            sub = [row for row in rule_rows if predicate(row)]
            if not sub:
                continue
            net = [fnum(row.get("net_profit")) for row in sub]
            dd = [fnum(row.get("max_drawdown_total_wealth")) for row in sub]
            min_eq = [fnum(row.get("min_equity")) for row in sub]
            out.append(
                {
                    "rule": rule,
                    "period": period,
                    "n_starts": len(sub),
                    "profitable_rate": sum(int(fnum(row.get("profitable"))) for row in sub) / len(sub),
                    "ruin_rate": sum(int(fnum(row.get("ruined"))) for row in sub) / len(sub),
                    "breached_7500_rate": sum(int(fnum(row.get("breached_7500"))) for row in sub) / len(sub),
                    "breached_6800_rate": sum(int(fnum(row.get("breached_6800"))) for row in sub) / len(sub),
                    "breached_5000_rate": sum(int(fnum(row.get("breached_5000"))) for row in sub) / len(sub),
                    "median_net_profit": q(net, 0.50),
                    "p25_net_profit": q(net, 0.25),
                    "p10_net_profit": q(net, 0.10),
                    "worst_net_profit": min(net),
                    "best_net_profit": max(net),
                    "median_maxdd_total_wealth": q(dd, 0.50),
                    "p10_maxdd_total_wealth": q(dd, 0.10),
                    "worst_maxdd_total_wealth": min(dd),
                    "median_min_equity": q(min_eq, 0.50),
                    "worst_min_equity": min(min_eq),
                }
            )
    return out


def rows_for_equity_svg(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    previous = fnum(rows[0].get("total_wealth_before"), STARTING_BANKROLL) if rows else STARTING_BANKROLL
    for row in rows:
        total = fnum(row.get("total_wealth_after"), previous)
        out.append(
            {
                "issue": row.get("issue", ""),
                "issue_order": row.get("issue_order", ""),
                "calendar_year": row.get("calendar_year", ""),
                "profit_units": total - previous,
            }
        )
        previous = total
    return out


def md_rows(rows: list[dict[str, object]], cols: list[str], limit: int = 40) -> list[dict[str, object]]:
    return [{col: row.get(col, "") for col in cols} for row in rows[:limit]]


def run(args: argparse.Namespace) -> None:
    base_rows = load_base_issue_rows(args.issue_profit)
    rows_by_rule = {
        name: simulate_rule(
            rule_name=name,
            rule_desc=desc,
            rule_fn=fn,
            base_rows=base_rows,
            starting_bankroll=args.starting_bankroll,
        )
        for name, desc, fn in RULES
    }
    single_summary = [summarize_rule(rows, args.starting_bankroll) for rows in rows_by_rule.values()]
    annual = annual_rows(rows_by_rule)
    rolling_rows = rolling_start_rows(base_rows=base_rows, starting_bankroll=args.starting_bankroll)
    rolling_summary = summarize_rolling(rolling_rows)
    ledger = [row for rows in rows_by_rule.values() for row in rows]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "position_rule_single_path_ledger.csv", ledger)
    write_csv_all(args.output_dir / "position_rule_single_path_summary.csv", single_summary)
    write_csv_all(args.output_dir / "position_rule_annual.csv", annual)
    write_csv_all(args.output_dir / "position_rule_rolling_start_rows.csv", rolling_rows)
    write_csv_all(args.output_dir / "position_rule_rolling_start_summary.csv", rolling_summary)
    write_equity_svg(
        args.figure_path,
        {name: rows_for_equity_svg(rows) for name, rows in rows_by_rule.items()},
    )

    summary_cols = [
        "rule",
        "rule_desc",
        "stake_units",
        "profit_units",
        "final_total_wealth",
        "net_profit",
        "roi_on_stake",
        "min_equity",
        "max_drawdown_total_wealth",
        "ruined",
        "avg_cap",
        "cap_64_or_less_issues",
        "cap_128_issues",
        "cap_192_issues",
        "cap_256_issues",
        "cap_320_issues",
        "cap_384_issues",
        "cap_512_issues",
        "recent_profit_units",
        "recent_roi_on_stake",
    ]
    rolling_cols = [
        "rule",
        "period",
        "n_starts",
        "profitable_rate",
        "ruin_rate",
        "breached_7500_rate",
        "breached_6800_rate",
        "breached_5000_rate",
        "median_net_profit",
        "p10_net_profit",
        "worst_net_profit",
        "median_maxdd_total_wealth",
        "worst_maxdd_total_wealth",
        "median_min_equity",
        "worst_min_equity",
    ]
    recent_rolling = [row for row in rolling_summary if row.get("period") in {"all_starts", "start_2023_2025"}]
    report = [
        "# Live Position Management Rule Sweep",
        "",
        f"Starting bankroll: `{args.starting_bankroll:g}`.",
        "",
        "This sweep keeps the main production strategy unchanged and only changes the issue-cap rule. The replay is bankruptcy-aware: a rule cannot stake more than available account equity, and betting stops after equity reaches zero. There is no separate profit-lock account in this version.",
        "",
        "## Single 2014-Start Path",
        "",
        md_table(md_rows(single_summary, summary_cols, limit=20), limit=20),
        "",
        "## Rolling-Start Stress",
        "",
        "Each historical issue is treated as a fresh 10000-bankroll launch date. `start_2023_2025` is the harshest practical stress set for current deployment.",
        "",
        md_table(md_rows(recent_rolling, rolling_cols, limit=40), limit=40),
        "",
        "## Recommendation",
        "",
        "Use `profit_live_equity` as the live cap rule:",
        "",
        "```text",
        "live equity < 12000: cap 256",
        "live equity >= 12000: cap 320",
        "live equity >= 15000: cap 384",
        "```",
        "",
        "This keeps fixed 256 as the default behavior and adds risk only after the bankroll has grown in spendable live equity. It is cleaner than drawdown de-risking and less path-risky than ratcheting or adding a 512 tier.",
        "",
        "## Interpretation",
        "",
        "- Fixed 256 is the reference: no opportunity-cost from de-risking, but no upside scaling after profits.",
        "- Profit-tier rules keep 256 as the floor and only increase after the bankroll has already earned the right to take more risk.",
        "- `profit_live_equity` is the recommended rule. In the no-locking model, account equity is the only bankroll state that matters.",
        "- `profit_aggressive` tests whether adding a 512 tier is worth the extra path risk.",
        "",
        "## Files",
        "",
        f"- `{args.output_dir / 'position_rule_single_path_summary.csv'}`",
        f"- `{args.output_dir / 'position_rule_rolling_start_summary.csv'}`",
        f"- `{args.output_dir / 'position_rule_rolling_start_rows.csv'}`",
        f"- `{args.output_dir / 'position_rule_single_path_ledger.csv'}`",
        f"- `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")
    print(f"Wrote {args.output_dir / 'position_rule_rolling_start_summary.csv'}")
    print(f"Wrote {args.figure_path}")


def check_next_cap(args: argparse.Namespace) -> None:
    target_cap, reason = profit_tier_live_equity_rule(
        RuleState(
            equity=args.equity,
            locked_profit=args.locked_profit,
            total_wealth_highwater=args.total_wealth_highwater,
            high_watermark=args.high_watermark,
            loss_streak=0,
            dead_streak=0,
            previous_cap=args.previous_cap,
        )
    )
    cap = executable_cap(target_cap, args.equity)
    pending_limit = min(3.0 * cap, args.equity * 0.08) if cap > 0 else 0.0
    payload = {
        "equity": args.equity,
        "locked_profit": args.locked_profit,
        "total_wealth": args.equity + args.locked_profit,
        "high_watermark": args.high_watermark,
        "drawdown": max(0.0, args.high_watermark - args.equity),
        "target_issue_cap": target_cap,
        "next_issue_cap": cap,
        "cap_reason": reason,
        "constrained_by_equity": cap < target_cap,
        "pending_exposure": args.pending_exposure,
        "pending_limit_after_new_issue": pending_limit,
        "allowed_new_stake_by_pending_limit": max(0.0, pending_limit - args.pending_exposure),
        "red_zone_review": args.high_watermark - args.equity >= 3200.0 or args.equity < 6800.0,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


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
        default=Path("results/live_position_management_rules_20260629"),
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/live_position_management_rules_2026-06-29.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/live_position_management_rules_2026-06-29.svg"),
    )
    parser.add_argument("--starting-bankroll", type=float, default=STARTING_BANKROLL)
    parser.add_argument("--check-next-cap", action="store_true")
    parser.add_argument("--equity", type=float, default=STARTING_BANKROLL)
    parser.add_argument("--locked-profit", type=float, default=0.0)
    parser.add_argument("--high-watermark", type=float, default=STARTING_BANKROLL)
    parser.add_argument("--total-wealth-highwater", type=float, default=STARTING_BANKROLL)
    parser.add_argument("--previous-cap", type=float, default=DEFAULT_INITIAL_CAP)
    parser.add_argument("--pending-exposure", type=float, default=0.0)
    args = parser.parse_args()
    if args.check_next_cap:
        check_next_cap(args)
        return
    if not args.issue_profit.exists():
        raise SystemExit(f"missing input: {args.issue_profit}")
    run(args)


if __name__ == "__main__":
    main()
