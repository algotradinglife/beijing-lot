"""Offline-only handicap-draw probability research primitives.

This package deliberately has no command-line entry point, database access,
network access, ticket representation, price input, or return calculation.
"""

from .loop import (
    HistoricalP1P2Row,
    LoopConfig,
    LoopResult,
    ProjectionEligibility,
    build_checksummed_artifact,
    independent_poisson_handicap_probabilities,
    run_chronological_loop,
    validate_historical_rows,
)
from .approximate_replay import (
    ApproximatePrediction,
    ApproximateReplayConfig,
    ApproximateReplayResult,
    ApproximateReplayRow,
    ProperScoreSummary,
    build_checksummed_approximate_artifact,
    fit_final_proxy_candidates,
    run_approximate_issue_replay,
    summarize_predictions,
    validate_approximate_rows,
)

__all__ = [
    "HistoricalP1P2Row",
    "LoopConfig",
    "LoopResult",
    "ProjectionEligibility",
    "build_checksummed_artifact",
    "independent_poisson_handicap_probabilities",
    "run_chronological_loop",
    "validate_historical_rows",
    "ApproximatePrediction",
    "ApproximateReplayConfig",
    "ApproximateReplayResult",
    "ApproximateReplayRow",
    "ProperScoreSummary",
    "build_checksummed_approximate_artifact",
    "fit_final_proxy_candidates",
    "run_approximate_issue_replay",
    "summarize_predictions",
    "validate_approximate_rows",
]
