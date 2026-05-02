import numpy as np
import pandas as pd

from src.drawdown.anatomy import worst_drawdown, compute_drawdown_series


def test_drawdown_series_basic():
    bk = np.array([100.0, 110.0, 105.0, 120.0, 90.0, 130.0])
    peaks, dd = compute_drawdown_series(bk)
    assert peaks[1] == 110.0
    assert peaks[3] == 120.0
    assert peaks[4] == 120.0  # peak holds while underwater
    assert dd[4] == (90.0 - 120.0) / 120.0
    assert dd[5] == 0.0  # new peak


def test_worst_drawdown_single_bad_week():
    # +10, +10, -50, +5, +5
    weekly = pd.DataFrame({
        "week_key": ["w1", "w2", "w3", "w4", "w5"],
        "week_pnl": [10.0, 10.0, -50.0, 5.0, 5.0],
    })
    a = worst_drawdown(weekly, initial=100.0)
    # bankroll: 100,110,120,70,75,80; peak=120 at idx 2 (after w2 = seq idx 2)
    assert a.peak_value == 120.0
    assert a.trough_value == 70.0
    assert a.n_losing_weeks == 1
    assert "single" in a.verdict


def test_worst_drawdown_streak():
    # losing streak
    weekly = pd.DataFrame({
        "week_key": [f"w{i}" for i in range(6)],
        "week_pnl": [20.0, -5.0, -5.0, -5.0, -5.0, -5.0],
    })
    a = worst_drawdown(weekly, initial=100.0)
    # peak after w0 = 120; trough at w5 = 95
    assert a.peak_value == 120.0
    assert a.n_losing_weeks == 5
    assert a.streak_share > 0.6  # no single week dominates
    assert "streak" in a.verdict
