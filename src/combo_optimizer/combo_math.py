"""Pure-math helpers for combo EV, Kelly, and break-even thresholds.

No I/O, no rounding, no side effects. All stake quantization lives in
``sizer``.
"""
from __future__ import annotations

from typing import Iterable

from .types import RETURN_RATE, Candidate, Combo


def joint_probability(legs: Iterable[Candidate]) -> float:
    p = 1.0
    for leg in legs:
        p *= leg.p_hat
    return p


def joint_sp(legs: Iterable[Candidate]) -> float:
    sp = 1.0
    for leg in legs:
        sp *= leg.sp
    return sp


def combo_payout_per_yuan(legs: Iterable[Candidate]) -> float:
    """∏ SP × 0.65 — the gross multiplier when the combo wins."""
    return joint_sp(legs) * RETURN_RATE


def combo_ev(legs: Iterable[Candidate]) -> float:
    """E[return] − 1 per yuan staked."""
    legs = tuple(legs)
    return joint_probability(legs) * combo_payout_per_yuan(legs) - 1.0


def kelly_fraction_full(p: float, payout_per_yuan: float) -> float:
    """Full-Kelly fraction for a binary bet.

    f* = (p × b − (1 − p)) / b   where b = payout_per_yuan − 1
    Equivalent simplification: f* = (p × payout − 1) / (payout − 1).

    Returns 0 when the bet is non-+EV or the payout is degenerate.
    """
    b = payout_per_yuan - 1.0
    if b <= 0.0:
        return 0.0
    f = (p * payout_per_yuan - 1.0) / b
    return max(0.0, f)


def kelly_stake(
    bankroll: float,
    p: float,
    payout_per_yuan: float,
    kelly_fraction: float = 0.25,
) -> float:
    """Bankroll × kelly_fraction × f*  (raw, unquantized)."""
    f = kelly_fraction_full(p, payout_per_yuan)
    return max(0.0, bankroll * kelly_fraction * f)


def break_even_per_leg_edge(n_legs: int) -> float:
    """Per-leg multiplier r = p×SP needed so that r^N × 0.65 = 1.

    Returns r − 1 (the per-leg edge). Useful for sanity / docs.
    """
    return (1.0 / RETURN_RATE) ** (1.0 / n_legs) - 1.0


def combo_from_candidates(legs: Iterable[Candidate]) -> Combo:
    return Combo(legs=tuple(legs))
