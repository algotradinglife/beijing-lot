from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from bankroll_policy.fixed_n7 import (
    CONTROLLING_K,
    INITIAL_BANKROLL,
    N,
    POLICIES,
    SOURCE_VERSION,
    Stage4Error,
    _decision,
    _digest,
    _project_counts,
    _validate_candidates,
    reconstruct_active_requests,
    verify,
)

ROOT = Path(__file__).resolve().parents[1]


def _refresh_manifest(output: Path) -> None:
    manifest = {
        path.relative_to(output).as_posix(): _digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (output / "SHA256SUMS.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def test_integer_projection_conserves_budget_with_sub_yen2_residual() -> None:
    counts, residual = _project_counts(np.asarray([0.6, 0.3, 0.1]), 101.0)
    assert counts.tolist() == [30, 15, 5]
    assert counts.sum() * 2 + residual == 101.0
    assert 0 <= residual < 2


def test_projection_rejects_invalid_simplex() -> None:
    with pytest.raises(Stage4Error, match="simplex"):
        _project_counts(np.asarray([0.7, -0.1, 0.4]), 100.0)


def test_committed_active_panel_is_nonempty_exact_and_source_bound() -> None:
    requests = pd.read_parquet(ROOT / "results/issue-207/active_research_ticket_requests.parquet")
    assert not requests.empty
    assert set(requests.policy) == set(POLICIES)
    assert set(requests.k) == {8, 16, 32}
    assert requests.n.eq(N).all()
    assert requests.research_only.astype(bool).all()
    assert not requests.promoted.astype(bool).any()
    assert requests.capital_authority.eq("STAGE4_EXPERIMENT_ONLY").all()
    assert requests.source_package_version.eq(SOURCE_VERSION).all()
    assert requests.loc[requests.k.eq(CONTROLLING_K), "panel_role"].eq("CONTROLLING").all()
    assert requests.loc[requests.k.ne(CONTROLLING_K), "panel_role"].eq("SENSITIVITY_ONLY").all()
    assert requests.ticket_identity.str.split("|").map(len).eq(N).all()
    assert requests.match_indices.str.split("|").map(lambda values: len(set(values))).eq(N).all()
    np.testing.assert_allclose(
        requests.pre_tax_gross_multiple,
        requests.tax_adjusted_gross_multiple / 0.65,
        rtol=0,
        atol=1e-12,
    )


def test_exact_k8_identities_recompute_from_frozen_stage3() -> None:
    candidates = pd.read_parquet(ROOT / "results/issue-206/candidate_ledger.parquet")
    expected = reconstruct_active_requests(candidates)
    actual = pd.read_parquet(ROOT / "results/issue-207/active_research_ticket_requests.parquet")
    columns = ["split", "issue", "policy", "k", "rank", "ticket_identity", "source_cells_json"]
    expected = expected.loc[expected.k.eq(CONTROLLING_K), columns].astype(str)
    actual = actual.loc[actual.k.eq(CONTROLLING_K), columns].astype(str)
    pd.testing.assert_frame_equal(actual.reset_index(drop=True), expected.reset_index(drop=True))


def test_capital_ledger_has_exact_conservation_no_topup_and_integer_tickets() -> None:
    ledger = pd.read_parquet(ROOT / "results/issue-207/issue_capital_ledger.parquet")
    np.testing.assert_allclose(
        ledger.post_issue_bankroll_yuan,
        ledger.pre_issue_bankroll_yuan - ledger.funded_stake_yuan + ledger.gross_payout_yuan,
        rtol=0,
        atol=1e-8,
    )
    assert ledger.funded_stake_yuan.ge(0).all()
    assert ledger.funded_stake_yuan.le(ledger.pre_issue_bankroll_yuan + 1e-8).all()
    assert np.isclose((ledger.funded_stake_yuan / 2) % 1, 0).all()
    assert ledger.post_issue_bankroll_yuan.ge(-1e-8).all()
    assert set(ledger.experiment_role) == {
        "ACTIVE_LEARNED_ONLY",
        "ACTIVE_EQUAL_FUNDING_CONTROL",
        "ACTIVE_SCORE_WEIGHTED_CONTROL",
    }


def test_safe_lane_is_lower_exposure_only_not_active_evidence() -> None:
    safe = pd.read_csv(ROOT / "results/issue-207/safe_reference_ledger.csv")
    assert safe.funded_stake_yuan.eq(0).all()
    assert safe.attribution.eq("LOWER_EXPOSURE_ONLY").all()
    assert set(safe.experiment_role) == {"SAFE_FALLBACK_MIXED", "CASH"}
    decision = json.loads((ROOT / "results/issue-207/decision.json").read_text())
    assert decision["safe_reference_interpretation"].startswith("NO_BET/cash")
    assert decision["DEPLOYABLE_POLICY"] is False


def test_identified_comparisons_have_exact_common_executable_schedule() -> None:
    matched = pd.read_csv(ROOT / "results/issue-207/matched_comparisons.csv")
    identified = matched.loc[matched.equal_capital_schedule.astype(bool)]
    assert not identified.empty
    np.testing.assert_allclose(
        identified.candidate_turnover_yuan,
        identified.comparator_turnover_yuan,
        rtol=0,
        atol=1e-8,
    )
    assert identified.capital_schedule_hash.eq(identified.comparator_schedule_hash).all()


def test_decision_ignores_unmatched_and_lower_exposure_rows() -> None:
    metrics = pd.DataFrame()
    matched = pd.DataFrame(
        [
            {
                "k": 8,
                "comparison_role": "EQUAL_FUNDING_CONTROL",
                "equal_capital_schedule": False,
                "candidate_controller": "SIMPLE_LOGISTIC",
                "matched_lift_ending_capital_yuan": 999_999.0,
                "matched_lift_max_drawdown_pct": 1.0,
            }
        ]
    )
    decision = _decision(metrics, matched)
    assert decision["ACTIVE_OVERLAY_EVIDENCE"] is False
    assert decision["negative_freeze"] == "NATIVE_2_YUAN"


def test_semantic_verifier_rejects_remanifested_safe_lane_pseudo_edge(tmp_path: Path) -> None:
    output = tmp_path / "issue-207"
    shutil.copytree(ROOT / "results/issue-207", output)
    safe_path = output / "safe_reference_ledger.csv"
    safe = pd.read_csv(safe_path)
    safe.loc[0, "attribution"] = "ACTIVE_OVERLAY_EVIDENCE"
    safe.to_csv(safe_path, index=False)
    _refresh_manifest(output)
    with pytest.raises(Stage4Error, match="safe reference ledger|safe lane pseudo-Edge"):
        verify(output)


@pytest.mark.parametrize("column,value", [("control_joint_probability", np.nan), ("predicted_sp_product", np.inf), ("predicted_sp_product", 0.0)])
def test_candidate_validation_rejects_invalid_pre_event_inputs(column: str, value: float) -> None:
    candidates = pd.read_parquet(ROOT / "results/issue-206/candidate_ledger.parquet")
    candidates.loc[candidates.index[0], column] = value
    with pytest.raises(Stage4Error, match="non-finite|non-positive"):
        _validate_candidates(candidates)


def test_candidate_validation_rejects_duplicate_and_malformed_n7() -> None:
    candidates = pd.read_parquet(ROOT / "results/issue-206/candidate_ledger.parquet")
    duplicate = pd.concat([candidates, candidates.iloc[[0]]], ignore_index=True)
    with pytest.raises(Stage4Error, match="not unique"):
        _validate_candidates(duplicate)
    malformed = candidates.copy()
    malformed.loc[malformed.index[0], "n"] = 6
    with pytest.raises(Stage4Error, match="non-N7"):
        _validate_candidates(malformed)


def test_semantic_verifier_rejects_remanifested_active_settlement_tamper(tmp_path: Path) -> None:
    output = tmp_path / "issue-207"
    shutil.copytree(ROOT / "results/issue-207", output)
    path = output / "active_research_ticket_requests.parquet"
    frame = pd.read_parquet(path)
    frame.loc[frame.index[0], "realized_gross"] = 12345.0
    frame.to_parquet(path, index=False)
    _refresh_manifest(output)
    with pytest.raises(Stage4Error, match="active panel"):
        verify(output)


def test_semantic_verifier_rejects_remanifested_capital_ledger_tamper(tmp_path: Path) -> None:
    output = tmp_path / "issue-207"
    shutil.copytree(ROOT / "results/issue-207", output)
    path = output / "issue_capital_ledger.parquet"
    frame = pd.read_parquet(path)
    row = frame.index[0]
    frame.loc[row, "gross_payout_yuan"] += 100.0
    frame.loc[row, "net_pnl_yuan"] += 100.0
    frame.loc[row, "post_issue_bankroll_yuan"] += 100.0
    frame.to_parquet(path, index=False)
    _refresh_manifest(output)
    with pytest.raises(Stage4Error, match="capital ledger"):
        verify(output)


def test_committed_package_verifies() -> None:
    receipt = verify(ROOT / "results/issue-207")
    assert receipt["status"] == "PASS"
    assert receipt["engine_valid"] is True
    assert receipt["deployable_policy"] is False
    assert receipt["active_request_rows"] > 0
