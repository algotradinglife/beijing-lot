"""Settle a TicketPlan against actual results.

The 北单 combo settlement rule is simple: ALL legs must hit; otherwise
the entire combo loses. When all legs hit, the gross prize per ticket is
``stake_per_ticket × ∏actual_winning_SP × 0.65``. Profit is gross prize
minus stake.

We use ACTUAL winning SP (the dataset preserves this on the winning
side) for hit legs, since we only ever settle combos where every leg
hit — there is no losing-leg-SP problem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from src.combo_optimizer.types import RETURN_RATE, Combo, TicketPlan


@dataclass(frozen=True)
class ComboSettlement:
    """Outcome of one TicketPlan settled against actuals."""

    plan: TicketPlan
    all_hit: bool
    realised_payout_per_yuan: float  # ∏actual_SP × 0.65 if hit, else 0
    total_stake: int
    total_profit: float  # negative when missed


def settle_combo(
    combo: Combo,
    actuals: dict[str, dict],
) -> tuple[bool, float]:
    """Check whether every leg of ``combo`` matched the actual result.

    ``actuals`` maps match_id -> {"result_code": "3"|"1"|"0",
    "winning_sp": float}.

    Returns (all_hit, payout_per_yuan).
    """
    payout = RETURN_RATE
    for leg in combo.legs:
        rec = actuals.get(leg.match_id)
        if rec is None:
            return False, 0.0
        if str(rec["result_code"]) != str(leg.selection):
            return False, 0.0
        sp = float(rec["winning_sp"])
        if sp <= 0:
            return False, 0.0
        payout *= sp
    return True, payout


def settle_plan(
    plan: TicketPlan,
    actuals: dict[str, dict],
) -> ComboSettlement:
    """Settle one TicketPlan; profit = stake × (payout − 1) when all hit."""
    all_hit, realised = settle_combo(plan.combo, actuals)
    total_stake = plan.total_stake
    if all_hit:
        profit = total_stake * (realised - 1.0)
    else:
        profit = -float(total_stake)
    return ComboSettlement(
        plan=plan,
        all_hit=all_hit,
        realised_payout_per_yuan=realised,
        total_stake=total_stake,
        total_profit=profit,
    )


def settle_plans(
    plans: Iterable[TicketPlan],
    actuals: dict[str, dict],
) -> List[ComboSettlement]:
    return [settle_plan(p, actuals) for p in plans]
