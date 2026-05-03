"""Combo enumeration and EV ranking.

Given a small candidate pool (top-K, K ≤ ~20), enumerate C(K, n_legs)
combos, drop those below an EV threshold, and rank by EV descending.

Two ranking modes:
  - **EV-only** (legacy):  pure EV-descending sort. Single highest-EV leg
    will appear in nearly every selected combo, causing portfolio
    correlation collapse.
  - **Diversity-aware (greedy)**:  at each pick step, score combos by
    ``ev - λ × overlap_penalty`` where overlap_penalty = sum of how many
    times each leg has already appeared. Smoothly trades EV for
    diversification.
"""
from __future__ import annotations

from collections import Counter
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
    """Pure EV-descending rank (legacy)."""
    ranked = sorted(combos, key=lambda c: c.ev, reverse=True)
    return ranked[:max_combos]


def _leg_id(leg: Candidate) -> str:
    """Stable identifier for a leg (match_id + selection)."""
    return f"{leg.match_id}:{leg.selection}"


def select_diverse_combos(
    combos: Iterable[Combo],
    max_combos: int,
    *,
    diversity_lambda: float = 0.5,
) -> List[Combo]:
    """Greedy diversity-aware selection.

    At each step pick the combo maximizing
        score = combo.ev - diversity_lambda × Σ (1 + leg_count[l])
    where leg_count is the number of times each leg already appears in
    selected combos. The "1 +" softens the early-stage penalty so the
    first combo is still picked for raw EV.

    diversity_lambda interpretation:
      - 0.0 → identical to pure EV ranking
      - 0.3 → light diversity bias (typical)
      - 0.5 → moderate (default)
      - 1.0 → strong diversity, may sacrifice EV
      - >2  → diversity dominates, near-uniform leg distribution
    """
    pool = list(combos)
    if not pool or max_combos <= 0:
        return []

    leg_count: Counter = Counter()
    selected: List[Combo] = []
    remaining = list(pool)

    while remaining and len(selected) < max_combos:
        # Score each remaining combo
        best_idx = -1
        best_score = float("-inf")
        for i, c in enumerate(remaining):
            penalty = sum(leg_count[_leg_id(l)] for l in c.legs)
            score = c.ev - diversity_lambda * penalty
            if score > best_score:
                best_score = score
                best_idx = i
        # Pick the best
        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        for l in chosen.legs:
            leg_count[_leg_id(l)] += 1

    return selected


def build_combos(
    candidates: Iterable[Candidate],
    *,
    n_legs: int = 7,
    min_ev: float = 0.10,
    max_combos: int = 50,
    diversity_lambda: float = 0.5,
) -> List[Combo]:
    """Enumerate, filter, and rank combos.

    If ``diversity_lambda > 0`` (default 0.5), uses greedy diversity-aware
    selection so the same leg won't dominate the portfolio. Set to 0.0
    to recover legacy EV-only ranking.
    """
    eligible = filter_by_combo_ev(
        enumerate_combos(candidates, n_legs=n_legs), min_ev
    )
    if diversity_lambda <= 0:
        return rank_combos(eligible, max_combos)
    return select_diverse_combos(
        eligible, max_combos, diversity_lambda=diversity_lambda
    )
