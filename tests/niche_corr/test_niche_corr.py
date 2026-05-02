"""Tests for the niche_corr package."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)

from src.niche_corr.niches import SURVIVED_16, filter_long_by_stratum
from src.niche_corr.returns import (add_devig_phat, assign_week,
                                    per_niche_weekly_return,
                                    build_return_matrix)
from src.niche_corr.corr import pairwise_corr, cluster_niches
from src.niche_corr.portfolio import (fill_zeros, stats, min_variance,
                                      efficient_frontier, bootstrap_min_var)
from src.niche_corr.backtest import (metrics, strategy_equal,
                                     strategy_dynamic_top3, run_all)


def _toy_long():
    """Hand-crafted 3 weeks × 4 matches × 3 options = 36 leg rows."""
    rows = []
    base = pd.Timestamp("2020-01-06")  # Monday
    for w in range(3):
        for m in range(4):
            mid = f"M{w}_{m}"
            ts = base + pd.Timedelta(days=7 * w + (m % 3))
            # contrived SPs and outcome
            sps = [3.0, 3.5, 6.0]  # home, draw, away
            # winner depends on (w,m)
            winner_idx = (w + m) % 3
            for i, opt in enumerate(("3", "1", "0")):
                rows.append(dict(
                    match_id=mid, expect=200001 + w, kickoff_ts=ts,
                    league="LX", league_tier="LowerEU",
                    handicap=-1.0, handicap_class="h1",
                    option=opt, sp=sps[i],
                    did_win=int(i == winner_idx),
                    sp_bucket="5-8" if sps[i] >= 5 else "3-5",
                    implied=1.0 / sps[i],
                    q_obs=int(i == winner_idx) * sps[i],
                    leg_ev=0.0,
                    option_label={"3": "home", "1": "draw", "0": "away"}[opt],
                ))
    return pd.DataFrame(rows)


def test_niche_definitions_count():
    assert len(SURVIVED_16) == 16
    ids = [n["id"] for n in SURVIVED_16]
    assert len(set(ids)) == 16, "ids must be unique"
    for n in SURVIVED_16:
        assert n["stratum"], "stratum must not be empty"


def test_filter_by_stratum():
    long = _toy_long()
    sub = filter_long_by_stratum(long, dict(option="0"))
    assert (sub["option"].astype(str) == "0").all()
    assert len(sub) == 12  # one per match × 12 matches


def test_devig_phat_sums_to_one_per_match():
    long = _toy_long()
    long2 = add_devig_phat(long)
    sums = long2.groupby("match_id")["p_hat"].sum()
    assert np.allclose(sums.values, 1.0, atol=1e-9)


def test_per_niche_weekly_return_shapes():
    long = add_devig_phat(_toy_long())
    long = assign_week(long)
    s = per_niche_weekly_return(long, dict(handicap_class="h1"), n_legs=3)
    # 4 matches/week, h1 yields one leg/match → 4 candidates → top 3 form combo
    assert len(s) == 3
    assert s.index.is_monotonic_increasing
    # finite returns
    assert np.isfinite(s.values).all()


def test_build_return_matrix_columns():
    long = add_devig_phat(_toy_long())
    R = build_return_matrix(_toy_long(), niches=SURVIVED_16[:3], n_legs=3)
    assert list(R.columns) == ["N01", "N02", "N03"]


def test_pairwise_corr_diagonal_one():
    R = pd.DataFrame(np.random.RandomState(0).randn(40, 4),
                     index=pd.date_range("2020-01-06", periods=40, freq="W"))
    R.columns = ["A", "B", "C", "D"]
    C = pairwise_corr(R, min_overlap=10)
    assert np.allclose(np.diag(C.values), 1.0)


def test_cluster_returns_groups():
    R = pd.DataFrame(np.random.RandomState(1).randn(60, 4),
                     columns=list("ABCD"))
    # make A & B highly correlated
    R["B"] = R["A"] + 0.05 * R["B"]
    C = pairwise_corr(R, min_overlap=10)
    info = cluster_niches(C, t=0.7)
    assert len(info["labels"]) == 4
    # A and B should share a cluster
    lab = dict(zip(info["ids"], info["labels"]))
    assert lab["A"] == lab["B"]


def test_min_variance_bounds_and_sum():
    rng = np.random.default_rng(0)
    X = rng.standard_normal((100, 5))
    cov = np.cov(X, rowvar=False)
    w = min_variance(cov)
    assert (w >= -1e-9).all()
    assert abs(w.sum() - 1.0) < 1e-6


def test_min_variance_with_target_return():
    rng = np.random.default_rng(1)
    X = rng.standard_normal((100, 4)) * 0.05
    mu = X.mean(axis=0)
    cov = np.cov(X, rowvar=False)
    target = float(mu.max() - 1e-4)
    w = min_variance(cov, mu=mu, target=target)
    assert abs(w.sum() - 1.0) < 1e-6
    assert w @ mu >= target - 1e-6


def test_efficient_frontier_monotone_volume():
    rng = np.random.default_rng(2)
    X = rng.standard_normal((150, 5)) * 0.04
    mu = X.mean(axis=0)
    cov = np.cov(X, rowvar=False)
    f = efficient_frontier(mu, cov, n_points=10)
    assert len(f) == 10
    # the highest-target portfolio should have at least the lowest-target's mu
    assert f["mu"].iloc[-1] >= f["mu"].iloc[0] - 1e-6


def test_bootstrap_min_var_columns():
    R = pd.DataFrame(np.random.RandomState(3).randn(80, 4) * 0.1,
                     columns=list("ABCD"))
    boot = bootstrap_min_var(R, n_boot=20, seed=0)
    assert set(boot.columns) >= {"niche", "mean_w", "std_w", "p05", "p95"}
    assert len(boot) == 4


def test_metrics_basic():
    eq = pd.Series([100, 110, 105, 120, 130],
                   index=pd.date_range("2020-01-06", periods=5, freq="W"))
    m = metrics(eq)
    assert m["final"] == 130
    assert m["MaxDD"] < 0  # had a drawdown 110→105
    assert m["CAGR"] > 0


def test_strategy_equal_runs():
    R = pd.DataFrame(np.random.RandomState(4).randn(30, 4) * 0.1,
                     index=pd.date_range("2020-01-06", periods=30, freq="W"),
                     columns=list("ABCD"))
    s = strategy_equal(R, bankroll=1000.0, f=0.02)
    assert s["equity"].iloc[0] != 0
    assert "CAGR" in s


def test_dynamic_top3_no_lookahead():
    R = pd.DataFrame(np.random.RandomState(5).randn(30, 5) * 0.1,
                     index=pd.date_range("2020-01-06", periods=30, freq="W"),
                     columns=list("ABCDE"))
    s = strategy_dynamic_top3(R, bankroll=1000.0, f=0.02, window=8, k=3)
    # First 8 weeks: equity flat at start (no weights assigned yet)
    eq = s["equity"]
    assert (eq.iloc[:8] == 1000.0).all()


def test_run_all_keys():
    R = pd.DataFrame(np.random.RandomState(6).randn(40, 5) * 0.1,
                     index=pd.date_range("2020-01-06", periods=40, freq="W"),
                     columns=list("ABCDE"))
    out = run_all(R)
    assert set(out.keys()) == {"single_best", "equal", "markowitz",
                               "dynamic_top3"}
    for s in out.values():
        assert "Sharpe" in s and "CAGR" in s and "MaxDD" in s
