from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import nbformat
import pandas as pd
import pytest

from model_support_panel.builder import (
    EXPECTED_SOURCE_MANIFEST_SHA256,
    ModelSupportBuildError,
    _build_from_frozen_sources,
    _root_checksums,
    compare_packages,
    verify_package,
    write_json,
    write_parquet,
)
from model_support_panel.contract import CONTRACT_VERSION


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results/bj216_model_support_panel_v1"
EXPECTED_SOURCE_MANIFEST = (
    "ad1060fdee801277b00e6a40c5e28722d9df8fae025e163c4c15ed7b0d32f76b"
)


def test_frozen_artifact_is_outcome_blind_and_negative() -> None:
    assert EXPECTED_SOURCE_MANIFEST_SHA256 == EXPECTED_SOURCE_MANIFEST
    assert verify_package(PACKAGE) == {
        "status": "PASS",
        "contract_version": CONTRACT_VERSION,
        "disposition": "BLOCKED_ACCUMULATE_CAUSAL_SUPPORT",
        "model_ready_for_204": False,
        "eligible_issue_epochs": 24,
        "panel_rows": 5085,
        "outcome_namespace": "PHYSICALLY_ABSENT",
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST,
    }
    decision = json.loads(
        (PACKAGE / "analysis/decision.json").read_text(encoding="utf-8")
    )
    assert decision["accumulation"] == {
        "eligible_issue_epochs": 24,
        "issues_needed_before_development_horizon": 6,
        "issues_needed_before_full_readiness_horizon": 13,
        "next_measurable_condition": (
            "At least 37 chronologically assigned eligible issue epochs, with "
            "each required role meeting the frozen 80% N7 and 80% core "
            "coverage thresholds."
        ),
    }
    development = decision["role_results"][0]
    assert development["n7_issue_pass_rate"] == pytest.approx(20 / 24)
    assert development["core_match_coverage"] == pytest.approx(1695 / 2156)
    assert not (PACKAGE / "labels").exists()
    inventory = pd.read_csv(
        PACKAGE / "sources/source_inventory.csv", keep_default_na=False
    )
    assert inventory.columns.tolist() == [
        "logical_source",
        "filename",
        "bytes",
        "table_name",
        "schema_sha256",
        "value_rows_read",
        "classification",
        "exclusion_reason",
    ]
    excluded = inventory[
        inventory["classification"].eq("SCHEMA_ONLY_EXCLUDED_SOURCE")
    ]
    assert excluded["exclusion_reason"].str.len().gt(0).all()
    assert excluded["value_rows_read"].eq(0).all()


def test_frozen_source_replay_is_byte_identical(tmp_path: Path) -> None:
    replay = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_bj216_model_support_panel.py"),
            "replay",
            "--source-package",
            str(PACKAGE),
            "--output",
            str(replay),
        ],
        cwd=ROOT,
        check=True,
    )
    assert compare_packages(PACKAGE, replay)["status"] == "PASS_IDENTICAL"


def test_verifier_rejects_rehashed_source_attack(tmp_path: Path) -> None:
    attacked = tmp_path / "attacked"
    shutil.copytree(PACKAGE, attacked)
    source = attacked / "sources/selected_snapshots.parquet"
    frame = pd.read_parquet(source)
    frame.loc[0, "sp_3"] = float(frame.loc[0, "sp_3"]) + 0.25
    write_parquet(source, frame)
    source_manifest = json.loads(
        (attacked / "sources/MANIFEST.json").read_text(encoding="utf-8")
    )
    source_manifest["files"]["selected_snapshots.parquet"] = {
        "bytes": source.stat().st_size,
        "sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(),
    }
    write_json(attacked / "sources/MANIFEST.json", source_manifest)
    manifest = json.loads((attacked / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["source_manifest_sha256"] = __import__("hashlib").sha256(
        (attacked / "sources/MANIFEST.json").read_bytes()
    ).hexdigest()
    write_json(attacked / "MANIFEST.json", manifest)
    write_json(attacked / "SHA256SUMS.json", _root_checksums(attacked))
    with pytest.raises(ModelSupportBuildError):
        verify_package(attacked)


def test_verifier_rejects_coherent_full_rehash_source_attack(
    tmp_path: Path,
) -> None:
    matches = pd.read_parquet(PACKAGE / "sources/matches.parquet")
    snapshots = pd.read_parquet(PACKAGE / "sources/selected_snapshots.parquet")
    snapshots.loc[0, "sp_3"] = float(snapshots.loc[0, "sp_3"]) + 0.25
    source_freeze = json.loads(
        (PACKAGE / "sources/source_freeze.json").read_text(encoding="utf-8")
    )
    source_inventory = pd.read_csv(
        PACKAGE / "sources/source_inventory.csv", keep_default_na=False
    )
    with pytest.raises(
        ModelSupportBuildError,
        match="source identity differs from exact package lock",
    ):
        _build_from_frozen_sources(
            tmp_path / "coherent-forgery",
            source_matches=matches,
            source_snapshots=snapshots,
            source_freeze=source_freeze,
            source_inventory=source_inventory,
        )


def test_verifier_rejects_rehashed_decision_attack(tmp_path: Path) -> None:
    attacked = tmp_path / "attacked"
    shutil.copytree(PACKAGE, attacked)
    decision_path = attacked / "analysis/decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["model_ready_for_204"] = True
    decision["disposition"] = "READY_FOR_204_REVIEW"
    write_json(decision_path, decision)
    write_json(attacked / "SHA256SUMS.json", _root_checksums(attacked))
    with pytest.raises(ModelSupportBuildError, match="decision is not derivable"):
        verify_package(attacked)


def test_notebook_is_clean_executed_and_bounded() -> None:
    notebook = nbformat.read(
        ROOT
        / "notebooks/research/issue-216/bj216_causal_p34_model_support.ipynb",
        as_version=4,
    )
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert code and all(cell.execution_count is not None for cell in code)
    assert all(
        output.get("output_type") != "error"
        for cell in code
        for output in cell.outputs
    )
    source = "\n".join("".join(cell.source) for cell in code).lower()
    assert "fit(" not in source
    assert "settlement" not in source
