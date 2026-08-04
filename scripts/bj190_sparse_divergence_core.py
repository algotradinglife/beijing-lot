#!/usr/bin/env python3
"""Outcome-unexposed primitives for Issue #190's sparse divergence freeze.

The accepted #180 core remains byte-for-byte authoritative.  This module only
exposes the latent Poisson calls that the accepted core already makes and turns
them into auditable, truncated score-difference distributions.  The controlling
independent branch is #180's T1_DEEP_TEAM log pool; no #179/TL market-derived
feature enters that branch.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


CODES = ("3", "1", "0")
FAMILY_ORDER = (
    "LATENT_STRENGTH",
    "HOME_AWAY_SPLIT",
    "ROLLING_FORM",
    "REST_CONGESTION",
    "OPPONENT_ADJUSTMENT",
    "TEAM_INITIALIZATION",
    "H2H_PRIOR",
)
MAX_GOALS = 12
RECONCILIATION_TOLERANCE = 5e-12


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def normalize(values: Sequence[float]) -> tuple[float, ...]:
    total = math.fsum(values)
    if not math.isfinite(total) or total <= 0:
        raise RuntimeError("cannot normalize non-positive distribution")
    return tuple(float(value) / total for value in values)


def handicap_code(score_difference: int, handicap: float) -> str:
    adjusted = float(score_difference) + float(handicap)
    return "3" if adjusted > 1e-9 else "0" if adjusted < -1e-9 else "1"


def poisson_difference_distribution(
    lambda_home: float,
    lambda_away: float,
    *,
    max_goals: int = MAX_GOALS,
) -> dict[int, float]:
    """Return #180's exact truncated independent-Poisson difference PMF.

    #180 clips each intensity to [0.08, 6], enumerates both goal counts from
    zero through ``max_goals`` inclusive, then normalizes the retained joint
    mass.  Tail mass outside the square is deliberately excluded.
    """

    lambda_home = min(6.0, max(0.08, float(lambda_home)))
    lambda_away = min(6.0, max(0.08, float(lambda_away)))

    def pmf(value: float) -> list[float]:
        rows = [math.exp(-value)]
        for goals in range(1, max_goals + 1):
            rows.append(rows[-1] * value / goals)
        return rows

    mass: Counter[int] = Counter()
    for home_goals, home_p in enumerate(pmf(lambda_home)):
        for away_goals, away_p in enumerate(pmf(lambda_away)):
            mass[home_goals - away_goals] += home_p * away_p
    values = normalize([mass[difference] for difference in range(-max_goals, max_goals + 1)])
    return {
        difference: values[difference + max_goals]
        for difference in range(-max_goals, max_goals + 1)
    }


def mapped_probabilities(
    distribution: Mapping[int, float], handicap: float
) -> tuple[float, float, float]:
    counts = Counter({code: 0.0 for code in CODES})
    for difference, probability in distribution.items():
        counts[handicap_code(int(difference), handicap)] += float(probability)
    return normalize([counts[code] for code in CODES])  # type: ignore[return-value]


def expected_margin(distribution: Mapping[int, float]) -> float:
    return math.fsum(int(difference) * float(probability) for difference, probability in distribution.items())


def distribution_payload(distribution: Mapping[int, float]) -> list[dict[str, object]]:
    return [
        {"score_difference": int(difference), "probability": f"{probability:.15f}"}
        for difference, probability in sorted(distribution.items())
    ]


def no_vig_from_prices(prices: Sequence[float]) -> tuple[float, float, float]:
    if len(prices) != 3 or any(not math.isfinite(float(price)) or float(price) <= 1 for price in prices):
        raise RuntimeError("target-safe price vector is incomplete or invalid")
    inverse = [1.0 / float(price) for price in prices]
    return normalize(inverse)  # type: ignore[return-value]


def capture_family_latents(
    state: Any,
    row: Mapping[str, object],
    cutoff: Any,
    accepted_core: Any,
) -> tuple[
    dict[str, tuple[float, float, float]],
    dict[str, object],
    dict[str, tuple[float, float, float, int]],
]:
    """Capture the seven accepted #180 Poisson call sites without changing them."""

    original = accepted_core.poisson_handicap
    calls: list[tuple[float, float, float, int]] = []

    def recorder(
        lambda_home: float,
        lambda_away: float,
        handicap: float,
        max_goals: int = MAX_GOALS,
    ) -> tuple[float, float, float]:
        calls.append((float(lambda_home), float(lambda_away), float(handicap), int(max_goals)))
        return original(lambda_home, lambda_away, handicap, max_goals)

    accepted_core.poisson_handicap = recorder
    try:
        vectors, diagnostics = state.family_vectors(row, cutoff)
    finally:
        accepted_core.poisson_handicap = original
    if len(calls) != len(FAMILY_ORDER):
        raise RuntimeError(f"#180 Poisson call-count drift: {len(calls)}")
    captured = dict(zip(FAMILY_ORDER, calls, strict=True))
    if tuple(vectors) != FAMILY_ORDER:
        raise RuntimeError(f"#180 family order drift: {tuple(vectors)}")
    return vectors, diagnostics, captured


