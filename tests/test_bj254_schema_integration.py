"""Final integration and adversarial checks for Issue #254."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from schema_integration import IntegrationError, build_integration_package, verify_integration_package
from test_bj253_physical_schema import _make_live, _make_xlsm


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rehash(package: Path) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {p.relative_to(package).as_posix(): _hash(p) for p in sorted(package.rglob("*")) if p.is_file() and p.name != "MANIFEST.json"}
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def external_root(tmp_path: Path) -> Path:
    root = tmp_path / "external"
    root.mkdir()
    _make_xlsm(root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite")
    _make_live(root / "beidan_live.db")
    identity = root / "derived" / "bj251_canonical_identity_v3" / "tables"
    identity.mkdir(parents=True)
    pd.DataFrame([
        {"issue_code": issue, "match_idx": idx, "issue_slot_id": f"bjslot:{issue}:{idx:03d}", "fixture_entity_id": None}
        for issue, indices in (("140101", range(1, 5)), ("26001", range(10, 14)))
        for idx in indices
    ]).to_csv(identity / "issue_slot_identity.csv", index=False)
    return root


def test_builds_complete_handoff(external_root: Path) -> None:
    package = build_integration_package(external_root)
    receipt = verify_integration_package(package)
    assert receipt["status"] == "PASS"
    assert receipt["predecessors"] == 4
    assert receipt["downstream_contracts"] == 5


def test_rejects_resigned_predecessor_rewrite(external_root: Path) -> None:
    package = build_integration_package(external_root)
    path = package / "predecessors.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["accepted_commit"] = "0" * 40
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    _rehash(package)
    with pytest.raises(IntegrationError, match="predecessor binding"):
        verify_integration_package(package)


def test_rejects_resigned_missing_downstream_contract(external_root: Path) -> None:
    package = build_integration_package(external_root)
    path = package / "downstream_readiness.csv"
    frame = pd.read_csv(path)
    frame.loc[frame["issue"].ne(237)].to_csv(path, index=False)
    _rehash(package)
    with pytest.raises(IntegrationError, match="downstream contract"):
        verify_integration_package(package)


def test_rejects_label_column_leak_even_after_rehash(external_root: Path) -> None:
    package = build_integration_package(external_root)
    features = package / "normalized_snapshot" / "features" / "m3_feature_cells.parquet"
    frame = pd.read_parquet(features)
    frame["result_code"] = "3"
    frame.to_parquet(features, index=False)
    _rehash(package / "normalized_snapshot")
    _rehash(package)
    with pytest.raises(Exception, match="schema mismatch|prohibited"):
        verify_integration_package(package)
