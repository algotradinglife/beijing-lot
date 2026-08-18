"""Minimal physical M×3 data contract frozen by Issue #253."""

from .builder import (
    build_representative_package,
    load_feature_cells,
    resolve_data_root,
    verify_package,
)
from .contract import CONTRACT_VERSION, OUTCOME_CODES

__all__ = [
    "CONTRACT_VERSION",
    "OUTCOME_CODES",
    "build_representative_package",
    "load_feature_cells",
    "resolve_data_root",
    "verify_package",
]
