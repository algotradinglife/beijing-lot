"""Filter and top-K candidate selection.

Two operations:
1. Drop low-edge candidates (single-leg edge ≤ T).
2. Same-match dedup: at most ONE candidate per match_id (a combo cannot
   have two legs on the same match — only one outcome happens).
3. Take top-K by edge.
"""
from __future__ import annotations

from typing import Iterable, List

from .types import Candidate

DEFAULT_SINGLE_LEG_EDGE_FLOOR = 0.05


def filter_by_edge(
    candidates: Iterable[Candidate], min_edge: float = DEFAULT_SINGLE_LEG_EDGE_FLOOR
) -> List[Candidate]:
    """Strictly greater than min_edge keeps marginal picks out."""
    return [c for c in candidates if c.edge > min_edge]


def dedup_by_match(candidates: Iterable[Candidate]) -> List[Candidate]:
    """Keep the highest-edge candidate per match_id."""
    best: dict[str, Candidate] = {}
    for c in candidates:
        prev = best.get(c.match_id)
        if prev is None or c.edge > prev.edge:
            best[c.match_id] = c
    # Stable order: by descending edge.
    return sorted(best.values(), key=lambda c: c.edge, reverse=True)


def top_k(candidates: Iterable[Candidate], k: int) -> List[Candidate]:
    ranked = sorted(candidates, key=lambda c: c.edge, reverse=True)
    return ranked[:k]


def select_pool(
    candidates: Iterable[Candidate],
    *,
    min_edge: float = DEFAULT_SINGLE_LEG_EDGE_FLOOR,
    k: int = 14,
) -> List[Candidate]:
    """End-to-end: filter → dedup → top-K."""
    return top_k(dedup_by_match(filter_by_edge(candidates, min_edge=min_edge)), k)
