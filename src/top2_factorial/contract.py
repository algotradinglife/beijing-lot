"""Frozen constants for BJ-UNIFIED-TOP2-FACTORIAL-001/v1."""

from __future__ import annotations

N_LEGS = 7
OUTCOME_ORDER = ("3", "1", "0")
HORIZONS = ("10h", "initial", "1h")
PRIMARY_HORIZON = "10h"
FIT_YEARS = tuple(range(2014, 2022))
TUNE_YEAR = 2022
EVAL_YEARS = (2023, 2024)
STAKE_UNIT = 2.0
FUNDED_UNITS = 128
ISSUE_STAKE = STAKE_UNIT * FUNDED_UNITS
PAYOUT_FACTOR = 0.65
STARTING_CAPITAL = 100_000.0
MAX_COMPRESSED_LEGS = 2
MODEL_SEED = 324
BOOTSTRAP_DRAWS = 2_000
BOOTSTRAP_BLOCK = 5
CELLS = tuple(f"S{s}O{o}A{a}" for s in (0, 1) for o in (0, 1) for a in (0, 1))
FEATURE_COLUMNS = (
    "q3", "q1", "q0", "line_q3", "line_q1", "line_q0",
    "div3", "div1", "div0", "retained_mass", "entropy", "q_gap",
    "native_handicap_line", "abs_handicap_line", "n_available_books",
    "issue_retained_mean", "issue_retained_std", "issue_div_abs_mean",
    "retained_pct_rank",
)
HYPERPARAMETERS = (
    {"max_leaf_nodes": 7, "l2_regularization": 1.0},
    {"max_leaf_nodes": 15, "l2_regularization": 1.0},
    {"max_leaf_nodes": 15, "l2_regularization": 5.0},
)
TERMINAL_DECISIONS = (
    "NO_INCREMENT", "COMPONENT_SIGNAL", "INTERACTION_SIGNAL", "CANDIDATE_SIGNAL",
)
