import json
from pathlib import Path
import shutil

import nbformat
import pandas as pd
import pytest

from scripts.execute_bj203_notebook import execute_notebook
from unified_tensor.builder import (
    _decision_report,
    _downstream_readiness,
    _load_inputs,
    _namespace_manifest,
    TensorBuildError,
    build_inference,
    compare_inference_replay,
    digest,
    verify_package,
    verify_superseded_package,
    write_json,
    write_csv,
    write_parquet,
)
from unified_tensor.contract import FEATURE_NAMES, HELDOUT_ISSUES, HELDOUT_2026_ISSUES
from unified_tensor.inference import load_issue_tensors
from unified_tensor.settlement_labels import load_development_labels


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results/bj203_causal_tensor_v2"
SUPERSEDED_PACKAGE = ROOT / "results/bj203_causal_tensor_v1"


def test_superseded_bj203_v1_remains_byte_verifiable() -> None:
    assert verify_superseded_package(SUPERSEDED_PACKAGE) == {
        "contract_version": "bj203-causal-tensor-v1",
        "exact_head": "38dc5ae1223a96cf361db851215143bd73afb05d",
        "files": 25,
        "status": "SUPERSEDED_EVIDENCE_PASS",
    }


def test_frozen_bj203_artifact_verifies_exact_census() -> None:
    assert verify_package(PACKAGE) == {
        "contract_version": "bj203-causal-tensor-v2",
        "issues": 394,
        "matches": 110_906,
        "cells": 332_718,
        "features": 24,
        "development_label_cells": 303_663,
        "heldout_issues": 52,
        "heldout_label_cells": 0,
        "status": "PASS",
    }


def test_frozen_bj203_heldout_namespace_is_identity_only() -> None:
    labels = load_development_labels(PACKAGE)
    assert set(labels["issue"].astype(str)).isdisjoint(HELDOUT_ISSUES)
    assert not list((PACKAGE / "labels").glob("*heldout*"))
    registry = pd.read_csv(PACKAGE / "audit/heldout_registry.csv", dtype=str)
    assert tuple(registry["issue"]) == HELDOUT_ISSUES
    assert set(registry["label_status"]) == {"ABSENT_BY_CONTRACT"}
    assert tuple(registry.tail(50)["issue"]) == HELDOUT_2026_ISSUES
    assert set(registry.tail(17)["identity_timing_statuses"]) == {
        "TIMESTAMPED_IDENTITY_ONLY"
    }


def test_frozen_bj203_2026_extension_is_decision_feature_empty() -> None:
    tensors = load_issue_tensors(PACKAGE, issues=HELDOUT_2026_ISSUES)
    permitted = {
        "outcome_code_numeric",
        "kickoff_delay_hours",
        "match_position_fraction",
        "calendar_year",
    }
    forbidden_indices = [
        index for index, feature in enumerate(FEATURE_NAMES) if feature not in permitted
    ]
    assert len(tensors) == 50
    assert all(not tensor.masks[:, :, forbidden_indices].any() for tensor in tensors)
    extension = pd.read_parquet(PACKAGE / "sources/heldout_match_identity.parquet")
    assert len(extension) == 8_661
    assert tuple(extension["issue"].drop_duplicates()) == HELDOUT_2026_ISSUES


def test_frozen_bj203_heldout_source_identity_rejects_tamper(tmp_path: Path) -> None:
    source = PACKAGE / "sources/heldout_match_identity.parquet"
    tampered = pd.read_parquet(source)
    tampered.loc[0, "identity_source"] = "tampered"
    tampered_path = tmp_path / source.name
    write_parquet(tampered_path, tampered)
    with pytest.raises(TensorBuildError, match="held-out identity extension hash"):
        _load_inputs(
            None,
            PACKAGE / "sources/unavailable_match_identity.parquet",
            heldout_identity_extension=tampered_path,
        )


def test_frozen_bj203_blocks_downstream_market_learner() -> None:
    readiness = json.loads(
        (PACKAGE / "analysis/downstream_readiness.json").read_text(encoding="utf-8")
    )
    assert readiness["decision"] == "BLOCKED_PENDING_DATA_CAPABILITY"
    assert readiness["downstream_issue"] == 204
    assert (
        readiness["required_data_capability"]["proposed_contract_id"]
        == "BJ-UNIFIED-MARKET-COVERAGE-001"
    )


