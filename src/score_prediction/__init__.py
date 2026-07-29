"""Reference implementations of correct-score prediction strategies."""

from .v771 import (
    AuxiliaryMode,
    Candidate,
    Diagnostics,
    MatchOdds,
    PredictionResult,
    ThreeWayOdds,
    predict,
)

__all__ = [
    "AuxiliaryMode",
    "Candidate",
    "Diagnostics",
    "MatchOdds",
    "PredictionResult",
    "ThreeWayOdds",
    "predict",
]
