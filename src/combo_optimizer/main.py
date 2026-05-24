"""Top-level entry: ``build_plan`` glues selector → builder → sizer."""
from __future__ import annotations

import logging
from typing import FrozenSet, List, Optional

from .builder import build_combos
from .selector import DEFAULT_SINGLE_LEG_EDGE_FLOOR, select_pool
from .sizer import apply_bankroll_cap, size_one_combo
from .types import Candidate, TicketPlan

log = logging.getLogger(__name__)


def build_plan(
    candidates: List[Candidate],
    bankroll: float,
    *,
    weekly_stake_cap_frac: float = 0.25,
    n_legs: int = 7,
    top_k: int = 14,
    single_leg_edge_floor: float = DEFAULT_SINGLE_LEG_EDGE_FLOOR,
    combo_ev_threshold: float = 0.10,
    kelly_fraction: float = 0.25,
    max_combos: int = 50,
    diversity_lambda: float = 0.5,
    cross_n_used: Optional[FrozenSet[str]] = None,
    cross_n_lambda: float = 0.0,
) -> List[TicketPlan]:
    """Build a weekly portfolio of 7-leg combo tickets.

    Steps:
      1. Filter by single-leg edge floor.
      2. Same-match dedup; keep top-K.
      3. Enumerate C(K, n_legs); filter by combo EV; rank.
      4. Per-combo Kelly stake with tax-cap ticket split.
      5. Portfolio-level bankroll-cap scaling.

    Returns: list of TicketPlan sorted by combo EV descending.
    """
    if bankroll <= 0:
        raise ValueError("bankroll must be positive")
    if n_legs < 2:
        raise ValueError("n_legs must be ≥ 2")

    pool = select_pool(candidates, min_edge=single_leg_edge_floor, k=top_k)
    if len(pool) < n_legs:
        log.warning(
            "Only %d viable candidates (need %d). Returning empty plan.",
            len(pool),
            n_legs,
        )
        return []

    combos = build_combos(
        pool,
        n_legs=n_legs,
        min_ev=combo_ev_threshold,
        max_combos=max_combos,
        diversity_lambda=diversity_lambda,
        cross_n_used=cross_n_used,
        cross_n_lambda=cross_n_lambda,
    )
    if not combos:
        log.warning("No combo passed EV threshold %.3f.", combo_ev_threshold)
        return []

    raw_plans: List[TicketPlan] = []
    for combo in combos:
        plan = size_one_combo(combo, bankroll, kelly_fraction=kelly_fraction)
        if plan is not None:
            raw_plans.append(plan)

    if not raw_plans:
        log.warning("All combos rejected at sizing stage (stake < 2 yuan).")
        return []

    return apply_bankroll_cap(raw_plans, bankroll, weekly_stake_cap_frac)