def test_frozen_bj203_readiness_rejects_semantic_rehash_attack(
    tmp_path: Path,
) -> None:
    attacked = tmp_path / "package"
    shutil.copytree(PACKAGE, attacked)
    readiness_path = attacked / "analysis/downstream_readiness.json"
    report_path = attacked / "analysis/DECISION_REPORT.md"
    coverage_path = attacked / "audit/feature_coverage.csv"
    manifest_path = attacked / "MANIFEST.json"
    sums_path = attacked / "SHA256SUMS.json"

    coverage = pd.read_csv(coverage_path)
    coverage["present_cells"] = coverage["total_cells"]
    coverage["coverage_rate"] = 1.0
    write_csv(coverage_path, coverage)
    readiness = _downstream_readiness(coverage)
    write_json(readiness_path, readiness)
    report_path.write_text(
        _decision_report(readiness), encoding="utf-8", newline="\n"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["downstream_readiness_sha256"] = digest(readiness_path)
    manifest["decision_report_sha256"] = digest(report_path)
    write_json(manifest_path, manifest)
    sums = json.loads(sums_path.read_text(encoding="utf-8"))
    sums["audit/feature_coverage.csv"] = digest(coverage_path)
    sums["analysis/downstream_readiness.json"] = digest(readiness_path)
    sums["analysis/DECISION_REPORT.md"] = digest(report_path)
    sums["MANIFEST.json"] = digest(manifest_path)
    write_json(sums_path, sums)

    with pytest.raises(
        TensorBuildError,
        match="feature coverage does not match inference masks",
    ):
        verify_package(attacked)


def test_frozen_bj203_features_reject_full_manifest_rehash_attack(
    tmp_path: Path,
) -> None:
    attacked = tmp_path / "package"
    shutil.copytree(PACKAGE, attacked)
    values_path = attacked / "inference/feature_values.parquet"
    namespace_manifest_path = attacked / "inference/MANIFEST.json"
    root_manifest_path = attacked / "MANIFEST.json"
    sums_path = attacked / "SHA256SUMS.json"

    values = pd.read_parquet(values_path)
    values.loc[:2, "fundamental_probability"] = [0.25, 0.25, 0.5]
    write_parquet(values_path, values)
    _namespace_manifest(attacked / "inference", "outcome_unexposed_inference")
    root_manifest = json.loads(root_manifest_path.read_text(encoding="utf-8"))
    root_manifest["inference_namespace_manifest_sha256"] = digest(
        namespace_manifest_path
    )
    write_json(root_manifest_path, root_manifest)
    sums = json.loads(sums_path.read_text(encoding="utf-8"))
    sums["inference/feature_values.parquet"] = digest(values_path)
    sums["inference/MANIFEST.json"] = digest(namespace_manifest_path)
    sums["MANIFEST.json"] = digest(root_manifest_path)
    write_json(sums_path, sums)

    with pytest.raises(
        TensorBuildError,
        match="package feature values differ from frozen sources",
    ):
        verify_package(attacked)


def test_frozen_bj203_masks_every_snapshot_after_issue_cutoff() -> None:
    leakage = pd.read_csv(PACKAGE / "audit/leakage_audit.csv")
    assert int(leakage["source_after_cutoff_cells"].max()) > 0
    assert int(leakage["unmasked_after_cutoff_cells"].sum()) == 0
    assert set(leakage["cutoff_check"]) == {"PASS"}


def test_frozen_bj203_retains_all_unavailable_match_rows() -> None:
    extension = pd.read_parquet(PACKAGE / "sources/unavailable_match_identity.parquet")
    assert len(extension) == 275
    assert extension["extension_status"].value_counts().to_dict() == {
        "MISSING_NATIVE_LINE": 252,
        "MISSING_1H_EURO": 18,
        "MISSING_1H_EURO;MISSING_NATIVE_LINE": 3,
        "MISSING_TEAM_IDENTITY;MISSING_1H_EURO": 2,
    }


def test_bj203_notebook_is_executed_and_error_free() -> None:
    notebook_path = (
        ROOT / "notebooks/research/issue-203/bj203_causal_tensor_contract.ipynb"
    )
    notebook = nbformat.read(notebook_path, as_version=4)
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert [cell.execution_count for cell in code_cells] == list(
        range(1, len(code_cells) + 1)
    )
    assert all(
        output.output_type != "error"
        for cell in code_cells
        for output in cell.outputs
    )
    assert any(
        output.output_type == "display_data" and "image/png" in output.data
        for cell in code_cells
        for output in cell.outputs
    )


def test_bj203_notebook_clean_execution_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    frozen = ROOT / "notebooks/research/issue-203/bj203_causal_tensor_contract.ipynb"
    replay = tmp_path / frozen.name
    shutil.copyfile(frozen, replay)
    execute_notebook(replay)
    assert digest(replay) == digest(frozen)


def test_bj203_detached_inference_replay_is_byte_identical(tmp_path: Path) -> None:
    replay = tmp_path / "replay"
    build_inference(
        replay,
        identity_extension=(
            PACKAGE / "sources/unavailable_match_identity.parquet"
        ),
        heldout_identity_extension=(
            PACKAGE / "sources/heldout_match_identity.parquet"
        ),
    )
    assert compare_inference_replay(PACKAGE, replay)["status"] == (
        "BYTE_IDENTICAL_PASS"
    )
    payload = replay / "inference/cell_identity.parquet"
    payload.unlink()
    payload.symlink_to(PACKAGE / "inference/cell_identity.parquet")
    with pytest.raises(TensorBuildError, match="must not use symlinks"):
        compare_inference_replay(PACKAGE, replay)


def test_bj203_replay_comparison_rejects_hardlink_alias(tmp_path: Path) -> None:
    frozen = tmp_path / "frozen"
    replay = tmp_path / "replay"
    frozen.mkdir()
    replay.mkdir()
    frozen_schema = frozen / "schema.json"
    frozen_schema.write_text("{}\n", encoding="utf-8")
    (replay / "schema.json").hardlink_to(frozen_schema)
    with pytest.raises(TensorBuildError, match="must not alias frozen files"):
        compare_inference_replay(frozen, replay)
