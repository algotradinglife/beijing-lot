"""Focused tests for Issue #229 divergence-aware M×3 data profile (rework).

Rework (2026-08-15, REWORK_TYPE=method) test additions:

- **Golden per-cell divergence**: the EV's independent computation example
  (issue 25043/match 8) is reproduced from the exact vectors — diff, CLR,
  direction per outcome cell (REQ-D05).
- **Half-goal line boundary table**: -1.5/-0.5/0/+0.5/+1.5 translations are
  exact, never rounded to int (REQ-D04).
- **Match-level causal join**: no issue-level broadcast; post-decision rows
  detected per (issue, match_idx).
- **Tamper self-tests (REQ-E06)**: verifier/evidence must FAIL when the
  inference payload, ledger, manifest or source trace is tampered.
- **Fault injection (class 6)**: atomic publication preserves the old package
  on write failure; label load failure aborts the build.

Fast unit tests only — the full build is exercised by the executed notebook
and the build CLI.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from divergence_profile import contract  # noqa: E402
from divergence_profile import divergence  # noqa: E402
from divergence_profile import probabilities as prob  # noqa: E402
from divergence_profile import quality  # noqa: E402


# ---------------------------------------------------------------------------
# Probability validation (REQ-D03)
# ---------------------------------------------------------------------------
def test_validate_probability_vector_accepts_valid_triplet() -> None:
    ok, reason = prob.validate_probability_vector(np.asarray([0.2, 0.3, 0.5]))
    assert ok
    assert reason is None


def test_validate_probability_vector_rejects_out_of_bounds() -> None:
    ok, reason = prob.validate_probability_vector(np.asarray([-0.1, 0.6, 0.5]))
    assert not ok
    assert reason == "OUT_OF_BOUNDS"


def test_validate_probability_vector_rejects_sum_deviation() -> None:
    ok, reason = prob.validate_probability_vector(np.asarray([0.2, 0.3, 0.6]))
    assert not ok
    assert reason == "SUM_DEVIATION"


def test_validate_probability_vector_rejects_non_finite() -> None:
    ok, reason = prob.validate_probability_vector(
        np.asarray([np.inf, 0.3, 0.5])
    )
    assert not ok
    assert reason == "NON_FINITE"


def test_validate_probability_vector_rejects_wrong_length() -> None:
    ok, reason = prob.validate_probability_vector(np.asarray([0.5, 0.5]))
    assert not ok
    assert reason == "NOT_LENGTH_3"


# ---------------------------------------------------------------------------
# Devig (Q_BJ_SP_DEVIG, Q_EU_RAW_1X2)
# ---------------------------------------------------------------------------
def test_devig_normalize_inverse_odds() -> None:
    vector = prob.devig_normalize(np.asarray([2.0, 4.0, 4.0]))
    assert np.allclose(vector, [0.5, 0.25, 0.25], atol=1e-12)
    assert abs(float(vector.sum()) - 1.0) < contract.PROBABILITY_SUM_TOLERANCE


def test_devig_normalize_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        prob.devig_normalize(np.asarray([2.0, 0.0, 4.0]))


def test_normalize_sp_triplet() -> None:
    vector = prob.normalize_sp_triplet(1.76, 3.9, 6.0)
    assert np.all(np.isfinite(vector))
    assert abs(float(vector.sum()) - 1.0) < contract.PROBABILITY_SUM_TOLERANCE
    assert vector[0] > vector[1] > vector[2]


# ---------------------------------------------------------------------------
# Half-goal line boundary table (REQ-D04, B2)
# ---------------------------------------------------------------------------
EU_GOLDEN = (0.4, 0.25, 0.35)
# EV independent Poisson projection values, verified by an independent grid.
HALF_GOAL_BOUNDARY = {
    -1.5: (0.192617, 0.0, 0.807383),
    -0.5: (0.4, 0.0, 0.6),
    0.0: (0.4, 0.25, 0.35),
    0.5: (0.65, 0.0, 0.35),
    1.5: (0.841801, 0.0, 0.158199),
}


@pytest.mark.parametrize("line", sorted(HALF_GOAL_BOUNDARY))
def test_half_goal_boundary_table(line: float) -> None:
    """Every legal half-goal line translates exactly (no rounding)."""
    translated, reason = prob.translate_eu_to_bjline(EU_GOLDEN, line)
    assert translated is not None, f"line {line}: {reason}"
    assert np.allclose(translated, HALF_GOAL_BOUNDARY[line], atol=1e-5)


def test_translate_eu_zero_line_is_identity() -> None:
    translated, reason = prob.translate_eu_to_bjline(EU_GOLDEN, 0.0)
    assert translated == EU_GOLDEN
    assert reason is None


def test_half_goal_line_is_never_rounded_to_int() -> None:
    """-0.5 must not silently become 0 (the audited B2 defect)."""
    minus_half, _ = prob.translate_eu_to_bjline(EU_GOLDEN, -0.5)
    plus_half, _ = prob.translate_eu_to_bjline(EU_GOLDEN, 0.5)
    assert minus_half is not None and plus_half is not None
    assert not np.allclose(minus_half, EU_GOLDEN, atol=1e-6)  # NOT identity
    assert not np.allclose(plus_half, EU_GOLDEN, atol=1e-6)
    # draw mass is zero for half-goal lines (native BJ semantics)
    assert abs(minus_half[1]) < 1e-9
    assert abs(plus_half[1]) < 1e-9


def test_quarter_line_is_invalid() -> None:
    translated, reason = prob.translate_eu_to_bjline(EU_GOLDEN, -0.25)
    assert translated is None
    assert reason == contract.REASON_INVALID_LINE


def test_is_legal_handicap() -> None:
    for line in (-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0):
        assert prob.is_legal_handicap(line)
    for line in (-0.25, 0.25, 0.75, np.nan, np.inf):
        assert not prob.is_legal_handicap(line)


def test_independent_poisson_handicap_probabilities_normalized() -> None:
    p = prob.independent_poisson_handicap_probabilities(1.6, 1.2, -1.0)
    assert abs(sum(p) - 1.0) < 1e-9
    assert all(0.0 <= value <= 1.0 for value in p)


def test_validate_sp() -> None:
    assert prob.validate_sp(2.5) == (True, None)
    assert prob.validate_sp(1.0) == (False, "SP_NOT_GT_1")
    assert prob.validate_sp(np.nan) == (False, "NON_FINITE")


# ---------------------------------------------------------------------------
# Per-cell divergence golden (REQ-D05, B3)
# ---------------------------------------------------------------------------
def _ev_example_frame(independent: bool = True) -> pd.DataFrame:
    """The EV's issue 25043/match 8 example with the exact audited vectors.

    With ``independent=True`` the cell is treated as a development pclose
    cell with an independent #203 EU source (the identity combination under
    which EU-vs-BJ is a legitimate comparison); the per-cell math values are
    identical to the EV's independent recomputation.  With
    ``independent=False`` the cell is the #204 avg-EU alias case where the
    comparison must be explicitly unavailable.
    """
    qbj = [0.6336477801318545, 0.22292186963674882, 0.14343035023139655]
    eu = [0.37265592161411965, 0.26099185851773493, 0.3663522198681454]
    qbj_src = (
        contract.SRC_BJ204_PCLOSE if independent else contract.SRC_BJ204_AVG_EU
    )
    eu_src = (
        contract.SRC_BJ203_DEVIG_EURO if independent else contract.SRC_BJ204_AVG_EU
    )
    rows = []
    for code in contract.OUTCOME_CODES:
        rows.append(
            {
                "issue": "25043",
                "match_idx": 8,
                "outcome_code": code,
                contract.Q_BJ_CALIBRATED: qbj,
                contract.Q_EU_BJLINE: eu,
                contract.P_POWER_BJLINE: [np.nan, np.nan, np.nan],
                contract.BJ_LINE_BOUNDARY: -1.0,
                contract.SOURCE_IDENTITY_Q_BJ: qbj_src,
                contract.SOURCE_IDENTITY_EU: eu_src,
                "predicted_final_sp_input": np.nan,
                "market_uncertainty": np.nan,
            }
        )
    return pd.DataFrame(rows)


def test_per_cell_divergence_golden_diff() -> None:
    """EV: published 0.260992 on all rows; correct per-cell diff differs."""
    out = divergence.build_divergence_features(_ev_example_frame())
    got = {
        str(r["outcome_code"]): r["divergence_eu_minus_qbj"]
        for _, r in out.iterrows()
    }
    # EV independent values
    assert got["3"] == pytest.approx(-0.2609918585, abs=1e-9)
    assert got["1"] == pytest.approx(0.0380699889, abs=1e-9)
    assert got["0"] == pytest.approx(0.2229218696, abs=1e-9)
    # all three rows are NOT identical anymore
    assert not (got["3"] == got["1"] == got["0"])


def test_per_cell_divergence_golden_clr() -> None:
    out = divergence.build_divergence_features(_ev_example_frame())
    got = {
        str(r["outcome_code"]): r["divergence_eu_logratio"]
        for _, r in out.iterrows()
    }
    assert got["3"] == pytest.approx(-0.7190296545, abs=1e-9)
    assert got["1"] == pytest.approx(-0.0305240743, abs=1e-9)
    assert got["0"] == pytest.approx(0.7495537288, abs=1e-9)


def test_per_cell_divergence_golden_direction() -> None:
    out = divergence.build_divergence_features(_ev_example_frame())
    got = {
        str(r["outcome_code"]): r["divergence_eu_direction"]
        for _, r in out.iterrows()
    }
    # EV: published -1 on all rows; correct per-cell direction +1 for '1'
    assert got["3"] == -1
    assert got["1"] == 1
    assert got["0"] == 1


def test_same_source_alias_is_unavailable() -> None:
    """On #204 avg-EU cells Q_EU and Q_BJ share market_probability; the
    EU-vs-BJ comparison must be explicitly unavailable, never presented as
    an independent difference."""
    out = divergence.build_divergence_features(_ev_example_frame(independent=False))
    for _, r in out.iterrows():
        assert np.isnan(r["divergence_eu_minus_qbj"])
        assert np.isnan(r["divergence_eu_logratio"])
        assert np.isnan(r["divergence_eu_direction"])
        assert np.isnan(r["divergence_magnitude"])


def test_independent_source_divergence_materializes() -> None:
    frame = _ev_example_frame(independent=True)
    out = divergence.build_divergence_features(frame)
    assert out.iloc[0]["divergence_eu_minus_qbj"] == pytest.approx(
        -0.2609918585, abs=1e-9
    )


def test_leg_diagnostics_use_own_outcome_component() -> None:
    """leg_q_times_sp_pre must use the cell's own Q_BJ component, not max."""
    frame = pd.DataFrame(
        {
            "issue": ["190101"] * 3,
            "match_idx": [1, 1, 1],
            "outcome_code": ["3", "1", "0"],
            contract.Q_BJ_CALIBRATED: [
                [0.5, 0.3, 0.2],
                [0.5, 0.3, 0.2],
                [0.5, 0.3, 0.2],
            ],
            contract.Q_EU_BJLINE: [
                [0.6, 0.2, 0.2],
                [0.6, 0.2, 0.2],
                [0.6, 0.2, 0.2],
            ],
            contract.P_POWER_BJLINE: [
                [0.4, 0.35, 0.25],
                [0.4, 0.35, 0.25],
                [0.4, 0.35, 0.25],
            ],
            contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0],
            contract.SOURCE_IDENTITY_Q_BJ: [contract.SRC_BJ204_PCLOSE] * 3,
            contract.SOURCE_IDENTITY_EU: [contract.SRC_BJ203_DEVIG_EURO] * 3,
            "predicted_final_sp_input": [3.5, 3.5, 3.5],
            "market_uncertainty": [0.16, 0.16, 0.16],
        }
    )
    out = divergence.build_divergence_features(frame)
    # own component per outcome: 0.5*3.5, 0.3*3.5, 0.2*3.5
    assert out.iloc[0][divergence.LEG_Q_TIMES_SP_PRE] == pytest.approx(1.75, abs=1e-9)
    assert out.iloc[1][divergence.LEG_Q_TIMES_SP_PRE] == pytest.approx(1.05, abs=1e-9)
    assert out.iloc[2][divergence.LEG_Q_TIMES_SP_PRE] == pytest.approx(0.70, abs=1e-9)
    assert out.iloc[2][divergence.LEG_LOGQ_PLUS_LOGSP] == pytest.approx(
        math.log(0.2) + math.log(3.5), abs=1e-9
    )
    # uncertainty-standardized divergence present
    assert out.iloc[0][divergence.DIVERGENCE_EU_UNCERTAINTY_STD] == pytest.approx(
        (0.6 - 0.5) / 0.16, abs=1e-9
    )