def weighted_family_intensities(
    captured: Mapping[str, Sequence[float]],
    family_weights: Mapping[str, float],
) -> tuple[float, float]:
    """Expose T1_DEEP_TEAM's frozen component-intensity expectation.

    T1_DEEP_TEAM log-pools the seven mapped 3/1/0 vectors and therefore is not
    itself a single independent-Poisson call.  Its raw-margin axis is frozen as
    the accepted TEAM_PRIMARY-weighted mean of the seven already-existing
    effective Poisson intensities.  This is an explicit model-side expectation,
    not a reverse-engineered market mean.
    """

    if tuple(captured) != FAMILY_ORDER or tuple(family_weights) != FAMILY_ORDER:
        raise RuntimeError("T1_DEEP_TEAM family order drift")
    total = math.fsum(float(family_weights[name]) for name in FAMILY_ORDER)
    if abs(total - 1.0) > 1e-12:
        raise RuntimeError("T1_DEEP_TEAM family weights do not sum to one")
    home = math.fsum(
        float(family_weights[name])
        * min(6.0, max(0.08, float(captured[name][0])))
        for name in FAMILY_ORDER
    )
    away = math.fsum(
        float(family_weights[name])
        * min(6.0, max(0.08, float(captured[name][1])))
        for name in FAMILY_ORDER
    )
    return home, away


def h2h_difference_distribution(
    state: Any,
    row: Mapping[str, object],
    prior_distribution: Mapping[int, float],
) -> dict[int, float]:
    """Reproduce #180's 12-observation Poisson shrinkage for H2H_PRIOR."""

    home = str(row.get("home_team_id") or "")
    away = str(row.get("away_team_id") or "")
    h2h_rows = list(state.h2h.get((home, away), ()))
    h2h_rows.extend(
        (away_goals, home_goals)
        for home_goals, away_goals in state.h2h.get((away, home), ())
    )
    mass: Counter[int] = Counter(
        {int(difference): 12.0 * float(probability) for difference, probability in prior_distribution.items()}
    )
    for home_goals, away_goals in h2h_rows:
        difference = int(round(float(home_goals) - float(away_goals)))
        if difference < -MAX_GOALS or difference > MAX_GOALS:
            raise RuntimeError("H2H score difference exceeds frozen support")
        mass[difference] += 1.0
    values = normalize([mass[difference] for difference in range(-MAX_GOALS, MAX_GOALS + 1)])
    return {
        difference: values[difference + MAX_GOALS]
        for difference in range(-MAX_GOALS, MAX_GOALS + 1)
    }


def group_mass_calibrated_distribution(
    family_distributions: Mapping[str, Mapping[int, float]],
    family_weights: Mapping[str, float],
    target_probabilities: Sequence[float],
    handicap: float,
) -> dict[int, float]:
    """Create a p-only diagnostic distribution for #180's log-pooled primary.

    A log pool of three-way aggregates is not a single Poisson model.  We first
    construct a weighted log-pool shape over score differences, then rescale the
    within-code shapes so their three group masses equal the accepted primary
    p3/p1/p0 exactly.  This distribution is diagnostic and must not be presented
    as latent intensities or as the controlling expected-margin estimator.
    """

    active = {name: float(weight) for name, weight in family_weights.items() if float(weight) > 0}
    total_weight = math.fsum(active.values())
    if set(active) - set(family_distributions) or total_weight <= 0:
        raise RuntimeError("invalid family distribution pool")
    shape: dict[int, float] = {}
    for difference in range(-MAX_GOALS, MAX_GOALS + 1):
        shape[difference] = math.exp(
            math.fsum(
                weight / total_weight
                * math.log(max(1e-300, float(family_distributions[name][difference])))
                for name, weight in active.items()
            )
        )
    groups: dict[str, list[int]] = {code: [] for code in CODES}
    for difference in shape:
        groups[handicap_code(difference, handicap)].append(difference)
    target = normalize([float(value) for value in target_probabilities])
    output: dict[int, float] = {}
    for index, code in enumerate(CODES):
        group_total = math.fsum(shape[difference] for difference in groups[code])
        if group_total <= 0:
            raise RuntimeError("empty score-difference outcome group")
        for difference in groups[code]:
            output[difference] = target[index] * shape[difference] / group_total
    return dict(sorted(output.items()))


def probability_reconciliation_error(
    actual: Sequence[float], expected: Sequence[float]
) -> float:
    if len(actual) != 3 or len(expected) != 3:
        raise RuntimeError("probability vector must contain exactly three values")
    return max(abs(float(left) - float(right)) for left, right in zip(actual, expected, strict=True))


def directional_ticket_accounting(n: int = 7) -> dict[str, object]:
    """Freeze the exact equal-budget one-code directional construction."""

    full = 3**n
    unique_after_one_code_delete = 2 * 3 ** (n - 1)
    residual_repeats = full - unique_after_one_code_delete
    if unique_after_one_code_delete + residual_repeats != full:
        raise AssertionError("directional accounting drift")
    return {
        "n": n,
        "full_unique_ticket_count": full,
        "one_code_deleted_unique_ticket_count": unique_after_one_code_delete,
        "deterministic_residual_repeat_count": residual_repeats,
        "executed_ticket_count": full,
        "per_ticket_stake_yuan": 2,
        "planned_stake_yuan": 2 * full,
        "max_ticket_multiplicity": 2,
        "rule": "enumerate the 1458 tickets excluding the most-negative-delta code at the strongest eligible leg; repeat the 729 highest joint-estimator-probability tickets once; ties by base-3 ordinal",
    }
