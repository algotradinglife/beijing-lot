"""Tests for the weekly bankroll simulator."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.sweep.simulator import simulate, _floor_even


def test_floor_even_basic():
    assert _floor_even(5.7) == 4
    assert _floor_even(2.0) == 2
    assert _floor_even(1.9) == 0
    assert _floor_even(-3) == 0


def _synthetic_qual(n_matches=20, n_weeks=4, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for w in range(n_weeks):
        wk = 202300 + w
        for i in range(n_matches):
            sp = float(rng.uniform(2.0, 6.0))
            p = 1.10 / sp  # implied q=1.10 (slight +EV)
            rows.append(dict(
                match_id=f"w{w}_m{i}",
                expect=180000 + w,
                week_key=wk,
                sp=sp,
                p_train=p,
                did_win=int(rng.uniform() < p),
                q_train=1.10,
            ))
    return pd.DataFrame(rows)


def test_simulate_runs_and_keeps_bankroll_finite():
    qual = _synthetic_qual()
    sim = simulate(
        qual, n_legs=2, initial_bankroll=100_000.0,
        max_combos_per_week=20, enumerate_threshold=200,
        test_only=False,  # synthetic data has no train/test split
    )
    assert sim.final_bankroll >= 0
    if not sim.weekly.empty:
        assert (sim.weekly["week_stake"] >= 0).all()
        # weekly cap respected
        prev_b = 100_000.0
        for _, r in sim.weekly.iterrows():
            assert r["week_stake"] <= 0.25 * prev_b + 1.0  # +1 round-up margin
            prev_b = r["bankroll_end"]


def test_kelly_zero_when_no_edge():
    """If joint_p × payout ≤ 1, Kelly returns 0 → no stake placed."""
    rng = np.random.default_rng(1)
    rows = []
    for i in range(10):
        sp = 5.0
        # p_train such that p×SP×0.65 = 0.5 (way below break-even)
        p = 0.5 / (sp * 0.65)
        rows.append(dict(
            match_id=f"m{i}", expect=180000, week_key=202301,
            sp=sp, p_train=p, did_win=0, q_train=p * sp,
        ))
    qual = pd.DataFrame(rows)
    sim = simulate(qual, n_legs=2, test_only=False)
    assert sim.combos.empty or sim.combos["total_stake"].sum() == 0


def test_settlement_pays_out_correctly():
    """A guaranteed-winning combo with high SP should bump bankroll."""
    rows = [
        dict(match_id="m1", expect=180000, week_key=202301,
             sp=5.0, p_train=0.95, did_win=1, q_train=4.5),
        dict(match_id="m2", expect=180000, week_key=202301,
             sp=4.0, p_train=0.95, did_win=1, q_train=3.6),
    ]
    qual = pd.DataFrame(rows)
    sim = simulate(qual, n_legs=2, test_only=False, initial_bankroll=10_000.0)
    if not sim.weekly.empty:
        # Both legs hit, so payout=stake*SP*SP*0.65
        assert sim.weekly.iloc[0]["n_hits"] == 1
        assert sim.weekly.iloc[0]["week_pnl"] > 0


def test_weekly_cap_enforced():
    """Make many high-edge combos; total stake must be capped at 25% bankroll."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(30):
        sp = 4.0
        rows.append(dict(
            match_id=f"m{i}", expect=180000, week_key=202301,
            sp=sp, p_train=0.95, did_win=1, q_train=3.8,
        ))
    qual = pd.DataFrame(rows)
    sim = simulate(qual, n_legs=2, max_combos_per_week=200,
                   test_only=False, initial_bankroll=100_000.0)
    if not sim.weekly.empty:
        wk = sim.weekly.iloc[0]
        # Allow rounding margin
        assert wk["week_stake"] <= 25_000 + 100
