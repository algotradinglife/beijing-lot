"""Frozen research contract for BJ-UNIFIED-NEURAL-TOP2-RESIDUAL-001."""

from __future__ import annotations

OUTCOMES = ("3", "1", "0")
N_LEGS = 7
DISTINCT_TICKETS = 2**N_LEGS
FUNDED_UNITS = 512
STAKE_PER_UNIT = 2.0
ISSUE_STAKE_CNY = FUNDED_UNITS * STAKE_PER_UNIT
PAYOUT_FACTOR = 0.65
STARTING_CAPITAL_CNY = 100_000.0

TRAIN_YEARS = (2020, 2021, 2022)
DEVELOPMENT_YEAR = 2023
TERMINAL_YEAR = 2024
ALL_YEARS = (*TRAIN_YEARS, DEVELOPMENT_YEAR, TERMINAL_YEAR)

MODEL_SEEDS = (33401, 33402, 33403, 33404, 33405)
BOOTSTRAP_SEEDS = tuple(range(334100, 335100))

MLP_CONFIGS = (
    {"name": "MLP16_A001", "hidden_layer_sizes": (16,), "alpha": 0.001},
    {"name": "MLP32_A010", "hidden_layer_sizes": (32,), "alpha": 0.01},
    {"name": "MLP32X16_A010", "hidden_layer_sizes": (32, 16), "alpha": 0.01},
)

PRIMARY_ARMS = ("S0O0", "S1O0", "S0O1", "S1O1")
CONTROL_ARMS = ("LINEAR_S1O0", "LINEAR_S0O1", "LINEAR_S1O1", "SHUFFLED_S1O1")

FEATURE_COLUMNS = (
    "q_eu",
    "q_line",
    "divergence",
    "abs_divergence",
    "native_handicap_line",
    "n_available_books",
    "mapping_accepted",
    "issue_matches",
    "issue_books_mean",
    "issue_line_abs_mean",
    "issue_entropy_mean",
    "issue_divergence_abs_mean",
    "outcome_3",
    "outcome_1",
    "outcome_0",
)

FORBIDDEN_FEATURE_TOKENS = (
    "result",
    "winning_sp",
    "settlement",
    "gross",
    "pnl",
    "target",
    "label",
    "issue_year",
)
