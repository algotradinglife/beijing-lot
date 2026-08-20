from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from issue209.dynamic_policy import (
    ActionSpec,
    STATE_FEATURES,
    action_features,
    build_issue_states,
    generate_tickets,
    select_policy_actions,
    settle_ticket_arrays,
)


def _units() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    units = pd.DataFrame(
        {
            "issue": ["a", "a", "b", "b"],
            "match_idx": [1, 2, 1, 2],
            "snapshot_kind": ["10h"] * 4,
            "issue_year": [2021, 2021, 2022, 2022],
            "temporal_role": ["fit", "fit", "tune", "tune"],
            "mapping_accepted": [True] * 4,
            "n_available_books": [8, 7, 9, 9],
            "native_handicap_line": [0, 1, -1, 0],
            "realized_outcome": ["3", "1", "0", "3"],
            "SP_SETTLE": [2.0, 3.0, 4.0, 2.5],
            "Y": [1, 1, 1, 1],
            "eu_vs_line_divergence_3": [0.1, 0.0, -0.1, 0.2],
            "eu_vs_line_divergence_1": [-0.1, 0.1, 0.0, -0.1],
            "eu_vs_line_divergence_0": [0.0, -0.1, 0.1, -0.1],
        }
    )
    probabilities = pd.DataFrame(
        {"3": [0.6, 0.4, 0.2, 0.7], "1": [0.2, 0.4, 0.3, 0.2], "0": [0.2, 0.2, 0.5, 0.1]}
    )
    value = pd.DataFrame(index=units.index)
    for outcome in ("3", "1", "0"):
        value[f"ev_raw_{outcome}"] = probabilities[outcome] * 2.5
        value[f"value_q10_{outcome}"] = probabilities[outcome] * 2.0
        value[f"value_q90_{outcome}"] = probabilities[outcome] * 3.0
    return units, probabilities, value


def test_issue_state_is_outcome_unexposed() -> None:
    units, probabilities, value = _units()
    before = build_issue_states(units, value, probabilities)
    attacked = units.copy()
    attacked["realized_outcome"] = attacked["realized_outcome"].iloc[::-1].to_numpy()
    attacked["SP_SETTLE"] = 9999.0
    attacked["Y"] = 1 - attacked["Y"]
    after = build_issue_states(attacked, value, probabilities)
    pd.testing.assert_frame_equal(before, after)


def test_seed_and_outcomes_are_not_action_features() -> None:
    frame = pd.DataFrame([{feature: 1.0 for feature in STATE_FEATURES}])
    frame["n"] = 5
    frame["k"] = 32
    frame["stake_total"] = 64.0
    frame["generator"] = "WEIGHTED_WOR"
    frame["seed"] = 123
    frame["Y"] = 1
    frame["SP_SETTLE"] = 9.0
    frame["realized_outcome"] = "3"
    features = action_features(frame)
    assert not {"seed", "Y", "SP_SETTLE", "realized_outcome"} & set(features.columns)


def test_selection_cannot_use_hindsight_utility() -> None:
    predictions = pd.DataFrame(
        {
            "issue": ["a", "a", "b", "b"],
            "issue_year": [2023] * 4,
            "temporal_role": ["calibration"] * 4,
            "action_key": ["A", "B", "A", "B"],
            "n": [3, 7, 3, 7],
            "k": [8, 8, 8, 8],
            "generator": ["TOP_VALUE"] * 4,
            "predicted_mean_utility_bps": [2.0, 1.0, 1.0, 2.0],
            "predicted_q10_utility_bps": [0.0] * 4,
            "predicted_risk_score": [2.0, 1.0, 1.0, 2.0],
        }
    )
    actual = pd.DataFrame(
        {
            "issue": ["a", "a", "b", "b"],
            "action_key": ["A", "B", "A", "B"],
            "utility_bps": [-100.0, 1000.0, 1000.0, -100.0],
            "mean_pnl": [-10.0, 100.0, 100.0, -10.0],
            "stake_total": [16.0] * 4,
            "mean_hit_rate": [0.0] * 4,
        }
    )
    first = select_policy_actions(predictions, actual)
    attacked = actual.copy()
    attacked[["utility_bps", "mean_pnl"]] *= -999.0
    second = select_policy_actions(predictions, attacked)
    assert first.set_index("issue")["action_key"].to_dict() == {"a": "A", "b": "B"}
    assert first.set_index("issue")["action_key"].to_dict() == second.set_index("issue")["action_key"].to_dict()


def test_wr_and_wor_have_explicit_ticket_identity_semantics() -> None:
    ev = np.array([[0.9, 0.1, 0.1], [0.8, 0.2, 0.1], [0.7, 0.2, 0.1], [0.6, 0.2, 0.1]])
    probabilities = ev / ev.sum(axis=1, keepdims=True)
    wr_matches, wr_outcomes = generate_tickets(
        ev, probabilities, ActionSpec(3, 64, "WEIGHTED_WR"), seed=7
    )
    wor_matches, wor_outcomes = generate_tickets(
        ev, probabilities, ActionSpec(3, 64, "WEIGHTED_WOR"), seed=7
    )
    wr_ids = [tuple(sorted(zip(m.tolist(), o.tolist()))) for m, o in zip(wr_matches, wr_outcomes)]
    wor_ids = [tuple(sorted(zip(m.tolist(), o.tolist()))) for m, o in zip(wor_matches, wor_outcomes)]
    assert len(set(wor_ids)) == len(wor_ids)
    assert len(set(wr_ids)) <= len(wr_ids)


def test_shared_settlement_and_ticket_level_payout() -> None:
    matches = np.array([[0, 1], [0, 1]])
    outcomes = np.array([[0, 1], [0, 2]])
    realized = np.array([0, 1])
    sp = np.array([2.0, 3.0])
    pnl, hit_rate = settle_ticket_arrays(matches, outcomes, realized, sp)
    assert hit_rate == 0.5
    # Two CNY2 tickets cost 4; one winner returns 2 * 0.65 * (2*3) = 7.8.
    assert pnl == pytest.approx(3.8)
