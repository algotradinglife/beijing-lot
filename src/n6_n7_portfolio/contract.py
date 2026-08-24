"""Frozen constants for BJ-UNIFIED-N6-N7-PORTFOLIO-001/v2 (issue #378).

Consumes ONLY the frozen accepted surfaces:
- #381 results/n6_corrected_all_r (corrected N6 complete R0-R6 surface;
  R0/R3 are the canonical comparison arms and no R is standalone-positive)
- #377 results/n6_support_transfer_grid (corrected N6 grid; C0E0 == #381 R3 control)
- #373 results/n7_support_transfer_grid (corrected N7 R3 CONTROL C0E0; C1E2/C1E3
  are explicitly exposed mechanism hypotheses, never admitted experts)

Metric definitions mirror the frozen #381/#377/#373 protocol implementations
(path metrics, circular moving-block bootstrap, rolling windows, payout
concentration) so that every number quoted here is comparable to the accepted
grid packages.
"""

CONTRACT_ID = "BJ-UNIFIED-N6-N7-PORTFOLIO-001/v2"
ISSUE_NUMBER = 378
RESULT_PACKAGE = "results/n6_n7_portfolio"

UPSTREAM_N6_ALL_R = "results/n6_corrected_all_r"               # #381
UPSTREAM_N6_GRID = "results/n6_support_transfer_grid"          # #377
UPSTREAM_N7_GRID = "results/n7_support_transfer_grid"          # #373

EXPECTED_UPSTREAM_MANIFEST_SHA256 = {
    UPSTREAM_N6_ALL_R: "2fd3d3cdd05233145a0e65e4d39110ac094948fc7db46fe7f6ffdde338634eb1",
    UPSTREAM_N6_GRID: "ef7c6aab409d86b090ff76d5e12e18ac22d78b011223a01644fd931db8ec5930",
    UPSTREAM_N7_GRID: "61bbaa679a3081284b325c26ab26c40dfe8d149ceb27aa4b5c7129b44acc73a7",
}

YEARS = (2022, 2023, 2024)

# Frozen financial constants (from the three upstream contracts).
FUNDED_UNITS = 512
STAKE_PER_UNIT_CNY = 2.0
ISSUE_STAKE_CNY = 1_024.0          # normalized stake per active issue, CNY
PAYOUT_FACTOR = 0.65               # applied once per complete winning ticket
STARTING_CAPITAL_CNY = 100_000.0

# Preregistered portfolio (no tuning).
POOL_WEIGHT = 0.5                  # 50/50 capital weight per sleeve
SLEEVE_STAKE_CNY = 512.0           # CNY512 sleeve budget = 0.5 x CNY1,024
PARALLEL_SLEEVE_STAKE_CNY = 1_024.0  # transparent parallel-sleeve 1:1 scale diagnostic
TOTAL_ISSUE_STAKE_CNY = 1_024.0    # portfolio total per calendar issue
PARALLEL_TOTAL_ISSUE_STAKE_CNY = 2_048.0  # scale diagnostic total

# Chronology / bootstrap protocol (identical to upstream grids).
BOOTSTRAP_DRAWS = 5_000
BOOTSTRAP_SEED = 378_001           # portfolio diagnostics stream
BOOTSTRAP_SEED_ASYNC = 378_002     # async-contribution stream
MOVING_BLOCK_LENGTH = 10
ROLLING_WINDOWS = (20, 30, 50)

# Facing labels.
N6_ARM_R0 = "N6_R0"                # #381 corrected N6 R0 canonical (benchmark)
N6_ARM_R3 = "N6_R3"                # #381 corrected N6 R3 canonical control
N7_ARM_C0E0 = "N7_C0E0"            # #373 corrected N7 R3 CONTROL
N7_ARM_C1E2 = "N7_C1E2"            # #373 mechanism hypothesis (no admission)
N7_ARM_C1E3 = "N7_C1E3"            # #373 mechanism hypothesis (no admission)

POOL_PAIR = (N6_ARM_R3, N7_ARM_C0E0)  # the only pool-forming pair
MECHANISM_PAIRS = (
    (N6_ARM_R3, N7_ARM_C1E2),
    (N6_ARM_R3, N7_ARM_C1E3),
)

PATH_PORTFOLIO = "PORTFOLIO_50_50"      # preregistered 0.5/0.5 sleeves
PATH_N7_HALVED = "N7_HALVED"            # dilution counterfactual: 0.5 x N7 only
PATH_PARALLEL = "PARALLEL_1_1"          # scale diagnostic: both sleeves at CNY1,024
PATH_MECHANICAL = "MECHANICAL_WA"       # weighted-average identity, == portfolio by construction

# Expected issue counts (frozen upstream).
EXPECTED_N6_ISSUES = 152
EXPECTED_N7_ISSUES = 151
EXPECTED_COMMON_ISSUES = 151
# Single calendar exclusion: 23032 is settled/trusted on the N6 six-fixture
# surface but UNTRUSTED_SELECTED_LEG on the N7 seven-fixture surface.
EXPECTED_EXCLUSIVE_N6_ISSUES = {"23032"}

# Golden upstream risk values for metric-definition lock (ALL scope).
GOLDEN_N6_R3_RISK = {
    "max_drawdown_fraction": 0.4689267598841704,
    "longest_profitable_issue_losing_run": 19,
    "open_underwater_issues": 152,
    "largest_payout_share": 0.1721942744986267,
    "payout_hhi": 0.0675443997102184,
}
GOLDEN_N7_C0E0_RISK = {
    "max_drawdown_fraction": 0.3316501342795853,
    "longest_profitable_issue_losing_run": 19,
    "open_underwater_issues": 1,
    "largest_payout_share": 0.3253289469750434,
    "payout_hhi": 0.136820315421169,
}
GOLDEN_N6_R3_PNL = -12_299.98964156374
GOLDEN_N6_R0_PNL = -33_511.091628594215
GOLDEN_N7_C0E0_PNL = 32_689.126229573667
GOLDEN_N7_C1E2_PNL = 39_259.00009032017
GOLDEN_N7_C1E3_PNL = 32_797.518650308615
