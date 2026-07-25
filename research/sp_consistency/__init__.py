"""Research-only primitives for SP-CONSISTENCY-001A.

The package deliberately contains no ticket, portfolio, stake, settlement, or
production-API code.  G0 coverage auditing must pass before any probability
comparison or outcome-scored evaluation is authorised.
"""

from .coverage import G0_CONFIG_VERSION, run_g0_coverage_audit
from .mapping import (
    HandicapProbabilityBounds,
    aggregate_complete_score_distribution,
    poisson_grid_handicap_bounds,
    score_distribution_handicap_bounds,
)
from .snapshot import create_g0_input_snapshot

__all__ = [
    "G0_CONFIG_VERSION",
    "HandicapProbabilityBounds",
    "aggregate_complete_score_distribution",
    "create_g0_input_snapshot",
    "poisson_grid_handicap_bounds",
    "run_g0_coverage_audit",
    "score_distribution_handicap_bounds",
]
