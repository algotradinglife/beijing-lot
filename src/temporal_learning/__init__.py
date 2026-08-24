"""Shared cutoff-driven historical-learning protocol."""

from .closure import (
    ImplementationClosure,
    implementation_closure,
    closure_receipt,
)
from .core import (
    AvailabilityFilter,
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
)
from .example_selector import ThresholdSelection, select_cutoff_threshold

__all__ = [
    "AvailabilityFilter",
    "Cutoff",
    "EffectiveSamplePolicy",
    "FitResult",
    "ImplementationClosure",
    "LearningContext",
    "LearningReceipt",
    "PartitionPolicy",
    "SelectionResult",
    "TemporalContractError",
    "ThresholdSelection",
    "WeightingPolicy",
    "WalkForwardRunner",
    "closure_receipt",
    "implementation_closure",
    "prepare_learning_context",
    "select_cutoff_threshold",
    "temporal_cache_key",
]