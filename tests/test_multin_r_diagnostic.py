from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.multin_r_diagnostic.contract import PERIODS, TARGET_N_VALUES
from src.multin_r_diagnostic.pipeline import (
    _verify_settlement_economics,
    annual_matrix,
    common_settled_bundles,
    diagnostic_spec,
    replacement_signal_diagnostic,
)
from src.multin_top2_r0.contract import ISSUE_STAKE_CNY, PAYOUT_FACTOR, STAKE_PER_UNIT_CNY, units_per_ticket


def _settled_frame() -> pd.DataFrame:
    rows = []
    for year in (2022, 2023, 2024):
        for issue_offset in (1, 2):
            issue = f"{str(year)[-2:]}{issue_offset:03d}"
            for n in TARGET_N_VALUES:
                for r in range(n + 1):
                    pnl = -100.0 + 10.0 * r + issue_offset
                    rows.append(
                        {
                            "stage": "RETROSPECTIVE_DIAGNOSTIC", "issue": issue,
                            "issue_year": year,
                            "issue_anchor_ts": pd.Timestamp(f"{year}-01-{issue_offset:02d}", tz="UTC"),
                            "n": n, "r": r, "arm": f"R{r}",
                            "settlement_status": "SETTLED", "stake_cny": ISSUE_STAKE_CNY,
                            "gross_cny": ISSUE_STAKE_CNY + pnl, "pnl_cny": pnl,
                            "hit": True,
                        }
                    )
    return pd.DataFrame(rows)


def test_spec_has_full_target_grid_and_no_other_bundles() -> None:
    spec = diagnostic_spec()
    assert spec[3] == (0, 1, 2, 3)
    assert spec[6] == tuple(range(7))
    assert spec[7] == () and spec[10] == ()


def test_matrix_has_complete_88_row_keyspace_and_roles() -> None:
    matrix, _ = annual_matrix(_settled_frame())
    assert len(matrix) == 88
    assert set(matrix["period"]) == set(PERIODS)
    assert matrix[matrix["r"].eq(0)][[
        "lift_vs_r0_cny", "armwise_ex_largest_lift_vs_r0_cny",
        "largest_abs_paired_delta_sensitivity_cny", "hit_rate_lift_vs_r0",
    ]].eq(0).all().all()
    assert set(matrix[matrix["period"].eq("2022")]["period_role"]) == {"DEVELOPMENT_DIAGNOSTIC"}
    assert set(matrix[matrix["period"].eq("ALL_2022_2024")]["period_role"]) == {"DESCRIPTIVE_ONLY"}


def test_common_settlement_fails_when_an_r_arm_is_missing() -> None:
    frame = _settled_frame()
    broken = frame[~((frame["n"].eq(3)) & (frame["r"].eq(3)) & (frame["issue_year"].eq(2022)))]
    with pytest.raises(AssertionError, match="missing R arm"):
        common_settled_bundles(broken)


def test_common_settlement_excludes_issue_from_every_arm() -> None:
    frame = _settled_frame()
    mask = (
        frame["n"].eq(4) & frame["r"].eq(2)
        & frame["issue_year"].eq(2023) & frame["issue"].eq("23001")
    )
    frame.loc[mask, "settlement_status"] = "UNTRUSTED_SELECTED_LEG"
    common, ledger = common_settled_bundles(frame)
    n4_2023 = common[common["n"].eq(4) & common["issue_year"].eq(2023)]
    assert set(n4_2023["issue"]) == {"23002"}
    assert n4_2023.groupby("r").size().eq(1).all()
    excluded = ledger[
        ledger["n"].eq(4) & ledger["issue_year"].eq(2023) & ledger["issue"].eq("23001")
    ]
    assert len(excluded) == 1 and not bool(excluded.iloc[0]["included"])


def test_ticket_level_once_payout_reconciliation_rejects_tamper() -> None:
    n, r, issue = 3, 0, "22001"
    winning_sp = np.asarray([2.0, 3.0, 4.0])
    gross = units_per_ticket(n) * STAKE_PER_UNIT_CNY * PAYOUT_FACTOR * float(winning_sp.prod())
    bundles = pd.DataFrame([{
        "issue": issue, "n": n, "r": r, "gross_cny": gross,
        "stake_cny": ISSUE_STAKE_CNY, "pnl_cny": gross - ISSUE_STAKE_CNY,
    }])
    attribution = pd.DataFrame({
        "issue": [issue] * n, "n": [n] * n, "r": [r] * n,
        "included": [True] * n, "winning_sp": winning_sp,
    })
    assert _verify_settlement_economics(bundles, attribution)
    bundles.loc[0, "gross_cny"] += 1
    assert not _verify_settlement_economics(bundles, attribution)


def test_per_leg_payout_factor_is_rejected() -> None:
    n, r, issue = 3, 0, "22001"
    winning_sp = np.asarray([2.0, 3.0, 4.0])
    wrong_gross = (
        units_per_ticket(n) * STAKE_PER_UNIT_CNY
        * (PAYOUT_FACTOR ** n) * float(winning_sp.prod())
    )
    bundles = pd.DataFrame([{
        "issue": issue, "n": n, "r": r, "gross_cny": wrong_gross,
        "stake_cny": ISSUE_STAKE_CNY, "pnl_cny": wrong_gross - ISSUE_STAKE_CNY,
    }])
    attribution = pd.DataFrame({
        "issue": [issue] * n, "n": [n] * n, "r": [r] * n,
        "included": [True] * n, "winning_sp": winning_sp,
    })
    assert not _verify_settlement_economics(bundles, attribution)


def test_replacement_signal_ignores_order_only_support_flip() -> None:
    bundles = _settled_frame()
    bundles = bundles[
        bundles["n"].eq(3) & bundles["r"].isin([0, 1])
    ].copy()
    rows = []
    for row in bundles.itertuples(index=False):
        for match_idx in range(1, 4):
            rows.append({
                "issue": row.issue, "issue_year": row.issue_year,
                "n": row.n, "r": row.r, "match_idx": match_idx,
                "baseline_support": "31", "qeu_support": "13",
                "support": "13" if row.r == 1 else "31",
                "result_code": "3", "included": True,
            })
    signal = replacement_signal_diagnostic(pd.DataFrame(rows), bundles)
    assert signal["qeu_set_applied_legs"].eq(0).all()
    assert signal["rescued_results"].eq(0).all()
    assert signal["displaced_winners"].eq(0).all()