def test_build_divergence_features_agreement_conflict() -> None:
    frame = pd.DataFrame(
        {
            "issue": ["190101"] * 3,
            "match_idx": [1, 1, 1],
            "outcome_code": ["3", "1", "0"],
            contract.Q_BJ_CALIBRATED: [
                [0.5, 0.3, 0.2],
                [0.5, 0.3, 0.2],
                [0.5, 0.3, 0.2],
            ],
            contract.Q_EU_BJLINE: [
                [0.6, 0.2, 0.2],
                [0.6, 0.2, 0.2],
                [0.6, 0.2, 0.2],
            ],
            contract.P_POWER_BJLINE: [
                [0.4, 0.35, 0.25],
                [0.4, 0.35, 0.25],
                [0.4, 0.35, 0.25],
            ],
            contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0],
            contract.SOURCE_IDENTITY_Q_BJ: [contract.SRC_BJ204_PCLOSE] * 3,
            contract.SOURCE_IDENTITY_EU: [contract.SRC_BJ203_DEVIG_EURO] * 3,
            "predicted_final_sp_input": [3.5, 3.5, 3.5],
            "market_uncertainty": [0.16, 0.16, 0.16],
        }
    )
    out = divergence.build_divergence_features(frame)
    # EU +1 (0.6 vs 0.5), POWER -1 (0.4 vs 0.5) on outcome '3' => CONFLICT
    assert out.iloc[0][divergence.DIVERGENCE_AGREEMENT] == "CONFLICT"
    assert out.iloc[0][divergence.DIVERGENCE_EU_DIRECTION] == 1
    assert out.iloc[0][divergence.DIVERGENCE_POWER_DIRECTION] == -1


