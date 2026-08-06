from pathlib import Path
import shutil

import nbformat
import pandas as pd
import pytest

from scripts.execute_bj203_notebook import execute_notebook
from unified_tensor.builder import (
    TensorBuildError,
    build_inference,
    compare_inference_replay,
    digest,
    verify_package,
)
from unified_tensor.contract import HELDOUT_ISSUES
from unified_tensor.settlement_labels import load_development_labels


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results/bj203_causal_tensor_v1"


def test_frozen_bj203_artifact_verifies_exact_census() -> None:
    assert verify_package(PACKAGE) == {
        "contract_version": "bj203-causal-tensor-v1",
        "issues": 344,
        "matches": 102_245,
        "cells": 306_735,
        "features": 24,
        "development_label_cells": 303_663,
        "heldout_issues": 2,
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
