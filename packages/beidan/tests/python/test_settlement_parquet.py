"""Offline tests for the settlement Parquet conversion and its manifest contract."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from beidan_backend.datasets import settlement_parquet as sp

SOURCE_DDL = """
CREATE TABLE observation(observation_id INTEGER PRIMARY KEY, issue TEXT, slot INTEGER, play TEXT,
  native_match_id TEXT, status TEXT, score TEXT, halftime_score TEXT, expected_option TEXT,
  source_sha256 TEXT, source_url TEXT, received_at TEXT, payload_json TEXT);
CREATE TABLE option_sp(observation_id INTEGER, option TEXT, raw_sp TEXT, sp REAL, cell_id TEXT);
CREATE TABLE receipt(payload_json TEXT);
CREATE TABLE sp_correction_batch(batch_id TEXT PRIMARY KEY, applied_at TEXT, note TEXT,
  row_count INTEGER, original_receipt_json TEXT, ledger_json TEXT, raw_html BLOB, backup_path TEXT);
INSERT INTO observation VALUES
 (1,'090918',1,'spf','11','完场','2:0','1:0','胜','aa','u','2026-01-01T00:00:00+00:00','{"a":1}'),
 (2,'26095',2,'jq','22','完场','1:1',NULL,NULL,'bb','u','2026-01-01T00:00:00+00:00',NULL),
 (3,'26095',3,'bf','33','取消','',NULL,NULL,'cc','u','2026-01-01T00:00:00+00:00',NULL);
INSERT INTO option_sp VALUES
 (1,'胜','1.76',1.76,'c1'),(1,'平','3.4',3.4,'c3'),(2,'1球','4.1',4.1,'c3');
INSERT INTO receipt VALUES ('{"k":1}');
INSERT INTO sp_correction_batch VALUES ('b1','2026-01-01','n',3,'{}','{}',X'00FF','/b');
"""


def _make_source(tmp_path: Path) -> Path:
    database = tmp_path / "source.sqlite"
    conn = sqlite3.connect(database)
    conn.executescript(SOURCE_DDL)
    conn.commit()
    conn.close()
    return database


def _convert(tmp_path: Path, **kwargs) -> tuple[dict, Path]:
    database = _make_source(tmp_path)
    root = tmp_path / "root"
    (root / "tmp").mkdir(parents=True)
    manifest = sp.convert_settlement(
        database=database, output_root=root, version="fixture-v1",
        source_registry={"version": "fixture-v1"},
        generated_at="2026-10-04T00:00:00+00:00", **kwargs)
    return manifest, root / "datasets/settlement/versions/fixture-v1"


def test_issue_year_handles_both_eras_and_invalid():
    assert sp.issue_year("26095") == 2026
    assert sp.issue_year("090918") == 2009
    assert sp.issue_year("X") is None
    assert sp.issue_year("") is None
    assert sp.issue_year(None) is None


def test_conversion_preserves_row_counts_and_partitions(tmp_path):
    manifest, version_dir = _convert(tmp_path)
    assert manifest["row_counts"] == {
        "observation": 3, "option_sp": 3, "receipt": 1, "sp_correction_batch": 1}
    assert manifest["partition_by"] == "issue_year"
    # observation and option_sp are partitioned; receipt is whole.
    obs = sorted(p.name for p in (version_dir / "tables/observation").iterdir())
    assert obs == ["part-issue-year=2009.parquet", "part-issue-year=2026.parquet"]
    assert (version_dir / "tables/receipt.parquet").is_file()
    assert manifest["tables"]["option_sp"]["partitions"] == 2
    assert manifest["tables"]["receipt"]["kind"] == "whole"


def test_binary_columns_stay_binary(tmp_path):
    import pyarrow.parquet as pq

    _manifest, version_dir = _convert(tmp_path)
    table = pq.read_table(version_dir / "tables/sp_correction_batch.parquet")
    assert str(table.schema.field("raw_html").type) == "binary"
    assert table.column("raw_html").to_pylist() == [b"\x00\xff"]


def test_manifest_binds_source_hash_and_verifies(tmp_path):
    manifest, version_dir = _convert(tmp_path)
    assert len(manifest["source"]["sha256"]) == 64
    assert manifest["converter"]["sha256"]
    loaded = json.loads((version_dir / "manifest.json").read_text(encoding="utf-8"))
    assert loaded["schema"] == "beijing_lot_parquet_dataset_v1"
    result = sp.verify_manifest(version_dir)
    assert result["ok"] is True and result["tables"] == 4


def test_verify_detects_tampering(tmp_path):
    _manifest, version_dir = _convert(tmp_path)
    target = version_dir / "tables/receipt.parquet"
    target.write_bytes(target.read_bytes() + b"tamper")
    result = sp.verify_manifest(version_dir)
    assert result["ok"] is False
    assert any(p.endswith("receipt.parquet") for p in result["mismatches"])


def test_reconversion_is_idempotent_and_refuses_new_content(tmp_path):
    _manifest, version_dir = _convert(tmp_path)
    database = tmp_path / "source.sqlite"
    root = tmp_path / "root"

    # identical content: republishing the same label is a no-op, not an error
    again = sp.convert_settlement(
        database=database, output_root=root, version="fixture-v1")
    assert again["version"] == "fixture-v1"
    assert version_dir.is_dir()

    # different content under a finalized label is refused
    conn = sqlite3.connect(database)
    conn.execute("INSERT INTO receipt VALUES ('{\"k\":2}')")
    conn.commit()
    conn.close()
    with pytest.raises(sp.DatasetConversionError, match="already published with different content"):
        sp.convert_settlement(database=database, output_root=root, version="fixture-v1")


def test_missing_source_and_missing_root_fail_closed(tmp_path):
    root = tmp_path / "root"
    (root / "tmp").mkdir(parents=True)
    with pytest.raises(sp.DatasetConversionError, match="source database is absent"):
        sp.convert_settlement(database=tmp_path / "nope.sqlite", output_root=root, version="v")
    with pytest.raises(sp.DatasetConversionError, match="output root is not available"):
        sp.convert_settlement(
            database=_make_source(tmp_path), output_root=tmp_path / "absent", version="v")
