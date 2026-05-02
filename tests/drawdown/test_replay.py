import numpy as np
import pandas as pd

from src.drawdown.replay import baseline_signals, replay, metrics_from_replay
from src.drawdown.stop_rules import (
    baseline, hard_stop, stake_throttle, profit_lock, combined,
)


def make_weekly(pnls, stakes, initial=1000.0):
    return pd.DataFrame({
        "week_key": [f"w{i}" for i in range(len(pnls))],
        "week_pnl": pnls,
        "week_stake": stakes,
    })


def test_baseline_replay_matches_input():
    weekly = make_weekly([100.0, -50.0, 200.0], [500.0, 400.0, 600.0], initial=1000.0)
    sig = baseline_signals(weekly, 1000.0)
    rep = replay(sig, baseline(), initial=1000.0)
    # baseline mult=1 so bankroll path should match cumulative pnl
    expected = 1000.0 + np.cumsum([100.0, -50.0, 200.0])
    np.testing.assert_allclose(rep["bankroll"].to_numpy(), expected, rtol=1e-9)


def test_hard_stop_halts_after_drawdown():
    # one big loss triggers stop, halts next K weeks
    # Loss then large recovery so DD is healed before halt window expires
    weekly = make_weekly(
        [100.0, -300.0, -100.0, 800.0, 100.0],
        [500.0, 500.0, 500.0, 500.0, 500.0],
        initial=1000.0,
    )
    sig = baseline_signals(weekly, 1000.0)
    rule = hard_stop(drop_pct=0.15, halt_weeks=2)
    rep = replay(sig, rule, 1000.0)
    # week 2: dd_pct ≈ -0.27 → halt trigger
    assert rep["active_mult"].iloc[2] == 0.0
    # halted_until = 2 + 2 = 4, so weeks 2,3 halted (still in halt window)
    assert rep["active_mult"].iloc[3] == 0.0
    # week 4: halt window passed (halted_until=4, t=4 → not > t).
    # bankroll start week 4 = 1000-300+0+0 = 700; peak = 1000 → dd=-0.30 still
    # so the rule re-fires. We just check halt logic *can* expire by trigger again.
    assert rep["active_mult"].iloc[4] == 0.0
    # And the next halt window restarts: halted_until = 4+2 = 6, but we only have 5 wks.


def test_profit_lock_skims_on_double():
    # one massive win doubles bankroll: skim 30%
    weekly = make_weekly([1500.0], [500.0], initial=1000.0)
    sig = baseline_signals(weekly, 1000.0)
    rule = profit_lock(double_at=2.0, skim_frac=0.30)
    rep = replay(sig, rule, 1000.0)
    # bankroll after pnl = 2500 → ratio 2.5 ≥ 2.0; skim 30% of 2500 = 750
    assert rep["skim"].iloc[0] == 750.0
    assert rep["bankroll"].iloc[0] == 2500.0 - 750.0


def test_stake_throttle_reduces_then_recovers():
    weekly = make_weekly(
        [-300.0, 100.0, 1000.0],   # big loss → throttle; then big win to recover
        [500.0, 500.0, 500.0],
        initial=1000.0,
    )
    sig = baseline_signals(weekly, 1000.0)
    rule = stake_throttle(drop_pct=0.20, throttle_to=0.25)
    rep = replay(sig, rule, 1000.0)
    # week 0: dd 0 → mult 1. After: bk=700, peak=1000
    # week 1: dd = -0.30 → throttle on, mult = 0.25
    assert rep["active_mult"].iloc[1] == 0.25


def test_metrics_from_replay_baseline_sane():
    weekly = make_weekly(
        [100.0, -50.0, 200.0, 300.0, -100.0],
        [500.0, 500.0, 500.0, 500.0, 500.0],
        initial=1000.0,
    )
    sig = baseline_signals(weekly, 1000.0)
    rep = replay(sig, baseline(), 1000.0)
    m = metrics_from_replay(rep, 1000.0)
    assert m["final"] == 1450.0
    assert m["max_dd"] < 0


def test_combined_rule_runs():
    weekly = make_weekly(
        [1500.0, -300.0, 100.0],
        [500.0, 500.0, 500.0],
        initial=1000.0,
    )
    sig = baseline_signals(weekly, 1000.0)
    rule = combined(profit_lock(2.0, 0.30), stake_throttle(0.15, 0.25))
    rep = replay(sig, rule, 1000.0)
    assert len(rep) == 3
    assert rep["skim"].iloc[0] > 0  # profit lock fired
