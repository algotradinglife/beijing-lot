import numpy as np

from issue285.protection import (
    chosen_protected_legs,
    protect_ticket_portfolio,
    settle_unique_ticket_portfolio,
    ticket_miss_distance,
)


def test_ticket_miss_distance_keeps_near_miss_information() -> None:
    tickets = np.array([[0, 1, 2], [0, 1, 1], [2, 2, 2]])
    assert ticket_miss_distance(tickets, np.array([0, 1, 2])).tolist() == [0, 1, 2]


def test_single_flip_and_cartesian_have_expected_support() -> None:
    ticket = np.array([[0, 0, 0]])
    probability = np.array([[0.2, 0.5, 0.3]] * 3)
    divergence = np.zeros((3, 3))
    kwargs = {
        "probability": probability,
        "divergence": divergence,
        "proposal_surface": probability,
        "rule": "LOW_SELECTED_PROBABILITY",
        "protected_legs": 2,
        "alternative_depth": 1,
        "seed": 1,
    }
    single = protect_ticket_portfolio(ticket, structure="SINGLE_FLIP", **kwargs)
    cartesian = protect_ticket_portfolio(ticket, structure="FULL_CARTESIAN", **kwargs)
    assert len(single) == 3
    assert len(cartesian) == 4


def test_low_probability_rule_localizes_the_vulnerable_leg() -> None:
    probability = np.array(
        [[0.7, 0.2, 0.1], [0.4, 0.3, 0.3], [0.8, 0.1, 0.1]]
    )
    legs = chosen_protected_legs(
        np.array([0, 0, 0]),
        probability=probability,
        divergence=np.zeros((3, 3)),
        proposal_surface=probability,
        rule="LOW_SELECTED_PROBABILITY",
        protected_legs=1,
        seed=1,
    )
    assert legs.tolist() == [1]


def test_portfolio_deduplicates_and_applies_factor_once() -> None:
    result = settle_unique_ticket_portfolio(
        np.array([[0, 1], [0, 1], [1, 1]]),
        realized_outcomes=np.array([0, 1]),
        winning_sp=np.array([2.0, 3.0]),
    )
    assert result == {
        "unique_tickets": 2,
        "hit_count": 1,
        "stake_cny": 4.0,
        "gross_cny": 7.800000000000001,
        "pnl_cny": 3.8000000000000007,
    }
