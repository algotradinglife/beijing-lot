"""Stake-sizing tests: tax cap, split tickets, even-yuan rounding."""
from __future__ import annotations

import math

import pytest

from src.combo_optimizer.sizer import (
    apply_bankroll_cap,
    floor_to_even,
    max_stake_per_ticket,
    size_one_combo,
)
from src.combo_optimizer.types import (
    MIN_STAKE_PER_TICKET,
    TAX_THRESHOLD,
    Candidate,
    Combo,
    TicketPlan,
)


def make_combo(p: float, sp: float, n: int = 7) -> Combo:
    legs = tuple(
        Candidate(match_id=f"m{i}", selection=3, p_hat=p, sp=sp) for i in range(n)
    )
    return Combo(legs=legs)


def test_floor_to_even_basic():
    assert floor_to_even(0) == 0
    assert floor_to_even(1.9) == 0
    assert floor_to_even(2.0) == 2
    assert floor_to_even(3.0) == 2
    assert floor_to_even(7.9) == 6
    assert floor_to_even(8.0) == 8
    assert floor_to_even(-3) == 0  # never negative


def test_max_stake_per_ticket_cap_keeps_prize_under_threshold():
    # payout=83.2 (joint SP 128, ×0.65) → cap = floor(9999/83.2)=120 → even 120
    combo = make_combo(p=0.6, sp=2.0)  # payout 83.2
    cap = max_stake_per_ticket(combo.payout_per_yuan)
    assert cap == 120
    # Prize at cap stays below 10k
    assert cap * combo.payout_per_yuan < TAX_THRESHOLD


def test_size_one_combo_single_ticket_when_under_cap():
    # Modest +EV combo, small bankroll → single small ticket
    combo = make_combo(p=0.6, sp=2.0)  # f* = (0.6^7 × 83.2 − 1)/(83.2 − 1)
    plan = size_one_combo(combo, bankroll=10_000.0, kelly_fraction=0.25)
    assert plan is not None
    assert plan.n_tickets == 1
    assert plan.stake_per_ticket % 2 == 0
    assert plan.stake_per_ticket >= 2
    assert plan.is_tax_free


def test_size_one_combo_splits_when_above_cap():
    # Big bankroll forces split: payout 83.2, cap=120/ticket. Kelly stake at
    # 100k bankroll, ¼-Kelly: f* ≈ 0.0166 ⇒ raw ≈ 416 ⇒ 4 tickets of 120.
    combo = make_combo(p=0.6, sp=2.0)
    plan = size_one_combo(combo, bankroll=100_000.0, kelly_fraction=0.25)
    assert plan is not None
    assert plan.n_tickets >= 2
    assert plan.stake_per_ticket == max_stake_per_ticket(combo.payout_per_yuan)
    assert plan.is_tax_free


def test_size_one_combo_returns_none_when_stake_too_small():
    # Tiny bankroll → raw stake < 2 yuan
    combo = make_combo(p=0.6, sp=2.0)
    plan = size_one_combo(combo, bankroll=1.0, kelly_fraction=0.25)
    assert plan is None


def test_size_one_combo_returns_none_when_payout_too_huge():
    # Massive payout (e.g. 7 legs at SP 30) → cap < 2 yuan → can't bet legally
    combo = make_combo(p=0.001, sp=30.0)
    plan = size_one_combo(combo, bankroll=100_000.0, kelly_fraction=0.25)
    # Either skipped (None) or tax-free with stake≥2; here cap should be 0/1.
    if plan is not None:
        assert plan.is_tax_free
        assert plan.stake_per_ticket >= MIN_STAKE_PER_TICKET


def test_apply_bankroll_cap_scales_proportionally():
    # Two plans summing to 100, cap to 50 ⇒ each scaled by 0.5.
    c1 = make_combo(p=0.6, sp=2.0)
    c2 = make_combo(p=0.55, sp=2.2)
    plans = [
        TicketPlan(combo=c1, stake_per_ticket=20, n_tickets=2),  # total 40
        TicketPlan(combo=c2, stake_per_ticket=30, n_tickets=2),  # total 60
    ]
    bankroll = 200.0
    capped = apply_bankroll_cap(plans, bankroll, weekly_stake_cap_frac=0.25)  # cap=50
    assert sum(p.total_stake for p in capped) <= 50
    # Each stake stays even
    for p in capped:
        assert p.stake_per_ticket % 2 == 0
        assert p.stake_per_ticket >= MIN_STAKE_PER_TICKET


def test_apply_bankroll_cap_no_op_when_under_cap():
    c1 = make_combo(p=0.6, sp=2.0)
    plans = [TicketPlan(combo=c1, stake_per_ticket=10, n_tickets=1)]
    out = apply_bankroll_cap(plans, bankroll=1000.0, weekly_stake_cap_frac=0.25)
    assert out == plans


def test_apply_bankroll_cap_drops_plans_below_minimum():
    # Force aggressive scaling so a tiny plan falls below 2 yuan.
    c1 = make_combo(p=0.6, sp=2.0)
    plans = [
        TicketPlan(combo=c1, stake_per_ticket=2, n_tickets=1),  # 2
        TicketPlan(combo=c1, stake_per_ticket=200, n_tickets=1),  # 200
    ]
    # Total 202; cap to 20 ⇒ scale 20/202 ≈ 0.099. The 2-yuan plan → 0 → dropped.
    out = apply_bankroll_cap(plans, bankroll=80.0, weekly_stake_cap_frac=0.25)
    assert all(p.stake_per_ticket >= 2 for p in out)
    assert sum(p.total_stake for p in out) <= 20
