"""Build N-leg combos per ISO week from the qualifying-picks stream.

Constraint: legs in a combo must come from DISTINCT matches (one option
per match). For a week with K candidates spanning M distinct matches,
we sample up to ``max_combos_per_week`` combos uniformly without
replacement; if C(M, N) <= 5000 we enumerate all.
"""
from __future__ import annotations

from itertools import combinations
from math import comb
from typing import Iterator, List, Optional

import numpy as np
import pandas as pd


def _choose_one_per_match(picks: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """When multiple options of the same match qualify (rare), pick the
    one with the highest ``p_train * sp`` (i.e., highest q_train)."""
    if picks.empty:
        return picks
    return (
        picks.sort_values("q_train", ascending=False)
        .drop_duplicates("match_id", keep="first")
        .reset_index(drop=True)
    )


def build_combos_for_week(
    week_picks: pd.DataFrame,
    n_legs: int,
    *,
    max_combos_per_week: int = 500,
    enumerate_threshold: int = 5000,
    rng: Optional[np.random.Generator] = None,
) -> List[List[int]]:
    """Returns a list of N-tuples (each is a list of row indices into
    ``week_picks``). Indices index into the *one-per-match* deduped frame —
    callers should pass already-deduped picks."""
    rng = rng or np.random.default_rng(0)
    K = len(week_picks)
    if K < n_legs:
        return []

    total = comb(K, n_legs)
    if total <= enumerate_threshold:
        return [list(c) for c in combinations(range(K), n_legs)]

    # Sample without replacement: each combo is a sorted random subset.
    # Use rejection on duplicates.
    seen: set[tuple[int, ...]] = set()
    out: list[list[int]] = []
    target = min(max_combos_per_week, total)
    attempts = 0
    while len(out) < target and attempts < target * 4:
        attempts += 1
        idx = tuple(sorted(rng.choice(K, size=n_legs, replace=False).tolist()))
        if idx in seen:
            continue
        seen.add(idx)
        out.append(list(idx))
    return out


def iter_weekly_combos(
    qual: pd.DataFrame,
    n_legs: int,
    *,
    max_combos_per_week: int = 500,
    enumerate_threshold: int = 5000,
    seed: int = 7,
) -> Iterator[tuple[int, pd.DataFrame, list[list[int]]]]:
    """Yield (week_key, deduped_picks_df, combos_idx_list) per week."""
    rng = np.random.default_rng(seed)
    for wk, sub in qual.groupby("week_key", sort=True):
        ded = _choose_one_per_match(sub, rng)
        if len(ded) < n_legs:
            continue
        combos = build_combos_for_week(
            ded, n_legs,
            max_combos_per_week=max_combos_per_week,
            enumerate_threshold=enumerate_threshold,
            rng=rng,
        )
        if not combos:
            continue
        yield int(wk), ded, combos


# ---------------------------------------------------------------------------
# Vectorized combo materialization

def materialize_combos(
    week_picks: pd.DataFrame, combos_idx: list[list[int]],
) -> pd.DataFrame:
    """Return per-combo summary: joint_p, joint_sp, all_hit, payout_per_yuan."""
    if not combos_idx:
        return pd.DataFrame(columns=["joint_p", "joint_sp", "all_hit",
                                     "payout_per_yuan"])
    sp = week_picks["sp"].to_numpy()
    p = week_picks["p_train"].to_numpy()
    won = week_picks["did_win"].to_numpy().astype(bool)
    arr = np.array(combos_idx, dtype=int)  # (n_combos, n_legs)
    joint_sp = np.prod(sp[arr], axis=1)
    joint_p = np.prod(p[arr], axis=1)
    all_hit = np.all(won[arr], axis=1)
    return pd.DataFrame(dict(
        joint_p=joint_p,
        joint_sp=joint_sp,
        all_hit=all_hit,
        payout_per_yuan=joint_sp * 0.65,
    ))
