"""Correct-score research primitives; deliberately not an execution surface."""

from .contract import CorrectScoreOddsSnapshot, CorrectScoreQuote, OddsEligibility, validate_snapshot
from .experiment import ResearchCandidate, ResearchExperimentResult, run_research_experiment
from .model import TemperatureCalibration, independent_poisson_score_probs, fit_temperature_calibration

__all__ = [
    "CorrectScoreOddsSnapshot",
    "CorrectScoreQuote",
    "OddsEligibility",
    "ResearchCandidate",
    "ResearchExperimentResult",
    "TemperatureCalibration",
    "fit_temperature_calibration",
    "independent_poisson_score_probs",
    "run_research_experiment",
    "validate_snapshot",
]
