from __future__ import annotations

from pathlib import Path
import copy

import numpy as np
import pandas as pd
import pytest

from src.n7_cutoff_walkforward.contract import (
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    PAYOUT_FACTOR,
    POLICIES,
    PRIMARY_ARM,
    PRIMARY_TICKETS,
    SECONDARY_ARM,
    SECONDARY_TICKETS,
    STAKE_PER_UNIT_CNY,
)
from src.n7_cutoff_walkforward.pipeline import (
    ContractError,
    PACKAGE_FILES,
    _read,
    _circular_block_indices,
    _verify_semantics,
    construct_downstream,
)


ROOT = Path(__file__).resolve().parents[1]


def _mapped() -> pd.DataFrame:
    rows = []
    for policy_index, policy in enumerate(POLICIES):
        for match_idx in range(1, 9):
            offset = 0.002 * policy_index * ((match_idx % 3) - 1)
            q3 = 0.58 + 0.005 * match_idx + offset
            q1 = 0.27 - 0.002 * match_idx
            q0 = 1.0 - q3 - q1
            line = (0.40, 0.30, 0.30)
            rows.append(
                {
                    "issue_code": "23001",
                    "issue_year": 2023,
                    "match_idx": match_idx,
                    "fixture_decision_ts": pd.Timestamp("2023-01-01T10:00:00Z")
                    + pd.Timedelta(minutes=match_idx),
                    "policy": policy,
                    "q_effective_3": q3,
                    "q_effective_1": q1,
                    "q_effective_0": q0,
                    "q_line_3": line[0],
                    "q_line_1": line[1],
                    "q_line_0": line[2],
                }
            )
    return pd.DataFrame(rows)


def _settlement() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issue": ["23001"] * 8,
            "issue_year": [2023] * 8,
            "issue_anchor_ts": [pd.Timestamp("2023-01-01T10:01:00Z")] * 8,
            "match_idx": range(1, 9),
            "fixture_decision_ts": [
                pd.Timestamp("2023-01-01T10:00:00Z")
                + pd.Timedelta(minutes=value)
                for value in range(1, 9)
            ],
            "result_code": ["3"] * 8,
            "winning_sp": [2.0] * 8,
            "settlement_available": [True] * 8,
            "settlement_quality": ["trusted"] * 8,
        }
    )


def test_complete_ticket_spaces_and_fixed_budget() -> None:
    result = construct_downstream(_mapped(), _settlement())
    tickets = result["tickets"]
    for arm, expected in ((PRIMARY_ARM, PRIMARY_TICKETS), (SECONDARY_ARM, SECONDARY_TICKETS)):
        group = tickets[tickets["support_arm"].eq(arm)]
        assert group.groupby(["issue", "policy"]).size().eq(expected).all()
        assert group.groupby(["issue", "policy"])["units"].sum().eq(FUNDED_UNITS).all()
        assert group.groupby(["issue", "policy"])["stake_cny"].sum().eq(ISSUE_STAKE_CNY).all()
        assert not group.duplicated(["issue", "policy", "ticket_identity"]).any()


def test_ticket_level_once_payout_reconciles() -> None:
    result = construct_downstream(_mapped(), _settlement())
    bundles = result["bundles"]
    tickets = result["tickets"]
    attribution = result["attribution"]
    for row in bundles.itertuples():
        legs = attribution[
            attribution["policy"].eq(row.policy)
            & attribution["support_arm"].eq(row.support_arm)
        ].sort_values("match_idx")
        code = "|".join(legs["result_code"])
        winner = tickets[
            tickets["policy"].eq(row.policy)
            & tickets["support_arm"].eq(row.support_arm)
            & tickets["ticket_code"].eq(code)
        ]
        units = int(winner["units"].iloc[0]) if len(winner) else 0
        expected = units * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * 2.0**7
        assert np.isclose(row.gross_cny, expected, rtol=0, atol=1e-12)
        assert np.isclose(row.pnl_cny, expected - ISSUE_STAKE_CNY, rtol=0, atol=1e-12)


def test_missing_selected_settlement_fails_closed() -> None:
    settlement = _settlement()
    settlement.loc[settlement["match_idx"].eq(8), "settlement_available"] = False
    result = construct_downstream(_mapped(), settlement)
    bundles = result["bundles"]
    assert not bundles["settlement_complete"].any()
    assert bundles["pnl_cny"].isna().all()
    assert not bundles["arm_exact_common"].any()
    assert result["coverage"]["inclusion_status"].eq(
        "EXCLUDED_SELECTED_FIXTURE_UNTRUSTED"
    ).all()


def test_moving_block_is_seeded_and_chronological() -> None:
    left = _circular_block_indices(23, 50, np.random.default_rng(392001))
    right = _circular_block_indices(23, 50, np.random.default_rng(392001))
    assert np.array_equal(left, right)
    assert left.shape == (50, 23)
    steps = (np.diff(left, axis=1) % 23)[:, :9]
    assert np.all(steps == 1)


def _stored() -> dict[str, object]:
    package = ROOT / "results/n7_cutoff_walkforward"
    return {key: _read(package / name) for name, key in PACKAGE_FILES.items()}


def test_admitted_history_cache_tamper_fails_closed() -> None:
    stored = _stored()
    stored["receipts"] = copy.deepcopy(stored["receipts"])
    stored["receipts"][0]["n7_cache_identity"] = "0" * 64
    with pytest.raises(ContractError, match="cache binding"):
        _verify_semantics(stored)


def test_ticket_budget_tamper_fails_closed() -> None:
    stored = _stored()
    stored["tickets"] = stored["tickets"].copy()
    stored["tickets"].loc[0, "units"] += 1
    with pytest.raises(ContractError, match="512"):
        _verify_semantics(stored)


def test_settlement_gross_tamper_fails_closed() -> None:
    stored = _stored()
    stored["bundles"] = stored["bundles"].copy()
    index = stored["bundles"].index[stored["bundles"]["settlement_complete"]][0]
    stored["bundles"].loc[index, "gross_cny"] += 1.0
    stored["bundles"].loc[index, "pnl_cny"] += 1.0
    with pytest.raises(ContractError, match="payout reconciliation"):
        _verify_semantics(stored)


def test_decision_keyset_deletion_fails_closed() -> None:
    stored = _stored()
    stored["decisions"] = stored["decisions"].iloc[1:].copy()
    with pytest.raises(ContractError, match="decision key set"):
        _verify_semantics(stored)
