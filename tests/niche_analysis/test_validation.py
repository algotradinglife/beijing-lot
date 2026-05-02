"""Tests for train/test split + bootstrap niche evaluation."""

import numpy as np
import pandas as pd
import pytest

from src.niche_analysis.data_loader import train_test_split_by_issue
from src.niche_analysis.validation import bootstrap_niche, evaluate_stratum


def _toy_long(seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(150):  # 150 issues
        for j in range(50):  # 50 matches per issue
            for opt in ("3", "1", "0"):
                rows.append({
                    "issue": str(24000 + i),
                    "match_idx": j,
                    "option_type": opt,
                    "handicap_class": "h0",
                    "option_strength": "fav" if opt == "3" else "mid",
                    "league_tier": "Top5EU",
                    "prob_bucket": ".45-.55",
                    "implied_prob": 0.5,
                    "did_win": int(rng.random() < 0.5),
                    "winning_sp": 2.5 if rng.random() < 0.5 else float("nan"),
                    "eu_odds": 2.0,
                })
    return pd.DataFrame(rows)


def test_train_test_split_by_issue_no_overlap():
    long = _toy_long()
    train, test = train_test_split_by_issue(long, train_frac=100/150)
    train_issues = set(train["issue"])
    test_issues = set(test["issue"])
    assert train_issues.isdisjoint(test_issues)
    assert len(train_issues) == 100
    assert len(test_issues) == 50


def test_train_test_split_preserves_total_rows():
    long = _toy_long()
    train, test = train_test_split_by_issue(long, train_frac=100/150)
    assert len(train) + len(test) == len(long)


def test_evaluate_stratum_sane_outputs():
    long = _toy_long()
    res = evaluate_stratum(long, {"option_type": "3", "league_tier": "Top5EU"})
    assert res["n"] > 0
    assert 0 <= res["post_mean"] <= 1
    assert res["post_p05"] <= res["post_p50"] <= res["post_p95"]
    assert 0 <= res["P_EV_gt_1_05"] <= 1


def test_evaluate_stratum_empty_returns_zero():
    long = _toy_long()
    res = evaluate_stratum(long, {"option_type": "DOES_NOT_EXIST"})
    assert res["n"] == 0


def test_bootstrap_niche_ci_bracketed():
    long = _toy_long()
    out = bootstrap_niche(long, {"option_type": "3"}, n_boot=300)
    assert out["ci_low"] <= out["boot_mean"] <= out["ci_high"]
    assert 0 <= out["ci_low"] <= 1
    assert 0 <= out["ci_high"] <= 1
