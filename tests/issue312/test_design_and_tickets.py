from __future__ import annotations

import numpy as np
import pandas as pd

from issue209.dynamic_policy import ActionSpec, generate_tickets
from issue209.dynamic_policy import settle_ticket_arrays
from issue312.design import CubeAction, build_action_registry, registry_diagnostics
from issue312.experiment import paired_control_diagnostics
from issue312.policy import select_policy_allocations
from issue312.tickets import generate_cube_tickets


def _inputs(matches: int = 12) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(312)
    probability = rng.dirichlet([3.0, 2.0, 3.0], size=matches)
    ev = probability * rng.uniform(2.0, 5.0, size=(matches, 3))
    divergence = probability - np.full((matches, 3), 1 / 3)
    return ev, probability, divergence


def test_registry_keeps_all_anchors_and_has_pairwise_diagnostics() -> None:
    registry = build_action_registry()
    assert len(registry) == 192
    assert registry["action_key"].nunique() == 192
    assert registry["is_anchor"].sum() == 96
    assert set(registry["n"]) == set(range(3, 11))
    marginal, pairwise = registry_diagnostics(registry)
    assert set(marginal["factor"]) == {
        "n",
        "k",
        "match_selector",
        "pool_excess",
        "outcome_direction",
        "generator",
        "protection",
    }
    assert len(pairwise) == 21
    assert pairwise["coverage_fraction"].between(0, 1).all()


def test_anchor_is_byte_identical_to_issue306_generator() -> None:
    ev, probability, divergence = _inputs()
    action = CubeAction(
        7, 32, "GLOBAL_VALUE", -1, "RAW_VALUE", "WEIGHTED_WOR", "NONE"
    )
    actual_matches, actual_outcomes, protected = generate_cube_tickets(
        ev, probability, divergence, action, seed=44
    )
    expected_matches, expected_outcomes = generate_tickets(
        ev, probability, ActionSpec(7, 32, "WEIGHTED_WOR"), seed=44
    )
    np.testing.assert_array_equal(actual_matches, expected_matches)
    np.testing.assert_array_equal(actual_outcomes, expected_outcomes)
    assert protected == 0


def test_candidate_pool_changes_match_support_without_replacement_inside_ticket() -> None:
    ev, probability, divergence = _inputs()
    action = CubeAction(
        5, 128, "DIVERGENCE", 2, "DIVERGENCE", "WEIGHTED_WR", "NONE"
    )
    matches, outcomes, protected = generate_cube_tickets(
        ev, probability, divergence, action, seed=99
    )
    assert matches.shape == outcomes.shape == (128, 5)
    assert all(len(set(row)) == 5 for row in matches.tolist())
    assert len(np.unique(matches)) <= 7
    assert protected == 0


def test_soft_reentry_and_alt_protection_do_not_add_tickets() -> None:
    ev, probability, divergence = _inputs()
    base = CubeAction(6, 128, "HYBRID", 4, "RAW_VALUE", "WEIGHTED_WOR", "NONE")
    protected_action = CubeAction(
        6, 128, "HYBRID", 4, "RAW_VALUE", "WEIGHTED_WOR", "SOFT_REENTRY_15"
    )
    base_matches, base_outcomes, _ = generate_cube_tickets(
        ev, probability, divergence, base, seed=77
    )
    matches, outcomes, protected = generate_cube_tickets(
        ev, probability, divergence, protected_action, seed=77
    )
    assert len(matches) == len(base_matches) == 128
    assert protected > 0
    assert np.any(outcomes != base_outcomes)
    identities = {
        tuple(sorted(zip(match.tolist(), outcome.tolist(), strict=True)))
        for match, outcome in zip(matches, outcomes, strict=True)
    }
    assert len(identities) == 128


def test_beijing_factor_is_applied_once_per_winning_nfold_ticket() -> None:
    ticket_matches = np.repeat(np.array([[0, 1, 2]]), 8, axis=0)
    ticket_outcomes = np.zeros((8, 3), dtype=int)
    realized = np.zeros(3, dtype=int)
    winning_sp = np.full(3, 2.0)
    pnl, hit_rate = settle_ticket_arrays(
        ticket_matches, ticket_outcomes, realized, winning_sp
    )
    expected_gross = 8 * 2.0 * 0.65 * (2.0**3)
    assert np.isclose(pnl, expected_gross - 16.0)
    assert hit_rate == 1.0


def test_policy_allocations_reject_mismatched_issue_support() -> None:
    predictions = pd.DataFrame(
        {
            "issue": ["A"],
            "issue_year": [2023],
            "action_key": ["N7_K512_SGLOBAL_VALUE_ALL_ORAW_VALUE_GWEIGHTED_WOR_RNONE"],
            "n": [7],
            "k": [512],
            "match_selector": ["GLOBAL_VALUE"],
            "pool_excess": [-1],
            "outcome_direction": ["RAW_VALUE"],
            "generator": ["WEIGHTED_WOR"],
            "protection": ["NONE"],
            "effective_k": [512],
            "predicted_mean_roi": [0.0],
            "predicted_positive_probability": [0.0],
            "predicted_tail_5x_probability": [0.0],
            "predicted_mean_downside_roi": [0.0],
            "predicted_conditional_log_gross": [0.0],
            "predicted_mean_roi_std": [0.0],
        }
    )
    issue306 = pd.DataFrame(
        {
            "issue": ["B"],
            "issue_year": [2023],
            "condition": ["LEARNED_MEAN_DETERMINISTIC"],
            "n": [7],
            "k": [512],
            "generator": ["WEIGHTED_WOR"],
            "copies": [1],
            "allocated_tickets": [512],
        }
    )
    labels = pd.DataFrame(
        {
            "issue": ["D"],
            "issue_year": [2021],
            "action_key": [predictions.iloc[0]["action_key"]],
            "k": [512],
            "mean_pnl_cny": [0.0],
        }
    )
    with np.testing.assert_raises(AssertionError):
        select_policy_allocations(
            {name: predictions for name in ("LEARNED", "ISSUE_BLOCK_SHUFFLED", "IDENTITY_SHUFFLED")},
            primary_family="MEAN",
            issue306_allocations=issue306,
            development_labels=labels,
        )


def test_paired_diagnostics_use_named_control_and_pair_before_median() -> None:
    rows = []
    values = {
        "PRIMARY": [0.0, 100.0, 101.0],
        "NAMED_CONTROL": [50.0, 51.0, 200.0],
        "OTHER_CONTROL": [500.0, 0.0, 0.0],
    }
    for condition, terminals in values.items():
        for seed, terminal in enumerate(terminals):
            rows.append(
                {
                    "condition": condition,
                    "seed": seed,
                    "terminal_capital_cny": terminal,
                }
            )
    diagnostics = paired_control_diagnostics(
        pd.DataFrame(rows),
        primary_condition="PRIMARY",
        control_condition="NAMED_CONTROL",
    )
    assert diagnostics == {
        "paired_seed_count": 3,
        "difference_of_seed_medians_cny": 49.0,
        "paired_seed_median_lift_cny": -50.0,
        "paired_seed_wins": 1,
    }
