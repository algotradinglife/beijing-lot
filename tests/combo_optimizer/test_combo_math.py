"""Pure-math tests for combo EV / Kelly / payout."""
from __future__ import annotations

import math

import pytest

from src.combo_optimizer.combo_math import (
    break_even_per_leg_edge,
    combo_ev,
    combo_payout_per_yuan,
    kelly_fraction_full,
    kelly_stake,
)
from src.combo_optimizer.types import RETURN_RATE, Candidate, Combo


def _legs(n: int, sp: float, p: float) -> list[Candidate]:
    return [
        Candidate(match_id=f"m{i}", selection=3, p_hat=p, sp=sp) for i in range(n)
    ]


def test_combo_payout_seven_legs_sp_two():
    legs = _legs(7, sp=2.0, p=0.6)
    # 2^7 = 128, × 0.65 = 83.2
    assert combo_payout_per_yuan(legs) == pytest.approx(2.0 ** 7 * RETURN_RATE)
    assert combo_payout_per_yuan(legs) == pytest.approx(83.2)


def test_combo_ev_seven_legs_p06_sp2():
    legs = _legs(7, sp=2.0, p=0.6)
    # joint p = 0.6^7 ≈ 0.0279936; payout 83.2 ⇒ EV = 0.0279936×83.2 − 1
    expected = 0.6 ** 7 * 2.0 ** 7 * RETURN_RATE - 1.0
    assert combo_ev(legs) == pytest.approx(expected)
    # Sanity: this combo IS +EV (1.2^7 = 2.986... > 1.538)
    assert combo_ev(legs) > 0


def test_combo_ev_breakeven_sanity():
    # Per-leg multiplier r = 1.064 ≈ break-even at 7 legs
    r = (1.0 / RETURN_RATE) ** (1.0 / 7)
    # Pick p=0.5, sp = r/p so that p×sp = r exactly.
    p = 0.5
    sp = r / p
    legs = _legs(7, sp=sp, p=p)
    assert combo_ev(legs) == pytest.approx(0.0, abs=1e-12)


def test_break_even_per_leg_edge_matches_memory_doc():
    # From the v2 pivot memo: 7-leg break-even ≈ 6.4%, 10-leg ≈ 4.4%
    # Memo rounds to 6.4% / 4.4%; allow 1e-3 tolerance.
    assert break_even_per_leg_edge(7) == pytest.approx(0.0635, abs=1e-3)
    assert break_even_per_leg_edge(10) == pytest.approx(0.0444, abs=1e-3)


def test_combo_dataclass_properties_match_helpers():
    legs = tuple(_legs(7, sp=3.0, p=0.4))
    combo = Combo(legs=legs)
    assert combo.joint_p == pytest.approx(0.4 ** 7)
    assert combo.joint_sp == pytest.approx(3.0 ** 7)
    assert combo.payout_per_yuan == pytest.approx(3.0 ** 7 * RETURN_RATE)
    assert combo.ev == pytest.approx(combo_ev(legs))


def test_kelly_fraction_zero_when_negative_ev():
    # p × payout = 0.4 × 1.5 = 0.6 < 1 ⇒ −EV ⇒ f* = 0
    assert kelly_fraction_full(p=0.4, payout_per_yuan=1.5) == 0.0


def test_kelly_fraction_basic():
    # p=0.6, payout=2.0 ⇒ f* = (0.6×2 − 1)/(2−1) = 0.2
    assert kelly_fraction_full(p=0.6, payout_per_yuan=2.0) == pytest.approx(0.2)


def test_kelly_stake_quarter_kelly():
    # f* = 0.2, bankroll = 100k, fraction = 0.25 ⇒ 5_000
    assert kelly_stake(
        bankroll=100_000.0, p=0.6, payout_per_yuan=2.0, kelly_fraction=0.25
    ) == pytest.approx(5_000.0)


def test_kelly_handles_degenerate_payout():
    # payout_per_yuan ≤ 1 means b ≤ 0 ⇒ no Kelly
    assert kelly_fraction_full(p=0.99, payout_per_yuan=1.0) == 0.0
    assert kelly_fraction_full(p=0.99, payout_per_yuan=0.5) == 0.0
