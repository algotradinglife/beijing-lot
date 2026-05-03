"""Tests for greedy diversity-aware combo selection."""
from __future__ import annotations

from collections import Counter

import pytest

from src.combo_optimizer.builder import (
    build_combos,
    enumerate_combos,
    rank_combos,
    select_diverse_combos,
)
from src.combo_optimizer.types import Candidate


def _mk_candidate(match_id: str, sp: float, p_hat: float, selection: int = 3) -> Candidate:
    return Candidate(match_id=match_id, selection=selection, p_hat=p_hat, sp=sp)


def _make_unbalanced_pool():
    """Build a pool where leg ``a`` has dramatically higher per-leg edge.

    Without diversity, ``a`` will appear in every selected combo; with
    diversity it should be capped.
    """
    legs = []
    # leg a: very high q (over-priced)
    legs.append(_mk_candidate("M01", sp=4.0, p_hat=0.50))  # q = 2.0
    # legs b..h: modest q ~ 1.2
    for i in range(2, 9):
        legs.append(_mk_candidate(f"M{i:02d}", sp=4.0, p_hat=0.30))  # q = 1.2
    return legs


def test_legacy_ev_only_concentrates_on_strong_leg():
    """Pure EV ranking puts the strong leg in nearly every selected combo."""
    pool = _make_unbalanced_pool()
    eligible = enumerate_combos(pool, n_legs=4)
    # Use loose EV filter so all are eligible
    selected = rank_combos(eligible, max_combos=20)
    leg_a_count = sum(1 for c in selected if any(l.match_id == "M01" for l in c.legs))
    # Without diversity, the strong leg should appear in EVERY selected combo
    assert leg_a_count >= 18, f"expected near-100% concentration, got {leg_a_count}/20"


def test_diversity_reduces_concentration():
    """Greedy diversity sharply caps the strong leg's appearance rate."""
    pool = _make_unbalanced_pool()
    eligible = enumerate_combos(pool, n_legs=4)
    selected = select_diverse_combos(eligible, max_combos=20, diversity_lambda=0.5)
    leg_a_count = sum(1 for c in selected if any(l.match_id == "M01" for l in c.legs))
    # With moderate diversity λ, leg a should be capped
    assert leg_a_count < 20, "diversity must reduce concentration"
    # And other legs should appear meaningfully
    other_legs = Counter()
    for c in selected:
        for l in c.legs:
            other_legs[l.match_id] += 1
    # The strong leg should not dominate (no single leg in >80% of combos)
    max_appearances = max(other_legs.values())
    assert max_appearances <= 16, (
        f"Even leg a should not exceed 80% under λ=0.5, got max {max_appearances}/20"
    )


def test_diversity_lambda_zero_matches_legacy():
    """λ=0 should reproduce pure EV ranking."""
    pool = _make_unbalanced_pool()
    eligible = enumerate_combos(pool, n_legs=4)
    legacy = rank_combos(eligible, max_combos=20)
    diverse = select_diverse_combos(eligible, max_combos=20, diversity_lambda=0.0)
    # The first pick must match (highest-EV combo); later picks may diverge if
    # ties exist, but at λ=0 the ordering is by EV with stable tie-break.
    assert legacy[0].ev == diverse[0].ev


def test_higher_lambda_more_uniform_distribution():
    """As λ grows, the leg distribution should become more uniform."""
    pool = _make_unbalanced_pool()
    eligible = enumerate_combos(pool, n_legs=4)

    def max_appearances(lmbd):
        sel = select_diverse_combos(eligible, max_combos=20, diversity_lambda=lmbd)
        c = Counter()
        for combo in sel:
            for l in combo.legs:
                c[l.match_id] += 1
        return max(c.values()) if c else 0

    low = max_appearances(0.1)
    high = max_appearances(2.0)
    assert high <= low, f"λ=2 should be more uniform than λ=0.1, got {high} vs {low}"


def test_returns_empty_when_no_combos():
    selected = select_diverse_combos([], max_combos=10, diversity_lambda=0.5)
    assert selected == []


def test_respects_max_combos_cap():
    pool = _make_unbalanced_pool()
    eligible = enumerate_combos(pool, n_legs=4)
    selected = select_diverse_combos(eligible, max_combos=5, diversity_lambda=0.5)
    assert len(selected) == 5


def test_build_combos_uses_diversity_by_default():
    """Top-level build_combos should default to diversity-aware mode."""
    pool = _make_unbalanced_pool()
    selected = build_combos(pool, n_legs=4, min_ev=-1.0, max_combos=20)
    leg_a_count = sum(1 for c in selected if any(l.match_id == "M01" for l in c.legs))
    assert leg_a_count < 20, "default build_combos should diversify"


def test_legacy_mode_via_lambda_zero():
    pool = _make_unbalanced_pool()
    selected = build_combos(
        pool, n_legs=4, min_ev=-1.0, max_combos=20, diversity_lambda=0.0
    )
    leg_a_count = sum(1 for c in selected if any(l.match_id == "M01" for l in c.legs))
    assert leg_a_count >= 18, "diversity_lambda=0 should match legacy concentration"
