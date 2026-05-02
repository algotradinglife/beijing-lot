"""Tests for Kelly stake + realised PnL."""
from __future__ import annotations

import pytest

from src.backtest.kelly import RETURN_RATE, quarter_kelly_stake, realised_pnl


def test_no_stake_when_no_edge():
    # SP = 1.50, p = 0.5 -> p × SP × 0.65 = 0.4875 < 1, no edge
    assert quarter_kelly_stake(p=0.5, sp=1.5, bankroll=10_000) == 0.0


def test_no_stake_when_payout_below_one():
    # SP × 0.65 ≤ 1 means decimal odds ≤ 1 -> no real bet possible
    assert quarter_kelly_stake(p=0.99, sp=1.0, bankroll=10_000) == 0.0


def test_quarter_kelly_capped_per_match():
    # Huge edge (p=0.9, sp=10): full Kelly would be enormous.  5% cap kicks in.
    stake = quarter_kelly_stake(p=0.9, sp=10.0, bankroll=10_000)
    assert stake <= 0.05 * 10_000 + 1e-9
    assert stake > 0


def test_quarter_kelly_value_unbounded():
    # Modest edge: p=0.4, sp=4.0 -> o_eff=2.6, edge = 0.4*2.6-1 = 0.04
    # f_kelly = 0.04 / 1.6 = 0.025 ; quarter = 0.00625
    # bankroll 10_000 -> stake ~62.5
    stake = quarter_kelly_stake(p=0.4, sp=4.0, bankroll=10_000)
    assert 50 < stake < 80


def test_realised_pnl_win():
    # 100 staked, sp=2.0, win -> profit = 100 * (2.0*0.65 - 1) = 100*0.3 = 30
    assert abs(realised_pnl(100.0, 2.0, won=True) - 30.0) < 1e-9


def test_realised_pnl_loss():
    assert realised_pnl(100.0, 2.0, won=False) == -100.0


def test_realised_pnl_zero_stake():
    assert realised_pnl(0.0, 5.0, won=True) == 0.0
