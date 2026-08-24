"""Frozen contract for Issue #355."""

CONTRACT_ID = "BJ-UNIFIED-LOWN-MATCH-SELECTOR-001/v1"
ISSUE_NUMBER = 355
N_VALUES = (3, 4, 5)
OUTCOMES = ("3", "1", "0")
DEVELOPMENT_YEARS = (2019, 2020, 2021)
TRANSFER_YEARS = (2022, 2023, 2024)
TRAIN_START_YEAR = 2017
TRAIN_CUTOFF_YEAR = 2021
ARMS = ("S0_RAW_MASS", "SELECTED_MODEL")
MODEL_FAMILIES = ("S0_RAW_MASS", "S1_CALIBRATED_MASS", "S2_LOGISTIC", "S3_HGB")
ISSUE_STAKE_CNY = 1_024.0
STARTING_CAPITAL_CNY = 100_000.0
PAYOUT_FACTOR = 0.65
STAKE_UNIT_CNY = 2.0
FUNDED_UNITS = 512
BOOTSTRAP_DRAWS = 5_000
BOOTSTRAP_SEED = 355_2026
RANDOM_STATE = 355_2026

FEATURE_RELATIVE = "results/low_n_selector_data/features/selector_features.parquet"
LABEL_RELATIVE = "results/low_n_selector_data/labels/selector_labels.parquet"
UPSTREAM_FREEZE_RELATIVE = "results/low_n_selector_data/FREEZE_RECEIPT.json"
SETTLEMENT_RELATIVE = "derived/beidan_xlsm/beidan_xlsm.sqlite"

NUMERIC_FEATURES = (
    "retained_mass",
    "p_min",
    "top1_probability",
    "top2_probability",
    "top1_top2_gap",
    "top2_top3_gap",
    "probability_entropy",
    "probability_hhi",
    "native_handicap_line",
    "abs_native_handicap_line",
    "n_available_books",
    "divergence_l1",
    "divergence_max_abs",
    "divergence_omitted",
    "divergence_top2_mean_abs",
    "q_candidate_3",
    "q_candidate_1",
    "q_candidate_0",
    "q_raw_eu_3",
    "q_raw_eu_1",
    "q_raw_eu_0",
    "q_line_3",
    "q_line_1",
    "q_line_0",
    "divergence_3",
    "divergence_1",
    "divergence_0",
    "prior_global_hit_rate",
    "prior_global_residual",
    "prior_mass_bin_hit_rate",
    "prior_mass_bin_residual",
    "prior_line_hit_rate",
    "prior_line_residual",
    "prior_omitted_hit_rate",
    "prior_omitted_residual",
    "retained_mass_percentile",
    "divergence_abs_percentile",
    "books_percentile",
    "issue_retained_mean",
    "issue_retained_std",
    "issue_retained_min",
    "issue_retained_max",
    "retained_gap_to_n3_cutoff",
    "retained_gap_to_n4_cutoff",
    "retained_gap_to_n5_cutoff",
)

CATEGORICAL_FEATURES = (
    "omitted_outcome",
    "causal_grade",
    "handicap_norm_source",
    "issue_date_source",
)
