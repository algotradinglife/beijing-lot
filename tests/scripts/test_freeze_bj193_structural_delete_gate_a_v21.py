from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj193_structural_delete_gate_a_v21.py"
ADAPTER = ROOT / "scripts" / "bj193_structural_delete_adapter.py"
PACKAGE = ROOT / "results" / "bj193_gate_a_chain_interface_v21"
V2_ADAPTER = (
    ROOT
    / "results"
    / "bj193_gate_a_chain_interface_v2"
    / "conditional_chain_adapter.py"
)


def load(path: Path, name: str):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


def assert_no_package_bytecode() -> None:
    for package in (
        PACKAGE,
        ROOT / "results" / "bj193_gate_a_chain_interface_v2",
    ):
        assert not list(package.rglob("__pycache__"))
        assert not list(package.rglob("*.pyc"))


def test_frozen_source_loaders_do_not_mutate_immutable_packages():
    assert_no_package_bytecode()
    freeze = load(SCRIPT, "bj193_v21_test_bytecode_free_freeze")
    freeze.load_module(V2_ADAPTER, "bj193_v21_test_bytecode_free_runner_loader")
    load(V2_ADAPTER, "bj193_v21_test_bytecode_free_test_loader")
    assert_no_package_bytecode()


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
    accepted_v2 = load(V2_ADAPTER, "bj193_v21_test_accepted_v2_adapter")
    assert_no_package_bytecode()
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
    assert anchor["p_replay"]["status"] == "ACTIVE"
    assert anchor["q_replay"]["status"] == "ACTIVE"
    composition = golden["composition"]
    assert composition["same_code_already_absent"]["reason_code"] == (
        "STRUCTURAL_DELETE_ALREADY_ABSENT"
    )
    assert composition["same_code_already_absent"]["requested_ticket_count"] == 1458
    assert composition["distinct_additional_delete"]["requested_ticket_count"] == 972
    assert composition["distinct_additional_delete"]["requested_stake_yuan"] == 1944
    assert composition["missing_registry_row"]["status"] == "UNAVAILABLE"
    assert composition["missing_registry_row"]["requested_stake_yuan"] == 0
    assert composition["stage2_no_bet"]["status"] == "NO_BET"
    assert composition["stage2_no_bet"]["reason_code"] == (
        "STAGE2_NO_BET_ZERO_FLOW"
    )
    assert composition["stage2_no_bet"]["requested_ticket_count"] == 0
    assert composition["stage2_no_bet"]["requested_stake_yuan"] == 0
    assert composition["stage2_unavailable"]["status"] == "UNAVAILABLE"
    assert composition["stage2_unavailable"]["reason_code"] == (
        "STAGE2_UNAVAILABLE_ZERO_FLOW"
    )
    assert composition["stage2_unavailable"]["requested_ticket_count"] == 0
    assert composition["stage2_unavailable"]["requested_stake_yuan"] == 0
    mismatch = composition["registry_trace_issue_mismatch"]
    assert mismatch["status"] == "UNAVAILABLE"
    assert mismatch["reason_code"] == "STRUCTURAL_REGISTRY_TRACE_ISSUE_MISMATCH"
    assert mismatch["requested_ticket_count"] == 0
    assert mismatch["requested_stake_yuan"] == 0

    expected_by_action = {}
    catalog = rows(
        ROOT
        / "results"
        / "bj193_gate_a_chain_interface_v2"
        / "stage3_bet_catalog.csv.gz"
    )
    for row in catalog:
        parameters = json.loads(row["parameters_json"])
        mechanism = parameters["mechanism"]
        if mechanism in {"P_MIN_GLOBAL_DELETE", "Q_MIN_GLOBAL_DELETE"}:
            expected_by_action[mechanism] = accepted_v2.stage3_replay_signature(
                issue=anchor["issue"],
                stage1_output_sha256="1" * 64,
                stage2_output_sha256="2" * 64,
                derived_stage3_action_sha256=row[
                    "derived_interface_identity_sha256"
                ],
            )
    for key in (
        "same_code_already_absent",
        "distinct_additional_delete",
        "stage2_no_bet",
        "stage2_unavailable",
    ):
        assert composition[key]["stage3_replay_signature_sha256"] == (
            expected_by_action["P_MIN_GLOBAL_DELETE"]
        )
    assert anchor["p_replay"]["stage3_replay_signature_sha256"] == (
        expected_by_action["P_MIN_GLOBAL_DELETE"]
    )
    assert anchor["q_replay"]["stage3_replay_signature_sha256"] == (
        expected_by_action["Q_MIN_GLOBAL_DELETE"]
    )
    assert mismatch["stage3_replay_signature_sha256"] == (
        accepted_v2.stage3_replay_signature(
            issue=str(int(str(anchor["issue"])) + 1),
            stage1_output_sha256="1" * 64,
            stage2_output_sha256="2" * 64,
            derived_stage3_action_sha256=next(
                row["derived_interface_identity_sha256"]
                for row in catalog
                if json.loads(row["parameters_json"])["mechanism"]
                == "Q_MIN_GLOBAL_DELETE"
            ),
        )
    )
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


def test_structural_adapter_rejects_malformed_chain_digest():
    adapter = load(ADAPTER, "bj193_v21_test_malformed_digest")
    with pytest.raises(ValueError, match="invalid SHA-256 identity"):
        adapter.compose_structural_delete(
            "P_MIN_GLOBAL_DELETE",
            [str(index) for index in range(7)],
            {"status": "NO_BET"},
            {},
            issue="999999",
            stage1_output_sha256="not-a-digest",
            stage2_output_sha256="2" * 64,
            derived_stage3_action_sha256="3" * 64,
        )


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
