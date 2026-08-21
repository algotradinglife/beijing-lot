from __future__ import annotations

import pandas as pd
import pytest

from issue296.evaluation import (
    apply_validation_fallback,
    capital_path,
    fixed_weights,
    summarize_path,
)


def test_whole_bundle_path_obeys_capital_and_compounds() -> None:
    table = pd.DataFrame(
        {
            "issue": [1, 2],
            "issue_year": [2023, 2023],
            "stake_A": [20.0, 20.0],
            "pnl_A": [10.0, -20.0],
            "gross_A": [30.0, 0.0],
            "hits_A": [1.0, 0.0],
            "available_A": [True, True],
        }
    )
    weights = pd.DataFrame(
        {
            "issue": [1, 2],
            "issue_year": [2023, 2023],
            "condition": ["TEST", "TEST"],
            "weight_A": [0.5, 0.5],
            "weight_CASH": [0.5, 0.5],
        }
    )
    path = capital_path(table, weights, ["A"], initial_capital_cny=100.0)
    assert path["closing_capital_cny"].tolist() == [120.0, 60.0]
    summary = summarize_path(path)
    assert summary["terminal_capital_cny"] == 60.0
    assert summary["max_drawdown_pct"] == 50.0


def test_capital_path_rejects_non_simplex_weights() -> None:
    table = pd.DataFrame(
        {
            "issue": [1],
            "issue_year": [2023],
            "stake_A": [20.0],
            "pnl_A": [10.0],
            "gross_A": [30.0],
            "hits_A": [1.0],
            "available_A": [True],
        }
    )
    weights = pd.DataFrame(
        {
            "issue": [1],
            "issue_year": [2023],
            "condition": ["INVALID"],
            "weight_A": [0.8],
            "weight_CASH": [0.8],
        }
    )
    with pytest.raises(ValueError, match="sum to one"):
        capital_path(table, weights, ["A"])


def test_validation_guard_falls_back_before_test() -> None:
    table = pd.DataFrame(
        {
            "issue": [1, 2],
            "issue_year": [2022, 2023],
            "stake_A": [20.0, 20.0],
            "pnl_A": [-20.0, 100.0],
            "gross_A": [0.0, 120.0],
            "hits_A": [0.0, 1.0],
            "available_A": [True, True],
        }
    )
    learned = fixed_weights(table, ["A"], {"A": 1.0}, condition="LEARNED")
    baseline = fixed_weights(table, ["A"], {}, condition="BASELINE")
    guarded, receipt = apply_validation_fallback(
        table, learned, baseline, ["A"], condition="GUARDED"
    )
    assert receipt["decision"] == "FROZEN_BASELINE_FALLBACK"
    assert guarded["weight_CASH"].eq(1.0).all()
