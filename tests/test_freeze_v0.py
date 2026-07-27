from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from src.freeze_v0 import FreezeV0Error, FreezeV0Store, digest, file_hash, hourly_attempt_times


CUTOFF = datetime.fromisoformat("2026-07-30T12:00:00+08:00")


def _replay(decision_input: dict[str, object], source_receipt: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    pool: dict[str, object] = {
        "generator_version": "synthetic-v1", "generator_contract": "one-candidate-per-match", "seed": 7,
        "input_sha256": digest(decision_input),
        "candidates": [{"candidate_id": f"c{match['match_idx']}", "match_indices": [match["match_idx"]]} for match in decision_input["matches"]],
    }
    plans: dict[str, object] = {
        "contract_version": "freeze-v0-plans-v1", "input_sha256": digest(decision_input), "candidate_pool_sha256": digest(pool),
        "actual": {"tickets": [], "status": "CONTROL", "unused_budget_yuan": 2},
        "disjoint_unit": {"tickets": [], "status": "NO_BET_INFEASIBLE", "unused_budget_yuan": 2},
        "disjoint_equal_yuan": {"tickets": [], "status": "NO_BET_INFEASIBLE", "unused_budget_yuan": 2},
        "disjoint_risk_parity": {"tickets": [], "status": "NO_BET_INFEASIBLE", "unused_budget_yuan": 2},
    }
    return pool, plans


def _inputs() -> dict[str, object]:
    membership = [{"match_idx": 1}, {"match_idx": 2}]
    value = {
        "membership": membership,
        "decision_input": {
            "formal_contract_version": "v3.3.3", "formal_input_sha256": "a" * 64,
            "matches": [{"match_idx": 1, "p": {"3": 0.4, "1": 0.3, "0": 0.3}, "sp": {"3": 2.0, "1": 3.0, "0": 4.0}, "sale_cutoff_hkt": "2026-07-30T12:00:00+08:00", "source_observed_at_hkt": "2026-07-30T08:59:00+08:00", "sp_provenance_sha256": "c" * 64}, {"match_idx": 2, "p": {"3": 0.4, "1": 0.3, "0": 0.3}, "sp": {"3": 2.0, "1": 3.0, "0": 4.0}, "sale_cutoff_hkt": "2026-07-30T12:00:00+08:00", "source_observed_at_hkt": "2026-07-30T08:59:00+08:00", "sp_provenance_sha256": "d" * 64}],
        },
        "candidate_ticket_pool": {}, "plans": {},
        "source_receipt": {
            "issue": "26100", "issue_membership": membership, "source_sha256": "b" * 64,
            "source_observed_at_hkt": "2026-07-30T09:00:00+08:00", "trusted_clock_provenance": {"authority": "synthetic"},
            "cutoff_at_hkt": "2026-07-30T12:00:00+08:00", "earliest_kickoff_at_hkt": "2026-07-30T12:00:00+08:00",
        },
    }
    value["candidate_ticket_pool"], value["plans"] = _replay(value["decision_input"], value["source_receipt"])
    return value


def _capture(store: FreezeV0Store, *, at: datetime = datetime.fromisoformat("2026-07-30T09:00:00+08:00"), **overrides):
    payload = _inputs() | overrides
    return store.capture_attempt(issue="26100", captured_at=at, cutoff_at=CUTOFF, **payload)


def test_pass_attempt_is_content_addressed_research_only_and_exact(tmp_path) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    result = _capture(store)
    assert result["status"] == "PASS"
    attempt = tmp_path / "freeze_v0" / "26100" / "attempts" / f"20260730T090000+0800_{result['snapshot_id']}"
    assert {path.name for path in attempt.iterdir()} == {"manifest.json", "decision_input.json", "candidate_ticket_pool.json", "plans.json", "source_receipt.json", "SHA256SUMS"}
    manifest = json.loads((attempt / "manifest.json").read_text())
    assert manifest["snapshot_id"] == result["snapshot_id"]
    assert manifest["research_only"] is True
    assert manifest["research_evidence_eligible"] is False
    assert manifest["operational_execution_enabled"] is False
    assert manifest["downloadable_for_purchase"] is False
    assert store.verify_attempt(issue="26100", snapshot_id=result["snapshot_id"])["snapshot_id"] == result["snapshot_id"]


@pytest.mark.parametrize("mutation, reason", [
    (lambda value: value["membership"].pop(), "complete issue membership"),
    (lambda value: value["decision_input"].update({"final_score": "1-0"}), "outcome field"),
    (lambda value: value["decision_input"].pop("formal_input_sha256"), "hashes are required"),
])
def test_invalid_attempt_emits_receipt_and_later_attempt_can_pass(tmp_path, mutation, reason) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    bad = _inputs()
    mutation(bad)
    failed = store.capture_attempt(issue="26100", captured_at=datetime.fromisoformat("2026-07-30T09:00:00+08:00"), cutoff_at=CUTOFF, **bad)
    assert failed["status"] == "FAIL"
    assert reason in failed["reason"]
    assert _capture(store, at=datetime.fromisoformat("2026-07-30T10:00:00+08:00"))["status"] == "PASS"


def test_tamper_and_cutoff_fail_closed(tmp_path) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    result = _capture(store)
    attempt = tmp_path / "freeze_v0" / "26100" / "attempts" / f"20260730T090000+0800_{result['snapshot_id']}"
    (attempt / "plans.json").write_text('{"actual":{"outcome":"bad"}}\n')
    with pytest.raises(FreezeV0Error, match="SHA256SUMS payload mismatch"):
        store.verify_attempt(issue="26100", snapshot_id=result["snapshot_id"])
    late = _capture(store, at=CUTOFF + timedelta(seconds=1))
    assert late["status"] == "FAIL"
    assert "after cutoff" in late["reason"]


def test_schedule_final_uses_latest_valid_before_cutoff_and_is_write_once(tmp_path) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    assert hourly_attempt_times(available_at=datetime.fromisoformat("2026-07-30T09:10:00+08:00"), cutoff_at=CUTOFF, safety_margin=timedelta(minutes=5)) == [
        datetime.fromisoformat("2026-07-30T09:10:00+08:00"), datetime.fromisoformat("2026-07-30T10:10:00+08:00"), datetime.fromisoformat("2026-07-30T11:10:00+08:00"), datetime.fromisoformat("2026-07-30T11:55:00+08:00"),
    ]
    first = _capture(store, at=datetime.fromisoformat("2026-07-30T09:00:00+08:00"))
    second = _capture(store, at=datetime.fromisoformat("2026-07-30T11:00:00+08:00"))
    bad_final_input = _inputs()["decision_input"] | {"final_score": "1-0"}
    failed = _capture(store, at=CUTOFF, decision_input=bad_final_input)
    assert failed["status"] == "FAIL"
    final = store.finalize_cutoff(issue="26100", cutoff_at=CUTOFF, finalized_at=datetime.fromisoformat("2026-07-30T12:01:00+08:00"))
    assert final["status"] == "PASS"
    assert final["snapshot_id"] == second["snapshot_id"] != first["snapshot_id"]
    assert file_hash(tmp_path / "freeze_v0" / "26100" / "attempts" / f"20260730T090000+0800_{first['snapshot_id']}" / "SHA256SUMS")
    with pytest.raises(FreezeV0Error, match="write-once"):
        store.finalize_cutoff(issue="26100", cutoff_at=CUTOFF, finalized_at=datetime.fromisoformat("2026-07-30T12:02:00+08:00"))


def test_final_records_missed_freeze_when_no_attempt_passes(tmp_path) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    final = store.finalize_cutoff(issue="26100", cutoff_at=CUTOFF, finalized_at=datetime.fromisoformat("2026-07-30T12:01:00+08:00"))
    assert final["status"] == "MISSED_FREEZE"
    assert final["research_evidence_eligible"] is False


def test_cutoff_completion_clock_is_allowed_when_bound_source_agrees(tmp_path) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    selected = _capture(store, at=CUTOFF)
    assert selected["status"] == "PASS"
    final = store.finalize_cutoff(issue="26100", cutoff_at=CUTOFF, finalized_at=CUTOFF)
    assert final["snapshot_id"] == selected["snapshot_id"]


def test_partial_pool_with_recomputed_hashes_fails_independent_replay(tmp_path) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    payload = _inputs()
    payload["candidate_ticket_pool"]["candidates"] = payload["candidate_ticket_pool"]["candidates"][:1]
    payload["plans"]["candidate_pool_sha256"] = digest(payload["candidate_ticket_pool"])
    result = store.capture_attempt(issue="26100", captured_at=datetime.fromisoformat("2026-07-30T09:00:00+08:00"), cutoff_at=CUTOFF, **payload)
    assert result["status"] == "FAIL"
    assert "deterministic replay" in result["reason"]


@pytest.mark.parametrize("layer, reason", [("receipt", "source receipt observation"), ("match", "match source observation")])
def test_future_source_observation_fails_before_candidate_selection(tmp_path, layer, reason) -> None:
    store = FreezeV0Store(tmp_path / "freeze_v0", replay_candidate_pool=_replay)
    payload = _inputs()
    if layer == "receipt":
        payload["source_receipt"]["source_observed_at_hkt"] = "2026-07-30T09:01:00+08:00"
    else:
        payload["decision_input"]["matches"][0]["source_observed_at_hkt"] = "2026-07-30T09:01:00+08:00"
    result = store.capture_attempt(issue="26100", captured_at=datetime.fromisoformat("2026-07-30T09:00:00+08:00"), cutoff_at=CUTOFF, **payload)
    assert result["status"] == "FAIL"
    assert reason in result["reason"]
