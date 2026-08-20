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
    proposal_identity_indices: np.ndarray
    generator: str
    seed: int

    def __post_init__(self) -> None:
        if self.match_positions.ndim != 2 or self.outcome_positions.ndim != 2:
            raise ValueError("ticket arrays must be two-dimensional")
        if self.match_positions.shape != self.outcome_positions.shape:
            raise ValueError("match and outcome arrays must have identical shape")
        if len(set(self.identities)) != len(self.identities):
            raise ValueError("stream contains duplicate ticket identities")
        if self.proposal_identity_indices.ndim != 1:
            raise ValueError("proposal identity log must be one-dimensional")
        if len(self.match_positions):
            if len(self.proposal_identity_indices) < len(self.match_positions):
                raise ValueError("proposal log cannot be shorter than unique support")
            if np.any(self.proposal_identity_indices < 0) or np.any(
                self.proposal_identity_indices >= len(self.match_positions)
            ):
                raise ValueError("proposal log contains an unknown ticket identity")
            discovered = np.unique(self.proposal_identity_indices)
            if not np.array_equal(discovered, np.arange(len(self.match_positions))):
                raise ValueError("every unique ticket needs a proposal observation")
        elif len(self.proposal_identity_indices):
            raise ValueError("empty ticket support cannot have proposals")

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

    @property
    def proposal_counts(self) -> np.ndarray:
        """Proposal frequencies observed before this stream prefix stopped."""

        return np.bincount(
            self.proposal_identity_indices, minlength=self.unique_k
        ).astype(int)

    def prefix(self, k: int) -> "DistinctTicketStream":
        """Return the first K unique tickets from the same frozen stream."""

        if k <= 0:
            raise ValueError("k must be positive")
        stop = min(k, self.unique_k)
        if stop == 0:
            proposal_stop = 0
        else:
            # Identity numbers are assigned at first discovery.  Truncating at
            # discovery of K-1 prevents a small-K action from seeing proposal
            # repeats that occurred only while searching for a larger K.
            proposal_stop = int(
                np.flatnonzero(self.proposal_identity_indices == stop - 1)[0]
            ) + 1
        return DistinctTicketStream(
            match_positions=self.match_positions[:stop].copy(),
            outcome_positions=self.outcome_positions[:stop].copy(),
            proposal_identity_indices=self.proposal_identity_indices[
                :proposal_stop
            ].copy(),
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
        proposal_log = np.arange(len(matches), dtype=int)
    else:
        matches, outcomes, proposal_log = _weighted_unique(
            value,
            prob,
            n=n,
            k=requested_unique,
            seed=seed,
            generator=generator,
            max_proposals=max_proposals,
        )
    return DistinctTicketStream(matches, outcomes, proposal_log, generator, int(seed))


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
    log_value = np.log(np.clip(value, 1e-12, None))
    match_best = log_value.max(axis=1)
    ranked_matches = np.argsort(-match_best, kind="stable")
    pool_size = min(len(value), max(n + 8, 32))
    while True:
        pool = np.sort(ranked_matches[:pool_size])
        terminal = _top_value_from_pool(log_value, pool=pool, n=n, k=k)
        if pool_size == len(value) or not terminal:
            break
        kth_score = terminal[min(k, len(terminal)) - 1][0]
        best_excluded = float(match_best[ranked_matches[pool_size]])
        other_best = np.sort(match_best[np.arange(len(value)) != ranked_matches[pool_size]])[
            ::-1
        ][: n - 1]
        excluded_upper_bound = best_excluded + float(other_best.sum())
        # Strict inequality avoids changing deterministic tie ordering.
        if kth_score > excluded_upper_bound and len(terminal) >= k:
            break
        pool_size = min(len(value), pool_size * 2)
    matches = np.asarray([[m for m, _ in identity] for _, identity in terminal], dtype=int)
    outcomes = np.asarray([[o for _, o in identity] for _, identity in terminal], dtype=int)
    return matches, outcomes


def _top_value_from_pool(
    log_value: np.ndarray, *, pool: np.ndarray, n: int, k: int
) -> list[tuple[float, tuple[tuple[int, int], ...]]]:
    """Exact top-K dynamic program on a candidate match pool.

    Scores and identities stay in NumPy arrays during pruning.  This is the
    same beam recurrence as the tuple implementation, without constructing and
    sorting millions of temporary Python objects for large Beijing issues.
    """

    scores: list[np.ndarray] = [np.empty(0, dtype=float) for _ in range(n + 1)]
    matches: list[np.ndarray] = [
        np.empty((0, legs), dtype=int) for legs in range(n + 1)
    ]
    outcomes: list[np.ndarray] = [
        np.empty((0, legs), dtype=int) for legs in range(n + 1)
    ]
    scores[0] = np.array([0.0])
    matches[0] = np.empty((1, 0), dtype=int)
    outcomes[0] = np.empty((1, 0), dtype=int)
    for pool_position, match_position in enumerate(pool):
        for legs in range(min(n, pool_position + 1), 0, -1):
            prior_count = len(scores[legs - 1])
            added_scores = (
                np.repeat(scores[legs - 1], 3)
                + np.tile(log_value[match_position], prior_count)
            )
            added_matches = np.column_stack(
                [
                    np.repeat(matches[legs - 1], 3, axis=0),
                    np.full(prior_count * 3, match_position, dtype=int),
                ]
            )
            added_outcomes = np.column_stack(
                [
                    np.repeat(outcomes[legs - 1], 3, axis=0),
                    np.tile(np.arange(3, dtype=int), prior_count),
                ]
            )
            candidate_scores = np.concatenate([scores[legs], added_scores])
            candidate_matches = np.concatenate([matches[legs], added_matches], axis=0)
            candidate_outcomes = np.concatenate(
                [outcomes[legs], added_outcomes], axis=0
            )
            if len(candidate_scores) > k:
                selected = np.argpartition(candidate_scores, -k)[-k:]
            else:
                selected = np.arange(len(candidate_scores))
            order = selected[
                np.argsort(-candidate_scores[selected], kind="stable")
            ]
            scores[legs] = candidate_scores[order]
            matches[legs] = candidate_matches[order]
            outcomes[legs] = candidate_outcomes[order]
    terminal = [
        (
            float(score),
            tuple(zip(match_row.tolist(), outcome_row.tolist())),
        )
        for score, match_row, outcome_row in zip(scores[n], matches[n], outcomes[n])
    ]
    terminal.sort(key=lambda item: (-item[0], item[1]))
    return terminal


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
    proposal_log: list[int] = []
    proposals = 0
    while len(identities) < k and proposals < proposal_limit:
        remaining_proposals = proposal_limit - proposals
        # Drawing proposals in bounded NumPy blocks removes the Python loop
        # over every match/outcome while retaining deterministic proposal order.
        block_size = min(max(64, 2 * (k - len(identities))), remaining_proposals)
        score = np.log(match_weight)[None, :] + rng.gumbel(
            size=(block_size, len(match_weight))
        )
        chosen_block = np.argpartition(score, -n, axis=1)[:, -n:]
        chosen_block.sort(axis=1)
        branch = branch_weight[chosen_block]
        branch_sum = branch.sum(axis=2, keepdims=True)
        normalized = np.divide(
            branch,
            branch_sum,
            out=probability[chosen_block].copy(),
            where=branch_sum > 0,
        )
        normalized /= normalized.sum(axis=2, keepdims=True)
        uniforms = rng.random(size=(block_size, n, 1))
        outcomes_block = (uniforms > np.cumsum(normalized, axis=2)).sum(axis=2)
        outcomes_block = np.minimum(outcomes_block, 2)
        for chosen, outcomes in zip(chosen_block, outcomes_block):
            proposals += 1
            identity = tuple(zip(chosen.tolist(), outcomes.tolist()))
            existing = index_by_identity.get(identity)
            if existing is not None:
                if generator == "WEIGHTED_WR":
                    proposal_log.append(existing)
            else:
                index_by_identity[identity] = len(identities)
                identities.append(identity)
                proposal_log.append(len(identities) - 1)
            if len(identities) >= k or proposals >= proposal_limit:
                break
    matches = np.asarray([[m for m, _ in identity] for identity in identities], dtype=int)
    outcomes = np.asarray([[o for _, o in identity] for identity in identities], dtype=int)
    return matches, outcomes, np.asarray(proposal_log, dtype=int)
