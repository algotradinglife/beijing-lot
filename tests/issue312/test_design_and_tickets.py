from __future__ import annotations

import numpy as np

from issue209.dynamic_policy import ActionSpec, generate_tickets
from issue312.design import CubeAction, build_action_registry, registry_diagnostics
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
