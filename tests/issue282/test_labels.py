import numpy as np
import pandas as pd

from issue282.actions import PrototypeAction
from issue282.labels import divergence_value_surface, materialize_action_labels


def _inputs(matches: int = 5):
    units = pd.DataFrame(
        {
            "issue": ["23001"] * matches,
            "match_idx": np.arange(matches),
            "snapshot_kind": ["10h"] * matches,
            "issue_year": [2023] * matches,
            "temporal_role": ["calibration"] * matches,
            "eu_vs_line_divergence_3": [0.05] * matches,
            "eu_vs_line_divergence_1": [-0.02] * matches,
            "eu_vs_line_divergence_0": [-0.03] * matches,
        }
    )
    probabilities = pd.DataFrame(
        np.tile([0.55, 0.30, 0.15], (matches, 1)), columns=["3", "1", "0"]
    )
    values = pd.DataFrame(
        {
            "ev_raw_3": np.linspace(1.2, 1.6, matches),
            "ev_raw_1": np.linspace(0.9, 1.0, matches),
            "ev_raw_0": np.linspace(0.7, 0.8, matches),
        }
    )
    settlement = pd.DataFrame(
        {
            "issue": ["23001"] * matches,
            "match_idx": np.arange(matches),
            "realized_outcome": ["3"] * matches,
            "SP_SETTLE": [2.0] * matches,
            "Y": [1] * matches,
        }
    )
    return units, probabilities, values, settlement


def test_materialize_nested_action_labels() -> None:
    units, probabilities, values, settlement = _inputs()
    actions = tuple(
        PrototypeAction("ALL", "CELL_VALUE", 3, generator, k)
        for generator in ("TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR")
        for k in (2, 4)
    )
    result = materialize_action_labels(
        units,
        probabilities,
        values,
        settlement,
        actions=actions,
        stream_seeds=(1, 2),
    )
    assert len(result) == 6
    assert set(result["k"]) == {2, 4}
    assert result.loc[result.generator.eq("TOP_VALUE"), "stream_count"].eq(1).all()
    wr = result[result.generator.eq("WEIGHTED_WR")].set_index("k")
    wor = result[result.generator.eq("WEIGHTED_WOR")].set_index("k")
    assert np.allclose(wr["pnl_cny_mean"], wor["pnl_cny_mean"])
    assert (wr["proposal_count_mean"] >= wor["proposal_count_mean"]).all()


def test_selector_changes_available_match_pool() -> None:
    units, probabilities, values, settlement = _inputs(8)
    actions = (
        PrototypeAction("ALL", "MARKET_PROBABILITY", 3, "TOP_VALUE", 2),
        PrototypeAction("TOP_HALF_VALUE", "MARKET_PROBABILITY", 3, "TOP_VALUE", 2),
    )
    result = materialize_action_labels(
        units, probabilities, values, settlement, actions=actions, stream_seeds=(1,)
    )
    assert result.set_index("selector").loc["ALL", "selected_match_count"] == 8
    assert (
        result.set_index("selector").loc[
            "TOP_HALF_VALUE", "selected_match_count"
        ]
        == 4
    )


def test_divergence_value_tilts_toward_eu_probability_above_bj_line() -> None:
    value = np.ones((1, 3))
    eu = np.array([[0.50, 0.30, 0.20]])
    divergence = np.array([[0.10, -0.05, -0.05]])
    tilted = divergence_value_surface(value, eu, divergence)
    assert tilted[0, 0] > 1.0
    assert tilted[0, 1] < 1.0
    assert tilted[0, 2] < 1.0
