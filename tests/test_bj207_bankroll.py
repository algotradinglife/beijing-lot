from __future__ import annotations

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd
import pytest

from bankroll_policy.fixed_n7 import (
    CONTROLLING_K,

    N,
    POLICIES,
    SOURCE_VERSION,
    Stage4Error,
    _decision,
    _digest,
    _notebook_contract_digest,
    _publish_stage,
    _project_counts,
    _rolling_window_rows,
    _validate_candidates,
    reconstruct_active_requests,
    replay_path,
    run,
    verify,
    Inputs,
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


@pytest.mark.parametrize("budget", [-1.0, np.nan, np.inf])
def test_projection_rejects_invalid_budget(budget: float) -> None:
    with pytest.raises(Stage4Error, match="budget_yuan"):
        _project_counts(np.asarray([0.6, 0.3, 0.1]), budget)


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
    assert ledger.controller_family.isin(
        {"LEARNED_CONTROLLER", "SCORE_WEIGHTED_CONTROL", "NATIVE_EQUAL_CONTROL", "EQUAL_FUNDING_CONTROL"}
    ).all()


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
    issue = pd.read_parquet(ROOT / "results/issue-207/matched_comparator_issue_ledger.parquet")
    ticket = pd.read_parquet(ROOT / "results/issue-207/matched_ticket_tax_lot_ledger.parquet")
    assert not issue.empty
    assert not ticket.empty
    assert ticket.tax_lot_count.eq(ticket.repeat_count).all()
    schema = json.loads((ROOT / "results/issue-207/schema.json").read_text())
    catalog = {table["name"]: table for table in schema["tables"]}
    primary_key = catalog["matched_ticket_tax_lot_ledger.parquet"]["primary_key"]
    assert "candidate_controller" in primary_key
    assert not ticket.duplicated(primary_key, keep=False).any()


def test_rolling_window_drawdown_is_local_to_window_peak() -> None:
    # The full-path historical peak is 200 before this window.  The local
    # window starts at 100, rises to 120, then falls to 90: local MDD is 25%,
    # not the 55% full-path drawdown encoded in the input column.
    path = pd.DataFrame(
        {
            "year": [2023, 2023],
            "issue": ["1", "2"],
            "post_issue_bankroll_yuan": [120_000.0, 90_000.0],
            "drawdown_pct": [0.40, 0.55],
            "active": [True, True],
        }
    )
    # Use a direct two-issue variant by extending to the minimum supported five.
    path = pd.concat(
        [
            path,
            pd.DataFrame(
                {
                    "year": [2023, 2023, 2023],
                    "issue": ["3", "4", "5"],
                    "post_issue_bankroll_yuan": [90_000.0, 90_000.0, 90_000.0],
                    "drawdown_pct": [0.55, 0.55, 0.55],
                    "active": [True, True, True],
                }
            ),
        ],
        ignore_index=True,
    )
    rows = _rolling_window_rows(path, {})
    first = next(row for row in rows if row["window_issues"] == 5)
    assert first["time_zero_anchor"] is True
    assert first["window_max_drawdown_pct"] == pytest.approx(0.25, abs=1e-12)


def test_notebook_contract_digest_ignores_outputs_but_binds_source(tmp_path: Path) -> None:
    original = json.loads((ROOT / "notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb").read_text())
    path = tmp_path / "notebook.ipynb"
    path.write_text(json.dumps(original), encoding="utf-8")
    baseline = _notebook_contract_digest(path)
    original["cells"][1]["execution_count"] = 999
    original["cells"][1]["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["changed"]}]
    path.write_text(json.dumps(original), encoding="utf-8")
    assert _notebook_contract_digest(path) == baseline
    original["cells"][1]["source"].append("\n# source mutation")
    path.write_text(json.dumps(original), encoding="utf-8")
    assert _notebook_contract_digest(path) != baseline


def test_post_rename_parent_fsync_failure_removes_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import bankroll_policy.fixed_n7 as mod

    stage = tmp_path / ".result.stage"
    output = tmp_path / "result"
    stage.mkdir()
    (stage / "payload").write_text("durable", encoding="utf-8")
    real_fsync = mod._fsync_dir
    calls = 0

    def fail_once(path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("INJECT_POST_RENAME_PARENT_FSYNC")
        real_fsync(path)

    monkeypatch.setattr(mod, "_fsync_dir", fail_once)
    with pytest.raises(OSError, match="INJECT_POST_RENAME_PARENT_FSYNC"):
        _publish_stage(stage, output)
    assert not output.exists()
    retry_stage = tmp_path / ".result.stage"
    retry_stage.mkdir()
    _publish_stage(retry_stage, output)
    assert output.exists()


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
                "terminal_evidentiary": False,
            }
        ]
    )
    decision = _decision(metrics, matched, frozen_learned_choice="SIMPLE_LOGISTIC")
    assert decision["ACTIVE_OVERLAY_EVIDENCE"] is False
    assert decision["negative_freeze"] == "NATIVE_2_YUAN"
    assert decision["frozen_learned_controller_choice"] == "SIMPLE_LOGISTIC"


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


