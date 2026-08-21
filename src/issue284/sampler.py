"""Leakage-safe, issue-normalized N-match subset sampling for Issue #284."""

from __future__ import annotations

import hashlib
import itertools
import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

PROPOSAL_FAMILIES = (
    "UNIFORM",
    "VALUE_WEIGHTED",
    "DIVERGENCE_WEIGHTED",
    "SHAPE_STRATIFIED",
)


def sample_issue_subsets(
    *,
    issue: str,
    match_ids: Sequence[str],
    n: int,
    value_score: Sequence[float],
    divergence_score: Sequence[float],
    reliability_score: Sequence[float] | None = None,
    samples_per_family: int = 8,
    seed: int = 284_001,
    epoch: int = 0,
) -> pd.DataFrame:
    """Sample distinct N-match identities from one issue using four proposals.

    The recorded ``ordered_draw_probability`` is the probability of the seeded
    sequential draw order under its proposal. It is diagnostic and is not used
    as an inverse-probability training weight. Issue-normalized loss, not row
    count or proposal probability, controls statistical contribution.
    """

    ids = tuple(str(match_id) for match_id in match_ids)
    m = len(ids)
    if len(set(ids)) != m:
        raise ValueError("match identities must be unique inside an issue")
    if not 1 <= n <= m:
        raise ValueError("n must be between one and the issue match count")
    if samples_per_family <= 0 or epoch < 0:
        raise ValueError("samples_per_family must be positive and epoch nonnegative")
    value = _finite_score(value_score, m, "value_score")
    divergence = _finite_score(divergence_score, m, "divergence_score")
    reliability = (
        np.ones(m, dtype=float)
        if reliability_score is None
        else _finite_score(reliability_score, m, "reliability_score")
    )
    total_requested = samples_per_family * len(PROPOSAL_FAMILIES)
    total_possible = math.comb(m, n)
    target = min(total_requested, total_possible)
    max_inclusions = max(1, math.ceil(1.75 * target * n / m))
    inclusion_count = np.zeros(m, dtype=int)
    seen: set[tuple[int, ...]] = set()
    rows: list[dict[str, object]] = []

    if total_possible <= total_requested:
        combinations = list(itertools.combinations(range(m), n))
        rng = _rng(seed, issue, n, epoch, "EXHAUSTIVE")
        rng.shuffle(combinations)
        for indexes in combinations:
            _append_row(
                rows,
                issue=issue,
                ids=ids,
                indexes=indexes,
                n=n,
                family="UNIFORM",
                epoch=epoch,
                seed=seed,
                ordered_draw_probability=1.0 / total_possible,
            )
        return assign_issue_weights(pd.DataFrame(rows))

    proposal_weights = {
        "UNIFORM": np.ones(m, dtype=float),
        "VALUE_WEIGHTED": _positive_weight(value) * _reliability_tilt(reliability),
        "DIVERGENCE_WEIGHTED": _positive_weight(np.abs(divergence))
        * _reliability_tilt(reliability),
        "SHAPE_STRATIFIED": _shape_stratified_weight(
            value, divergence, reliability
        ),
    }
    for family in PROPOSAL_FAMILIES:
        rng = _rng(seed, issue, n, epoch, family)
        family_count = 0
        attempts = 0
        while family_count < samples_per_family and len(rows) < target:
            attempts += 1
            if attempts > max(500, 100 * samples_per_family):
                break
            ordered, probability = _weighted_draw_without_replacement(
                rng, proposal_weights[family], n
            )
            indexes = tuple(sorted(ordered))
            if indexes in seen:
                continue
            if np.any(inclusion_count[list(indexes)] >= max_inclusions):
                continue
            seen.add(indexes)
            inclusion_count[list(indexes)] += 1
            _append_row(
                rows,
                issue=issue,
                ids=ids,
                indexes=indexes,
                n=n,
                family=family,
                epoch=epoch,
                seed=seed,
                ordered_draw_probability=probability,
            )
            family_count += 1

    if len(rows) < target:
        rng = _rng(seed, issue, n, epoch, "BALANCED_FILL")
        attempts = 0
        while len(rows) < target and attempts < 20_000:
            attempts += 1
            balance = 1.0 / (1.0 + inclusion_count.astype(float))
            ordered, probability = _weighted_draw_without_replacement(rng, balance, n)
            indexes = tuple(sorted(ordered))
            if indexes in seen:
                continue
            seen.add(indexes)
            inclusion_count[list(indexes)] += 1
            _append_row(
                rows,
                issue=issue,
                ids=ids,
                indexes=indexes,
                n=n,
                family="BALANCED_FILL",
                epoch=epoch,
                seed=seed,
                ordered_draw_probability=probability,
            )
    if len(rows) != target:
        raise RuntimeError(
            f"could not sample requested distinct subsets: {len(rows)} != {target}"
        )
    result = assign_issue_weights(pd.DataFrame(rows))
    result["match_inclusion_cap"] = max_inclusions
    result["max_match_inclusion_fraction"] = float(inclusion_count.max() / len(rows))
    return result


