import numpy as np
import pytest

from issue284.labels import settle_sampled_action_grid, settle_sampled_subset


def test_subset_settlement_applies_coefficient_once() -> None:
    result = settle_sampled_subset(
        subset_id="toy",
        cell_value=np.full((3, 3), 1.0),
        probability=np.full((3, 3), 1 / 3),
        realized_outcomes=np.array([0, 0, 0]),
        winning_sp=np.array([2.0, 2.0, 2.0]),
        k=27,
        seed=1,
    )
    assert result["effective_k"] == 27
    assert result["stake_cny"] == 54.0
    assert result["pnl_cny"] == 2 * 0.65 * 2**3 - 54.0
    assert np.isclose(result["model_expected_pnl_cny100"], -35.0)


def test_subset_settlement_is_deterministic() -> None:
    kwargs = {
        "subset_id": "deterministic",
        "cell_value": np.arange(21, dtype=float).reshape(7, 3) + 1,
        "probability": np.full((7, 3), 1 / 3),
        "realized_outcomes": np.zeros(7, dtype=int),
        "winning_sp": np.full(7, 1.5),
        "k": 32,
        "seed": 7,
    }
    assert settle_sampled_subset(**kwargs) == settle_sampled_subset(**kwargs)


def test_action_grid_uses_nested_prefixes_and_explicit_marginals() -> None:
    result = settle_sampled_action_grid(
        subset_id="grid",
        cell_value=np.tile(np.array([3.0, 2.0, 1.0]), (4, 1)),
        probability=np.full((4, 3), 1 / 3),
        realized_outcomes=np.zeros(4, dtype=int),
        winning_sp=np.full(4, 2.0),
        generators=("TOP_VALUE",),
        k_values=(8, 16, 32),
        seed=1,
    )
    assert result["requested_k"].tolist() == [8, 16, 32]
    assert result["effective_k"].tolist() == [8, 16, 32]
    assert result["incremental_stake_cny"].tolist() == [16.0, 16.0, 32.0]
    assert np.allclose(
        result["incremental_pnl_cny"].cumsum(), result["pnl_cny"]
    )
    assert np.allclose(
        result["incremental_expected_pnl_cny"].cumsum(),
        result["expected_pnl_cny"],
    )
    assert not result["is_effective_k_alias"].any()
    # The only winning ticket pays CNY2 * 0.65 * 2^4 once.
    assert np.isclose(result.iloc[-1]["gross_return_cny"], 20.8)


def test_action_grid_rejects_wr_wor_alias_in_r1_stage() -> None:
    with pytest.raises(ValueError, match="WR/WOR aliases"):
        settle_sampled_action_grid(
            subset_id="alias",
            cell_value=np.ones((3, 3)),
            probability=np.full((3, 3), 1 / 3),
            realized_outcomes=np.zeros(3, dtype=int),
            winning_sp=np.ones(3),
            generators=("WEIGHTED_WOR",),
            k_values=(8,),
        )


def test_action_grid_separates_proposal_from_expected_value() -> None:
    value = np.array([[1.2, 0.8, 0.4], [1.1, 0.9, 0.5], [1.3, 0.7, 0.6]])
    probability = np.full((3, 3), 1.0 / 3.0)
    result = settle_sampled_action_grid(
        subset_id="proposal-mode",
        cell_value=value,
        probability=probability,
        proposal_surface=probability,
        outcome_weight_mode="MARKET_PROBABILITY",
        realized_outcomes=np.array([0, 1, 2]),
        winning_sp=np.array([2.0, 3.0, 4.0]),
        generators=("TOP_VALUE",),
        k_values=(8,),
    )
    assert result["outcome_weight_mode"].eq("MARKET_PROBABILITY").all()
    assert np.isfinite(result["expected_pnl_cny"]).all()
