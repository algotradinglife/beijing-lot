from __future__ import annotations

import pandas as pd

from issue292.policy import (
    attach_action_economics,
    average_seed_predictions,
    combine_sleeves,
    select_capped_tail_sleeve,
    select_single_sleeve,
    summarize_policy,
)


def _predictions(value: float) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issue": ["23001", "23001"],
            "issue_year": [2023, 2023],
            "temporal_role": ["calibration", "calibration"],
            "action_key": ["N3_K8_WEIGHTED_WOR", "N8_K8_WEIGHTED_WR"],
            "n": [3, 8],
            "k": [8, 8],
            "generator": ["WEIGHTED_WOR", "WEIGHTED_WR"],
            "predicted_mean_utility_bps": [value, value],
            "predicted_positive_probability": [0.2, 0.1],
            "predicted_positive_pnl": [10.0, 100.0],
            "predicted_nonpositive_pnl": [-10.0, -16.0],
            "predicted_q10_utility_bps": [value, value],
            "predicted_risk_score": [value, value],
        }
    )


def test_seed_predictions_and_action_economics_align() -> None:
    averaged = average_seed_predictions([_predictions(1.0), _predictions(3.0)])
    actual = pd.DataFrame(
        {
            "issue": ["23001", "23001"],
            "action_key": averaged["action_key"],
            "stake_total": [16.0, 16.0],
            "mean_pnl": [2.0, -4.0],
            "pnl_seed_q10": [-2.0, -16.0],
            "mean_hit_rate": [0.1, 0.0],
        }
    )
    joined = attach_action_economics(averaged, actual)
    assert joined["predicted_mean_utility_bps"].tolist() == [2.0, 2.0]
    assert joined["stake_total"].tolist() == [16.0, 16.0]


def test_predicted_loss_cannot_exceed_physical_stake() -> None:
    predicted = _predictions(-10_000.0)
    actual = pd.DataFrame(
        {
            "issue": ["23001", "23001"],
            "action_key": predicted["action_key"],
            "stake_total": [16.0, 16.0],
            "mean_pnl": [-16.0, -16.0],
            "pnl_seed_q10": [-16.0, -16.0],
            "mean_hit_rate": [0.0, 0.0],
        }
    )
    joined = attach_action_economics(predicted, actual)
    assert joined["predicted_mean_roi"].tolist() == [-1.0, -1.0]
    assert joined["predicted_q10_roi"].tolist() == [-1.0, -1.0]


def test_barbell_can_fund_core_and_reject_tail() -> None:
    actual = pd.DataFrame(
        {
            "issue": ["23001", "23001"],
            "action_key": _predictions(2.0)["action_key"],
            "stake_total": [16.0, 16.0],
            "mean_pnl": [2.0, -4.0],
            "pnl_seed_q10": [-2.0, -16.0],
            "mean_hit_rate": [0.1, 0.0],
        }
    )
    joined = attach_action_economics(_predictions(2.0), actual)
    core = select_single_sleeve(
        joined,
        policy="CORE",
        n_min=3,
        n_max=6,
        score_column="predicted_q10_roi",
        threshold=-1.0,
        threshold_column="predicted_q10_roi",
    )
    tail = select_single_sleeve(
        joined,
        policy="TAIL",
        n_min=7,
        n_max=10,
        score_column="predicted_mean_roi",
        threshold=2.0,
        threshold_column="predicted_mean_roi",
    )
    combined = combine_sleeves(core, tail, policy="BARBELL")
    assert combined["funded_core"].all()
    assert not combined["funded_tail"].any()
    assert combined["pnl_cny"].iloc[0] == 2.0
    assert summarize_policy(combined)["pnl_cny"] == 2.0


def test_tail_sleeve_obeys_physical_capital_fraction() -> None:
    predictions = pd.DataFrame(
        {
            "issue": ["23001"] * 4,
            "issue_year": [2023] * 4,
            "n": [3, 8, 8, 8],
            "k": [128, 8, 32, 128],
            "action_key": ["CORE", "TAIL8", "TAIL32", "TAIL128"],
            "generator": ["WEIGHTED_WOR"] * 4,
            "predicted_mean_roi": [-0.01, 0.10, 0.30, 0.90],
            "stake_total": [256.0, 16.0, 64.0, 256.0],
            "mean_pnl": [0.0, 4.0, 12.0, 100.0],
            "pnl_seed_q10": [-10.0, -16.0, -64.0, -256.0],
            "mean_hit_rate": [0.1, 0.01, 0.01, 0.01],
        }
    )
    core = pd.DataFrame(
        {
            "issue": ["23001"],
            "issue_year": [2023],
            "stake_cny": [256.0],
            "funded": [True],
        }
    )
    tail = select_capped_tail_sleeve(
        predictions,
        core,
        policy="TAIL",
        threshold=0.0,
        maximum_fraction=0.20,
    )
    assert tail["selected_action_key"].iloc[0] == "TAIL32"
    fraction = tail["stake_cny"].iloc[0] / (256.0 + tail["stake_cny"].iloc[0])
    assert fraction <= 0.20
