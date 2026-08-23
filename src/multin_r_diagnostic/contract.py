"""Frozen contract for Issue #352 retrospective diagnostics."""

from __future__ import annotations

from pathlib import Path

CONTRACT_ID = "BJ-UNIFIED-MULTIN-R-DIAGNOSTIC-001/v1"
ISSUE_NUMBER = 352
PARENT_ISSUE = 202
TARGET_N_VALUES = tuple(range(3, 7))
YEARS = (2022, 2023, 2024)
PERIODS = ("2022", "2023", "2024", "ALL_2022_2024")
PERIOD_ROLES = {
    "2022": "DEVELOPMENT_DIAGNOSTIC",
    "2023": "EXPOSED_HISTORICAL_EVALUATION",
    "2024": "EXPOSED_HISTORICAL_EVALUATION",
    "ALL_2022_2024": "DESCRIPTIVE_ONLY",
}
STARTING_CAPITAL_CNY = 100_000.0

FROZEN_349_RECEIPT = Path("results/multin_fixed_rn/freeze_receipt.json")
FROZEN_349_RECEIPT_SHA256 = "7e771b86896d051a205582150eb333434722105433cda5d79c79a1903a9aea41"
FROZEN_349_SELECTED_R = {
    "3": 0, "4": 0, "5": 0, "6": 0, "7": 3, "8": 0, "9": 1, "10": 0,
}

OUTPUT_RELATIVE = Path("results/multin_r_diagnostic")
REPORT_RELATIVE = Path("docs/research/Issue-352-MultiN-R-Annual-Diagnostic.md")
NOTEBOOK_RELATIVE = Path(
    "notebooks/research/multin-r-diagnostic/multin_r_diagnostic.ipynb"
)
FIGURE_LIFT_RELATIVE = Path(
    "docs/research/figures/issue_352_multin_r_annual_lift.png"
)
FIGURE_RISK_RELATIVE = Path(
    "docs/research/figures/issue_352_multin_r_annual_risk.png"
)