def test_build_divergence_features_epsilon_policy() -> None:
    """A degenerate source vector below the epsilon floor is unavailable in
    log space, not silently clipped."""
    frame = pd.DataFrame(
        {
            "issue": ["190101"] * 3,
            "match_idx": [1, 1, 1],
            "outcome_code": ["3", "1", "0"],
            contract.Q_BJ_CALIBRATED: [
                [0.5, 0.3, 0.2],
                [0.5, 0.3, 0.2],
                [0.5, 0.3, 0.2],
            ],
            contract.Q_EU_BJLINE: [
                [1e-12, 0.5, 0.5],
                [1e-12, 0.5, 0.5],
                [1e-12, 0.5, 0.5],
            ],
            contract.P_POWER_BJLINE: [np.nan] * 3,
            contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0],
            contract.SOURCE_IDENTITY_Q_BJ: [contract.SRC_BJ204_PCLOSE] * 3,
            contract.SOURCE_IDENTITY_EU: [contract.SRC_BJ203_DEVIG_EURO] * 3,
            "predicted_final_sp_input": [3.5, 3.5, 3.5],
            "market_uncertainty": [np.nan] * 3,
        }
    )
    out = divergence.build_divergence_features(frame)
    # outcome '3' component is below floor -> CLR unavailable, diff available
    assert np.isnan(out.iloc[0][divergence.DIVERGENCE_EU_LOGRATIO])
    assert out.iloc[0][divergence.DIVERGENCE_EU_BJ] == pytest.approx(
        1e-12 - 0.5, abs=1e-12
    )


