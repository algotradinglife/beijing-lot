"""Combo enumeration / EV-threshold tests."""
from __future__ import annotations

import math

import pytest

from src.combo_optimizer.builder import (
    build_combos,
    enumerate_combos,
    filter_by_combo_ev,
    rank_combos,
)
from src.combo_optimizer.types import Candidate


def _pool(k: int, p: float = 0.55, sp: float = 3.0) -> list[Candidate]:
    return [
        Candidate(match_id=f"m{i}", selection=3, p_hat=p, sp=sp) for i in range(k)
    ]


def test_enumerate_count_c_14_7():
    pool = _pool(14)
    combos = enumerate_combos(pool, n_legs=7)
    assert len(combos) == math.comb(14, 7) == 3432


def test_enumerate_returns_empty_when_pool_too_small():
    assert enumerate_combos(_pool(5), n_legs=7) == []


def test_combo_legs_have_distinct_match_ids():
    combos = enumerate_combos(_pool(8), n_legs=7)
    for c in combos:
        ids = [leg.match_id for leg in c.legs]
        assert len(set(ids)) == len(ids)


def test_filter_by_combo_ev_keeps_only_above_threshold():
    # 7 legs at p=0.55, sp=3.0 ⇒ joint p = 0.55^7, payout = 3^7 × 0.65
    # ev = 0.55^7 × 3^7 × 0.65 − 1 = (1.65)^7 × 0.65 − 1 ≈ 24.9
    pool = _pool(8, p=0.55, sp=3.0)
    combos = enumerate_combos(pool, n_legs=7)
    assert all(c.ev > 1.0 for c in combos)
    kept = filter_by_combo_ev(combos, min_ev=0.10)
    assert len(kept) == len(combos)
    # Threshold above the actual EV ⇒ everything dropped
    dropped = filter_by_combo_ev(combos, min_ev=1e6)
    assert dropped == []


def test_rank_combos_by_ev_descending():
    # Build a heterogeneous pool: one very strong candidate
    base = _pool(7, p=0.5, sp=3.0)
    strong = Candidate(match_id="strong", selection=3, p_hat=0.7, sp=4.0)
    pool = base + [strong]
    combos = enumerate_combos(pool, n_legs=7)
    ranked = rank_combos(combos, max_combos=3)
    # Top combo should include the strong leg
    assert any(leg.match_id == "strong" for leg in ranked[0].legs)
    # Sorted descending
    evs = [c.ev for c in ranked]
    assert evs == sorted(evs, reverse=True)


def test_build_combos_filters_and_caps():
    pool = _pool(10, p=0.55, sp=3.0)
    combos = build_combos(pool, n_legs=7, min_ev=0.10, max_combos=5)
    assert len(combos) == 5
    assert all(c.ev >= 0.10 for c in combos)
