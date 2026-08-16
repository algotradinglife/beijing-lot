"""divergence_profile — Issue #229 divergence-aware M×3 data profile.

Reusable, deterministic package that binds the four upstream frozen data
packages (#203/#204/#214/#180), materializes the six probability
representations, computes per-cell divergence features, runs DQ-01..DQ-12 and
emits the canonical handoff for #209.

Rework 2026-08-15 (REWORK_TYPE=method): match-level causal joins, per-feature
observed-at/availability masks, per-cell divergence semantics, float
half-goal line translation, source-identity anti-alias registry, full-payload
0.65 boundary scan, computed (never hardcoded) REQ-D evidence and atomic
package publication.
"""

from . import contract  # noqa: F401
from . import divergence  # noqa: F401
from . import figures  # noqa: F401
from . import handoff  # noqa: F401
from . import manifest  # noqa: F401
from . import probabilities  # noqa: F401
from . import profile  # noqa: F401
from . import publication  # noqa: F401
from . import quality  # noqa: F401
from . import sources  # noqa: F401
from .builder import (  # noqa: F401
    BuildReceipt,
    assemble_cells,
    build,
    build_evidence,
    disposition,
    write_package,
)
from .handoff import (  # noqa: F401
    HandoffValidationError,
    load_causal_inference_cells,
    load_package,
    validate_package,
)

__all__ = [
    "BuildReceipt",
    "assemble_cells",
    "build",
    "build_evidence",
    "contract",
    "disposition",
    "divergence",
    "handoff",
    "HandoffValidationError",
    "load_causal_inference_cells",
    "load_package",
    "manifest",
    "probabilities",
    "profile",
    "publication",
    "quality",
    "sources",
    "validate_package",
    "write_package",
]
