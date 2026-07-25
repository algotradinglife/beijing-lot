"""Deterministic score-distribution to Beijing handicap 3/1/0 mapping.

Finite score grids are never renormalised.  If a grid omits probability mass,
the result is an interval for each 3/1/0 probability rather than a fabricated
point estimate.  This is the G1/G2 primitive for SP-CONSISTENCY-001A.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping


OutcomeVector = tuple[float, float, float]  # 3, 1, 0
Scoreline = tuple[int, int]
_TOLERANCE = 1e-12


@dataclass(frozen=True)
class HandicapProbabilityBounds:
    """Lower/upper 3/1/0 probabilities induced by a finite score grid."""

    lower: OutcomeVector
    upper: OutcomeVector
    represented_mass: float
    omitted_mass: float

    @property
    def point_probabilities(self) -> OutcomeVector | None:
        """Return a point only when the distribution is complete."""

        if self.omitted_mass <= _TOLERANCE:
            return self.lower
        return None


def _validate_handicap(handicap: int) -> None:
    if not isinstance(handicap, int) or isinstance(handicap, bool):
        raise ValueError("handicap must be an integer")


def _validate_scores(probabilities: Mapping[Scoreline, float]) -> float:
    if not probabilities:
        raise ValueError("score distribution must not be empty")
    total = 0.0
    for scoreline, probability in probabilities.items():
        if (
            not isinstance(scoreline, tuple)
            or len(scoreline) != 2
            or any(not isinstance(goals, int) or isinstance(goals, bool) or goals < 0 for goals in scoreline)
        ):
            raise ValueError("scorelines must be non-negative integer pairs")
        if not math.isfinite(probability) or probability < 0:
            raise ValueError("score probabilities must be finite and non-negative")
        total += probability
    if not math.isfinite(total) or total <= 0:
        raise ValueError("score distribution must contain positive mass")
    return total


def _outcome_index(home_goals: int, away_goals: int, handicap: int) -> int:
    adjusted_margin = home_goals + handicap - away_goals
    return 0 if adjusted_margin > 0 else 1 if adjusted_margin == 0 else 2


def score_distribution_handicap_bounds(
    probabilities: Mapping[Scoreline, float], handicap: int, *, omitted_mass: float = 0.0
) -> HandicapProbabilityBounds:
    """Map represented score mass and retain a valid bound for unrepresented mass.

    With unknown tail composition, each 3/1/0 class can receive at most all
    omitted mass.  The resulting intervals are conservative and mathematically
    valid; callers must not treat them as normalised point probabilities.
    """

    _validate_handicap(handicap)
    represented_mass = _validate_scores(probabilities)
    if not math.isfinite(omitted_mass) or omitted_mass < 0:
        raise ValueError("omitted_mass must be finite and non-negative")
    if represented_mass + omitted_mass > 1.0 + _TOLERANCE:
        raise ValueError("represented and omitted mass exceed one")
    if not math.isclose(represented_mass + omitted_mass, 1.0, abs_tol=_TOLERANCE):
        raise ValueError("represented and omitted mass must sum to one")

    lower = [0.0, 0.0, 0.0]
    for (home_goals, away_goals), probability in probabilities.items():
        lower[_outcome_index(home_goals, away_goals, handicap)] += probability
    return HandicapProbabilityBounds(
        lower=(lower[0], lower[1], lower[2]),
        upper=tuple(min(1.0, value + omitted_mass) for value in lower),  # type: ignore[arg-type]
        represented_mass=represented_mass,
        omitted_mass=omitted_mass,
    )


def aggregate_complete_score_distribution(
    probabilities: Mapping[Scoreline, float], handicap: int
) -> OutcomeVector:
    """Return an exact 3/1/0 vector only for a complete score distribution."""

    bounds = score_distribution_handicap_bounds(probabilities, handicap)
    point = bounds.point_probabilities
    if point is None:  # defensive; omitted mass is fixed to zero above
        raise ValueError("score distribution is incomplete")
    if not math.isclose(sum(point), 1.0, abs_tol=_TOLERANCE):
        raise ValueError("mapped probability vector is not normalised")
    return point


def _poisson_pmf(rate: float, goals: int) -> float:
    return math.exp(-rate) * rate**goals / math.factorial(goals)


def poisson_grid_handicap_bounds(
    lambda_home: float, lambda_away: float, handicap: int, *, max_goals: int
) -> HandicapProbabilityBounds:
    """Map an independent-Poisson grid without silently renormalising its tail."""

    _validate_handicap(handicap)
    if (
        not math.isfinite(lambda_home)
        or not math.isfinite(lambda_away)
        or lambda_home <= 0
        or lambda_away <= 0
        or not isinstance(max_goals, int)
        or isinstance(max_goals, bool)
        or max_goals < 0
    ):
        raise ValueError("Poisson rates must be positive and max_goals must be non-negative")
    probabilities = {
        (home_goals, away_goals): _poisson_pmf(lambda_home, home_goals)
        * _poisson_pmf(lambda_away, away_goals)
        for home_goals in range(max_goals + 1)
        for away_goals in range(max_goals + 1)
    }
    represented_mass = sum(probabilities.values())
    omitted_mass = max(0.0, 1.0 - represented_mass)
    return score_distribution_handicap_bounds(probabilities, handicap, omitted_mass=omitted_mass)