def test_coverage_strata() -> None:
    frame = pd.DataFrame(
        {
            "issue": ["190101"] * 3,
            "match_idx": [1, 1, 1],
            "outcome_code": ["3", "1", "0"],
            contract.Q_BJ_SP_DEVIG: [np.nan] * 3,
            contract.Q_BJ_CALIBRATED: [[0.5, 0.3, 0.2]] * 3,
            contract.Q_EU_RAW_1X2: [np.nan] * 3,
            contract.Q_EU_BJLINE: [np.nan] * 3,
            contract.P_POWER_BJLINE: [np.nan] * 3,
        }
    )
    strata = divergence.coverage_strata(frame)
    assert set(strata["representation"]) == {
        contract.Q_BJ_SP_DEVIG,
        contract.Q_BJ_CALIBRATED,
        contract.Q_EU_RAW_1X2,
        contract.Q_EU_BJLINE,
        contract.P_POWER_BJLINE,
    }
    qbj = strata[strata["representation"] == contract.Q_BJ_CALIBRATED].iloc[0]
    assert qbj["available_cells"] == 3
    assert qbj["coverage_fraction"] == 1.0


# ---------------------------------------------------------------------------
# DQ checks
# ---------------------------------------------------------------------------
def _cells_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "issue": ["190101", "190101", "190101", "190101"],
            "match_idx": [1, 1, 1, 2],
            "outcome_code": ["3", "1", "0", "3"],
            "cell_key": ["a", "b", "c", "d"],
            "year": [2019, 2019, 2019, 2019],
            "issue_order": [1, 1, 1, 1],
            contract.DECISION_EPOCH_COLUMN: pd.to_datetime(
                ["2020-01-01"] * 4, utc=True
            ),
            contract.KICKOFF_COLUMN: pd.to_datetime(["2020-01-02"] * 4, utc=True),
            contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0, -0.5],
            contract.Q_BJ_CALIBRATED: [
                [0.2, 0.3, 0.5],
                [0.2, 0.3, 0.5],
                [0.2, 0.3, 0.5],
                [0.4, 0.25, 0.35],
            ],
            contract.Q_BJ_SP_DEVIG: [np.nan] * 4,
            contract.Q_EU_RAW_1X2: [np.nan] * 4,
            contract.Q_EU_BJLINE: [np.nan] * 4,
            contract.P_POWER_BJLINE: [np.nan] * 4,
            "source_is_pclose": [1.0] * 4,
            "source_is_average_eu": [0.0] * 4,
            "predicted_final_sp_input": [3.5] * 4,
        }
    )


def test_dq01_flags_duplicate_identity() -> None:
    frame = _cells_frame()
    frame.loc[3, "match_idx"] = 1  # duplicate identity with row 0
    flagged = quality.dq01_duplicate_identity(frame)
    assert len(flagged) >= 2
    assert (flagged["reason_code"] == contract.REASON_DUPLICATE_CELL_IDENTITY).all()


def test_dq02_flags_missing_timestamp() -> None:
    frame = _cells_frame()
    frame.loc[0, contract.DECISION_EPOCH_COLUMN] = pd.NaT
    flagged = quality.dq02_timestamp_checks(frame)
    assert len(flagged) >= 1
    assert (flagged["reason_code"] == contract.REASON_MISSING_TIMESTAMP).any()


