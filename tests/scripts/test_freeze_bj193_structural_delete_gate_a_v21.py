from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj193_structural_delete_gate_a_v21.py"
ADAPTER = ROOT / "scripts" / "bj193_structural_delete_adapter.py"
PACKAGE = ROOT / "results" / "bj193_gate_a_chain_interface_v21"


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def rows(path: Path) -> list[dict[str, str]]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_v21_source_and_registry_are_outcome_unexposed_and_hash_bound():
    freeze = load(SCRIPT, "bj193_v21_test_freeze_sources")
    source = freeze.verify_sources()
    assert source["accepted_v2"]["manifest_sha256"] == freeze.V2_MANIFEST_SHA256
    assert source["structural_source"]["match_vector_sha256"] == (
        freeze.MATCH_VECTOR_SHA256
    )
    assert source["access"] == "OUTCOME_UNEXPOSED_GATE_A_ONLY"
    registry = freeze.complete_structural_registry()
    assert len(registry) == 47_819
    assert set(freeze.STRUCTURAL_REGISTRY_FIELDS) == set(registry[0])
    assert all("result" not in field for field in freeze.STRUCTURAL_REGISTRY_FIELDS)
    adapter = load(ADAPTER, "bj193_v21_test_registry_identity")
    assert all(
        row["structural_registry_row_sha256"]
        == adapter.structural_registry_row_identity(row)
        for row in (registry[0], registry[len(registry) // 2], registry[-1])
    )


def test_effective_mapping_preserves_pq_identities_and_splits_unit_class():
    freeze = load(SCRIPT, "bj193_v21_test_mapping")
    mapping = freeze.effective_action_mapping()
    assert len(mapping) == 963
    structural = [
        row
        for row in mapping
        if row["mechanism"]
        in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}
    ]
    full = [row for row in mapping if row["mechanism"] == "FULL_ENUMERATED"]
    assert len(structural) == 2
    assert len(full) == 1
    assert {row["weight_source"] for row in structural} == {"NA"}
    assert {row["native_economic_M"] for row in structural} == {1458}
    assert {row["replicate_count"] for row in structural} == {"1"}
    assert {row["replicate_mode"] for row in structural} == {
        "DETERMINISTIC_SINGLETON"
    }
    assert all(row["source_identity_preserved"] is True for row in structural)
    assert {
        row["effective_v21_compatibility_class_key"] for row in structural
    } == {freeze.structural_class_key()}
    assert full[0]["effective_v21_compatibility_class_key"] != (
        freeze.structural_class_key()
    )


def test_structural_coverage_is_complete_for_127_134_and_fails_closed_for_190():
    freeze = load(SCRIPT, "bj193_v21_test_coverage")
    registry = freeze.complete_structural_registry()
    mapping = freeze.effective_action_mapping()
    classes = freeze.compatibility_classes(mapping)
    coverage = freeze.coverage_registry(registry, classes)
    assert len(classes) == 8
    assert len(coverage) == 2_469 * 8
    assert sum(int(row["stage3_action_count"]) for row in coverage) == 2_469 * 963
    structural = [
        row
        for row in coverage
        if row["stage3_compatibility_class_key"] == freeze.structural_class_key()
    ]
    by_issue = {
        issue: [row for row in structural if row["stage1_upstream_issue"] == issue]
        for issue in {127, 134, 190}
    }
    assert by_issue[127] and by_issue[134] and by_issue[190]
    assert {row["compatibility_status"] for row in by_issue[127]} == {"COMPATIBLE"}
    assert {row["compatibility_status"] for row in by_issue[134]} == {"COMPATIBLE"}
    assert "COMPATIBLE" not in {
        row["compatibility_status"] for row in by_issue[190]
    }
    assert any(
        row["reason_code"] == "INCOMPLETE_PRE_EVENT_REGISTRY_COVERAGE_NO_FALLBACK"
        for row in by_issue[190]
    )


def test_structural_adapter_native_same_distinct_missing_mixed_and_ties():
    adapter = load(ADAPTER, "bj193_v21_test_adapter")
    golden = json.loads(
        (PACKAGE / "structural_delete_golden_vectors.json").read_text()
    )
    anchor = golden["native_137_anchor"]
    assert anchor["p_replay"]["delete_match_id"] == anchor[
        "accepted_p_delete"
    ]["delete_match_id"]
    assert anchor["q_replay"]["delete_match_id"] == anchor[
        "accepted_q_delete"
    ]["delete_match_id"]
    assert anchor["p_replay"]["requested_ticket_count"] == 1458
    assert anchor["q_replay"]["requested_ticket_count"] == 1458
    composition = golden["composition"]
    assert composition["same_code_already_absent"]["reason_code"] == (
        "STRUCTURAL_DELETE_ALREADY_ABSENT"
    )
    assert composition["same_code_already_absent"]["requested_ticket_count"] == 1458
    assert composition["distinct_additional_delete"]["requested_ticket_count"] == 972
    assert composition["distinct_additional_delete"]["requested_stake_yuan"] == 1944
    assert composition["missing_registry_row"]["status"] == "UNAVAILABLE"
    assert composition["missing_registry_row"]["requested_stake_yuan"] == 0
    assert golden["tie_fixture"]["expected_p"]["delete_leg_index_zero_based"] == 0
    assert golden["tie_fixture"]["expected_p"]["delete_code"] == "3"
    assert golden["tie_fixture"]["expected_q"]["delete_leg_index_zero_based"] == 0
    assert golden["tie_fixture"]["expected_q"]["delete_code"] == "3"

    tie_rows = [dict(row) for row in golden["tie_fixture"]["rows"]]
    mixed = [dict(row) for row in tie_rows]
    mixed[-1]["issue"] = "999998"
    mixed[-1]["issue_instance"] = "999998@OOS_TEST"
    mixed[-1]["structural_registry_row_sha256"] = (
        adapter.structural_registry_row_identity(mixed[-1])
    )
    valid, reason = adapter.validate_structural_rows(
        [row["match_id"] for row in mixed],
        {row["match_id"]: row for row in mixed},
    )
    assert valid == []
    assert reason == "STRUCTURAL_REGISTRY_MIXED_ISSUE_OR_FOLD"


def test_native_reconciliation_and_package_manifest_are_exact():
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    assert len(manifest) == 16
    for name, expected in manifest.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    reconciliation = json.loads(
        (PACKAGE / "native_137_structural_delete_reconciliation.json").read_text()
    )
    assert reconciliation["role_row_count"] == 501_928
    assert reconciliation["portfolio_count"] == 71_704
    assert reconciliation["p_anchor_match_count"] == 71_704
    assert reconciliation["q_anchor_match_count"] == 71_704
    assert reconciliation["mismatch_count"] == 0
    diagnostic = reconciliation["legacy_137_marker_diagnostic"]
    assert diagnostic["controlling"] is False
    assert diagnostic["q_mismatch_count"] == 1331
