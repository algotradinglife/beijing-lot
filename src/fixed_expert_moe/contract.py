"""Frozen scientific contract for Issue #332."""

from __future__ import annotations

from issue314.experts import EXPERTS

ISSUE = 332
CONTRACT_ID = "BJ-UNIFIED-FIXED-EXPERT-MOE-001/v1"
PAYOUT_FACTOR = 0.65
INITIAL_CAPITAL_CNY = 100_000.0
TOTAL_TICKETS = 512
TICKET_STAKE_CNY = 2.0
TOTAL_STAKE_CNY = TOTAL_TICKETS * TICKET_STAKE_CNY

MODEL_SEEDS = (31401, 31402, 31403, 31404, 31405)
EVALUATION_SEEDS = tuple(range(312101, 312112))
EVALUATION_YEARS = (2022, 2023, 2024)

# Exact integer reconciliation of 40%, 25%, 15%, 10%, 5%, 3%, 1.5%, 0.5%.
RANK_COUNTS = (205, 128, 77, 51, 26, 15, 8, 2)
SURFACE_COUNTS = tuple(sorted({64, 512, *RANK_COUNTS}))

EXPERT_NAMES = tuple(spec.name for spec in EXPERTS)
TARGET_COLUMNS = (
    "hit_rate",
    "within_one_rate",
    "within_two_rate",
    "positive_seed_fraction",
    "clipped_roi",
)

CURRENT_COLUMNS = (
    "n_matches",
    "books_mean",
    "line_abs_mean",
    "line_std",
    "market_top_mean",
    "market_top_q90",
    "entropy_mean",
    "divergence_abs_mean",
    "divergence_abs_q90",
    "divergence_signed_mean",
    "value_best_mean",
    "value_best_q90",
    "accepted_fraction",
)

STATE_STEMS = (
    "eu_brier",
    "line_brier",
    "eu_top2_residual",
    "line_top2_residual",
)
STATE_SUFFIXES = (
    "roll5_mean",
    "roll5_std",
    "roll5_count",
    "roll20_mean",
    "roll20_std",
    "roll20_count",
    "ewm5",
    "ewm20",
)
STATE_LAG_COLUMNS = tuple(
    f"lag_{stem}_{suffix}" for stem in STATE_STEMS for suffix in STATE_SUFFIXES
)

EXPERT_DESCRIPTOR_COLUMNS = (
    "expert_n",
    "expert_pool_excess",
    "expert_protected_leg_count",
    "expert_is_tail",
    "expert_is_wr",
    "expert_selector_global",
    "expert_selector_value",
    "expert_selector_divergence",
    "expert_selector_hybrid",
    "expert_direction_market",
    "expert_direction_value",
    "expert_direction_divergence",
)

EXPERT_LAG_METRICS = (
    "hit_rate",
    "within_one_rate",
    "within_two_rate",
    "positive_seed_fraction",
    "clipped_roi",
)
EXPERT_LAG_WINDOWS = (5, 20)

POLICIES = (
    "BEST_SINGLE_EXPERT",
    "EQUAL_MIX",
    "STATIC_SHRUNK_MIX",
    "CURRENT_ONLY_MOE",
    "LAGGED_MULTITASK_MOE",
    "LAGGED_HGB_MOE",
    "LAG_STATE_SHIFTED",
    "EXPERT_IDENTITY_SHUFFLED",
    "HARD_TOP1",
)

assert len(EXPERT_NAMES) == 8
assert sum(RANK_COUNTS) == TOTAL_TICKETS
