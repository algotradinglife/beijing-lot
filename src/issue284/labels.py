"""Pilot settlement labels for sampled N×3 subsets."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

import numpy as np
import pandas as pd

from issue282.counterfactuals import settle_distinct_prefixes
from issue282.tickets import DistinctTicketStream, build_distinct_ticket_stream

PILOT_GENERATORS = ("TOP_VALUE", "WEIGHTED_WR")
PILOT_K_VALUES = (8, 16, 32, 64, 128, 256, 512)


def settle_sampled_subset(
    *,
    subset_id: str,
    cell_value: np.ndarray,
    probability: np.ndarray,
    realized_outcomes: np.ndarray,
    winning_sp: np.ndarray,
    k: int = 128,
    seed: int = 284_101,
) -> dict[str, float | int | str]:
    """Settle one fixed-stake CELL_VALUE/WR pilot action on an N×3 subset."""

    value = np.asarray(cell_value, dtype=float)
    probabilities = np.asarray(probability, dtype=float)
    realized = np.asarray(realized_outcomes, dtype=int)
    sp = np.asarray(winning_sp, dtype=float)
    if value.ndim != 2 or value.shape[1] != 3 or probabilities.shape != value.shape:
        raise ValueError("cell value and probability must have shape (N, 3)")
    if realized.shape != (len(value),) or sp.shape != realized.shape:
        raise ValueError("settlement vectors must align with subset matches")
    if k <= 0:
        raise ValueError("k must be positive")
    maximum_support = 3 ** len(value)
    stream = build_subset_ticket_stream(
        value,
        probabilities,
        generator="WEIGHTED_WR",
        requested_unique=min(k, maximum_support),
        seed=derived_subset_seed(seed, subset_id),
    )
    settled = settle_distinct_prefixes(stream, realized, sp, [k]).iloc[0]
    expected = expected_stream_prefixes(stream, value, [k]).iloc[0]
    stake = float(settled["stake_cny"])
    pnl = float(settled["pnl_cny"])
    return {
        "subset_id": subset_id,
        "outcome_weight_mode": "CELL_VALUE",
        "generator": "WEIGHTED_WR",
        "k": int(k),
        "effective_k": int(settled["effective_k"]),
        "proposal_count": int(settled["proposal_count"]),
        "stake_cny": stake,
        "pnl_cny": pnl,
        "normalized_pnl_cny100": pnl / stake * 100.0 if stake > 0 else 0.0,
        "model_expected_pnl_cny": float(expected["expected_pnl_cny"]),
        "model_expected_return_per_cny": float(expected["expected_return_per_cny"]),
        "model_expected_pnl_cny100": float(expected["expected_return_per_cny"])
        * 100.0,
        "hit_count": int(settled["hit_count"]),
        "stake_hhi": float(settled["stake_hhi"]),
        "stake_ess": float(settled["stake_ess"]),
    }


def settle_sampled_action_grid(
    *,
    subset_id: str,
    cell_value: np.ndarray,
    probability: np.ndarray,
    proposal_surface: np.ndarray | None = None,
    outcome_weight_mode: str = "CELL_VALUE",
    realized_outcomes: np.ndarray,
    winning_sp: np.ndarray,
    generators: Iterable[str] = PILOT_GENERATORS,
    k_values: Iterable[int] = PILOT_K_VALUES,
    seed: int = 284_101,
) -> pd.DataFrame:
    """Settle nested K prefixes for the non-aliased Stage 1–3 generators."""

    value = np.asarray(cell_value, dtype=float)
    proposal = np.asarray(
        value if proposal_surface is None else proposal_surface, dtype=float
    )
    probabilities = np.asarray(probability, dtype=float)
    realized = np.asarray(realized_outcomes, dtype=int)
    sp = np.asarray(winning_sp, dtype=float)
    if (
        value.ndim != 2
        or value.shape[1] != 3
        or probabilities.shape != value.shape
        or proposal.shape != value.shape
    ):
        raise ValueError(
            "cell value, proposal surface and probability must have shape (N, 3)"
        )
    if realized.shape != (len(value),) or sp.shape != realized.shape:
        raise ValueError("settlement vectors must align with subset matches")
    requested = tuple(sorted(set(int(k) for k in k_values)))
    if not requested or requested[0] <= 0:
        raise ValueError("K anchors must be positive")
    generator_names = tuple(dict.fromkeys(str(name) for name in generators))
    if not generator_names:
        raise ValueError("at least one generator is required")
    unsupported = set(generator_names) - set(PILOT_GENERATORS)
    if unsupported:
        raise ValueError(
            "R=1 pilot excludes WR/WOR aliases and unsupported generators: "
            f"{sorted(unsupported)}"
        )

    frames: list[pd.DataFrame] = []
    for generator in generator_names:
        maximum_support = 3 ** len(value)
        stream = build_subset_ticket_stream(
            proposal,
            probabilities,
            generator=generator,
            requested_unique=min(max(requested), maximum_support),
            seed=0 if generator == "TOP_VALUE" else derived_subset_seed(seed, subset_id),
        )
        settled = settle_distinct_prefixes(stream, realized, sp, requested).copy()
        expected = expected_stream_prefixes(stream, value, requested).rename(
            columns={"effective_k": "expected_effective_k"}
        )
        settled = settled.merge(
            expected, on="requested_k", how="left", validate="one_to_one"
        )
        if not settled["effective_k"].eq(settled["expected_effective_k"]).all():
            raise AssertionError("realized and expected K prefixes are misaligned")
        settled = settled.drop(columns="expected_effective_k")
        settled["subset_id"] = subset_id
        settled["outcome_weight_mode"] = outcome_weight_mode
        settled["generator"] = generator
        settled["stream_seed"] = stream.seed
        settled["normalized_pnl_cny100"] = np.divide(
            settled["pnl_cny"],
            settled["stake_cny"],
            out=np.zeros(len(settled), dtype=float),
            where=settled["stake_cny"].to_numpy(float) > 0,
        ) * 100.0
        settled["model_expected_pnl_cny100"] = (
            settled["expected_return_per_cny"] * 100.0
        )
        settled["incremental_stake_cny"] = settled["stake_cny"].diff().fillna(
            settled["stake_cny"]
        )
        settled["incremental_pnl_cny"] = settled["pnl_cny"].diff().fillna(
            settled["pnl_cny"]
        )
        settled["marginal_pnl_per_cny"] = np.divide(
            settled["incremental_pnl_cny"],
            settled["incremental_stake_cny"],
            out=np.zeros(len(settled), dtype=float),
            where=settled["incremental_stake_cny"].to_numpy(float) > 0,
        )
        settled["incremental_expected_pnl_cny"] = (
            settled["expected_pnl_cny"].diff().fillna(settled["expected_pnl_cny"])
        )
        settled["marginal_expected_pnl_per_cny"] = np.divide(
            settled["incremental_expected_pnl_cny"],
            settled["incremental_stake_cny"],
            out=np.zeros(len(settled), dtype=float),
            where=settled["incremental_stake_cny"].to_numpy(float) > 0,
        )
        settled["is_effective_k_alias"] = settled["effective_k"].duplicated()
        frames.append(settled)
    return pd.concat(frames, ignore_index=True)


def expected_stream_prefixes(
    stream: DistinctTicketStream,
    cell_value: np.ndarray,
    k_values: Iterable[int],
    *,
    ticket_stake_cny: float = 2.0,
    payout_coefficient: float = 0.65,
) -> pd.DataFrame:
    """Compute pre-event expected P&L for common distinct-ticket prefixes."""

    value = np.asarray(cell_value, dtype=float)
    requested = tuple(sorted(set(int(k) for k in k_values)))
    if value.ndim != 2 or value.shape[1] != 3 or len(value) != stream.n:
        raise ValueError("cell value must align with the fixed-N ticket stream")
    if not requested or requested[0] <= 0:
        raise ValueError("K anchors must be positive")
    ticket_value = value[stream.match_positions, stream.outcome_positions]
    expected_gross = (
        ticket_stake_cny
        * payout_coefficient
        * np.prod(np.clip(ticket_value, 0.0, None), axis=1)
    )
    cumulative_gross = np.cumsum(expected_gross)
    rows: list[dict[str, float | int]] = []
    for k in requested:
        effective_k = min(k, stream.unique_k)
        stake = ticket_stake_cny * effective_k
        gross = float(cumulative_gross[effective_k - 1]) if effective_k else 0.0
        rows.append(
            {
                "requested_k": k,
                "effective_k": effective_k,
                "expected_stake_cny": stake,
                "expected_gross_cny": gross,
                "expected_pnl_cny": gross - stake,
                "expected_return_per_cny": gross / stake - 1.0 if stake else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_subset_ticket_stream(
    cell_value: np.ndarray,
    probability: np.ndarray,
    *,
    generator: str,
    requested_unique: int,
    seed: int,
) -> DistinctTicketStream:
    """Vectorized fixed-match outcome stream for one already sampled subset.

    With all N matches fixed, the only support is the `3**N` outcome-code
    matrix. The Gumbel ranking is the size-biased order of first discovery from
    weighted with-replacement draws; proposal repeats are irrelevant while
    every distinct ticket has the same R=1 stake.
    """

    value = np.nan_to_num(np.asarray(cell_value, dtype=float), nan=0.0)
    probabilities = np.nan_to_num(np.asarray(probability, dtype=float), nan=0.0)
    if value.ndim != 2 or value.shape[1] != 3 or probabilities.shape != value.shape:
        raise ValueError("cell value and probability must have shape (N, 3)")
    if generator not in PILOT_GENERATORS:
        raise ValueError(f"unsupported fixed-subset generator: {generator}")
    maximum_support = 3 ** len(value)
    stop = min(int(requested_unique), maximum_support)
    if stop <= 0:
        raise ValueError("requested unique ticket count must be positive")
    if generator == "TOP_VALUE":
        return build_distinct_ticket_stream(
            value,
            probabilities,
            n=len(value),
            generator="TOP_VALUE",
            requested_unique=stop,
            seed=0,
        )
    if stop == maximum_support:
        selected_outcomes = (
            np.indices((3,) * len(value), dtype=np.int8)
            .reshape(len(value), -1)
            .T.astype(int)
        )
        matches = np.tile(np.arange(len(value), dtype=int), (stop, 1))
        return DistinctTicketStream(
            match_positions=matches,
            outcome_positions=selected_outcomes,
            proposal_identity_indices=np.arange(stop, dtype=int),
            generator=generator,
            seed=int(seed),
        )
    branch = np.clip(value, 0.0, None)
    fallback = np.clip(probabilities, 0.0, None)
    fallback_sum = fallback.sum(axis=1, keepdims=True)
    fallback = np.divide(
        fallback,
        fallback_sum,
        out=np.full_like(fallback, 1.0 / 3.0),
        where=fallback_sum > 0,
    )
    row_sum = branch.sum(axis=1, keepdims=True)
    branch = np.divide(branch, row_sum, out=fallback.copy(), where=row_sum > 0)
    selected_outcomes = _weighted_outcome_first_discovery(
        branch, requested_unique=stop, seed=seed
    )
    matches = np.tile(
        np.arange(len(value), dtype=int), (len(selected_outcomes), 1)
    )
    return DistinctTicketStream(
        match_positions=matches,
        outcome_positions=selected_outcomes,
        proposal_identity_indices=np.arange(len(selected_outcomes), dtype=int),
        generator=generator,
        seed=int(seed),
    )


def _weighted_outcome_first_discovery(
    probability: np.ndarray, *, requested_unique: int, seed: int
) -> np.ndarray:
    """Vectorized iid proposals, retaining outcome codes at first discovery."""

    n = len(probability)
    rng = np.random.default_rng(seed)
    cumulative = np.cumsum(probability, axis=1)
    code_weight = np.power(3, np.arange(n, dtype=np.int64))
    identities: dict[int, np.ndarray] = {}
    proposal_limit = max(1_000, 50 * requested_unique)
    proposals = 0
    while len(identities) < requested_unique and proposals < proposal_limit:
        block = min(max(64, 2 * (requested_unique - len(identities))), proposal_limit - proposals)
        uniforms = rng.random((block, n, 1))
        outcomes = (uniforms > cumulative[None, :, :]).sum(axis=2)
        outcomes = np.minimum(outcomes, 2).astype(np.int8)
        codes = outcomes.astype(np.int64) @ code_weight
        for code, outcome in zip(codes, outcomes):
            proposals += 1
            if int(code) not in identities:
                identities[int(code)] = outcome.copy()
                if len(identities) == requested_unique:
                    break
    if not identities:
        raise RuntimeError("weighted proposal stream discovered no outcome code")
    return np.stack(list(identities.values())).astype(int)


def derived_subset_seed(seed: int, subset_id: str) -> int:
    digest = hashlib.sha256(f"{seed}|{subset_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big", signed=False)
