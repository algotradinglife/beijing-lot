"""Stake sizing: Kelly → tax-cap split → integer-yuan rounding.

The flow per combo:
  raw_stake  = bankroll × kelly_fraction × f*
  cap        = floor(9999 / payout_per_yuan), then floor to even
  if raw ≤ cap : 1 ticket of size raw (rounded down to even, ≥ 2)
  else         : ⌈raw / cap⌉ tickets each at cap

Then a portfolio-level scaling step caps total stake at
``weekly_stake_cap_frac × bankroll`` by reducing per-ticket stakes
proportionally (n_tickets stays constant).
"""
from __future__ import annotations

import math
from typing import Iterable, List, Optional

from .combo_math import kelly_fraction_full
from .types import (
    MIN_STAKE_PER_TICKET,
    TAX_FREE_PRIZE_CAP,
    Combo,
    TicketPlan,
)


def floor_to_even(x: float) -> int:
    """Largest even non-negative integer ≤ x."""
    n = int(math.floor(max(0.0, x)))
    return n - (n % 2)


def max_stake_per_ticket(payout_per_yuan: float) -> int:
    """Largest even-yuan stake whose prize stays below the 10k tax cliff."""
    if payout_per_yuan <= 0:
        return 0
    raw_cap = TAX_FREE_PRIZE_CAP / payout_per_yuan
    return floor_to_even(raw_cap)


def size_one_combo(
    combo: Combo,
    bankroll: float,
    *,
    kelly_fraction: float = 0.25,
) -> Optional[TicketPlan]:
    """Returns None if the combo isn't worth a single 2-yuan ticket."""
    payout = combo.payout_per_yuan
    f_star = kelly_fraction_full(combo.joint_p, payout)
    raw_stake = bankroll * kelly_fraction * f_star
    if raw_stake < MIN_STAKE_PER_TICKET:
        return None

    cap = max_stake_per_ticket(payout)
    if cap < MIN_STAKE_PER_TICKET:
        # Even the smallest legal ticket would breach the tax cap. Skip.
        return None

    if raw_stake <= cap:
        stake_per_ticket = floor_to_even(raw_stake)
        if stake_per_ticket < MIN_STAKE_PER_TICKET:
            return None
        return TicketPlan(combo=combo, stake_per_ticket=stake_per_ticket, n_tickets=1)

    # Need to split. Use cap-sized tickets; round up the count so the
    # total covers the desired raw stake.
    n_tickets = max(1, math.ceil(raw_stake / cap))
    return TicketPlan(combo=combo, stake_per_ticket=cap, n_tickets=n_tickets)


def apply_bankroll_cap(
    plans: Iterable[TicketPlan],
    bankroll: float,
    weekly_stake_cap_frac: float = 0.25,
) -> List[TicketPlan]:
    """Scale all stakes down proportionally if the portfolio exceeds the cap.

    n_tickets is preserved; stake_per_ticket is reduced (and re-rounded
    to even). Plans whose scaled stake falls below 2 yuan are dropped.
    """
    plans = list(plans)
    if not plans:
        return []

    cap_total = weekly_stake_cap_frac * bankroll
    current_total = sum(p.total_stake for p in plans)
    if current_total <= cap_total or current_total == 0:
        return plans

    scale = cap_total / current_total
    out: List[TicketPlan] = []
    for p in plans:
        new_stake = floor_to_even(p.stake_per_ticket * scale)
        if new_stake < MIN_STAKE_PER_TICKET:
            continue
        out.append(
            TicketPlan(
                combo=p.combo,
                stake_per_ticket=new_stake,
                n_tickets=p.n_tickets,
            )
        )
    return out