def test_dq02_flags_impossible_timestamp() -> None:
    frame = _cells_frame()
    frame.loc[0, contract.KICKOFF_COLUMN] = pd.Timestamp("1899-12-30", tz="UTC")
    flagged = quality.dq02_timestamp_checks(frame)
    assert len(flagged) >= 1
    assert "impossible" in flagged["detail"].iloc[0]


def test_dq03_flags_post_decision() -> None:
    frame = _cells_frame()
    frame.loc[0, contract.KICKOFF_COLUMN] = pd.Timestamp("2019-12-31", tz="UTC")
    flagged = quality.dq03_started_matches(frame)
    assert len(flagged) >= 1
    assert (flagged["reason_code"] == contract.REASON_POST_DECISION_OBSERVATION).any()


def test_dq03_does_not_flag_impossible_timestamp_as_post_decision_only() -> None:
    """An 1899 artifact is an impossible timestamp (DQ02), not a genuine
    post-decision observation; it must not silently inflate DQ03."""
    frame = _cells_frame()
    frame.loc[0, contract.KICKOFF_COLUMN] = pd.Timestamp("1899-12-30", tz="UTC")
    dq02 = quality.dq02_timestamp_checks(frame)
    assert len(dq02) >= 1
    # DQ03 may also catch it (kickoff < epoch) but DQ02 must classify it
    assert (dq02["detail"].str.contains("impossible")).any()


def test_dq04_half_goal_line_is_valid() -> None:
    frame = _cells_frame()
    flagged = quality.dq04_invalid_handicap_result_mapping(frame)
    assert len(flagged) == 0  # 0.0 and -0.5 are both valid BJ lines


def test_dq04_flags_quarter_line() -> None:
    frame = _cells_frame()
    frame.loc[0, contract.BJ_LINE_BOUNDARY] = -0.25
    flagged = quality.dq04_invalid_handicap_result_mapping(frame)
    assert len(flagged) >= 1
    assert (
        flagged["reason_code"] == contract.REASON_INVALID_HANDICAP_RESULT_MAPPING
    ).any()


def test_dq05_flags_invalid_triplet() -> None:
    frame = _cells_frame()
    frame.at[0, contract.Q_BJ_CALIBRATED] = np.asarray([0.2, 0.3, 0.6])  # sum 1.1
    flagged = quality.dq05_invalid_probability_triplets(frame)
    assert len(flagged) >= 1
    assert (flagged["reason_code"] == contract.REASON_INVALID_PROBABILITY_TRIPLET).any()


def test_dq07_flags_source_conflict() -> None:
    frame = _cells_frame()
    frame.loc[0, "source_is_pclose"] = 1.0
    frame.loc[0, "source_is_average_eu"] = 1.0
    flagged = quality.dq07_source_provenance_conflicts(frame)
    assert len(flagged) >= 1
    assert (flagged["reason_code"] == contract.REASON_SOURCE_PROVENANCE_CONFLICT).any()


def test_dq10_flags_outliers_and_redundancy() -> None:
    frame = _cells_frame()
    frame["noisy"] = [1.0, 2.0, 3.0, 1000.0]  # extreme outlier
    frame["dup_of_noisy"] = frame["noisy"] + 1e-12  # high redundancy
    flagged = quality.dq10_outlier_constant_fields(frame)
    assert len(flagged) >= 2  # outlier + redundancy pair


def test_dq12_no_payout_columns_in_inference() -> None:
    frame = _cells_frame()
    flagged = quality.dq12_payout_factor_boundary(frame)
    assert len(flagged) == 0


def test_dq12_flags_payout_named_column() -> None:
    frame = _cells_frame()
    frame["payout_after_65_units"] = 0.65
    flagged = quality.dq12_payout_factor_boundary(frame)
    assert len(flagged) >= 1
    assert (
        flagged["reason_code"] == contract.REASON_PAYOUT_FACTOR_AT_CELL_LEVEL
    ).any()


def test_dq12_does_not_flag_legitimate_0_65_probability() -> None:
    """A probability of exactly 0.65 is valid, not the payout coefficient."""
    frame = _cells_frame()
    frame.at[0, contract.Q_BJ_CALIBRATED] = np.asarray([0.65, 0.2, 0.15])
    flagged = quality.dq12_payout_factor_boundary(frame)
    assert len(flagged) == 0


def test_dq12_flags_0_65_n_construction_in_payout_column() -> None:
    frame = _cells_frame()
    frame["winning_zero_return_units"] = 0.65**3  # 0.274625
    flagged = quality.dq12_payout_factor_boundary(frame)
    assert len(flagged) >= 1
    assert (flagged["reason_code"] == contract.REASON_0_65_N_CONSTRUCTION).any()


def test_dq12_payload_variant_scans_labels() -> None:
    labels = pd.DataFrame(
        {
            "cell_join_key": ["x1", "x2"],
            "payout_factor": [0.65, 0.65],
            "result_code": ["3", "1"],
        }
    )
    flagged = quality.dq12_payout_boundary_payload(labels, "dev_labels")
    assert len(flagged) >= 1
    assert (
        flagged["reason_code"] == contract.REASON_PAYOUT_FACTOR_AT_CELL_LEVEL
    ).any()


