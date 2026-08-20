import numpy as np

from issue282.tickets import build_distinct_ticket_stream


def _surface(matches: int = 10):
    probability = np.tile(np.array([0.5, 0.3, 0.2]), (matches, 1))
    value = probability * np.linspace(2.0, 4.0, matches)[:, None]
    return value, probability


def test_top_value_returns_distinct_ticket_identities() -> None:
    value, probability = _surface()
    stream = build_distinct_ticket_stream(
        value,
        probability,
        n=5,
        generator="TOP_VALUE",
        requested_unique=16,
        seed=1,
    )
    assert stream.unique_k == 16
    assert len(set(stream.identities)) == 16
    assert np.all(stream.proposal_counts == 1)


def test_common_stream_prefix_is_identical_for_every_k() -> None:
    value, probability = _surface(20)
    stream = build_distinct_ticket_stream(
        value,
        probability,
        n=7,
        generator="WEIGHTED_WOR",
        requested_unique=32,
        seed=282001,
    )
    assert stream.prefix(8).identities == stream.identities[:8]
    assert stream.prefix(16).identities[:8] == stream.prefix(8).identities


def test_wr_collapses_duplicate_proposals_without_creating_stake() -> None:
    # A three-identity, deliberately skewed space forces repeated proposals
    # before the third distinct identity appears.  K still counts identities.
    value = np.array([[10.0, 1.0, 0.1]])
    probability = np.array([[0.50, 0.30, 0.20]])
    stream = build_distinct_ticket_stream(
        value,
        probability,
        n=1,
        generator="WEIGHTED_WR",
        requested_unique=3,
        seed=0,
        max_proposals=1_000,
    )
    assert stream.unique_k == 3
    assert len(set(stream.identities)) == stream.unique_k
    assert stream.proposal_counts.sum() >= stream.unique_k
    assert (stream.proposal_counts > 1).any()
