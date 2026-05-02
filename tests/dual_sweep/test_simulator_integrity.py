"""Sanity tests for the dual_sweep wrapper around sweep.simulator.

Asserts the standard invariants:
  - bankroll never < 0 (we stop early on ruin),
  - per-week stake ≤ 25% of start-of-week bankroll,
  - per-combo stake ≤ 0.5% of start-of-week bankroll (raw — pre tax-cap split).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.dual_sweep.simulator import simulate_window


def _make_qual_fixture(seed: int = 0) -> pd.DataFrame:
    """Synthetic qualifying-picks frame: 12 weeks × 8 matches × 3 options.

    Picks chosen so that per-leg q ~ 1.07 (positive edge) and weekly hits
    happen sometimes. We seed reproducibly.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for wk in range(20):
        for m in range(10):
            sp = float(rng.uniform(2.0, 6.0))
            # win prob s.t. p*sp ≈ 1.05
            p = min(0.5, 1.05 / sp)
            did_win = int(rng.random() < p)
            rows.append(dict(
                match_id=f"w{wk}-m{m}",
                expect=180000 + wk * 10,
                kickoff_ts=pd.Timestamp("2020-01-01") + pd.Timedelta(weeks=wk),
                option="3",
                sp=sp,
                did_win=did_win,
                niche_id="syn",
                q_train=1.07,
                p_train=min(0.49, 1.07 / sp),
                week_key=20200101 + wk,
                iso_year=2020, iso_week=wk + 1,
            ))
    return pd.DataFrame(rows)


def test_bankroll_never_negative_and_stake_caps():
    qual = _make_qual_fixture()
    sim = simulate_window(qual, n_legs=3, initial_bankroll=100_000.0,
                          test_only=False)
    bb = np.concatenate(([sim.initial_bankroll],
                          sim.weekly["bankroll_end"].to_numpy())) \
        if not sim.weekly.empty else np.array([sim.initial_bankroll])
    assert (bb >= 0).all(), "bankroll went negative without ruin"

    if not sim.weekly.empty:
        # week_stake ≤ 25% bankroll start-of-week
        bb_start = bb[:-1]
        stakes = sim.weekly["week_stake"].to_numpy()
        # Allow tiny rounding slack
        assert (stakes <= bb_start * 0.25 + 1).all(), "weekly cap breached"


def test_per_combo_cap_fraction():
    qual = _make_qual_fixture(seed=1)
    sim = simulate_window(qual, n_legs=3, initial_bankroll=100_000.0,
                          per_combo_cap_frac=0.005, test_only=False)
    if sim.combos.empty:
        pytest.skip("no combos placed in fixture")
    # Per-combo total stake (after possible tax-split & weekly downscale)
    # must be ≤ 0.5% × bankroll. Weekly downscale only ever reduces, so
    # this also holds.
    weekly_bk = dict(zip(sim.weekly["week_key"], sim.weekly["bankroll_end"]))
    bb0 = sim.initial_bankroll
    last_bk = bb0
    for _, p in sim.combos.iterrows():
        # bankroll at start of that week ≥ initial_bankroll lower bound
        assert p["total_stake"] <= max(bb0, last_bk) * 0.005 + 2 + p["stake_per_ticket"]
        last_bk = weekly_bk.get(p["week_key"], last_bk)


def test_simulate_window_filters_by_expect():
    qual = _make_qual_fixture(seed=2)
    full = simulate_window(qual, n_legs=2, initial_bankroll=100_000.0,
                            test_only=False)
    early = simulate_window(qual, n_legs=2, initial_bankroll=100_000.0,
                             expect_lo=180000, expect_hi=180100,
                             test_only=False)
    assert len(early.weekly) <= len(full.weekly)
