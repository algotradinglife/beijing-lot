from __future__ import annotations

import json

import numpy as np
import pandas as pd

from issue314.data import OUTCOMES, issue_features
from issue314.experiment import _integer_counts, _soft_weights, ticket_replay_receipt
from issue314.experts import EXPERTS, ExpertSpec, generate_tickets, settle_tickets


def _units(matches: int = 18) -> pd.DataFrame:
    rng = np.random.default_rng(314)
    market = rng.dirichlet([3, 2, 3], size=matches)
    line = rng.dirichlet([3, 2, 3], size=matches)
    frame = pd.DataFrame(
        {
            "issue": "24011",
            "match_idx": np.arange(1, matches + 1),
            "issue_year": 2024,
            "source_temporal_role": "sealed_feature_only",
            "experiment_role": "terminal",
            "n_available_books": 14,
            "native_handicap_line": 0.0,
            "mapping_accepted": True,
        }
    )
    for index, outcome in enumerate(OUTCOMES):
        frame[f"q_eu_bjline_{outcome}"] = market[:, index]
        frame[f"q_line_only_control_{outcome}"] = line[:, index]
        frame[f"eu_vs_line_divergence_{outcome}"] = market[:, index] - line[:, index]
    return frame


def test_issue_features_separate_source_and_experiment_roles() -> None:
    features = issue_features(_units())
    assert features.loc[0, "source_temporal_role"] == "sealed_feature_only"
    assert features.loc[0, "experiment_role"] == "terminal"
    assert not any(
        column in features.columns
        for column in ("result_code", "settlement_sp", "Y", "winning_sp")
    )


def test_explicit_support_never_reaches_depth_three() -> None:
    spec = next(
        value for value in EXPERTS if value.name == "TAIL_N7_DIVERGENCE_PROTECTED"
    )
    matches, outcomes, support, receipt = generate_tickets(
        _units(), spec, k=128, seed=11
    )
    assert matches.shape == outcomes.shape == (128, 7)
    assert support["coverage_depth"].max() == 2
    assert support["coverage_depth"].eq(2).sum() == 2
    assert receipt["maximum_coverage_depth"] == 2


def test_reset_contract_is_explicit_and_does_not_mutate_original() -> None:
    spec = EXPERTS[-1]
    reset = spec.reset("coverage_protection")
    assert reset.protected_leg_count == 0 and reset.protection == "NONE"
    assert spec.protected_leg_count == 2


def test_payout_factor_is_applied_once_to_complete_ticket() -> None:
    group = _units(matches=3)
    settlement = pd.DataFrame(
        {
            "match_idx": [1, 2, 3],
            "result_code": ["3", "3", "3"],
            "settlement_sp": [2.0, 2.0, 2.0],
            "settlement_available": [True, True, True],
        }
    )
    matches = np.array([[0, 1, 2]])
    outcomes = np.array([[0, 0, 0]])
    gross, correct, miss = settle_tickets(matches, outcomes, group, settlement)
    assert np.isclose(gross[0], 2.0 * 0.65 * 2.0**3)
    assert correct.tolist() == [3]
    assert miss.tolist() == [0]


def test_soft_gate_is_continuous_and_integer_funding_reconciles() -> None:
    local = pd.DataFrame(
        {
            "sleeve": ["CORE", "CORE", "TAIL", "TAIL"],
            "predicted_roi": [0.1, 0.0, 0.2, -0.1],
        }
    )
    weights = _soft_weights(local, 0.1)
    counts = _integer_counts(weights, 513)
    assert np.isclose(weights.sum(), 1.0)
    assert np.count_nonzero(weights) == 4
    assert counts.sum() == 513
    assert counts[2:].sum() in {51, 52}


def test_ticket_replay_receipt_reconciles_stake_and_accounting() -> None:
    paths = pd.DataFrame(
        {
            "total_k": [2, 3],
            "stake_cny": [4.0, 6.0],
            "gross_cny": [5.0, 0.0],
            "pnl_cny": [1.0, -6.0],
        }
    )
    receipt = ticket_replay_receipt(paths)
    assert receipt["pass"]
    assert json.loads(json.dumps(receipt))["payout_factor"] == 0.65


def test_random_protection_is_preoutcome_deterministic() -> None:
    spec = ExpertSpec("TEST", "CORE", 7, "GLOBAL", "MARKET", "WOR", 8, "RANDOM", 1)
    first = generate_tickets(_units(), spec, k=64, seed=7)
    second = generate_tickets(_units(), spec, k=64, seed=7)
    np.testing.assert_array_equal(first[0], second[0])
    np.testing.assert_array_equal(first[1], second[1])
