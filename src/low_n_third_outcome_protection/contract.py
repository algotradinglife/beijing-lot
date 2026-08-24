"""Frozen contract constants for Issue #356."""

CONTRACT_ID = "BJ-UNIFIED-LOWN-THIRD-OUTCOME-PROTECTION-001/v1"
ISSUE_NUMBER = 356

DEVELOPMENT_YEARS = (2019, 2020, 2021)
TRANSFER_YEARS = (2022, 2023, 2024)
OUTCOMES = ("3", "1", "0")

LANES = {
    "S0_N3": {"upstream_arm": "C0V0G0", "n": 3, "primary": True},
    "S0_N4": {"upstream_arm": "C0V0G0", "n": 4, "primary": True},
    "S0_N5": {"upstream_arm": "C0V0G0", "n": 5, "primary": True},
    "N3_VALUE": {"upstream_arm": "C0V1G0", "n": 3, "primary": False},
    "N4_COVERAGE_VALUE": {
        "upstream_arm": "C1V1G0",
        "n": 4,
        "primary": False,
    },
}

ISSUE_STAKE_CNY = 1_024.0
STAKE_UNIT_CNY = 2.0
FUNDED_UNITS = 512
PAYOUT_FACTOR = 0.65
STARTING_CAPITAL_CNY = 100_000.0
BOOTSTRAP_DRAWS = 5_000
BOOTSTRAP_SEED = 356_2026

UPSTREAM_PREOUTCOME = "results/low_n_eu_value_selector/preoutcome.parquet"
UPSTREAM_SELECTIONS = "results/low_n_eu_value_selector/selections.parquet"
UPSTREAM_TICKETS = "results/low_n_eu_value_selector/tickets.parquet"
UPSTREAM_DECISIONS = "results/low_n_eu_value_selector/decisions.parquet"
UPSTREAM_FREEZE = "results/low_n_eu_value_selector/freeze_receipt.json"
UPSTREAM_SOURCE = "results/low_n_eu_value_selector/source_receipt.json"
UPSTREAM_MANIFEST = "results/low_n_eu_value_selector/MANIFEST.json"
SCORE_SURFACE = "results/low_n_match_selector/score_surface.parquet"
VALUE_CELLS = "results/low_n_eu_value_data/cells/eu_value_cells.parquet"
S0_BUNDLES = "results/low_n_match_selector/preoutcome_bundles.parquet"
