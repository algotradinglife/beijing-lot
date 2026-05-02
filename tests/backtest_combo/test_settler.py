"""Settler unit tests."""
from __future__ import annotations

import pytest

from src.backtest_combo.settler import settle_combo, settle_plan
from src.combo_optimizer.types import RETURN_RATE, Candidate, Combo, TicketPlan


def make_combo(legs: list[tuple[str, int, float, float]]) -> Combo:
    return Combo(legs=tuple(
        Candidate(match_id=mid, selection=sel, p_hat=p, sp=sp)
        for mid, sel, p, sp in legs
    ))


def test_settle_combo_all_hit():
    combo = make_combo([("M1", 3, 0.5, 2.0), ("M2", 1, 0.3, 4.0), ("M3", 0, 0.4, 3.0)])
    actuals = {
        "M1": {"result_code": "3", "winning_sp": 2.1},
        "M2": {"result_code": "1", "winning_sp": 4.2},
        "M3": {"result_code": "0", "winning_sp": 3.1},
    }
    hit, payout = settle_combo(combo, actuals)
    assert hit is True
    expected = 2.1 * 4.2 * 3.1 * RETURN_RATE
    assert payout == pytest.approx(expected, rel=1e-9)


def test_settle_combo_one_miss():
    combo = make_combo([("M1", 3, 0.5, 2.0), ("M2", 1, 0.3, 4.0)])
    actuals = {
        "M1": {"result_code": "3", "winning_sp": 2.1},
        "M2": {"result_code": "0", "winning_sp": 4.2},  # picked 1, was 0
    }
    hit, payout = settle_combo(combo, actuals)
    assert hit is False
    assert payout == 0.0


def test_settle_combo_missing_match():
    combo = make_combo([("M1", 3, 0.5, 2.0), ("M_unknown", 1, 0.3, 4.0)])
    actuals = {"M1": {"result_code": "3", "winning_sp": 2.1}}
    hit, _ = settle_combo(combo, actuals)
    assert hit is False


def test_settle_combo_zero_sp_treated_as_miss():
    combo = make_combo([("M1", 3, 0.5, 2.0)])
    actuals = {"M1": {"result_code": "3", "winning_sp": 0.0}}
    hit, payout = settle_combo(combo, actuals)
    assert hit is False
    assert payout == 0.0


def test_settle_plan_profit_when_hit():
    combo = make_combo([("M1", 3, 0.5, 2.0), ("M2", 1, 0.3, 4.0)])
    plan = TicketPlan(combo=combo, stake_per_ticket=10, n_tickets=3)
    actuals = {
        "M1": {"result_code": "3", "winning_sp": 2.0},
        "M2": {"result_code": "1", "winning_sp": 4.0},
    }
    s = settle_plan(plan, actuals)
    payout = 2.0 * 4.0 * RETURN_RATE  # 5.2
    assert s.all_hit is True
    assert s.total_stake == 30
    assert s.total_profit == pytest.approx(30 * (payout - 1.0))


def test_settle_plan_loss_when_miss():
    combo = make_combo([("M1", 3, 0.5, 2.0), ("M2", 1, 0.3, 4.0)])
    plan = TicketPlan(combo=combo, stake_per_ticket=10, n_tickets=3)
    actuals = {
        "M1": {"result_code": "0", "winning_sp": 5.0},
        "M2": {"result_code": "1", "winning_sp": 4.0},
    }
    s = settle_plan(plan, actuals)
    assert s.all_hit is False
    assert s.total_stake == 30
    assert s.total_profit == -30.0
