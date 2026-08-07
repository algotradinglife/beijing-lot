"""Outcome-unexposed Track-A contract for Issue #204.

The contract is ordered by BJ issue identity, rather than calendar year.  That
is material here: 25043--25125 and 26011--26049 are the one-shot retrospective
window, while 26051+ remains reserved for #210.  This module intentionally has
no label-loading helper; official final-SP is a Gate-B-only target.
"""

from __future__ import annotations

from typing import Final


CONTRACT_VERSION: Final = "bj204-market-anchored-model-gate-a-v2"
UPSTREAM_CONTRACT_VERSION: Final = "bj203-causal-tensor-v2"
SOURCE_PACKAGE: Final = "results/bj203_causal_tensor_v2"

# The prior year-based wording incorrectly treated early 2025 development
# issues as embargoed and omitted the 75-issue retrospective archive.
DEVELOPMENT_ISSUE_MAX: Final = 25042
RETROSPECTIVE_TEST_RANGES: Final = ((25043, 25125), (26011, 26049))
RESERVE_ISSUE_MIN: Final = 26051
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

# ``predicted_final_sp`` is an outcome-unexposed input proxy.  It is never the
# supervised SP target.  The actual target is official final SP (3/1/0) and is
# unavailable to Gate A behind this target-only quality mask.
SP_TARGET: Final = {
    "target_id": "OFFICIAL_FINAL_SP_3_1_0",
    "field": "final_sp",
    "outcome_axis": ["3", "1", "0"],
    "quality_mask": "TARGET_ONLY_OFFICIAL_3SP_NOT_OPENED_GATE_A",
    "availability": "Gate-B only; no target values or target masks are loaded in Gate A",
}

PROXY_GRADE: Final = "RETROSPECTIVE_PROXY"

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
