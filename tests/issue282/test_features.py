import pandas as pd

from issue282.features import ISSUE_STATE_FEATURES, build_action_feature_frame


def test_action_features_are_preevent_and_action_conditioned() -> None:
    labels = pd.DataFrame(
        {
            "issue": ["23001", "23001"],
            "selector": ["ALL", "TOP_HALF_VALUE"],
            "outcome_weight_mode": ["CELL_VALUE", "MARKET_PROBABILITY"],
            "n": [7, 5],
            "generator": ["TOP_VALUE", "WEIGHTED_WR"],
            "k": [8, 32],
            "selected_match_count": [20, 10],
            "stake_cny_mean": [16.0, 64.0],
            "proposal_count_mean": [8.0, 40.0],
            "effective_k_mean": [8.0, 32.0],
            "pnl_cny_mean": [999.0, -999.0],
        }
    )
    state = {feature: 1.0 for feature in ISSUE_STATE_FEATURES}
    state.update({"issue": "23001", "n_matches": 20.0})
    result = build_action_feature_frame(labels, pd.DataFrame([state]))
    assert len(result) == 2
    assert "pnl_cny_mean" not in result
    assert result["action_n"].tolist() == [7.0, 5.0]
    assert result["action_selected_fraction"].tolist() == [1.0, 0.5]
