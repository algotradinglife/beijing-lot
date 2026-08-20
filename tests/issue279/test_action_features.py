from __future__ import annotations

import pandas as pd
import pytest

from issue279.features import build_action_features, feature_dictionary


def _states() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issue": ["23001"],
            "issue_year": [2023],
            "n_matches": [12],
            "accepted_fraction": [0.75],
            "prob_entropy_mean": [0.9],
            "prob_top_mean": [0.55],
            "value_best_mean": [1.1],
            "value_margin_mean": [0.1],
            "value_interval_mean": [0.2],
            "divergence_abs_mean": [0.04],
            "divergence_abs_q90": [0.08],
        }
    )


def _actions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "action_key": ["N7_K8_WR", "N5_K2048_WOR", "NO_BET"],
            "n": [7, 5, 0],
            "k": [8, 2048, 0],
            "generator": ["WEIGHTED_WR", "WEIGHTED_WOR", "NO_BET"],
        }
    )


def test_factory_accepts_external_k_without_operational_cap() -> None:
    frame = build_action_features(_states(), _actions())
    row = frame.loc[frame["action_key"].eq("N5_K2048_WOR")].iloc[0]
    assert row["stage3_requested_turnover"] == 4096.0
    assert row["stage4_requested_capital_fraction"] == pytest.approx(0.04096)


def test_outcome_fields_fail_closed() -> None:
    attacked = _states().assign(SP_SETTLE=99.0)
    with pytest.raises(ValueError, match="forbidden"):
        build_action_features(attacked, _actions())


def test_effective_coefficient_is_feature_only_and_dictionary_is_stage_addressable() -> None:
    frame = build_action_features(_states(), _actions())
    n7 = frame.loc[frame["action_key"].eq("N7_K8_WR")].iloc[0]
    assert n7["stage3_effective_coefficient_per_leg"] == pytest.approx(0.65 ** (1 / 7))
    dictionary = feature_dictionary()
    assert {"selection", "outcome", "ticket", "capital"}.issubset(set(dictionary["stage"]))


def test_infeasible_n_is_filtered_without_misaligned_action_arrays() -> None:
    states = _states().assign(n_matches=6)
    frame = build_action_features(states, _actions())
    assert "N7_K8_WR" not in set(frame["action_key"])
    assert {"N5_K2048_WOR", "NO_BET"} == set(frame["action_key"])
