"""Outcome-unexposed Track-A contract for Issue #204.

The contract deliberately separates a preregistered 2024 retrospective test
from the 2025-04+ namespace reserved for #210.  It contains no label-loading
helpers: opening labels is a separate, explicit Gate-B operation.
"""

from __future__ import annotations

from typing import Final


CONTRACT_VERSION: Final = "bj204-market-anchored-model-gate-a-v1"
UPSTREAM_CONTRACT_VERSION: Final = "bj203-causal-tensor-v2"
SOURCE_PACKAGE: Final = "results/bj203_causal_tensor_v2"

DEVELOPMENT_YEARS: Final = (2019, 2020, 2021, 2022, 2023)
RETROSPECTIVE_TEST_YEAR: Final = 2024
EMBARGO_START_YEAR: Final = 2025
CV_VALIDATION_YEARS: Final = (2021, 2022, 2023)
SEEDS: Final = (204001, 204002, 204003)

# Inputs are all present in the #203 inference namespace.  The model cannot
# read a target/settlement column; masks are explicit model inputs so missing
# data always has a deterministic fallback rather than implicit imputation.
MODEL_FEATURES: Final = (
    "calibrated_market_probability",
    "devig_euro_probability",
    "euro_1h_odds",
    "fundamental_probability",
    "probability_residual",
    "probability_residual_z",
    "predicted_final_sp",
    "native_handicap_line",
    "line_residual_mu",
    "line_residual_z",
    "market_uncertainty",
    "market_signature_breadth",
    "market_signature_dispersion",
    "history_training_rows_log1p",
    "min_history_n_log1p",
    "league_index",
    "home_team_index",
    "away_team_index",
    "kickoff_delay_hours",
    "match_position_fraction",
)

MARKET_BASELINE_FEATURE: Final = "calibrated_market_probability"
FALLBACK_RULE: Final = {
    "rule_id": "BJ204_MARKET_OR_NO_BET_V1",
    "market_vector": MARKET_BASELINE_FEATURE,
    "acceptance": "all three finite unmasked values sum to one within 2e-6",
    "on_acceptance": "emit the frozen market vector byte-for-byte after float32 load",
    "on_rejection": "emit explicit NO_BET_FROZEN; never emit a learned vector",
    "fallback_metric_reporting": "report pure baseline, model-only and fallback-mixed separately",
}

MODEL_FAMILIES: Final = (
    {
        "id": "MARKET_ONLY",
        "implementation": "frozen calibrated_market_probability",
        "role": "incumbent and exact safe fallback",
    },
    {
        "id": "LOGISTIC_RESIDUAL",
        "implementation": "sklearn.linear_model.LogisticRegression",
        "role": "complexity-matched multinomial residual control",
    },
    {
        "id": "HIST_GRADIENT_RESIDUAL",
        "implementation": "sklearn.ensemble.HistGradientBoostingClassifier",
        "role": "shallow nonlinear residual control",
    },
    {
        "id": "SET_ENCODER_RESIDUAL",
        "implementation": "PyTorch Deep Sets / Set Transformer only after controls",
        "role": "candidate issue-context residual; not trained in Gate A",
    },
)

METRICS: Final = (
    "multiclass_log_loss",
    "brier_score",
    "ece_equal_mass",
    "top1_coverage",
    "top2_coverage",
    "predicted_sp_mae",
    "fallback_coverage",
    "ood_coverage",
)
