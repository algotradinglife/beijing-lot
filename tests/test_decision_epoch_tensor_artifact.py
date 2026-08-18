from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import nbformat

from decision_epoch_tensor.builder import compare_packages, verify_package


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "results/bj214_decision_epoch_tensor_v1"


def test_artifact_receipts_and_exact_source_lock() -> None:
    receipt = verify_package(PACKAGE)
    source_manifest = PACKAGE / "sources/MANIFEST.json"
    assert receipt["status"] == "PASS"
    assert receipt["source_manifest_sha256"] == (
        "f05e02404a91bb63d2a40c55bbe572964cf681057df72f7c69c6145c4c78572d"
    )
    source_freeze = json.loads(
        (PACKAGE / "sources/source_freeze.json").read_text(encoding="utf-8")
    )
    assert source_freeze["source_freeze_cutoff_utc"] == "2026-08-07T09:59:02Z"
    assert source_freeze["outcome_namespace_read"] is False
    assert source_manifest.is_file()


def test_frozen_source_replay_is_byte_identical(tmp_path: Path) -> None:
    replay = tmp_path / "replay"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_bj214_decision_epoch_tensor.py"),
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


def test_notebook_is_clean_executed_and_bounded() -> None:
    notebook = nbformat.read(
        ROOT / "notebooks/research/issue-214/bj214_decision_epoch_market_sp_coverage.ipynb",
        as_version=4,
    )
    code = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert code and all(cell.execution_count is not None for cell in code)
    assert all(not output.get("output_type") == "error" for cell in code for output in cell.outputs)
    source = "\n".join("".join(cell.source) for cell in code).lower()
    assert "settlement" not in source
    assert "train" not in source
