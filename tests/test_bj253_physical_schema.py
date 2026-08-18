"""Focused contract tests for Issue #253's prototype physical layer."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import sys

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from physical_schema import (  # noqa: E402
    build_representative_package,
    load_feature_cells,
    resolve_data_root,
    verify_package,
)
from physical_schema.builder import PhysicalSchemaError, _file_inventory  # noqa: E402
from physical_schema.contract import feature_schema  # noqa: E402


def _make_xlsm(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY,
                issue TEXT,
                match_idx INTEGER,
                kickoff_ts TEXT,
                handicap_line_norm REAL
            );
            CREATE TABLE market_consensus (
                match_id INTEGER, market TEXT, snapshot TEXT,
                v1_avg REAL, v2_avg REAL, v3_avg REAL
            );
            CREATE TABLE official_500_settlements (
                issue TEXT, match_idx INTEGER, result_code TEXT,
                winning_sp REAL, fetched_at TEXT, raw_row_hash TEXT
            );
            """
        )
        for match_idx in range(1, 5):
            connection.execute(
                "INSERT INTO matches VALUES (?,?,?,?,?)",
                (match_idx, "140101", match_idx, f"2014-01-01 {12 + match_idx}:00:00", 0.0),
            )
            for snapshot, bump in (("initial", 0.0), ("10h", 0.1), ("1h", 0.2)):
                connection.execute(
                    "INSERT INTO market_consensus VALUES (?,?,?,?,?,?)",
                    (
                        match_idx,
                        "euro_1x2",
                        snapshot,
                        2.0 + bump,
                        3.0 + bump,
                        4.0 + bump,
                    ),
                )
            connection.execute(
                "INSERT INTO official_500_settlements VALUES (?,?,?,?,?,?)",
                (
                    "140101",
                    match_idx,
                    ("3", "1", "0", "3")[match_idx - 1],
                    2.0 + match_idx,
                    "2014-01-02 12:00:00",
                    f"hash-{match_idx}",
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _make_live(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE matches (
                match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,
                kickoff_ts TEXT, handicap_line REAL, fid TEXT
            );
            CREATE TABLE snapshots (
                match_id TEXT, snapshot_ts TEXT,
                sp_3 REAL, sp_1 REAL, sp_0 REAL,
                eu_h REAL, eu_d REAL, eu_a REAL
            );
            """
        )
        for offset, match_idx in enumerate(range(10, 14)):
            match_id = f"26001_{match_idx:03d}"
            connection.execute(
                "INSERT INTO matches VALUES (?,?,?,?,?,?)",
                (match_id, "26001", match_idx, "2026-01-01T12:00:00", 0.0, f"fid-{match_idx}"),
            )
            sp = (2.0, 3.0, 4.0) if offset < 3 else (2.0, None, None)
            connection.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?)",
                (match_id, "2026-01-01T00:00:00Z", *sp, 2.2, 3.2, 4.2),
            )
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def external_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    _make_xlsm(root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite")
    _make_live(root / "beidan_live.db")
    identity_dir = root / "derived" / "bj251_canonical_identity_v3" / "tables"
    identity_dir.mkdir(parents=True)
    rows = []
    for issue, indices in (("140101", range(1, 5)), ("26001", range(10, 14))):
        for match_idx in indices:
            rows.append(
                {
                    "issue_code": issue,
                    "match_idx": match_idx,
                    "issue_slot_id": f"bjslot:{issue}:{match_idx:03d}",
                    "fixture_entity_id": None,
                }
            )
    pd.DataFrame(rows).to_csv(identity_dir / "issue_slot_identity.csv", index=False)
    return root


def _rehash(package: Path) -> None:
    manifest_path = package / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = _file_inventory(package)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_build_verify_and_profile_realistic_slice(external_root: Path) -> None:
    package = build_representative_package(external_root)
    result = verify_package(package)
    assert result == {
        "status": "PASS",
        "issue_slots": 8,
        "issues": 2,
        "observations": 16,
        "feature_cells": 60,
        "available_feature_cells": 58,
        "missing_feature_cells": 2,
        "settlement_labels": 4,
        "namespace_feature_cells": {"historical_proxy": 36, "strict_forward": 24},
        "feature_name_cells": {"bj_sp": 12, "eu_decimal_odds": 48},
    }


def test_feature_reader_has_no_settlement_surface(external_root: Path) -> None:
    package = build_representative_package(external_root)
    features = load_feature_cells(package)
    assert not {"result_code", "winning_sp", "settled_at_utc"}.intersection(features.columns)
    control = sqlite3.connect(package / "control.sqlite")
    try:
        tables = {row[0] for row in control.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        control.close()
    assert "settlement_label" not in tables
    assert (package / "labels" / "labels.sqlite").exists()


def test_proxy_and_strict_namespaces_cannot_pool_silently(external_root: Path) -> None:
    package = build_representative_package(external_root)
    path = package / "features" / "m3_feature_cells.parquet"
    frame = pd.read_parquet(path)
    strict_index = frame.index[frame["namespace"].eq("strict_forward")][0]
    frame.loc[strict_index, "observed_at_utc"] = pd.NaT
    pq.write_table(
        pa.Table.from_pandas(frame, schema=feature_schema(), preserve_index=False), path
    )
    _rehash(package)
    with pytest.raises(PhysicalSchemaError, match="strict-forward feature lacks observed_at"):
        verify_package(package)


def test_missing_values_remain_masked_not_zero(external_root: Path) -> None:
    package = build_representative_package(external_root)
    features = load_feature_cells(package)
    missing = features.loc[~features["availability_mask"]]
    assert len(missing) == 2
    assert missing["value"].isna().all()
    assert missing["missing_reason"].eq("SOURCE_VALUE_MISSING_OR_INVALID").all()


def test_sqlite_enforces_three_outcome_domain(external_root: Path) -> None:
    package = build_representative_package(external_root)
    connection = sqlite3.connect(package / "control.sqlite")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO outcome_cell VALUES (?,?,?,?)",
                (
                    "bad-cell",
                    "bjplay:140101:001:BJ_HANDICAP_3WAY",
                    "bjslot:140101:001",
                    "X",
                ),
            )
    finally:
        connection.close()


def test_external_root_is_explicit_and_absolute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEIJING_LOT_DATA_ROOT", raising=False)
    with pytest.raises(PhysicalSchemaError, match="is required"):
        resolve_data_root()
    with pytest.raises(PhysicalSchemaError, match="must be absolute"):
        resolve_data_root("relative/data")
