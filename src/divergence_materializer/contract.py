"""Frozen scientific contract for Issue #238 v4."""

from __future__ import annotations

OUTCOMES = ("3", "1", "0")
HORIZONS = ("initial", "10h", "1h")
CONTRACT_VERSION = "BJ-UNIFIED-DIVERGENCE-MATERIALIZER-001/v4"
CAUSAL_GRADE = "RETROSPECTIVE_RELATIVE_PROXY"
MODEL_VERSION = "BJ238_LINE_TRANSLATOR_LOGIT_V1"

FIT_END = "2021-12-31 23:59:59"
TUNE_YEAR = 2022
CALIBRATION_YEAR = 2023
SEALED_START_YEAR = 2024

CONTROL_FEATURES = ("native_handicap_line",)
EXPERIMENTAL_FEATURES = (
    "native_handicap_line",
    "q_eu_3",
    "q_eu_1",
    "q_eu_0",
    "line_x_q_eu_3",
    "line_x_q_eu_1",
    "line_x_q_eu_0",
)

PROBABILITY_TOLERANCE = 1e-10
BOOTSTRAP_SEED = 2_382_026
BOOTSTRAP_DRAWS = 2_000
