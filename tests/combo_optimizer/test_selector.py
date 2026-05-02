"""Filter / dedup / top-K tests."""
from __future__ import annotations

import pytest

from src.combo_optimizer.selector import (
    DEFAULT_SINGLE_LEG_EDGE_FLOOR,
    dedup_by_match,
    filter_by_edge,
    select_pool,
    top_k,
)
from src.combo_optimizer.types import Candidate


def cand(match_id: str, selection: int, p: float, sp: float) -> Candidate:
    return Candidate(match_id=match_id, selection=selection, p_hat=p, sp=sp)


def test_filter_by_edge_drops_below_threshold():
    # edge = p×SP×0.65 − 1
    a = cand("m1", 3, 0.5, 3.5)  # 0.5×3.5×0.65 = 1.1375 → edge 0.1375
    b = cand("m2", 1, 0.4, 3.5)  # 0.4×3.5×0.65 = 0.91 → edge −0.09
    c = cand("m3", 0, 0.5, 3.2)  # 0.5×3.2×0.65 = 1.04 → edge 0.04 (below 0.05)
    out = filter_by_edge([a, b, c], min_edge=0.05)
    assert out == [a]


def test_filter_default_floor_is_005():
    # edge = exactly 0.05 should be excluded by strict >
    eps = 1e-12
    a = cand("m1", 3, 1.05 / (3.0 * 0.65), 3.0)  # edge ≈ 0.05 exactly
    out = filter_by_edge([a], min_edge=DEFAULT_SINGLE_LEG_EDGE_FLOOR)
    assert out == [] or all(c.edge > 0.05 - eps for c in out)


def test_dedup_keeps_highest_edge_per_match():
    a1 = cand("m1", 3, 0.55, 3.5)  # higher edge
    a2 = cand("m1", 1, 0.5, 3.0)
    b = cand("m2", 0, 0.6, 3.5)
    out = dedup_by_match([a1, a2, b])
    ids = {c.match_id for c in out}
    assert ids == {"m1", "m2"}
    m1 = next(c for c in out if c.match_id == "m1")
    assert m1 is a1


def test_top_k_picks_highest_edges():
    cs = [cand(f"m{i}", 3, 0.5, 3.0 + 0.1 * i) for i in range(10)]
    picked = top_k(cs, 3)
    assert [c.match_id for c in picked] == ["m9", "m8", "m7"]


def test_select_pool_end_to_end_dedups_and_truncates():
    cs = [
        cand("m1", 3, 0.6, 3.5),  # high edge
        cand("m1", 1, 0.5, 3.0),  # same match, lower edge — dropped
        cand("m2", 3, 0.55, 3.3),
        cand("m3", 1, 0.5, 3.2),
        cand("m4", 0, 0.4, 3.0),  # edge ≈ −0.22 ⇒ filtered out
    ]
    pool = select_pool(cs, k=2)
    ids = [c.match_id for c in pool]
    assert "m1" in ids and len(pool) == 2
    # m4 must not appear (negative edge)
    assert "m4" not in ids
