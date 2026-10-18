"""Offline regression checks for the QMD's pinned-input rejection boundary.

Uses deliberately minimal manifests because each case must stop before dataset
reading or parsing. No live NAS, network, raw database or settlement is used.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize(
    ("damage", "error_marker"),
    [("base_manifest", "manifest_path"),
     ("raw_manifest", "asset-manifest.json"),
     ("raw_receipt", "raw-receipts.json")],
)
def test_audit_rejects_changed_pinned_inputs_before_reading_data(tmp_path, damage, error_marker):
    root = Path(__file__).resolve().parents[1]
    qmd = root / "quarto/26098_fundamentals_completeness_20261018.qmd"
    quarto = shutil.which("quarto")
    assert quarto, "Declared Quarto runtime is required for this contract check"
    frozen = tmp_path / "frozen"
    hot = tmp_path / "hot"
    hot.mkdir()
    version = "20261008T143545725496Z"
    base = frozen / "datasets/source_issue_26098/versions" / version / "manifest.json"
    base.parent.mkdir(parents=True)
    base.write_text('{"fixture":"stop-before-reading-dataset"}\n')
    base_hash = hashlib.sha256(base.read_bytes()).hexdigest()
    raw = frozen / "raw"
    raw.mkdir()
    receipt = raw / "raw-receipts.json"
    receipt.write_text('[{"capture_observed_at":"2026-10-07T10:45:10.768941+00:00"}]\n')
    receipt_hash = hashlib.sha256(receipt.read_bytes()).hexdigest()
    manifest = raw / "asset-manifest.json"
    manifest.write_text(json.dumps({
        "dataset": "source_issue_26098", "version": version,
        "base_manifest_sha256": base_hash,
        "members": {"raw-receipts.json": receipt_hash},
    }))
    raw_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
    if damage == "base_manifest":
        base.write_text('{"fixture":"changed"}\n')
    elif damage == "raw_manifest":
        manifest.write_text('{"fixture":"changed"}\n')
    else:
        # Same second and same response identity could otherwise pass the old
        # microsecond-dropping comparison. The pinned receipt SHA must reject it.
        receipt.write_text('[{"capture_observed_at":"2026-10-07T10:45:10.000001+00:00"}]\n')
    copied_qmd = tmp_path / "audit.qmd"
    shutil.copyfile(qmd, copied_qmd)
    env = {**os.environ, "BEIDAN_PARQUET_ROOT": str(frozen),
           "BEIDAN_HOT_ROOT": str(hot), "R_LIBS_USER": str(root / "r_lib"),
           "R_ENVIRON_USER": "/dev/null", "R_PROFILE_USER": "/dev/null"}
    result = subprocess.run(
        [quarto, "render", str(copied_qmd), "-P", f"project_root:{root}",
         "-P", f"manifest_sha256:{base_hash}", "-P", f"raw_manifest_sha256:{raw_hash}",
         "-P", "raw_evidence_relative:raw"],
        cwd=root, env=env, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, timeout=90, check=False,
    )
    assert result.returncode != 0, result.stdout
    assert error_marker in result.stdout, result.stdout
    assert "is not TRUE" in result.stdout, result.stdout
    assert "unnamed-chunk-4" not in result.stdout, result.stdout
    assert not (hot / "26098-fundamentals-completeness-20261018/provenance.csv").exists()
