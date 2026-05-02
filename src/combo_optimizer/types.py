"""Dataclasses for the 北单 7-leg combo optimizer.

All structures are frozen and side-effect-free; pure compute lives in
``combo_math`` and stake/ticket logic in ``sizer``.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from operator import mul
from typing import Tuple

# 北单 parimutuel rake constant. 35% house take ⇒ 0.65 returned to winners.
RETURN_RATE = 0.65

# Tax cliff: single-ticket prize ≥ 10_000 yuan → 20% tax on full amount.
# We keep the prize strictly below the threshold by capping at 9_999.
TAX_FREE_PRIZE_CAP = 9_999.0
TAX_THRESHOLD = 10_000.0

# 北单 minimum bet unit: each ticket must be a positive even integer.
MIN_STAKE_PER_TICKET = 2


@dataclass(frozen=True)
class Candidate:
    """One filtered single-leg pick: (match, selection, p_hat, sp)."""

    match_id: str
    selection: int  # 3 (home win after handicap), 1 (draw), or 0 (away)
    p_hat: float
    sp: float

    @property
    def edge(self) -> float:
        """Single-leg expected return per yuan minus 1.

        edge = p_hat × SP × 0.65 − 1.
        Positive ⇒ +EV on the single-leg basis.
        """
        return self.p_hat * self.sp * RETURN_RATE - 1.0


@dataclass(frozen=True)
class Combo:
    """An ordered tuple of legs forming one parlay.

    Combo math assumes leg independence (an approximation; legs from
    distinct matches are usually weakly correlated, but combos that share
    legs in a portfolio are very correlated — see the writeup).
    """

    legs: Tuple[Candidate, ...]

    @property
    def n_legs(self) -> int:
        return len(self.legs)

    @property
    def joint_p(self) -> float:
        return reduce(mul, (leg.p_hat for leg in self.legs), 1.0)

    @property
    def joint_sp(self) -> float:
        return reduce(mul, (leg.sp for leg in self.legs), 1.0)

    @property
    def payout_per_yuan(self) -> float:
        """Gross multiplier on stake when the combo wins (rake applied once)."""
        return self.joint_sp * RETURN_RATE

    @property
    def ev(self) -> float:
        """Expected return per yuan minus 1; positive ⇒ +EV."""
        return self.joint_p * self.payout_per_yuan - 1.0

    @property
    def match_ids(self) -> Tuple[str, ...]:
        return tuple(leg.match_id for leg in self.legs)


@dataclass(frozen=True)
class TicketPlan:
    """A combo bet split across one or more identical physical tickets.

    Each ticket carries the same combo at ``stake_per_ticket`` yuan.
    Splitting is used to keep per-ticket prize below the 10k tax cliff.
    """

    combo: Combo
    stake_per_ticket: int  # even, ≥ 2
    n_tickets: int  # ≥ 1

    @property
    def total_stake(self) -> int:
        return self.stake_per_ticket * self.n_tickets

    @property
    def prize_per_ticket(self) -> float:
        """Gross prize for one winning ticket (before any tax)."""
        return self.stake_per_ticket * self.combo.payout_per_yuan

    @property
    def is_tax_free(self) -> bool:
        return self.prize_per_ticket < TAX_THRESHOLD

    @property
    def expected_total_return(self) -> float:
        """E[gross prize across all tickets] (winning prob × prize × n)."""
        return self.combo.joint_p * self.prize_per_ticket * self.n_tickets
