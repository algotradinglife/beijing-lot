"""TDD for src/sp_drift/walkforward.py — uncertainty quantification for the
N walk-forward (block bootstrap CI + leave-one-week-out fragility).

weeks are (issue, stake, pnl) triples, the same shape replay_policy rolls.
"""
from src.sp_drift.walkforward import (
    total_roi, weekly_roi, bootstrap_roi_ci, leave_one_week_out,
)

WEEKS = [("w1", 100.0, 10.0), ("w2", 100.0, -5.0), ("w3", 200.0, 60.0)]


def test_total_roi():
    # (10 - 5 + 60) / (100 + 100 + 200) = 65 / 400
    assert abs(total_roi(WEEKS) - 65.0 / 400.0) < 1e-12


def test_total_roi_empty_or_zero_stake_is_nan():
    import math
    assert math.isnan(total_roi([]))
    assert math.isnan(total_roi([("w", 0.0, 0.0)]))


def test_weekly_roi():
    wr = dict(weekly_roi(WEEKS))
    assert abs(wr["w1"] - 0.10) < 1e-12
    assert abs(wr["w2"] - (-0.05)) < 1e-12
    assert abs(wr["w3"] - 0.30) < 1e-12


def test_bootstrap_deterministic_same_seed():
    a = bootstrap_roi_ci(WEEKS, n_boot=2000, seed=7)
    b = bootstrap_roi_ci(WEEKS, n_boot=2000, seed=7)
    assert a == b


def test_bootstrap_ci_brackets_and_orders():
    r = bootstrap_roi_ci(WEEKS, n_boot=5000, seed=1)
    assert r["lo"] <= r["median"] <= r["hi"]
    assert r["lo"] <= r["mean"] <= r["hi"]
    assert abs(r["point"] - total_roi(WEEKS)) < 1e-12
    assert 0.0 <= r["p_positive"] <= 1.0


def test_bootstrap_p_positive_all_winning():
    # every week is a net winner -> every resample positive -> p_positive==1
    win = [("a", 100.0, 10.0), ("b", 100.0, 20.0), ("c", 100.0, 30.0)]
    r = bootstrap_roi_ci(win, n_boot=1000, seed=2)
    assert r["p_positive"] == 1.0


def test_bootstrap_degenerate_identical_weeks_zero_width():
    # every week has identical ROI -> every resample has the same ROI
    same = [("a", 100.0, 20.0), ("b", 100.0, 20.0), ("c", 100.0, 20.0)]
    r = bootstrap_roi_ci(same, n_boot=1000, seed=3)
    assert abs(r["lo"] - 0.20) < 1e-9 and abs(r["hi"] - 0.20) < 1e-9


def test_leave_one_week_out_identifies_dominant_week():
    r = leave_one_week_out(WEEKS)
    assert abs(r["base"] - total_roi(WEEKS)) < 1e-12
    # removing the big winner w3 should drop ROI the most
    assert r["max_drop"][0] == "w3"
    # removing the loser w2 should raise ROI
    assert r["max_rise"][0] == "w2"
    # per_week covers every issue exactly once
    assert sorted(i for i, _ in r["per_week"]) == ["w1", "w2", "w3"]
