"""Frozen constants for BJ-UNIFIED-N6-CORRECTED-ALL-R-001/v1."""

CONTRACT_ID = "BJ-UNIFIED-N6-CORRECTED-ALL-R-001/v1"
ISSUE_NUMBER = 381
YEARS = (2022, 2023, 2024)
OUTCOMES = ("3", "1", "0")
N_LEGS = 6
R_GRID = tuple(range(7))  # exactly 0..6, no dynamic R
ARMS = tuple(f"R{r}" for r in R_GRID)  # R0..R6
TICKETS = 64  # complete 2^6 Cartesian per issue/arm
FUNDED_UNITS = 512
UNITS_PER_TICKET = 8
STAKE_PER_UNIT_CNY = 2.0
STAKE_PER_TICKET_CNY = 16.0
ISSUE_STAKE_CNY = 1_024.0
PAYOUT_FACTOR = 0.65  # applied exactly once per complete winning ticket
STARTING_CAPITAL_CNY = 100_000.0

BOOTSTRAP_DRAWS = 5_000
BOOTSTRAP_SEED = 381_001
MOVING_BLOCK_LENGTH = 10
ROLLING_WINDOWS = (20, 30, 50)

# Upstream / parity sources
CORRECTED_PACKAGE = "results/low_n_selector_data"  # corrected #360 chronology package
UPSTREAM_N6_PACKAGE = "results/n6_chronology_sync"  # corrected #376 canonical R0/R3
LEGACY_PACKAGE = "results/multin_r_diagnostic"  # legacy #352 descriptive matrix
LEGACY_MANIFEST_SHA256 = (
    "de1da07545fe8052fc07db2bceb9e662336f3cea475a04ff1104b3645164349c"
)
RESULT_PACKAGE = "results/n6_all_r_diagnostic"