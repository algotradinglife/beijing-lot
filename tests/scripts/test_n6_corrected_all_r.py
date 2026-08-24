from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import json

from src.n6_corrected_all_r.contract import R_VALUES, RESULT_PACKAGE


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / RESULT_PACKAGE


def test_complete_exact_common_r_surface() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    keys = bundles.groupby("issue", observed=True)["r"].agg(lambda values: set(values))
    assert keys.map(lambda values: values == set(R_VALUES)).all()


def test_r0_r3_exactly_reproduce_376() -> None:
    parity = pd.read_parquet(PACKAGE / "r0_r3_parity.parquet")
    assert len(parity) == 304
    assert (parity["exact_pnl"] & parity["exact_support"]).all()


def test_ticket_and_pnl_economics() -> None:
    tickets = pd.read_parquet(PACKAGE / "tickets.parquet")
    groups = tickets.groupby(["issue", "r"], observed=True)
    assert groups.size().eq(64).all()
    assert groups["units"].sum().eq(512).all()
    assert np.isclose(groups["stake_cny"].sum(), 1024.0, rtol=0, atol=1e-12).all()
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    assert np.allclose(bundles["pnl_cny"], bundles["gross_cny"] - 1024.0, rtol=0, atol=1e-9)


def test_two_tail_sensitivities_are_distinct_fields() -> None:
    contrasts = pd.read_csv(PACKAGE / "matched_contrasts.csv")
    assert "armwise_ex_largest_lift_cny" in contrasts
    assert "lift_ex_largest_absolute_paired_delta_cny" in contrasts


def test_ticket_level_once_payout_recomputes_from_attribution() -> None:
    bundles = pd.read_parquet(PACKAGE / "issue_bundles.parquet")
    attribution = pd.read_parquet(PACKAGE / "support_attribution.parquet")
    for row in bundles.itertuples():
        legs = attribution[(attribution["issue"].eq(row.issue)) & (attribution["r"].eq(row.r))]
        assert len(legs) == 6
        expected = (
            16.0 * 0.65 * float(legs["winning_sp"].prod())
            if legs["realized_in_support"].all()
            else 0.0
        )
        assert np.isclose(row.gross_cny, expected, rtol=0, atol=1e-9)


def test_r5_r6_are_set_saturated_not_distinct_claims() -> None:
    decisions = pd.read_parquet(PACKAGE / "decisions.parquet")
    wide = decisions[decisions["r"].isin([5, 6])].pivot(
        index="issue", columns="r", values="support_json"
    )
    assert wide[5].eq(wide[6]).all()


def test_decision_does_not_reselect_or_admit() -> None:
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["positive_standalone_point_estimate_r"] == []
    assert decision["expert_admitted_r"] == []
    assert decision["fixed_r3_replaced"] is False


def test_shared_cutoff_mapping_is_exactly_rebound() -> None:
    receipt = json.loads((PACKAGE / "source_receipt.json").read_text(encoding="utf-8"))
    assert receipt["cutoff_contract"] == "BJ-UNIFIED-CUTOFF-LEARNING-001/v2"
    assert receipt["cutoff_identity"] == "EVALUATION_YEAR_2022"
    assert receipt["cutoff_probability_parity_rows"] == 48_658
    assert receipt["cutoff_probability_parity_exact_rows"] == 48_658
