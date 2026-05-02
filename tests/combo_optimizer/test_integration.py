"""End-to-end test: 30 mock candidates → build_plan."""
from __future__ import annotations

import random

import pytest

from src.combo_optimizer import Candidate, TicketPlan, build_plan


def make_mock_candidates(seed: int = 42, n: int = 30) -> list[Candidate]:
    """Realistic-ish edge distribution: most marginal, a few strong."""
    rng = random.Random(seed)
    cands: list[Candidate] = []
    for i in range(n):
        sp = rng.uniform(2.0, 5.0)
        # Implied (no-edge) probability is 1/SP; add a small edge.
        # ~70% of candidates: edge in [3%, 8%]; ~30%: edge in [8%, 15%].
        edge_target = rng.uniform(0.03, 0.08) if rng.random() < 0.7 else rng.uniform(0.08, 0.15)
        # p × SP × 0.65 = 1 + edge ⇒ p = (1 + edge) / (SP × 0.65)
        p_hat = (1.0 + edge_target) / (sp * 0.65)
        p_hat = min(0.95, max(0.01, p_hat))
        sel = rng.choice([3, 1, 0])
        cands.append(
            Candidate(match_id=f"match_{i:02d}", selection=sel, p_hat=p_hat, sp=sp)
        )
    return cands


def test_integration_basic_run():
    cands = make_mock_candidates()
    bankroll = 100_000.0
    plans = build_plan(cands, bankroll=bankroll)
    # Should produce some combos (with the mock distribution).
    assert isinstance(plans, list)
    assert len(plans) > 0


def test_integration_all_tickets_tax_free():
    cands = make_mock_candidates()
    plans = build_plan(cands, bankroll=100_000.0)
    for p in plans:
        assert p.is_tax_free, (
            f"Ticket prize {p.prize_per_ticket} ≥ 10000 — tax cliff breach"
        )


def test_integration_total_stake_within_cap():
    cands = make_mock_candidates()
    bankroll = 100_000.0
    plans = build_plan(cands, bankroll=bankroll, weekly_stake_cap_frac=0.25)
    total = sum(p.total_stake for p in plans)
    assert total <= 0.25 * bankroll + 0.5  # allow tiny rounding margin


def test_integration_stakes_are_even_integers_at_least_two():
    cands = make_mock_candidates()
    plans = build_plan(cands, bankroll=100_000.0)
    for p in plans:
        assert isinstance(p.stake_per_ticket, int)
        assert p.stake_per_ticket >= 2
        assert p.stake_per_ticket % 2 == 0


def test_integration_combos_have_seven_distinct_matches():
    cands = make_mock_candidates()
    plans = build_plan(cands, bankroll=100_000.0)
    for p in plans:
        ids = [leg.match_id for leg in p.combo.legs]
        assert len(ids) == 7
        assert len(set(ids)) == 7  # no same-match collision


def test_integration_too_few_candidates_returns_empty():
    cands = make_mock_candidates(n=5)
    plans = build_plan(cands, bankroll=100_000.0)
    assert plans == []


def test_integration_no_positive_edge_candidates_returns_empty():
    # All candidates have edge below the floor.
    cands = [
        Candidate(match_id=f"m{i}", selection=3, p_hat=0.30, sp=3.0)
        for i in range(30)
    ]
    # 0.30 × 3.0 × 0.65 = 0.585 ⇒ edge −0.415, all filtered out
    plans = build_plan(cands, bankroll=100_000.0)
    assert plans == []
