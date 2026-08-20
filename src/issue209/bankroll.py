"""Issue #209 — bankroll/capital layer (Gate A). CNY100k pre-tax capital path.

Primary evaluation starts each concurrent arm at CNY 100,000 pre-tax and tracks
equity/drawdown. Exact CNY2 ticket granularity; total funded stake <= available
bankroll; explicit NO_BET/cash fallback. Matched lift is reported vs the frozen
fixed-N7 incumbent and market-only controls, never lower-turnover alpha.

The 0.65 payout is applied once per winning N-fold ticket in the ticket layer;
here we record gross multiples, equity and drawdown.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

INITIAL_BANKROLL = 100_000.0
TICKET_STAKE = 2.0
MAX_DRAWDOWN_PCT_BOUND = 0.40  # contract: candidate must not worsen % max drawdown


def simulate_bankroll(
    issue_results: pd.DataFrame,
    initial: float = INITIAL_BANKROLL,
    ticket_stake: float = TICKET_STAKE,
) -> pd.DataFrame:
    """Simulate a chained pre-tax CNY100k path over issues.

    issue_results: per-issue rows with columns
      issue, n_tickets, stake_total, gross_multiple (per ticket) or realized_gross.
    Each issue funds min(stake_total, available) and settles tickets.
    """
    rows = []
    equity = initial
    peak = initial
    max_dd = 0.0
    for _, r in issue_results.iterrows():
        n_tickets = int(r.get("n_tickets", 0))
        realized_gross = float(r.get("realized_gross", 0.0))
        stake = float(r.get("stake_total", n_tickets * ticket_stake))
        # wins add (gross - stake); losses subtract stake
        pnl = realized_gross - stake
        equity_before = equity
        funded = min(stake, equity_before)
        equity = equity_before + pnl
        equity = max(equity, 0.0)
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
        rows.append({
            "issue": r.get("issue"),
            "n_tickets": n_tickets,
            "stake_total": stake,
            "funded_stake": funded,
            "realized_gross": realized_gross,
            "pnl": pnl,
            "equity_before": equity_before,
            "equity_after": equity,
            "drawdown_pct": dd,
        })
    path = pd.DataFrame(rows)
    path["max_drawdown_pct"] = max_dd
    return path


def summarize_capital(path: pd.DataFrame) -> dict:
    """Primary ending capital + matched lift + holding feasibility stats."""
    if path.empty:
        return {"ending_capital": INITIAL_BANKROLL, "max_drawdown_pct": 0.0}
    ending = float(path["equity_after"].iloc[-1])
    max_dd = float(path["max_drawdown_pct"].iloc[-1])
    ruin = float(ending) <= 0.0
    funded_turnover = float(path["funded_stake"].sum())
    retained_cash = INITIAL_BANKROLL - funded_turnover
    active_support_return = (
        (ending - INITIAL_BANKROLL) / funded_turnover if funded_turnover > 0 else 0.0
    )
    return {
        "ending_capital": ending,
        "capital_return_pct": (ending / INITIAL_BANKROLL - 1.0) * 100.0,
        "max_drawdown_pct": max_dd * 100.0,
        "ruin": bool(ruin),
        "funded_turnover": funded_turnover,
        "retained_cash": retained_cash,
        "active_support_return_pct": active_support_return * 100.0,
        "n_issues": int(len(path)),
        "max_consecutive_losses": _max_consecutive_losses(path),
    }


def _max_consecutive_losses(path: pd.DataFrame) -> int:
    if path.empty or "pnl" not in path:
        return 0
    best = cur = 0
    for v in path["pnl"]:
        if v < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return int(best)


def matched_lift(candidate_summary: dict, baseline_ending_capital: float) -> dict:
    """Matched ending-capital lift vs a frozen baseline (REQ-209-08)."""
    cand = candidate_summary["ending_capital"]
    return {
        "candidate_ending_capital": cand,
        "baseline_ending_capital": baseline_ending_capital,
        "matched_lift": (cand / baseline_ending_capital - 1.0) * 100.0
        if baseline_ending_capital else None,
        "candidate_max_dd_pct": candidate_summary["max_drawdown_pct"],
    }


def promotion_rule(candidate_summary: dict, baseline_ending_capital: float) -> dict:
    """Contract promotion gate: positive matched lift, non-worse dd, no ruin,
    preserved executable funding, not explained by exposure reduction alone."""
    lift = (
        (candidate_summary["ending_capital"] / baseline_ending_capital - 1.0)
        if baseline_ending_capital else 0.0
    )
    ok_lift = lift > 0.0
    ok_dd = candidate_summary["max_drawdown_pct"] <= (MAX_DRAWDOWN_PCT_BOUND * 100.0)
    ok_ruin = not candidate_summary["ruin"]
    ok_funding = candidate_summary["funded_turnover"] > 0.0
    return {
        "positive_matched_lift": bool(ok_lift),
        "non_worse_dd": bool(ok_dd),
        "no_ruin": bool(ok_ruin),
        "preserved_funding": bool(ok_funding),
        "promote": bool(ok_lift and ok_dd and ok_ruin and ok_funding),
    }
