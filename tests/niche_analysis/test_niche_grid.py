"""Tests for feature engineering and niche enumeration."""

import numpy as np
import pandas as pd
import pytest

from src.niche_analysis.data_loader import (
    classify_handicap, classify_league, devig_proportional, devig_power, to_long,
)
from src.niche_analysis.niche_grid import (
    empirical_sp_proxy, enumerate_niches, filter_long_by_stratum,
)


def test_classify_league_buckets():
    assert classify_league("英超") == "Top5EU"
    assert classify_league("西甲") == "Top5EU"
    assert classify_league("英冠") == "LowerEU"
    assert classify_league("巴甲") == "SouthAm"
    assert classify_league("日职") == "Asian"
    assert classify_league("foo") == "Other"
    assert classify_league(None) == "Other"


def test_classify_handicap():
    assert classify_handicap(0) == "h0"
    assert classify_handicap(0.0) == "h0"
    assert classify_handicap(1) == "h1"
    assert classify_handicap(-1) == "h1"
    assert classify_handicap(2) == "h2plus"
    assert classify_handicap(-3) == "h2plus"
    assert classify_handicap(None) == "h_unknown"
    assert classify_handicap(float("nan")) == "h_unknown"


def test_devig_proportional_sums_to_one():
    p = devig_proportional(2.0, 3.5, 4.0)
    assert abs(p.sum() - 1.0) < 1e-12
    # Inverted relative ordering: lowest odds → highest prob
    assert p[0] > p[1] > p[2] is False or p[0] >= p[1]


def test_devig_power_sums_to_one():
    p = devig_power(2.0, 3.5, 4.0)
    assert abs(p.sum() - 1.0) < 1e-3
    # Power method should give a different (slightly lower for fav) home prob
    p_prop = devig_proportional(2.0, 3.5, 4.0)
    # Both should have home as highest prob
    assert p.argmax() == p_prop.argmax()


def test_to_long_explodes_and_assigns_did_win():
    matches = pd.DataFrame([{
        "issue": "26001", "match_idx": 1, "league": "英超",
        "handicap": 0, "result_norm": "3", "winning_sp": 2.0,
        "avg_eu_home": 2.0, "avg_eu_draw": 3.4, "avg_eu_away": 4.0,
        "p_home": 0.55, "p_draw": 0.27, "p_away": 0.18,
        "league_tier": "Top5EU", "handicap_class": "h0",
    }])
    long = to_long(matches)
    assert len(long) == 3
    assert set(long["option_type"]) == {"3", "1", "0"}
    won = long[long["did_win"] == 1]
    assert len(won) == 1
    assert won.iloc[0]["option_type"] == "3"
    # Strength: home is favorite (highest p)
    assert long[long["option_type"] == "3"].iloc[0]["option_strength"] == "fav"
    assert long[long["option_type"] == "0"].iloc[0]["option_strength"] == "long"


def test_enumerate_niches_min_n_filter():
    # Build a synthetic long_df with one feature combo > min_n and one not
    rows = []
    for i in range(60):
        rows.append({
            "issue": str(i // 10), "match_idx": i,
            "option_type": "3", "handicap_class": "h0",
            "option_strength": "fav", "league_tier": "Top5EU",
            "prob_bucket": ".45-.55",
            "implied_prob": 0.5, "did_win": 1 if i % 2 == 0 else 0,
            "winning_sp": 2.0 if i % 2 == 0 else float("nan"),
            "eu_odds": 2.0,
        })
    for i in range(20):
        rows.append({
            "issue": str(i), "match_idx": i,
            "option_type": "1", "handicap_class": "h2plus",
            "option_strength": "mid", "league_tier": "Asian",
            "prob_bucket": ".25-.35",
            "implied_prob": 0.3, "did_win": 0,
            "winning_sp": float("nan"), "eu_odds": 3.5,
        })
    long = pd.DataFrame(rows)
    niches = enumerate_niches(long, min_n=50)
    # The Top5EU/h0/fav combo (n=60) must show up, the Asian/h2plus/mid (n=20) must not
    assert any(s.get("league_tier") == "Top5EU" and s.get("handicap_class") == "h0"
               for s in niches["stratum"])
    assert not any(s.get("league_tier") == "Asian" for s in niches["stratum"])


def test_filter_long_by_stratum():
    long = pd.DataFrame({
        "option_type": ["3", "1", "0", "3"],
        "league_tier": ["Top5EU", "Top5EU", "Asian", "Asian"],
        "did_win": [1, 0, 0, 1],
        "implied_prob": [0.5, 0.3, 0.2, 0.4],
        "winning_sp": [2.0, float("nan"), float("nan"), 2.5],
        "eu_odds": [2.0, 3.4, 4.0, 2.5],
    })
    sub = filter_long_by_stratum(long, {"league_tier": "Top5EU"})
    assert len(sub) == 2
    sub2 = filter_long_by_stratum(long, {"option_type": "3", "league_tier": "Asian"})
    assert len(sub2) == 1


def test_empirical_sp_proxy_uses_winning_sp_when_enough_wins():
    long = pd.DataFrame({
        "did_win": [1] * 12 + [0] * 8,
        "winning_sp": [2.0] * 12 + [float("nan")] * 8,
        "eu_odds": [2.5] * 20,
    })
    assert empirical_sp_proxy(long) == 2.0


def test_empirical_sp_proxy_falls_back_with_few_wins():
    long = pd.DataFrame({
        "did_win": [1] * 3 + [0] * 17,
        "winning_sp": [2.0] * 3 + [float("nan")] * 17,
        "eu_odds": [2.0] * 20,
    })
    # Falls back to mean(eu_odds) * 0.65 / 0.95
    expected = 2.0 * 0.65 / 0.95
    assert abs(empirical_sp_proxy(long) - expected) < 1e-9