def test_candidate_validation_rejects_future_labels_and_source_trace_tamper() -> None:
    candidates = pd.read_parquet(ROOT / "results/issue-206/candidate_ledger.parquet")
    leaked = candidates.copy()
    idx = leaked.index[leaked.split.eq("LOCKED_TEST")][0]
    leaked.loc[idx, "labels_available"] = True
    with pytest.raises(Stage4Error, match="future/locked labels leaked"):
        _validate_candidates(leaked)
    trace = candidates.copy()
    trace.loc[trace.index[0], "source_cells_json"] = '[{"bad":1}]'
    with pytest.raises(Stage4Error, match="malformed|incomplete source trace"):
        _validate_candidates(trace)


def test_replay_rejects_negative_or_empty_matched_schedule() -> None:
    candidates = pd.read_parquet(ROOT / "results/issue-206/candidate_ledger.parquet")
    requests = reconstruct_active_requests(candidates)
    issues = (
        requests.loc[
            requests.split.eq("CV_2023") & requests.policy.eq("MARKET_WR") & requests.k.eq(8),
            "issue",
        ]
        .astype(str)
        .unique()
        .tolist()
    )
    with pytest.raises(Stage4Error, match="empty matched funding schedule"):
        replay_path(
            requests,
            split="CV_2023",
            policy="MARKET_WR",
            k=8,
            method="SIMPLE_LOGISTIC",
            controllers={},
            calibrated={"SIMPLE_LOGISTIC": 0.01},
            funding_schedule={},
        )
    schedule = {issue: 0.0 for issue in issues}
    schedule[issues[0]] = -2.0
    with pytest.raises(Stage4Error, match="non-negative"):
        replay_path(
            requests,
            split="CV_2023",
            policy="MARKET_WR",
            k=8,
            method="SIMPLE_LOGISTIC",
            controllers={},
            calibrated={"SIMPLE_LOGISTIC": 0.01},
            funding_schedule=schedule,
        )


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


def test_semantic_verifier_rejects_remanifested_attribution_schema_and_decision_tamper(tmp_path: Path) -> None:
    output = tmp_path / "issue-207"
    shutil.copytree(ROOT / "results/issue-207", output)
    attribution_path = output / "attribution.csv"
    attribution = pd.read_csv(attribution_path)
    attribution.loc[0, "attribution"] = "BAD"
    attribution.to_csv(attribution_path, index=False)
    _refresh_manifest(output)
    with pytest.raises(Stage4Error, match="attribution"):
        verify(output)

    output2 = tmp_path / "issue-207-schema"
    shutil.copytree(ROOT / "results/issue-207", output2)
    schema_path = output2 / "schema.json"
    schema = json.loads(schema_path.read_text())
    schema["forbidden"].append("BAD")
    schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    _refresh_manifest(output2)
    with pytest.raises(Stage4Error, match="schema.json semantic mismatch"):
        verify(output2)

    output3 = tmp_path / "issue-207-decision"
    shutil.copytree(ROOT / "results/issue-207", output3)
    decision_path = output3 / "decision.json"
    decision = json.loads(decision_path.read_text())
    decision["frozen_learned_controller_choice"] = "SIMPLE_LOGISTIC"
    decision_path.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n")
    _refresh_manifest(output3)
    with pytest.raises(Stage4Error, match="decision semantic mismatch|decision/model-choice leakage"):
        verify(output3)


def test_semantic_verifier_rejects_provenance_and_model_choice_leakage(tmp_path: Path) -> None:
    output = tmp_path / "issue-207"
    shutil.copytree(ROOT / "results/issue-207", output)
    provenance_path = output / "provenance.json"
    provenance = json.loads(provenance_path.read_text())
    provenance["learned_controller_choice_boundary"] = "bad"
    provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    _refresh_manifest(output)
    with pytest.raises(Stage4Error, match="provenance.json semantic mismatch"):
        verify(output)

    output2 = tmp_path / "issue-207-model-choice"
    shutil.copytree(ROOT / "results/issue-207", output2)
    matched_path = output2 / "matched_comparisons.csv"
    matched = pd.read_csv(matched_path)
    leaked = matched.candidate_controller.eq("SIMPLE_LOGISTIC")
    if leaked.any():
        matched.loc[leaked, "terminal_evidentiary"] = True
        matched.to_csv(matched_path, index=False)
        _refresh_manifest(output2)
        with pytest.raises(Stage4Error, match="matched comparisons semantic replay mismatch|terminal model-choice leakage"):
            verify(output2)


def test_run_cleans_stage_on_keyboard_interrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output = tmp_path / "issue-207"
    stale = output.with_name(f".{output.name}.stage")
    stale.mkdir()
    (stale / "junk.txt").write_text("x", encoding="utf-8")

    import bankroll_policy.fixed_n7 as mod

    def boom(_source: Path) -> dict[str, object]:
        raise KeyboardInterrupt()

    monkeypatch.setattr(mod, "verify_stage3", boom)
    with pytest.raises(KeyboardInterrupt):
        run(Inputs(ROOT / "results/issue-206", output))
    assert not stale.exists()
    assert not output.exists()


def test_committed_package_verifies() -> None:
    receipt = verify(ROOT / "results/issue-207")
    assert receipt["status"] == "PASS"
    assert receipt["engine_valid"] is True
    assert receipt["deployable_policy"] is False
    assert receipt["active_request_rows"] > 0
    assert receipt["matched_issue_rows"] > 0
    assert receipt["matched_ticket_rows"] > 0
