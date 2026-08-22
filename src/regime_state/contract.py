"""Frozen constants for BJ-UNIFIED-REGIME-STATE-001/v1."""

from __future__ import annotations

CONTRACT = "BJ-UNIFIED-REGIME-STATE-001/v1"
YEARS = (2020, 2021, 2022, 2023, 2024)
PREDICTION_YEARS = (2022, 2023, 2024)
PRIMARY_HORIZON = "10h"
OUTCOMES = ("3", "1", "0")
WINDOWS = (5, 10, 20, 40)
HALF_LIVES = (5, 20)
MODEL_SEED = 330

MARKET_FEATURES = (
    "fixture_count",
    "trusted_fixture_fraction",
    "eu_entropy_mean",
    "eu_entropy_std",
    "line_entropy_mean",
    "line_entropy_std",
    "eu_top1_mass_mean",
    "eu_top2_mass_mean",
    "line_top1_mass_mean",
    "line_top2_mass_mean",
    "eu_concentration_mean",
    "line_concentration_mean",
    "divergence_signed_mean",
    "divergence_abs_mean",
    "divergence_abs_p90",
    "line_abs_mean",
    "books_mean",
)

TARGETS = (
    "eu_brier",
    "line_brier",
    "eu_top2_residual",
    "line_top2_residual",
    "allocator_delta",
)

DECISIONS = (
    "REGIME_STATE_OBSERVABLE",
    "SLOW_DRIFT_ONLY",
    "SPARSE_RESPONSE_REDESIGN",
    "NO_REGIME_SIGNAL",
)