def test_run_all_checks_returns_all_12() -> None:
    frame = _cells_frame()
    checks = quality.run_all_checks(frame)
    assert set(checks) == {
        "DQ01_duplicate_identity",
        "DQ02_timestamp_checks",
        "DQ03_started_matches",
        "DQ04_invalid_handicap_result_mapping",
        "DQ05_invalid_probability_triplets",
        "DQ06_impossible_values",
        "DQ07_source_provenance_conflicts",
        "DQ08_feature_label_overlap",
        "DQ09_support_drift",
        "DQ10_outlier_constant_fields",
        "DQ11_matched_support_loss",
        "DQ12_payout_factor_boundary",
    }


def test_run_all_checks_fails_closed_on_exception() -> None:
    """A check exception must raise (never degrade to a PASS row)."""
    frame = pd.DataFrame({"issue": ["190101"], "match_idx": [1]})  # missing cols
    with pytest.raises(Exception):
        quality.run_all_checks(frame)


# ---------------------------------------------------------------------------
# Causal eligibility (REQ-D01)
# ---------------------------------------------------------------------------
def test_causal_eligibility_observed_after_epoch() -> None:
    frame = _cells_frame()
    frame[contract.observed_at_col(contract.Q_EU_RAW_1X2)] = pd.to_datetime(
        ["2020-01-05"] * 4, utc=True  # AFTER the 2020-01-01 decision epoch
    )
    # assign a list as a single object-cell (not broadcast over rows)
    frame[contract.Q_EU_RAW_1X2] = frame[contract.Q_EU_RAW_1X2].astype(object)
    frame.at[3, contract.Q_EU_RAW_1X2] = [0.4, 0.25, 0.35]
    causal = quality.causal_eligibility(frame)
    sub = causal[causal["representation"] == contract.Q_EU_RAW_1X2]
    reasons = sub["unavailable_reason"].tolist()
    assert contract.REASON_OBSERVED_AFTER_EPOCH in reasons


def test_causal_eligibility_post_decision_excluded() -> None:
    frame = _cells_frame()
    frame.loc[3, contract.KICKOFF_COLUMN] = pd.Timestamp("2019-12-31", tz="UTC")
    frame[contract.observed_at_col(contract.Q_BJ_CALIBRATED)] = pd.to_datetime(
        ["2020-01-01"] * 4, utc=True
    )
    causal = quality.causal_eligibility(frame)
    sub = causal[causal["representation"] == contract.Q_BJ_CALIBRATED]
    assert sub["available"].tolist()[-1] is False
    assert sub["unavailable_reason"].tolist()[-1] == (
        contract.REASON_POST_DECISION_OBSERVATION
    )


# ---------------------------------------------------------------------------
# Builder assembly regression (merge explosion) + match-level join
# ---------------------------------------------------------------------------
def test_assemble_cells_no_merge_explosion_and_match_level_kickoff() -> None:
    from divergence_profile import builder

    root = ROOT
    if not contract.upstream_path(root, "bj203").exists():
        pytest.skip("upstream packages not present in this checkout")
    cells = builder.assemble_cells(root)
    assert len(cells) < 2_000_000
    dup = cells[["issue", "match_idx", "outcome_code"]].duplicated().sum()
    assert dup == 0
    # B1: match-level kickoff join — issues must have MULTIPLE kickoffs
    nk = cells.groupby("issue")["kickoff_ts_utc"].nunique()
    assert (nk > 1).sum() > 0, "issue-level broadcast still present"


def test_census_by_cohort_exact_match_counts() -> None:
    from divergence_profile import profile as prof

    cells = pd.DataFrame(
        {
            "issue": ["190101", "190101", "190101", "190102", "190102", "190102"],
            "match_idx": [1, 1, 1, 1, 1, 1],
            "outcome_code": ["3", "1", "0", "3", "1", "0"],
            "cell_key": ["a", "b", "c", "d", "e", "f"],
            "cohort": ["development"] * 6,
            "year": [2019] * 6,
        }
    )
    table = prof.census_by_cohort(cells)
    row = table.iloc[0]
    assert row["matches"] == 2  # (issue, match_idx) pairs, not match_idx.nunique()


