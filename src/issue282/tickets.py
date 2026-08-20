"""Distinct-ticket streams with common-random-number K prefixes.

K is the number of unique complete ticket identities. Proposal duplicates are
recorded as frequency evidence and never silently become additional stake.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

GENERATORS = {"TOP_VALUE", "WEIGHTED_WR", "WEIGHTED_WOR"}


@dataclass(frozen=True)
class DistinctTicketStream:
    """One deterministic ordered stream of unique ticket identities."""

    match_positions: np.ndarray
    outcome_positions: np.ndarray
    proposal_counts: np.ndarray
    generator: str
    seed: int

    def __post_init__(self) -> None:
        if self.match_positions.ndim != 2 or self.outcome_positions.ndim != 2:
            raise ValueError("ticket arrays must be two-dimensional")
        if self.match_positions.shape != self.outcome_positions.shape:
            raise ValueError("match and outcome arrays must have identical shape")
        if len(self.proposal_counts) != len(self.match_positions):
            raise ValueError("proposal_counts must align with unique tickets")
        if np.any(self.proposal_counts < 1):
            raise ValueError("every unique ticket needs at least one proposal")
        if len(set(self.identities)) != len(self.identities):
            raise ValueError("stream contains duplicate ticket identities")

    @property
    def identities(self) -> tuple[tuple[tuple[int, int], ...], ...]:
        return tuple(
            tuple(zip(matches.tolist(), outcomes.tolist()))
            for matches, outcomes in zip(self.match_positions, self.outcome_positions)
        )

    @property
    def n(self) -> int:
        return int(self.match_positions.shape[1]) if len(self.match_positions) else 0

    @property
    def unique_k(self) -> int:
        return int(len(self.match_positions))

    def prefix(self, k: int) -> "DistinctTicketStream":
        """Return the first K unique tickets from the same frozen stream."""

        if k <= 0:
            raise ValueError("k must be positive")
        stop = min(k, self.unique_k)
        return DistinctTicketStream(
            match_positions=self.match_positions[:stop].copy(),
            outcome_positions=self.outcome_positions[:stop].copy(),
            proposal_counts=self.proposal_counts[:stop].copy(),
            generator=self.generator,
            seed=self.seed,
        )


def build_distinct_ticket_stream(
    cell_value: np.ndarray,
    probabilities: np.ndarray,
    *,
    n: int,
    generator: str,
    requested_unique: int,
    seed: int,
    max_proposals: int | None = None,
) -> DistinctTicketStream:
    """Build a unique ticket stream whose prefixes define every K action.

    ``TOP_VALUE`` uses deterministic dynamic programming to obtain distinct
    high-value tickets. Weighted generators use one seeded proposal stream.
    WR records duplicate frequency; WOR rejects duplicates. Neither converts a
    duplicate into automatic stake.
    """

    value, prob = _validated_inputs(cell_value, probabilities, n, requested_unique)
    if generator not in GENERATORS:
        raise ValueError(f"unsupported generator: {generator}")
    if generator == "TOP_VALUE":
        matches, outcomes = _top_value_unique(value, n=n, k=requested_unique)
        counts = np.ones(len(matches), dtype=int)
    else:
        matches, outcomes, counts = _weighted_unique(
            value,
            prob,
            n=n,
            k=requested_unique,
            seed=seed,
            generator=generator,
            max_proposals=max_proposals,
        )
    return DistinctTicketStream(matches, outcomes, counts, generator, int(seed))


def _validated_inputs(
    cell_value: np.ndarray,
    probabilities: np.ndarray,
    n: int,
    requested_unique: int,
) -> tuple[np.ndarray, np.ndarray]:
    value = np.asarray(cell_value, dtype=float)
    prob = np.asarray(probabilities, dtype=float)
    if value.ndim != 2 or value.shape[1] != 3 or prob.shape != value.shape:
        raise ValueError("cell_value and probabilities must both have shape (M, 3)")
    if n <= 0 or n > len(value):
        raise ValueError("n must be feasible for the issue match count")
    if requested_unique <= 0:
        raise ValueError("requested_unique must be positive")
    clean_value = np.nan_to_num(value, nan=0.0, posinf=0.0, neginf=0.0)
    clean_prob = np.nan_to_num(prob, nan=0.0, posinf=0.0, neginf=0.0)
    clean_prob = np.clip(clean_prob, 0.0, None)
    row_sum = clean_prob.sum(axis=1, keepdims=True)
    clean_prob = np.divide(
        clean_prob,
        row_sum,
        out=np.full_like(clean_prob, 1.0 / 3.0),
        where=row_sum > 0,
    )
    return clean_value, clean_prob


def _top_value_unique(
    value: np.ndarray, *, n: int, k: int
) -> tuple[np.ndarray, np.ndarray]:
    # A state is (log score, legs). Keeping k partial states per leg count is
    # sufficient for requested top-k terminals under additive log scores.
    log_value = np.log(np.clip(value, 1e-12, None))
    states: list[list[tuple[float, tuple[tuple[int, int], ...]]]] = [
        [] for _ in range(n + 1)
    ]
    states[0] = [(0.0, ())]
    for match_position in range(len(value)):
        previous = [bucket.copy() for bucket in states]
        for legs in range(1, min(n, match_position + 1) + 1):
            candidates = previous[legs].copy()
            for score, identity in previous[legs - 1]:
                for outcome_position in range(3):
                    candidates.append(
                        (
                            score + float(log_value[match_position, outcome_position]),
                            (*identity, (match_position, outcome_position)),
                        )
                    )
            candidates.sort(key=lambda item: (-item[0], item[1]))
            states[legs] = candidates[:k]
    terminal = states[n]
    matches = np.asarray([[m for m, _ in identity] for _, identity in terminal], dtype=int)
    outcomes = np.asarray([[o for _, o in identity] for _, identity in terminal], dtype=int)
    return matches, outcomes


def _weighted_unique(
    value: np.ndarray,
    probability: np.ndarray,
    *,
    n: int,
    k: int,
    seed: int,
    generator: str,
    max_proposals: int | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    branch_weight = np.clip(value, 1e-12, None)
    match_weight = np.clip(branch_weight.max(axis=1), 1e-12, None)
    proposal_limit = max_proposals or max(1_000, 50 * k)
    identities: list[tuple[tuple[int, int], ...]] = []
    index_by_identity: dict[tuple[tuple[int, int], ...], int] = {}
    counts: list[int] = []
    proposals = 0
    while len(identities) < k and proposals < proposal_limit:
        proposals += 1
        gumbel = rng.gumbel(size=len(match_weight))
        chosen = np.argpartition(np.log(match_weight) + gumbel, -n)[-n:]
        chosen = np.sort(chosen)
        outcomes: list[int] = []
        for match_position in chosen:
            weights = branch_weight[match_position]
            if weights.sum() <= 0 or not np.isfinite(weights).all():
                weights = probability[match_position]
            outcomes.append(int(rng.choice(3, p=weights / weights.sum())))
        identity = tuple(zip(chosen.tolist(), outcomes))
        existing = index_by_identity.get(identity)
        if existing is not None:
            if generator == "WEIGHTED_WR":
                counts[existing] += 1
            continue
        index_by_identity[identity] = len(identities)
        identities.append(identity)
        counts.append(1)
    matches = np.asarray([[m for m, _ in identity] for identity in identities], dtype=int)
    outcomes = np.asarray([[o for _, o in identity] for identity in identities], dtype=int)
    return matches, outcomes, np.asarray(counts, dtype=int)
