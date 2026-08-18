"""Outcome-unexposed Track-A contract for Issue #204.

The contract is ordered by BJ issue identity, rather than calendar year.  That
is material here: 25043--25125 and 26011--26049 are the one-shot retrospective
window, while 26051+ remains reserved for #210.  This module intentionally has
no label-loading helper; official final-SP is a Gate-B-only target.
"""

from __future__ import annotations

from typing import Final


CONTRACT_VERSION: Final = "bj204-market-anchored-model-gate-a-v5"
UPSTREAM_CONTRACT_VERSION: Final = "bj203-causal-tensor-v2"
SOURCE_PACKAGE: Final = "results/bj203_causal_tensor_v2"

# The prior year-based wording incorrectly treated early 2025 development
# issues as embargoed and omitted the 75-issue retrospective archive.
DEVELOPMENT_ISSUE_MAX: Final = 25042
RETROSPECTIVE_TEST_RANGES: Final = ((25043, 25125), (26011, 26049))
RESERVE_ISSUE_MIN: Final = 26051
CV_VALIDATION_YEARS: Final = (2021, 2022, 2023)
SEEDS: Final = (204001, 204002, 204003)
OUTCOME_ORDER: Final = ("3", "1", "0")

# One common, outcome-unexposed M×3 interface is materialized for development
# and the locked test period.  Development uses a p_close market proxy after
# the official identity bridge; test uses normalized average-EU.  Source-grade
# indicators and explicit masks make that source transition observable instead
# of pretending that the two sources are byte-identical.
MODEL_FEATURES: Final = (
    "market_probability",
    "native_handicap_line",
    "source_is_pclose",
    "source_is_average_eu",
    "market_proxy_complete",
    "predicted_final_sp_input",
)

# ``predicted_final_sp`` is an outcome-unexposed input proxy.  It is never the
# supervised SP target.  The actual target is official final SP (3/1/0) and is
# unavailable to Gate A behind this target-only quality mask.
SP_TARGET: Final = {
    "target_id": "OFFICIAL_FINAL_SP_3_1_0",
    "field": "final_sp",
    "outcome_axis": list(OUTCOME_ORDER),
    "quality_mask": "TARGET_ONLY_OFFICIAL_3SP_NOT_OPENED_GATE_A",
    "availability": "Gate-B only; no target values or target masks are loaded in Gate A",
}

PROXY_GRADE: Final = "RETROSPECTIVE_PROXY"

MARKET_BASELINE_FEATURE: Final = "market_probability"
FALLBACK_RULE: Final = {
    "rule_id": "BJ204_MARKET_OR_NO_BET_V1",
    "market_vector": MARKET_BASELINE_FEATURE,
    "acceptance": "all three finite, strictly positive unmasked values sum to one within 2e-6",
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