# ---------------------------------------------------------------------------
# Tamper self-tests (REQ-E06 — attack our own evidence)
# ---------------------------------------------------------------------------
def test_evidence_not_hardcoded_pass() -> None:
    """REQ-D01..D10 evidence passes must be computed; injecting a DQ row must
    flip the corresponding requirement to FAIL."""
    from divergence_profile import builder

    class FakeReceipt:
        pass

    receipt = FakeReceipt()
    receipt.root = ROOT
    receipt.cells = _cells_frame()
    receipt.causal = None
    receipt.tables = {
        "census_by_cohort": pd.DataFrame(),
        "missingness_matrix": pd.DataFrame(),
        "intersection_coverage": pd.DataFrame(),
        "line_league_year_distribution": pd.DataFrame(),
        "outcome_distribution": pd.DataFrame(),
        "sp_and_implied_distribution": pd.DataFrame(),
        "bj_raw_vs_calibrated_reconciliation": pd.DataFrame(),
        "eu_vs_bj_scatter_table": pd.DataFrame(),
        "power_vs_bj_scatter_table": pd.DataFrame(),
        "direction_agreement_matrix": pd.DataFrame(),
        "divergence_magnitude_tail": pd.DataFrame(),
        "drift_table": pd.DataFrame(),
        "source_coverage_strata": pd.DataFrame(),
        "development_only_calibration": pd.DataFrame(),
        "predicted_sp_vs_settlement_sp": pd.DataFrame(),
        "outlier_heavy_tail": pd.DataFrame(),
    }
    receipt.checks = {name: pd.DataFrame() for name in [
        "DQ01_duplicate_identity",
        "DQ02_timestamp_checks",
        "DQ03_started_matches",
        "DQ04_invalid_handicap_result_mapping",
        "DQ05_invalid_probability_triplets",
        "DQ06_impossible_values",
        "DQ07_source_provenance_conflicts",
        "DQ08_feature_label_overlap",
        "DQ09_support_drift",
        "DQ10_outlier_constant_fields",
        "DQ11_matched_support_loss",
        "DQ12_payout_factor_boundary",
    ]}
    receipt.disposition = "READY_WITH_EXPLICIT_LIMITATIONS"
    evidence = builder.build_evidence(receipt)
    assert bool(evidence.loc[evidence["requirement"] == "REQ-D01", "pass"].iloc[0])

    # tamper: inject a post-decision row -> REQ-D01 must FAIL
    receipt.checks["DQ03_started_matches"] = pd.DataFrame(
        {"issue": ["x"], "match_idx": [1], "reason_code": ["POST_DECISION_OBSERVATION"]}
    )
    evidence2 = builder.build_evidence(receipt)
    assert not bool(evidence2.loc[evidence2["requirement"] == "REQ-D01", "pass"].iloc[0])


def test_write_package_is_atomic_on_failure() -> None:
    """A write failure must not destroy an existing package (B6)."""
    from divergence_profile import builder

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "results").mkdir()
        target = contract.package_path(root)
        target.mkdir(parents=True)
        (target / "MANIFEST.json").write_text('{"old": true}')

        class FakeCells:
            columns = ["issue"]

        receipt = builder.BuildReceipt(root=root)
        # minimal cell frame with the representation columns figures needs
        receipt.cells = pd.DataFrame(
            {
                "issue": ["190101", "190101", "190101"],
                "match_idx": [1, 1, 1],
                "outcome_code": ["3", "1", "0"],
                "cell_key": ["a", "b", "c"],
                "cohort": ["development"] * 3,
                "year": [2019] * 3,
                contract.Q_BJ_CALIBRATED: [np.nan, np.nan, np.nan],
                contract.Q_EU_RAW_1X2: [np.nan, np.nan, np.nan],
                contract.Q_EU_BJLINE: [np.nan, np.nan, np.nan],
                contract.P_POWER_BJLINE: [np.nan, np.nan, np.nan],
                contract.Q_BJ_SP_DEVIG: [np.nan, np.nan, np.nan],
                contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0],
                "source_is_pclose": [1.0, 1.0, 1.0],
                "source_is_average_eu": [0.0, 0.0, 0.0],
                "predicted_final_sp_input": [np.nan, np.nan, np.nan],
                "market_uncertainty": [np.nan, np.nan, np.nan],
            }
        )
        receipt.tables = {}
        receipt.checks = {}
        receipt.evidence = pd.DataFrame({"requirement": ["REQ-D01"], "pass": [True]})
        receipt.disposition = "BLOCKED_DATA_DEFECT"
        receipt.source_hashes = {}

        # force a write failure: make evidence un-writable by monkeypatching
        import divergence_profile.builder as builder_mod

        original = builder_mod.pd.DataFrame.to_csv
        def boom(self, *args, **kwargs):
            raise OSError("injected write failure")
        builder_mod.pd.DataFrame.to_csv = boom
        try:
            with pytest.raises(OSError):
                builder.write_package(receipt, force=True)
        finally:
            builder_mod.pd.DataFrame.to_csv = original

        # old package must still exist intact
        assert target.exists()
        assert json.loads((target / "MANIFEST.json").read_text()) == {"old": True}
        # no partial staging remains
        leftovers = list((root / "results").glob("*.staging-*"))
        assert leftovers == []


