"""Focused outcome-boundary and chronology tests for #204 Gate A."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import nbformat
import pandas as pd

from unified_model.contract import (
    CONTRACT_VERSION,
    DEVELOPMENT_YEARS,
    EMBARGO_START_YEAR,
    RETROSPECTIVE_TEST_YEAR,
)
from unified_model.gate_a import build_package, verify_package
from scripts.freeze_bj204_model_gate_a import _atomic_build
from scripts.execute_bj204_notebook import execute_notebook


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results/bj203_causal_tensor_v2"
FROZEN = ROOT / "results/bj204_gate_a_preoutcome_v1"


def test_bj204_gate_a_freezes_chronology_without_opening_labels(tmp_path: Path) -> None:
    package = tmp_path / "gate-a"
    receipt = build_package(package, source_package=SOURCE)

    assert receipt["status"] == "GATE_A_OUTCOME_UNEXPOSED_PASS"
    assert verify_package(package)["status"] == "PASS"
    assert not list(package.rglob("*label*"))

    splits = pd.read_csv(package / "split_manifest.csv", dtype={"issue": str})
    assert not splits["labels_permitted_gate_a"].astype(str).str.lower().eq("true").any()
    assert set(splits.loc[splits.role.eq("DEVELOPMENT"), "year"]) == set(DEVELOPMENT_YEARS)
    assert set(splits.loc[splits.role.eq("RETROSPECTIVE_TEST_LOCKED"), "year"]) == {
        RETROSPECTIVE_TEST_YEAR
    }
    assert splits.loc[splits.role.eq("RETROSPECTIVE_TEST_LOCKED"), "labels_permitted_gate_b"].all()
    assert splits.loc[splits.role.eq("EMBARGOED_FOR_210"), "year"].ge(EMBARGO_START_YEAR).all()

    card = json.loads((package / "freeze_card.json").read_text(encoding="utf-8"))
    assert card["contract_version"] == CONTRACT_VERSION
    assert card["source"]["labels_opened"] is False
    assert card["fallback"]["on_rejection"] == "emit explicit NO_BET_FROZEN; never emit a learned vector"
    assert card["chronology"]["retrospective_test_issue_count"] > 0


def test_bj204_gate_a_is_deterministic_and_records_cv_before_test(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    build_package(first, source_package=SOURCE)
    build_package(second, source_package=SOURCE)

    assert (first / "SHA256SUMS.json").read_bytes() == (second / "SHA256SUMS.json").read_bytes()
    assert (first / "CONTENT_IDENTITY.json").read_bytes() == (second / "CONTENT_IDENTITY.json").read_bytes()
    assert (first / "SHA256SUMS.json").read_bytes() == (FROZEN / "SHA256SUMS.json").read_bytes()
    assert (first / "CONTENT_IDENTITY.json").read_bytes() == (FROZEN / "CONTENT_IDENTITY.json").read_bytes()
    cv = pd.read_csv(first / "cv_manifest.csv")
    assert set(cv["test_year"]) == {RETROSPECTIVE_TEST_YEAR}
    assert not cv["test_labels_opened"].any()
    for row in cv.itertuples(index=False):
        assert all(int(year) < int(row.validation_year) for year in str(row.train_years).split(";"))


def test_bj204_atomic_wrapper_accepts_an_empty_stage_directory(tmp_path: Path) -> None:
    output = tmp_path / "immutable-package"
    receipt = _atomic_build(output, SOURCE)
    assert receipt["package"] == output.name
    assert verify_package(output)["status"] == "PASS"


def test_bj204_notebook_is_executed_and_clean_replay_is_deterministic(tmp_path: Path) -> None:
    frozen = ROOT / "notebooks/research/issue-204/bj204_track_a_gate_a.ipynb"
    notebook = nbformat.read(frozen, as_version=4)
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert [cell.execution_count for cell in code] == list(range(1, len(code) + 1))
    assert not [
        output
        for cell in code
        for output in cell.outputs
        if output.output_type == "error"
    ]
    replay = tmp_path / frozen.name
    shutil.copyfile(frozen, replay)
    execute_notebook(replay)
    assert replay.read_bytes() == frozen.read_bytes()