def assign_issue_weights(frame: pd.DataFrame) -> pd.DataFrame:
    """Assign weights summing to one inside every independent issue/epoch."""

    required = {"issue", "epoch"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"missing issue-weight columns: {sorted(missing)}")
    result = frame.copy()
    counts = result.groupby(["issue", "epoch"])["issue"].transform("size")
    if (counts <= 0).any():
        raise ValueError("empty issue groups cannot be weighted")
    result["issue_training_weight"] = 1.0 / counts.astype(float)
    return result


def _append_row(
    rows: list[dict[str, object]],
    *,
    issue: str,
    ids: tuple[str, ...],
    indexes: tuple[int, ...],
    n: int,
    family: str,
    epoch: int,
    seed: int,
    ordered_draw_probability: float,
) -> None:
    match_identity = tuple(ids[index] for index in indexes)
    digest = hashlib.sha256(
        f"{issue}|{n}|{'|'.join(match_identity)}".encode()
    ).hexdigest()[:20]
    rows.append(
        {
            "issue": str(issue),
            "n": int(n),
            "proposal_family": family,
            "epoch": int(epoch),
            "sampler_seed": int(seed),
            "subset_id": f"{issue}:N{n}:{digest}",
            "match_indices": indexes,
            "match_ids": match_identity,
            "ordered_draw_probability": float(ordered_draw_probability),
        }
    )


def _finite_score(values: Sequence[float], size: int, name: str) -> np.ndarray:
    score = np.asarray(values, dtype=float)
    if score.shape != (size,):
        raise ValueError(f"{name} must have one value per match")
    finite = score[np.isfinite(score)]
    fill = float(np.median(finite)) if len(finite) else 0.0
    return np.nan_to_num(score, nan=fill, posinf=fill, neginf=fill)


def _positive_weight(score: np.ndarray) -> np.ndarray:
    rank = pd.Series(score).rank(method="average", pct=True).to_numpy(dtype=float)
    return 0.10 + rank


def _reliability_tilt(reliability: np.ndarray) -> np.ndarray:
    return 0.50 + _positive_weight(reliability)


def _shape_stratified_weight(
    value: np.ndarray, divergence: np.ndarray, reliability: np.ndarray
) -> np.ndarray:
    signatures = np.column_stack(
        [
            _quantile_bin(value),
            _quantile_bin(np.abs(divergence)),
            _quantile_bin(reliability),
        ]
    )
    _, inverse, counts = np.unique(
        signatures, axis=0, return_inverse=True, return_counts=True
    )
    return 1.0 / counts[inverse].astype(float)


def _quantile_bin(score: np.ndarray) -> np.ndarray:
    rank = pd.Series(score).rank(method="average", pct=True).to_numpy(dtype=float)
    return np.minimum((3.0 * rank).astype(int), 2)


def _weighted_draw_without_replacement(
    rng: np.random.Generator, weights: np.ndarray, n: int
) -> tuple[tuple[int, ...], float]:
    remaining = np.arange(len(weights), dtype=int)
    remaining_weight = np.asarray(weights, dtype=float).copy()
    remaining_weight = np.where(
        np.isfinite(remaining_weight) & (remaining_weight > 0), remaining_weight, 1e-9
    )
    ordered: list[int] = []
    probability = 1.0
    for _ in range(n):
        probabilities = remaining_weight / remaining_weight.sum()
        position = int(rng.choice(len(remaining), p=probabilities))
        probability *= float(probabilities[position])
        ordered.append(int(remaining[position]))
        remaining = np.delete(remaining, position)
        remaining_weight = np.delete(remaining_weight, position)
    return tuple(ordered), probability


def _rng(seed: int, issue: str, n: int, epoch: int, family: str) -> np.random.Generator:
    digest = hashlib.sha256(
        f"{seed}|{issue}|{n}|{epoch}|{family}".encode()
    ).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big", signed=False))
