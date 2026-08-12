"""Causal issue × match × outcome tensors for BJ-UNIFIED-TENSOR-DATA-001.

The package root intentionally exposes only the outcome-unexposed inference
loader.  Settlement labels live in :mod:`unified_tensor.settlement_labels` and
must be imported explicitly by validation code.
"""

from .inference import IssueTensor, MatchProvenance, load_issue_tensor, load_issue_tensors

__all__ = [
    "IssueTensor",
    "MatchProvenance",
    "load_issue_tensor",
    "load_issue_tensors",
]
