"""Shared cutoff-driven historical-learning protocol."""

from .core import (
    AvailabilityFilter,
    AvailabilityPolicy,
    Cutoff,
    EffectiveSamplePolicy,
    FitResult,
    LearningContext,
    LearningReceipt,
    PartitionPolicy,
    SelectionResult,
    TemporalContractError,
    WeightingPolicy,
    WalkForwardRunner,
    prepare_learning_context,
    temporal_cache_key,
    temporal_client,
)
from .example_selector import ThresholdSelection, select_cutoff_threshold
from .provenance import implementation_closure, verify_implementation_closure

__all__ = [
    "AvailabilityFilter",
    "AvailabilityPolicy",
    "Cutoff",
    "EffectiveSamplePolicy",
    "FitResult",
    "LearningContext",
    "LearningReceipt",
    "PartitionPolicy",
    "SelectionResult",
    "TemporalContractError",
    "ThresholdSelection",
    "WeightingPolicy",
    "WalkForwardRunner",
    "prepare_learning_context",
    "implementation_closure",
    "select_cutoff_threshold",
    "temporal_cache_key",
    "temporal_client",
    "verify_implementation_closure",
]