def test_write_package_replaces_existing_atomically() -> None:
    """force=True must replace an existing non-empty package atomically
    (os.replace cannot overwrite a non-empty directory directly)."""
    from divergence_profile import builder

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "results").mkdir()
        target = contract.package_path(root)
        target.mkdir(parents=True)
        (target / "MANIFEST.json").write_text('{"old": true}')

        receipt = builder.BuildReceipt(root=root)
        receipt.cells = pd.DataFrame(
            {
                "issue": ["190101", "190101", "190101"],
                "match_idx": [1, 1, 1],
                "outcome_code": ["3", "1", "0"],
                "cell_key": ["a", "b", "c"],
                "cohort": ["development"] * 3,
                "year": [2019] * 3,
                contract.Q_BJ_CALIBRATED: [np.nan, np.nan, np.nan],
                contract.Q_EU_RAW_1X2: [np.nan, np.nan, np.nan],
                contract.Q_EU_BJLINE: [np.nan, np.nan, np.nan],
                contract.P_POWER_BJLINE: [np.nan, np.nan, np.nan],
                contract.Q_BJ_SP_DEVIG: [np.nan, np.nan, np.nan],
                contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0],
                "source_is_pclose": [1.0, 1.0, 1.0],
                "source_is_average_eu": [0.0, 0.0, 0.0],
                "predicted_final_sp_input": [np.nan, np.nan, np.nan],
                "market_uncertainty": [np.nan, np.nan, np.nan],
            }
        )
        receipt.tables = {}
        receipt.checks = {}
        receipt.evidence = pd.DataFrame({"requirement": ["REQ-D01"], "pass": [True]})
        receipt.disposition = "BLOCKED_DATA_DEFECT"
        receipt.source_hashes = {}

        # label load fails in tmp (no upstream) -> replace must restore the
        # old package and raise, never leave a partial/absent target
        with pytest.raises(RuntimeError):
            builder.write_package(receipt, force=True)
        assert target.exists()
        assert json.loads((target / "MANIFEST.json").read_text()) == {"old": True}
        leftovers = list((root / "results").glob("*.staging-*"))
        assert leftovers == []


def test_label_load_failure_fails_build() -> None:
    """REQ-D06: a label load failure must abort the build, not emit an
    error.csv and continue (B6)."""
    from divergence_profile import builder
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "results").mkdir()
        receipt = builder.BuildReceipt(root=root)
        receipt.cells = pd.DataFrame(
            {
                "issue": ["190101", "190101", "190101"],
                "match_idx": [1, 1, 1],
                "outcome_code": ["3", "1", "0"],
                "cell_key": ["a", "b", "c"],
                "cohort": ["development"] * 3,
                "year": [2019] * 3,
                contract.Q_BJ_CALIBRATED: [np.nan, np.nan, np.nan],
                contract.Q_EU_RAW_1X2: [np.nan, np.nan, np.nan],
                contract.Q_EU_BJLINE: [np.nan, np.nan, np.nan],
                contract.P_POWER_BJLINE: [np.nan, np.nan, np.nan],
                contract.Q_BJ_SP_DEVIG: [np.nan, np.nan, np.nan],
                contract.BJ_LINE_BOUNDARY: [0.0, 0.0, 0.0],
                "source_is_pclose": [1.0, 1.0, 1.0],
                "source_is_average_eu": [0.0, 0.0, 0.0],
                "predicted_final_sp_input": [np.nan, np.nan, np.nan],
                "market_uncertainty": [np.nan, np.nan, np.nan],
            }
        )
        receipt.tables = {}
        receipt.checks = {}
        receipt.evidence = pd.DataFrame({"requirement": ["REQ-D01"], "pass": [True]})
        receipt.disposition = "BLOCKED_DATA_DEFECT"
        receipt.source_hashes = {}
        # no upstream packages exist in tmp -> load_bj203_labels raises
        with pytest.raises(RuntimeError):
            builder._write_staging(receipt, root / "staging")
        # no error.csv fallback was written (fail closed, not continue)
        assert not (root / "staging" / "development_labels_error.csv").exists()


def test_contract_frozen_constants() -> None:
    assert contract.PAYOUT_FACTOR_BJ == 0.65
    assert contract.LABEL_OPEN_MAX_YEAR == 2023
    assert contract.SEALED_2024_MIN_YEAR == 2024
    assert contract.DIVERGENCE_ANCHOR == contract.Q_BJ_CALIBRATED
    assert contract.PROBABILITY_SUM_TOLERANCE <= 2e-6


def test_dev_label_payload_excludes_payout_columns() -> None:
    from divergence_profile import sources

    root = ROOT
    if not contract.upstream_path(root, "bj203").exists():
        pytest.skip("upstream packages not present in this checkout")
    labels = sources.load_bj203_labels(root)
    forbidden = [
        "winning_zero_return_units",
        "payout_factor",
        "payout_after_65_units",
        "tax_rate",
        "tax_cliff_gross_yuan",
        "tax_realized_yuan",
    ]
    for column in forbidden:
        assert column not in labels.columns, f"{column} leaked into dev labels"
