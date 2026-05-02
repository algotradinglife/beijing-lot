"""Tests for the per-week combo builder."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.sweep.combo_builder import (
    build_combos_for_week,
    materialize_combos,
    iter_weekly_combos,
    _choose_one_per_match,
)


def _make_picks(n_matches: int, week: int = 202301) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(dict(
        match_id=[f"m{i}" for i in range(n_matches)],
        week_key=[week] * n_matches,
        sp=rng.uniform(2.0, 8.0, n_matches),
        p_train=rng.uniform(0.15, 0.45, n_matches),
        did_win=rng.integers(0, 2, n_matches),
        q_train=rng.uniform(1.05, 1.5, n_matches),
    ))


def test_no_same_match_collisions_when_dedup():
    df = pd.concat([
        _make_picks(5),
        _make_picks(5).assign(q_train=lambda d: d.q_train + 1.0),  # duplicate match_ids
    ], ignore_index=True)
    out = _choose_one_per_match(df, np.random.default_rng(0))
    assert out["match_id"].is_unique
    # The kept rows must be the higher-q duplicates
    assert (out["q_train"] > 1.5).any()


def test_enumeration_when_small():
    picks = _make_picks(6)
    combos = build_combos_for_week(picks, n_legs=3, enumerate_threshold=5000)
    # C(6,3) = 20
    assert len(combos) == 20
    for c in combos:
        assert len(set(c)) == 3  # no duplicate leg indices in a combo


def test_sampling_when_large():
    picks = _make_picks(20)
    rng = np.random.default_rng(0)
    combos = build_combos_for_week(picks, n_legs=4, max_combos_per_week=50,
                                   enumerate_threshold=10, rng=rng)
    assert 0 < len(combos) <= 50
    seen = set(tuple(sorted(c)) for c in combos)
    assert len(seen) == len(combos)  # no dupes


def test_returns_empty_when_too_few():
    picks = _make_picks(3)
    assert build_combos_for_week(picks, n_legs=5) == []


def test_materialize_combos_correct_payout():
    picks = pd.DataFrame(dict(
        match_id=["a", "b", "c"], sp=[2.0, 3.0, 5.0],
        p_train=[0.5, 0.4, 0.2], did_win=[1, 1, 0],
    ))
    mat = materialize_combos(picks, [[0, 1], [0, 2], [1, 2]])
    assert mat.iloc[0]["joint_sp"] == 6.0
    assert mat.iloc[0]["payout_per_yuan"] == 6.0 * 0.65
    assert mat.iloc[0]["all_hit"]  # both hits
    assert not mat.iloc[1]["all_hit"]  # c missed


def test_iter_weekly_combos_groups_by_week():
    p1 = _make_picks(5, week=202301)
    p2 = _make_picks(6, week=202302)
    qual = pd.concat([p1, p2], ignore_index=True)
    weeks = list(iter_weekly_combos(qual, n_legs=2, enumerate_threshold=5000))
    assert len(weeks) == 2
    week_keys = [w[0] for w in weeks]
    assert sorted(week_keys) == [202301, 202302]
