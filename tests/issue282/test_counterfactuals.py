import numpy as np
import pytest

from issue282.counterfactuals import settle_distinct_prefixes
from issue282.tickets import DistinctTicketStream


def _stream() -> DistinctTicketStream:
    return DistinctTicketStream(
        match_positions=np.array([[0, 1], [0, 1], [0, 1]]),
        outcome_positions=np.array([[0, 1], [0, 0], [2, 1]]),
        proposal_identity_indices=np.array([0, 0, 1, 0, 2]),
        generator="WEIGHTED_WR",
        seed=282,
    )


def test_coefficient_is_applied_once_to_winning_ticket() -> None:
    result = settle_distinct_prefixes(
        _stream(),
        realized_outcomes=np.array([0, 1]),
        winning_sp=np.array([2.0, 3.0]),
        k_values=(1, 2, 3),
    )
    # Ticket zero wins: CNY2 * 0.65 * (2 * 3) = CNY7.8.
    assert result["gross_return_cny"].tolist() == pytest.approx([7.8, 7.8, 7.8])
    assert result["stake_cny"].tolist() == [2.0, 4.0, 6.0]
    assert result["pnl_cny"].tolist() == pytest.approx([5.8, 3.8, 1.8])


def test_wr_proposal_frequency_does_not_create_stake() -> None:
    result = settle_distinct_prefixes(
        _stream(),
        realized_outcomes=np.array([0, 1]),
        winning_sp=np.array([2.0, 3.0]),
        k_values=(2,),
    ).iloc[0]
    assert result["proposal_count"] == 3
    assert result["effective_k"] == 2
    assert result["stake_cny"] == 4.0


def test_stage4_multipliers_are_the_only_repeat_stake_authority() -> None:
    result = settle_distinct_prefixes(
        _stream(),
        realized_outcomes=np.array([0, 1]),
        winning_sp=np.array([2.0, 3.0]),
        k_values=(2,),
        stake_multipliers=np.array([2.0, 0.5, 0.0]),
    ).iloc[0]
    assert result["stake_cny"] == 5.0
    assert result["gross_return_cny"] == pytest.approx(15.6)
    assert result["stake_ess"] == pytest.approx(1.4705882353)
