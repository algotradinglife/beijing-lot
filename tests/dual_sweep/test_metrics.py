"""Tests for dual_sweep.metrics — Sharpe / Sortino / Calmar / MDD math."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.dual_sweep.metrics import (
    cagr,
    calmar,
    full_metrics,
    max_drawdown_curve,
    quality_metrics,
    sharpe,
    sortino,
    var_cvar,
)
from src.sweep.simulator import SimulationResult


def test_sharpe_known_series():
    # mean 1%, std 2% per week → Sharpe = 0.01/0.02 * sqrt(52) ≈ 3.6056
    rs = np.array([0.03, -0.01, 0.02, 0.0, 0.01] * 10)
    expected = rs.mean() / rs.std(ddof=1) * math.sqrt(52)
    assert sharpe(rs) == pytest.approx(expected, rel=1e-6)


def test_sortino_only_downside_in_denominator():
    rs = np.array([0.05, -0.02, 0.04, -0.03, 0.01])
    downside = rs[rs < 0]
    dstd = math.sqrt((downside ** 2).mean())
    expected = rs.mean() / dstd * math.sqrt(52)
    assert sortino(rs) == pytest.approx(expected, rel=1e-6)


def test_max_drawdown_simple():
    bb = np.array([100.0, 110.0, 105.0, 90.0, 95.0, 120.0])
    mdd_frac, mdd_abs, dur, time_uw = max_drawdown_curve(bb)
    # peak=110, trough=90 → DD = -20/110
    assert mdd_frac == pytest.approx(-20.0 / 110.0)
    assert mdd_abs == pytest.approx(-20.0)
    # underwater weeks: indices 2,3,4 (below 110); index 5 hits 120 = new peak
    assert time_uw == 3
    assert dur == 3


def test_calmar_and_cagr():
    # 100k → 200k over 104 weeks → 2 years → CAGR = sqrt(2) - 1
    cg = cagr(100_000, 200_000, 104)
    assert cg == pytest.approx(math.sqrt(2) - 1, rel=1e-6)
    # Calmar = cg / 0.2 if mdd = -20%
    assert calmar(cg, -0.20) == pytest.approx(cg / 0.20, rel=1e-6)


def test_var_cvar_quality():
    pnl = np.array([10.0, -5.0, -20.0, 3.0, -1.0, 15.0, -100.0])
    var, cv = var_cvar(pnl, 0.20)
    # 20th percentile of 7 values
    assert var <= 0  # should be a loss
    q = quality_metrics(pnl)
    assert q["profit_factor"] == pytest.approx(28.0 / 126.0, rel=1e-6)
    assert q["avg_win"] == pytest.approx((10 + 3 + 15) / 3.0, rel=1e-6)


def test_full_metrics_empty_simulation():
    sim = SimulationResult(
        weekly=pd.DataFrame(), combos=pd.DataFrame(),
        final_bankroll=100_000.0, initial_bankroll=100_000.0,
    )
    m = full_metrics(sim, "empty")
    assert m["n_weeks"] == 0
    assert m["total_profit"] == 0.0
