from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from issue306.evaluation import evaluate_allocations, learned_allocations
from issue306.experiment import _development_selected_policy, _permutation_control
from issue306.surface import NUISANCE_SEEDS, action_space, aggregate_action_labels


def test_action_space_is_full_n3_n10_grid() -> None:
    actions = action_space()
    assert len(actions) == 8 * 4 * 3
    assert {action.n for action in actions} == set(range(3, 11))
    assert {action.k for action in actions} == {8, 32, 128, 512}
    assert len(NUISANCE_SEEDS) == 5


def test_aggregate_labels_preserves_seed_probabilities() -> None:
    frame = pd.DataFrame(
        {
            "issue": ["1"] * 5,
            "issue_year": [2023] * 5,
            "temporal_role": ["test"] * 5,
            "seed": list(NUISANCE_SEEDS),
            "action_key": ["N7_K8_WEIGHTED_WR"] * 5,
            "n": [7] * 5,
            "k": [8] * 5,
            "generator": ["WEIGHTED_WR"] * 5,
            "effective_k": [8] * 5,
            "stake_cny": [16.0] * 5,
            "pnl_cny": [-16.0, -16.0, 20.0, 40.0, -16.0],
            "gross_cny": [0.0, 0.0, 36.0, 56.0, 0.0],
            "hit_count": [0, 0, 1, 1, 0],
            "hit_rate": [0.0, 0.0, 0.125, 0.125, 0.0],
        }
    )
    result = aggregate_action_labels(frame).iloc[0]
    assert np.isclose(result.positive_probability, 0.4)
    assert np.isclose(result.mean_roi, 0.15)
    assert result.seed_pnl_std_cny > 0


def test_learned_allocation_never_skips_and_uses_512_tickets() -> None:
    scores = pd.DataFrame(
        {
            "issue": ["1", "1", "1"],
            "issue_year": [2023] * 3,
            "action_key": ["N7_K512_WEIGHTED_WR", "N5_K32_WEIGHTED_WOR", "N3_K8_TOP_VALUE"],
            "n": [7, 5, 3],
            "k": [512, 32, 8],
            "generator": ["WEIGHTED_WR", "WEIGHTED_WOR", "TOP_VALUE"],
            "effective_k": [512, 32, 8],
            "tail_score": [3.0, 2.0, 1.0],
        }
    )
    deterministic = learned_allocations(
        scores, condition="DET", score_column="tail_score", mixture=False
    )
    mixture = learned_allocations(
        scores, condition="MIX", score_column="tail_score", mixture=True
    )
    assert deterministic["allocated_tickets"].sum() == 512
    assert mixture["allocated_tickets"].sum() == 512
    assert deterministic["copies"].sum() >= 1
    assert mixture["copies"].sum() >= 1


def test_physical_replay_enforces_equal_stake() -> None:
    allocation = pd.DataFrame(
        {
            "issue": ["1"],
            "issue_year": [2023],
            "condition": ["TEST"],
            "action_key": ["N7_K512_TOP_VALUE"],
            "n": [7],
            "k": [512],
            "generator": ["TOP_VALUE"],
            "copies": [1],
            "allocated_tickets": [512],
        }
    )
    ledger = pd.DataFrame(
        {
            "issue": ["1"] * 5,
            "issue_year": [2023] * 5,
            "seed": list(NUISANCE_SEEDS),
            "action_key": ["N7_K512_TOP_VALUE"] * 5,
            "n": [7] * 5,
            "k": [512] * 5,
            "generator": ["TOP_VALUE"] * 5,
            "effective_k": [512] * 5,
            "stake_cny": [1_024.0] * 5,
            "pnl_cny": [-1_024.0] * 5,
            "gross_cny": [0.0] * 5,
            "hit_count": [0] * 5,
        }
    )
    path = evaluate_allocations(allocation, ledger)
    assert len(path) == 5
    assert path["stake_cny"].eq(1_024.0).all()
    assert path["executed_tickets"].eq(512).all()
    assert path["closing_capital_cny"].eq(98_976.0).all()


def test_primary_policy_is_selected_only_from_development_years() -> None:
    rows = []
    pnl = {
        "LEARNED_MEAN_DETERMINISTIC": 5.0,
        "LEARNED_TAIL_DETERMINISTIC": 3.0,
        "LEARNED_TAIL_MIXTURE": -2.0,
    }
    for condition, value in pnl.items():
        for year in (2021, 2022):
            for seed in NUISANCE_SEEDS:
                rows.append(
                    {
                        "condition": condition,
                        "evaluation_year": year,
                        "seed": seed,
                        "pnl_cny": value,
                    }
                )
        # An extreme 2023 reversal must not change the development choice.
        rows.append(
            {
                "condition": condition,
                "evaluation_year": 2023,
                "seed": NUISANCE_SEEDS[0],
                "pnl_cny": 1_000.0 if "TAIL" in condition else -1_000.0,
            }
        )
    selected, scores = _development_selected_policy(pd.DataFrame(rows))
    assert selected == "LEARNED_MEAN_DETERMINISTIC"
    assert scores[selected] == 10.0


def test_permutation_control_replays_every_physical_seed() -> None:
    allocations = pd.DataFrame(
        {
            "issue": ["1", "2"],
            "action_key": ["A", "B"],
            "copies": [1, 1],
        }
    )
    ledger_rows = []
    for issue in ("1", "2"):
        for action in ("A", "B"):
            for seed in NUISANCE_SEEDS:
                ledger_rows.append(
                    {
                        "issue": issue,
                        "action_key": action,
                        "seed": seed,
                        "pnl_cny": float(int(issue) * (1 if action == "A" else 2)),
                    }
                )
    result = _permutation_control(
        allocations, pd.DataFrame(ledger_rows), replicates=3
    )
    assert len(result) == 3
    assert {f"terminal_seed_{seed}_cny" for seed in NUISANCE_SEEDS}.issubset(
        result.columns
    )
    assert result["median_terminal_capital_cny"].notna().all()


def test_committed_decision_preserves_fixed_coverage_and_signal_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    decision = json.loads(
        (root / "results/issue-306/decision.json").read_text(encoding="utf-8")
    )["decision"]
    assert decision["eligible_issue_policy"] == "ALL_ISSUES_ACTIVE_NO_LEARNED_SKIP"
    assert decision["committed_tickets_per_issue"] == 512
    assert decision["committed_stake_per_issue_cny"] == 1_024.0
    assert decision["development_selected_primary"] == "LEARNED_MEAN_DETERMINISTIC"
    assert decision["verdict"] == "ACTION_VALUE_SIGNAL"
    assert decision["development_signal"] is True
    assert decision["dynamic_ticket_signal"] is False
    assert decision["promotable"] is False
    assert decision["same_exposure_permutation_percentile"] >= 0.95
    assert decision["positive_vs_strongest_control_nuisance_seeds"] == 2
    assert decision["sealed_years"] == "2024+ not read"
