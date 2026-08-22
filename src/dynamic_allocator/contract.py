"""Frozen constants for BJ-UNIFIED-DYNAMIC-ALLOCATOR-001/v1."""

from __future__ import annotations

CONTRACT = "BJ-UNIFIED-DYNAMIC-ALLOCATOR-001/v1"
PRIMARY_HORIZON = "10h"
OOF_YEARS = (2020, 2021, 2022)
META_TRAIN_YEARS = (2020, 2021)
META_TUNE_YEAR = 2022
EVAL_YEARS = (2023, 2024)
STATIC_LAMBDAS = (0.0, 0.25, 0.5, 0.75, 1.0)
FUNDED_UNITS = 128
STAKE_UNIT = 2.0
ISSUE_STAKE = FUNDED_UNITS * STAKE_UNIT
STARTING_CAPITAL = 100_000.0
MODEL_SEED = 328

FEATURE_COLUMNS = (
    "eligible_fixtures",
    "selector_mean",
    "selector_std",
    "selector_cutoff_margin",
    "action_mean",
    "action_std",
    "positive_action_count",
    "retained_mean",
    "retained_std",
    "entropy_mean",
    "entropy_std",
    "divergence_abs_mean",
    "divergence_abs_std",
    "line_abs_mean",
    "books_mean",
    "ticket_value_cv",
    "ticket_value_max_share",
    "a1_hhi",
    "a0_a1_l1",
)

ARMS = (
    "L000",
    "L025",
    "L050",
    "L075",
    "L100",
    "DYN_RIDGE",
    "DYN_HGBR",
)

DECISIONS = (
    "DYNAMIC_ALLOCATOR_INCREMENT",
    "STATIC_INTERIOR_SIGNAL",
    "ENDPOINT_RETAINED",
    "NO_BASELINE_INCREMENT",
)
