"""北单 7-leg combo optimizer (v1 prototype).

Public API:
    Candidate, Combo, TicketPlan  — dataclasses
    build_plan                    — top-level entry
    combo_math, selector, builder, sizer  — submodules for power users
"""
from .builder import build_combos, enumerate_combos
from .combo_math import (
    break_even_per_leg_edge,
    combo_ev,
    combo_payout_per_yuan,
    kelly_fraction_full,
    kelly_stake,
)
from .main import build_plan
from .selector import dedup_by_match, filter_by_edge, select_pool, top_k
from .sizer import (
    apply_bankroll_cap,
    floor_to_even,
    max_stake_per_ticket,
    size_one_combo,
)
from .types import (
    MIN_STAKE_PER_TICKET,
    RETURN_RATE,
    TAX_FREE_PRIZE_CAP,
    TAX_THRESHOLD,
    Candidate,
    Combo,
    TicketPlan,
)

__all__ = [
    "Candidate",
    "Combo",
    "TicketPlan",
    "build_plan",
    "RETURN_RATE",
    "TAX_FREE_PRIZE_CAP",
    "TAX_THRESHOLD",
    "MIN_STAKE_PER_TICKET",
    "combo_ev",
    "combo_payout_per_yuan",
    "kelly_fraction_full",
    "kelly_stake",
    "break_even_per_leg_edge",
    "filter_by_edge",
    "dedup_by_match",
    "top_k",
    "select_pool",
    "enumerate_combos",
    "build_combos",
    "floor_to_even",
    "max_stake_per_ticket",
    "size_one_combo",
    "apply_bankroll_cap",
]
