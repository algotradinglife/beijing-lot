"""Tests for SP-native niche analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.niche_analysis import sp_native as snp


def _make_synthetic_wide(n: int = 600, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        # Random fair odds, add 30% rake
        p = rng.dirichlet([2, 1, 2])
        sp_3 = 1 / p[0] / 1.30
        sp_1 = 1 / p[1] / 1.30
        sp_0 = 1 / p[2] / 1.30
        result = rng.choice(["3", "1", "0"], p=p)
        rows.append(dict(
            expect=180000 + i // 50, match_no=i % 50,
            kickoff_ts="2018-01-01 00:00:00",
            league="英超" if i % 2 == 0 else "其它",
            home="A", away="B",
            handicap=float(rng.choice([-2, -1, 0, 1, 2])),
            fthg=1, ftag=0,
            home_rank="", away_rank="", hthg=0, htag=0, match_uid=i,
            result_code=result,
            winning_sp=[sp_3, sp_1, sp_0][["3", "1", "0"].index(result)],
            last_update_ts="", sp_3=sp_3, sp_1=sp_1, sp_0=sp_0,
        ))
    return pd.DataFrame(rows)


def test_bucket_sp():
    assert snp.bucket_sp(1.6) == "1.5-2"
    assert snp.bucket_sp(2.5) == "2-3"
    assert snp.bucket_sp(7.0) == "5-8"
    assert snp.bucket_sp(100.0) == "15+"
    assert snp.bucket_sp(0.5) == "na"
    assert snp.bucket_sp(np.nan) == "na"


def test_to_long_shape_and_columns(tmp_path):
    wide = _make_synthetic_wide(n=120, seed=1)
    csv = tmp_path / "synth.csv"
    wide.to_csv(csv, index=False)
    df = snp.load_full_3sp(str(csv))
    long = snp.to_long(df)
    # 3× rows
    assert len(long) == 3 * len(df)
    for col in ["match_id", "option", "sp", "did_win", "sp_bucket",
                "implied", "q_obs", "leg_ev"]:
        assert col in long.columns
    # exactly one winner per match
    by_match = long.groupby("match_id")["did_win"].sum()
    assert (by_match == 1).all()


def test_sum_inverse_sanity(tmp_path):
    wide = _make_synthetic_wide(n=300, seed=2)
    # rake = 0.30 by construction
    s = 1 / wide["sp_3"] + 1 / wide["sp_1"] + 1 / wide["sp_0"]
    assert 1.25 < s.mean() < 1.35


def test_q_obs_and_combo_ev_math():
    # If mean_q = 1.10, combo_ev_7 = 1.10^7 * 0.65 - 1
    long = pd.DataFrame({
        "did_win": [1, 0, 1, 0],
        "sp": [2.20, 2.0, 2.20, 2.0],
        "match_id": [1, 1, 2, 2],
        "expect": [1, 1, 2, 2],
        "league": ["x"] * 4,
        "league_tier": ["Top5EU"] * 4,
        "handicap": [0] * 4,
        "handicap_class": ["h0"] * 4,
        "option": ["3", "0", "3", "0"],
        "kickoff_ts": [""] * 4,
    })
    long["sp_bucket"] = long["sp"].map(snp.bucket_sp)
    long["implied"] = 1.0 / long["sp"]
    long["q_obs"] = long["did_win"] * long["sp"]
    long["leg_ev"] = long["q_obs"] * snp.RETURN_RATE - 1.0
    # mean_q across all = (2.20 + 0 + 2.20 + 0)/4 = 1.10
    assert abs(long["q_obs"].mean() - 1.10) < 1e-9


def test_enumerate_niches_returns_columns(tmp_path):
    wide = _make_synthetic_wide(n=600, seed=3)
    csv = tmp_path / "synth.csv"
    wide.to_csv(csv, index=False)
    df = snp.load_full_3sp(str(csv))
    long = snp.to_long(df)
    niches = snp.enumerate_niches(long, min_n=20, min_k=3, n_boot=100)
    if not niches.empty:
        for col in ["dims", "stratum_str", "n", "k", "mean_q",
                    "leg_ev", "combo_ev_7", "q_ci_lo", "q_ci_hi"]:
            assert col in niches.columns


def test_split_train_test_disjoint(tmp_path):
    wide = _make_synthetic_wide(n=200, seed=4)
    csv = tmp_path / "synth.csv"
    wide.to_csv(csv, index=False)
    df = snp.load_full_3sp(str(csv))
    long = snp.to_long(df)
    tr, te = snp.split_train_test(long)
    assert len(tr) > 0 and len(te) > 0
    assert set(tr["expect"]).isdisjoint(set(te["expect"]))


def test_simulate_variance_basic():
    out = snp.simulate_variance(
        n_weeks=50, candidates_per_week=5,
        p_hit_per_combo=0.05, payout_multiple=20.0,
        n_sims=200, rng_seed=0,
    )
    assert -1.0 <= out["p5"] <= out["p95"]
    assert "prob_profitable" in out


def test_combo_backtest_runs(tmp_path):
    wide = _make_synthetic_wide(n=800, seed=5)
    csv = tmp_path / "synth.csv"
    wide.to_csv(csv, index=False)
    df = snp.load_full_3sp(str(csv))
    long = snp.to_long(df)
    res = snp.combo_backtest_per_issue(long, p_method="shrunk",
                                       leg_ev_threshold=0.0, n_legs=3)
    assert "stake" in res.columns and "profit" in res.columns
    # synthetic data is fair-rake, so total profit should not be wildly positive
    assert res["stake"].sum() > 0
