"""Frozen experiment contract for Issue #359."""

CONTRACT_ID = "BJ-UNIFIED-LOWN-EU-VALUE-SELECTOR-001/v1"
ISSUE_NUMBER = 359
N_VALUES = (3, 4, 5)
OUTCOMES = ("3", "1", "0")
DEVELOPMENT_YEARS = (2019, 2020, 2021)
TRANSFER_YEARS = (2022, 2023, 2024)

ARMS = tuple(
    f"C{coverage}V{value}G{gap}"
    for coverage in (0, 1)
    for value in (0, 1)
    for gap in (0, 1)
)
BASELINE_ARM = "C0V0G0"
COVERAGE_DIAGNOSTIC_ARM = "C1V0G0"

ISSUE_STAKE_CNY = 1_024.0
STARTING_CAPITAL_CNY = 100_000.0
PAYOUT_FACTOR = 0.65
STAKE_UNIT_CNY = 2.0
FUNDED_UNITS = 512
BOOTSTRAP_DRAWS = 5_000
BOOTSTRAP_SEED = 359_2026

# Small preregistered development grid.  Value uses absolute, economically
# interpretable levels; coverage and gap use strictly-development quantiles.
COVERAGE_QUANTILES = (0.0, 0.10, 0.20)
VALUE_LEG_FLOORS = (0.90, 0.95, 1.00)
GAP_QUANTILES = (0.0, 0.10, 0.25)
MIN_DEVELOPMENT_BET_COVERAGE = 0.60
COMPLETE_TICKET_RETURN_FLOOR = 1.0

VALUE_CELLS_RELATIVE = "results/low_n_eu_value_data/cells/eu_value_cells.parquet"
VALUE_FREEZE_RELATIVE = "results/low_n_eu_value_data/FREEZE_RECEIPT.json"
VALUE_SOURCE_RELATIVE = "results/low_n_eu_value_data/SOURCE_RECEIPT.json"
SCORE_SURFACE_RELATIVE = "results/low_n_match_selector/score_surface.parquet"
S0_BUNDLES_RELATIVE = "results/low_n_match_selector/preoutcome_bundles.parquet"
S0_FREEZE_RELATIVE = "results/low_n_match_selector/freeze_receipt.json"
LABEL_RELATIVE = "results/low_n_selector_data/labels/selector_labels.parquet"
SETTLEMENT_RELATIVE = "derived/beidan_xlsm/beidan_xlsm.sqlite"
