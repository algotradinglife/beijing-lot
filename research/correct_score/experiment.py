"""Research-only Top-k and EV/q diagnostics for validated odds snapshots.

No function in this module writes tickets, calculates payout or ROI, sizes a
stake, or marks a candidate as actionable.  Returned candidates are paper
diagnostics only.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from .contract import CorrectScoreOddsSnapshot, OddsEligibility, Scoreline, validate_snapshot
from .model import TemperatureCalibration, temperature_scale


@dataclass(frozen=True)
class ResearchCandidate:
    """One ranked diagnostic, never an instruction to place a wager."""

    match_id: str
    snapshot_id: str
    scoreline: Scoreline
    calibrated_probability: float
    market_probability: float
    theoretical_edge: float
    q_ratio: float
    top_k_rank: int


@dataclass(frozen=True)
class ResearchExperimentResult:
    """A fail-closed per-snapshot result; ineligible inputs have no candidates."""

    eligibility: OddsEligibility
    candidates: tuple[ResearchCandidate, ...]


def _market_probabilities(snapshot: CorrectScoreOddsSnapshot) -> dict[Scoreline, float]:
    inverse = {quote.scoreline: 1.0 / quote.decimal_odds for quote in snapshot.quotes}
    total = sum(inverse.values())
    return {scoreline: value / total for scoreline, value in inverse.items()}


def run_research_experiment(
    snapshot: CorrectScoreOddsSnapshot,
    baseline_probabilities: Mapping[Scoreline, float],
    calibration: TemperatureCalibration,
    *,
    top_k: int,
    min_theoretical_edge: float = float("-inf"),
    min_q_ratio: float = 0.0,
    max_staleness: timedelta = timedelta(minutes=10),
) -> ResearchExperimentResult:
    """Rank only immutable, complete, fresh pre-match evidence.

    ``theoretical_edge = calibrated_probability * raw_decimal_odds - 1`` and
    ``q_ratio = calibrated_probability / de-vigged_market_probability`` are
    diagnostics.  They are not a return estimate, authorization, or stake
    rule.  An ineligible snapshot always yields an empty candidate tuple.
    """

    eligibility = validate_snapshot(snapshot, max_staleness=max_staleness)
    if not eligibility.eligible:
        return ResearchExperimentResult(eligibility, ())
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if min_q_ratio < 0:
        raise ValueError("min_q_ratio must be non-negative")

    scorelines = snapshot.required_scorelines
    if any(scoreline not in baseline_probabilities for scoreline in scorelines):
        raise ValueError("baseline probabilities must cover the immutable market catalogue")
    probability_mass = sum(float(baseline_probabilities[scoreline]) for scoreline in scorelines)
    if not math.isclose(probability_mass, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("baseline must include exhaustive outcome mass; truncated tails are ineligible")
    calibrated = temperature_scale(baseline_probabilities, scorelines, calibration.temperature)
    market = _market_probabilities(snapshot)
    raw_odds = {quote.scoreline: quote.decimal_odds for quote in snapshot.quotes}
    ranked = sorted(scorelines, key=lambda scoreline: (-calibrated[scoreline], scoreline))[:top_k]
    candidates = []
    for rank, scoreline in enumerate(ranked, start=1):
        edge = calibrated[scoreline] * raw_odds[scoreline] - 1.0
        q_ratio = calibrated[scoreline] / market[scoreline]
        if edge >= min_theoretical_edge and q_ratio >= min_q_ratio:
            candidates.append(
                ResearchCandidate(
                    match_id=snapshot.match_id,
                    snapshot_id=snapshot.snapshot_id,
                    scoreline=scoreline,
                    calibrated_probability=calibrated[scoreline],
                    market_probability=market[scoreline],
                    theoretical_edge=edge,
                    q_ratio=q_ratio,
                    top_k_rank=rank,
                )
            )
    return ResearchExperimentResult(eligibility, tuple(candidates))
