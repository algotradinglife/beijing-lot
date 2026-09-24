"""Stable model-fitting client for the Issue #383 walk-forward surface."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

from src.cutoff_mapping.api import MappingResult, fit_cutoff_mapping
from beidan_backend.temporal_learning import AvailabilityPolicy, Cutoff, WeightingPolicy

from .contract import (
    AVAILABILITY_POLICY,
    EXPONENTIAL_HALF_LIFE_DAYS,
    INTENDED_USE,
    MINIMUM_ESS,
    RECENT_BLEND,
    RECENT_WINDOW_ISSUES,
)


def weighting_policy(name: str, *, minimum_ess: float = MINIMUM_ESS) -> WeightingPolicy:
    if name == "EXPANDING_EQUAL":
        return WeightingPolicy.expanding_equal(minimum_ess=minimum_ess)
    if name == "EXPANDING_EXPONENTIAL":
        return WeightingPolicy.expanding_exponential(
            EXPONENTIAL_HALF_LIFE_DAYS, minimum_ess=minimum_ess
        )
    if name == "RECENT_STATE_BLEND":
        return WeightingPolicy.recent_state_blend(
            RECENT_WINDOW_ISSUES, RECENT_BLEND, minimum_ess=minimum_ess
        )
    raise ValueError(f"unknown policy: {name}")


def fit_issue_mapping(
    history: pd.DataFrame,
    target: pd.DataFrame,
    cutoff: Cutoff,
    *,
    repository_root: Path,
    source_hashes: Mapping[str, str],
    policy_name: str,
) -> MappingResult:
    """Fit one cutoff-bound policy; chronology remains owned by the shared API."""

    return fit_cutoff_mapping(
        history,
        target,
        cutoff,
        repository_root=repository_root,
        implementation_modules=("src.cutoff_walkforward.fitting",),
        source_hashes=source_hashes,
        weighting_policy=weighting_policy(policy_name),
        availability_policy=AvailabilityPolicy.historical_proxy(AVAILABILITY_POLICY),
        intended_use=INTENDED_USE,
    )
