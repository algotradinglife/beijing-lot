from __future__ import annotations

import itertools
from pathlib import Path

import numpy as np
import pandas as pd

from src.cutoff_walkforward.contract import (
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
    POLICIES,
    STAKE_PER_TICKET_CNY,
    TICKETS,
)
from src.cutoff_walkforward.pipeline import (
    construct_downstream,
    synthetic_shift_diagnostic,
)


ROOT = Path(__file__).resolve().parents[2]


def _mapped() -> pd.DataFrame:
    rows = []
    for policy in POLICIES:
        for match_idx in range(1, 8):
            rows.append(
                {
                    "policy": policy,
                    "issue_code": "2023001",
                    "issue_year": 2023,
                    "match_idx": match_idx,
                    "fixture_decision_ts": pd.Timestamp("2023-01-01T02:00:00Z"),
                    "q_effective_3": 0.60,
                    "q_effective_1": 0.30,
                    "q_effective_0": 0.10,
                }
            )
    return pd.DataFrame(rows)


def _settlement() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issue": ["2023001"] * 7,
            "issue_year": [2023] * 7,
            "match_idx": range(1, 8),
            "result_code": ["3"] * 7,
            "winning_sp": [2.0] * 7,
            "settlement_available": [True] * 7,
        }
    )


def test_n6_top2_cartesian_budget_and_payout_once() -> None:
    result = construct_downstream(_mapped(), _settlement())
    tickets = result["tickets"]
    bundles = result["bundles"]
    assert tickets.groupby(["issue", "policy"]).size().eq(TICKETS).all()
    assert (
        tickets.groupby(["issue", "policy"])["stake_cny"]
        .sum()
        .eq(ISSUE_STAKE_CNY)
        .all()
    )
    expected_codes = {
        "|".join(
            f"{match_idx}:{('3', '1')[choice]}"
            for match_idx, choice in zip(range(1, 7), choices, strict=True)
        )
        for choices in itertools.product((0, 1), repeat=6)
    }
    assert (
        set(tickets[tickets["policy"].eq(POLICIES[0])]["ticket_code"]) == expected_codes
    )
    expected_gross = STAKE_PER_TICKET_CNY * PAYOUT_FACTOR * 2.0**6
    assert np.allclose(bundles["gross_cny"], expected_gross, rtol=0, atol=1e-12)


def test_missing_settlement_fails_closed() -> None:
    settlement = _settlement()
    settlement["settlement_available"] = settlement["settlement_available"].astype(
        object
    )
    settlement.loc[0, "winning_sp"] = np.nan
    settlement.loc[0, "settlement_available"] = np.nan
    result = construct_downstream(_mapped(), settlement)
    bundles = result["bundles"]
    assert not bundles["settlement_complete"].any()
    assert bundles["pnl_cny"].isna().all()
    coverage = result["settlement_coverage"]
    assert coverage["incomplete_selected_matches"].eq(1).all()
    assert coverage["inclusion_status"].eq("EXCLUDED_SELECTED_FIXTURE_UNTRUSTED").all()


def test_synthetic_shift_is_bounded_and_recent_adapts() -> None:
    result = synthetic_shift_diagnostic(ROOT)
    paths = result["synthetic_paths"]
    assert paths["estimate"].between(0, 1).all()
    summary = result["synthetic_summary"].set_index("policy")
    assert (
        summary.loc["RECENT_STATE_BLEND", "final_estimate"]
        > summary.loc["EXPANDING_EQUAL", "final_estimate"]
    )
