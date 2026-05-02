"""Combo enumeration and EV ranking.

Given a small candidate pool (top-K, K ≤ ~20), enumerate C(K, n_legs)
combos, drop those below an EV threshold, and rank by EV descending.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable, List

from .types import Candidate, Combo


def enumerate_combos(
    candidates: Iterable[Candidate], n_legs: int = 7
) -> List[Combo]:
    pool = list(candidates)
    if len(pool) < n_legs:
        return []
    return [Combo(legs=tuple(legs)) for legs in combinations(pool, n_legs)]


def filter_by_combo_ev(combos: Iterable[Combo], min_ev: float) -> List[Combo]:
    return [c for c in combos if c.ev >= min_ev]


def rank_combos(combos: Iterable[Combo], max_combos: int) -> List[Combo]:
    ranked = sorted(combos, key=lambda c: c.ev, reverse=True)
    return ranked[:max_combos]


def build_combos(
    candidates: Iterable[Candidate],
    *,
    n_legs: int = 7,
    min_ev: float = 0.10,
    max_combos: int = 50,
) -> List[Combo]:
    return rank_combos(
        filter_by_combo_ev(enumerate_combos(candidates, n_legs=n_legs), min_ev),
        max_combos,
    )
