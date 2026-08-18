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

from schema_integration import (  # noqa: E402
    IntegrationError,
    build_integration_package,
    verify_integration_package,
)
from test_bj253_physical_schema import _make_live, _make_xlsm  # noqa: E402


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rehash(package: Path) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {
        p.relative_to(package).as_posix(): _hash(p)
        for p in sorted(package.rglob("*"))
        if p.is_file() and p != package / "MANIFEST.json"
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def external_root(tmp_path: Path) -> Path:
    root = tmp_path / "external"
    root.mkdir()
    xlsm = root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    _make_xlsm(xlsm)
    with sqlite3.connect(xlsm) as connection:
        for offset, issue in enumerate(("150101", "160101", "170101"), start=1):
            match_id = 100 + offset
            year = 2014 + offset
            connection.execute(
                "INSERT INTO matches VALUES (?,?,?,?,?)",
                (match_id, issue, 1, f"{year}-01-01 13:00:00", 0.0),
            )
            for snapshot, bump in (("initial", 0.0), ("10h", 0.1), ("1h", 0.2)):
                connection.execute(
                    "INSERT INTO market_consensus VALUES (?,?,?,?,?,?)",
                    (match_id, "euro_1x2", snapshot, 2.0 + bump, 3.0 + bump, 4.0 + bump),
                )
            connection.execute(
                "INSERT INTO official_500_settlements VALUES (?,?,?,?,?,?)",
                (issue, 1, "3", 3.0, f"{year}-01-02 12:00:00", f"hash-{issue}"),
            )
        connection.commit()
    _make_live(root / "beidan_live.db")
    identity = root / "derived" / "bj251_canonical_identity_v3" / "tables"
    identity.mkdir(parents=True)
    pd.DataFrame([
        {"issue_code": issue, "match_idx": idx, "issue_slot_id": f"bjslot:{issue}:{idx:03d}", "fixture_entity_id": None}
        for issue, indices in (
            ("140101", range(1, 5)),
            ("150101", (1,)),
            ("160101", (1,)),
            ("170101", (1,)),
            ("26001", range(10, 14)),
        )
        for idx in indices
    ]).to_csv(identity / "issue_slot_identity.csv", index=False)
    return root


def test_builds_complete_handoff(external_root: Path) -> None:
    package = build_integration_package(external_root)
    receipt = verify_integration_package(package)
    assert receipt["status"] == "PASS"
    assert receipt["predecessors"] == 4
    assert receipt["downstream_contracts"] == 5
    assert receipt["dictionary_fields"] > 0
    assert receipt["replay_receipt"]["historical_proxy_years"] == [2014, 2015, 2016, 2017]
    assert receipt["replay_receipt"]["byte_deterministic_replay"] is True
    readiness = pd.read_csv(package / "downstream_readiness.csv")
    assert readiness.loc[readiness["issue"].eq(235), "model_data_readiness"].item() == "RECOVERY_REQUIRED"
    assert readiness.loc[readiness["issue"].eq(237), "execution_readiness"].item() == "PI_SCOPE_REVIEW"


def test_rejects_resigned_predecessor_rewrite(external_root: Path) -> None:
    package = build_integration_package(external_root)
    path = package / "predecessors.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows[0]["accepted_head"] = "0" * 40
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


def test_rejects_resigned_data_dictionary_rewrite(external_root: Path) -> None:
    package = build_integration_package(external_root)
    path = package / "data_dictionary.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "semantic_boundary"] = "post_outcome_label"
    frame.to_csv(path, index=False)
    _rehash(package)
    with pytest.raises(IntegrationError, match="data dictionary"):
        verify_integration_package(package)


def test_rejects_resigned_replay_receipt_rewrite(external_root: Path) -> None:
    package = build_integration_package(external_root)
    path = package / "replay_receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["historical_proxy_years"] = [2014]
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["replay_receipt"] = receipt
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _rehash(package)
    with pytest.raises(IntegrationError, match="replay/restore"):
        verify_integration_package(package)
