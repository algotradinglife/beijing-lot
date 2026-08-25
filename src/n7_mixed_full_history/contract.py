"""Frozen contract for BJ-UNIFIED-N7-MIXED-FULL-HISTORY-001/v1 (Issue #394)."""

CONTRACT_ID = "BJ-UNIFIED-N7-MIXED-FULL-HISTORY-001/v1"
ISSUE_NUMBER = 394

# Frozen at execution start (2026-08-25T07:50:00Z) before opening 2025-2026
# settlements.  All trusted settlement-availability timestamps must be strictly
# earlier than this cutoff.
EVIDENCE_QUERY_CUTOFF_TS = "2026-08-25T07:50:00Z"

# Core years preserve exact #392 EXPANDING_EQUAL semantics; 2025-2026 are
# extension-evidence-only years.
CORE_YEARS = (2022, 2023, 2024)
EXTENSION_YEARS = (2025, 2026)
ALL_YEARS = (*CORE_YEARS, *EXTENSION_YEARS)

POLICY = "EXPANDING_EQUAL"

OUTCOMES = ("3", "1", "0")
N_LEGS = 7

# Standalone reference arms are CNY1,024 per issue (same frozen semantics as
# #392/#366): R3 CONTROL 128 tickets x 4 CNY2 units; C1E3 216 tickets with
# residual allocation, 512 units; R0 CONTROL 128 tickets x 4 CNY2 units.
STAKE_PER_UNIT_CNY = 2.0
ISSUE_STAKE_CNY = 1_024.0
PAYOUT_FACTOR = 0.65
STARTING_CAPITAL_CNY = 100_000.0
FUNDED_UNITS = 512

PRIMARY_ARM = "R3_CONTROL"
SECONDARY_ARM = "C1E3_SECONDARY"
COMPARATOR_ARM = "R0_CONTROL"
MIXED_PORTFOLIO = "MIXED_50_50"
PRIMARY_TICKETS = 128
SECONDARY_TICKETS = 216

# Mixed 50/50 portfolio: total CNY1,024 per issue (NOT 2,048).
# CNY512 to R3 = 128 tickets x exactly 2 CNY2 units per ticket.
# CNY512 to C1E3 = 216 tickets, 1 CNY2 unit each + 1 extra unit on first 40
# tickets under the accepted deterministic, outcome-blind canonical residual
# order (= _ticket_units with 216 tickets / 256 funded units).
MIXED_TOTAL_CNY = 1_024.0
MIXED_R3_SHARE_CNY = 512.0
MIXED_C1E3_SHARE_CNY = 512.0
MIXED_R3_UNITS_PER_TICKET = 2
MIXED_C1E3_FUNDED_UNITS = 256  # 216 base + 40 extra
MIXED_C1E3_EXTRA_TICKETS = 40

# Ideal fractional 50% + 50% counterfactual: R3 512/128 = 4.0 CNY per ticket
# (2 CNY2 units -- already integer), C1E3 512/216 CNY per ticket (fractional
# units), to separate integer-unit effects from support/portfolio effects.
FRACTIONAL_R3_CNY_PER_TICKET = MIXED_R3_SHARE_CNY / PRIMARY_TICKETS
FRACTIONAL_C1E3_CNY_PER_TICKET = MIXED_C1E3_SHARE_CNY / SECONDARY_TICKETS

# Bootstrap
MOVING_BLOCK_LENGTH = 10
BOOTSTRAP_DRAWS = 5_000
BOOTSTRAP_SEED = 394_001

# Upstreams (accepted frozen artifacts)
UPSTREAM_MAPPING_PACKAGE = "results/cutoff_walkforward"          # #383 mapping surface
UPSTREAM_N7_PACKAGE = "results/n7_chronology_sync"               # #366 corrected N7 action receipts
UPSTREAM_N7_WALKFORWARD = "results/n7_cutoff_walkforward"        # #392 accepted EXPANDING_EQUAL evidence (parity)
UPSTREAM_SHAPE_PACKAGE = "results/n7_support_transfer_grid"      # #373 shape helpers source

# Result package and deliverables
RESULT_PACKAGE = "results/n7_mixed_full_history"
REPORT_PATH = "docs/research/Issue-394-N7-Mixed-Full-History.md"
NOTEBOOK_PATH = (
    "notebooks/research/n7-mixed-full-history/Issue-394-N7-Mixed-Full-History.ipynb"
)
FIGURE_PATH = "docs/research/figures/issue_394_n7_mixed_full_history.png"

ALLOWED_VERDICTS = (
    "MIXED_N7_EXTENSION_HISTORICAL_SIGNAL_NO_PROMOTION",
    "NO_MIXED_N7_EXTENSION_INCREMENT",
    "FAIL_CLOSED",
)