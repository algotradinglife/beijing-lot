"""Independent-Poisson baseline and pre-registered temperature calibration."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from .contract import Scoreline


def independent_poisson_score_probs(
    lambda_home: float,
    lambda_away: float,
    scorelines: Sequence[Scoreline],
) -> dict[Scoreline, float]:
    """Return unconditioned exact-score probabilities for a supplied score grid.

    The omitted tail is intentionally not renormalized.  Renormalizing a
    truncated grid would overstate listed correct-score probabilities.
    """

    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("poisson rates must be positive")
    if len(set(scorelines)) != len(scorelines):
        raise ValueError("scorelines must be unique")
    return {
        scoreline: math.exp(-lambda_home)
        * lambda_home**scoreline[0]
        / math.factorial(scoreline[0])
        * math.exp(-lambda_away)
        * lambda_away**scoreline[1]
        / math.factorial(scoreline[1])
        for scoreline in scorelines
    }


def _normalized(values: Mapping[Scoreline, float], scorelines: Sequence[Scoreline]) -> dict[Scoreline, float]:
    raw = {scoreline: max(float(values[scoreline]), 1e-15) for scoreline in scorelines}
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("probabilities must contain positive mass")
    return {scoreline: value / total for scoreline, value in raw.items()}


def temperature_scale(
    probabilities: Mapping[Scoreline, float],
    scorelines: Sequence[Scoreline],
    temperature: float,
) -> dict[Scoreline, float]:
    """Calibrate a fixed score catalogue without using market odds or outcomes."""

    if temperature <= 0:
        raise ValueError("temperature must be positive")
    base = _normalized(probabilities, scorelines)
    powered = {scoreline: value ** (1.0 / temperature) for scoreline, value in base.items()}
    return _normalized(powered, scorelines)


@dataclass(frozen=True)
class TemperatureCalibration:
    """A calibration fitted only on an earlier, fully settled training period."""

    temperature: float
    n_training_rows: int
    logloss_before: float
    logloss_after: float


def _logloss(rows: Sequence[tuple[Mapping[Scoreline, float], Scoreline]], scorelines: Sequence[Scoreline], temperature: float) -> float:
    return -sum(
        math.log(max(temperature_scale(probabilities, scorelines, temperature)[outcome], 1e-15))
        for probabilities, outcome in rows
    ) / len(rows)


def fit_temperature_calibration(
    rows: Sequence[tuple[Mapping[Scoreline, float], Scoreline]],
    scorelines: Sequence[Scoreline],
) -> TemperatureCalibration:
    """Fit a deterministic 0.50--2.00 temperature grid on settled past rows."""

    if not rows:
        raise ValueError("calibration requires settled training rows")
    if not scorelines or len(set(scorelines)) != len(scorelines):
        raise ValueError("scorelines must be a non-empty unique catalogue")
    for probabilities, outcome in rows:
        if outcome not in scorelines or any(scoreline not in probabilities for scoreline in scorelines):
            raise ValueError("each training row must cover the settled scoreline catalogue")

    grid = tuple(round(0.50 + 0.025 * index, 3) for index in range(61))
    best_temperature = min(grid, key=lambda temperature: (_logloss(rows, scorelines, temperature), temperature))
    return TemperatureCalibration(
        temperature=best_temperature,
        n_training_rows=len(rows),
        logloss_before=_logloss(rows, scorelines, 1.0),
        logloss_after=_logloss(rows, scorelines, best_temperature),
    )
