"""Tests for sweep metrics."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.sweep.metrics import (
    bootstrap_ci,
    bootstrap_cumulative_roi,
    max_drawdown,
    sharpe_weekly,
    summarize,
    time_to_first_hit,
)
from src.sweep.simulator import SimulationResult


def test_max_drawdown_simple():
    bb = np.array([100.0, 120.0, 80.0, 90.0, 110.0])
    # peak 120 -> trough 80 -> dd = -1/3
    dd = max_drawdown(bb)
    assert abs(dd - (-1 / 3)) < 1e-9


def test_max_drawdown_monotone_zero():
    bb = np.array([100.0, 110.0, 130.0])
    assert max_drawdown(bb) == 0.0


def test_sharpe_weekly_positive():
    rng = np.random.default_rng(0)
    rois = rng.normal(0.01, 0.02, size=200)
    s = sharpe_weekly(rois)
    # Mean ≈ 0.01, std ≈ 0.02, annualized factor √52 ≈ 7.2
    assert s > 0


def test_sharpe_zero_for_constant_or_short():
    assert sharpe_weekly(np.array([0.0])) == 0.0
    assert sharpe_weekly(np.array([0.01, 0.01, 0.01])) == 0.0  # std=0


def test_time_to_first_hit():
    df = pd.DataFrame(dict(n_hits=[0, 0, 0, 2, 0]))
    assert time_to_first_hit(df) == 4
    assert time_to_first_hit(pd.DataFrame(dict(n_hits=[0, 0, 0]))) is None
    assert time_to_first_hit(pd.DataFrame(dict(n_hits=[]))) is None


def test_bootstrap_ci_shape():
    vals = np.random.default_rng(0).normal(0, 1, 100)
    lo, hi = bootstrap_ci(vals, n_boot=200)
    assert lo < hi


def test_bootstrap_cumulative_roi_handles_empty():
    lo, hi = bootstrap_cumulative_roi(pd.DataFrame(), 100_000.0)
    assert np.isnan(lo) and np.isnan(hi)


def test_summarize_handles_empty_simulation():
    sim = SimulationResult(
        weekly=pd.DataFrame(), combos=pd.DataFrame(),
        final_bankroll=100_000.0, initial_bankroll=100_000.0,
    )
    s = summarize(sim, n_legs=3, qual_test=pd.DataFrame())
    assert s["n_combos_total"] == 0
    assert s["cumulative_ROI"] == 0.0
