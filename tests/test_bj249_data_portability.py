from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_portability import create_snapshot, restore_snapshot, verify_snapshot  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(root: Path) -> Path:
    database = root / "data" / "sample.sqlite"
    database.parent.mkdir(parents=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE events(id INTEGER PRIMARY KEY, observed_at TEXT, value REAL)")
    connection.executemany(
        "INSERT INTO events(observed_at,value) VALUES(?,?)",
        [("2025-01-01T00:00:00Z", 1.0), ("2026-01-01T00:00:00Z", 2.0)],
    )
    connection.commit()
    connection.close()
    raw = root / "data" / "raw" / "source.txt"
    raw.parent.mkdir(parents=True)
    raw.write_text("raw-evidence\n", encoding="utf-8")
    return database


def _config(root: Path, *, missing: bool = False) -> Path:
    config = root / "config.json"
    config.write_text(
        json.dumps(
            {
                "assets": [
                    {
                        "kind": "sqlite",
                        "path": "data/missing.sqlite" if missing else "data/sample.sqlite",
                        "time_columns": [{"table": "events", "column": "observed_at"}],
                    },
                    {"kind": "tree", "path": "data/raw"},
                ]
            }
        ),
        encoding="utf-8",
    )
    return config


def test_snapshot_verify_restore_roundtrip_preserves_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    database = _source(source_root)
    before = (_sha(database), database.stat().st_mtime_ns)
    external = tmp_path / "external"
    snapshot = create_snapshot(
        config_path=_config(source_root), source_root=source_root,
        external_root=external, snapshot_id="sample-v1",
    )
    verification = verify_snapshot(snapshot)
    assert verification["status"] == "PASS"
    assert verification["asset_count"] == 2
    restored = tmp_path / "restored"
    receipt = restore_snapshot(snapshot_path=snapshot, target=restored)
    assert receipt["restored_asset_count"] == 2
    assert _sha(restored / "data/sample.sqlite") == _sha(snapshot / "data/sample.sqlite")
    assert (restored / "data/raw/source.txt").read_text() == "raw-evidence\n"
    assert (_sha(database), database.stat().st_mtime_ns) == before


def test_sqlite_receipt_binds_rows_schema_and_time_range(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _source(source_root)
    snapshot = create_snapshot(
        config_path=_config(source_root), source_root=source_root,
        external_root=tmp_path / "external", snapshot_id="sample-v1",
    )
    manifest = json.loads((snapshot / "MANIFEST.json").read_text())
    database = next(asset for asset in manifest["assets"] if asset["kind"] == "sqlite")
    assert database["sqlite"]["integrity_check"] == "ok"
    assert database["sqlite"]["row_counts"] == {"events": 2}
    assert database["sqlite"]["time_ranges"][0]["minimum"] == "2025-01-01T00:00:00Z"
    assert database["sqlite"]["time_ranges"][0]["maximum"] == "2026-01-01T00:00:00Z"


def test_tamper_is_rejected_before_restore_target_is_exposed(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _source(source_root)
    snapshot = create_snapshot(
        config_path=_config(source_root), source_root=source_root,
        external_root=tmp_path / "external", snapshot_id="sample-v1",
    )
    with (snapshot / "data/raw/source.txt").open("ab") as handle:
        handle.write(b"tamper")
    target = tmp_path / "restored"
    with pytest.raises(ValueError, match="(size|hash) mismatch"):
        restore_snapshot(snapshot_path=snapshot, target=target)
    assert not target.exists()


def test_failed_snapshot_never_publishes_final_directory(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _source(source_root)
    external = tmp_path / "external"
    with pytest.raises(FileNotFoundError):
        create_snapshot(
            config_path=_config(source_root, missing=True), source_root=source_root,
            external_root=external, snapshot_id="broken-v1",
        )
    assert not (external / "snapshots/broken-v1").exists()


def test_existing_snapshot_and_restore_targets_fail_closed(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _source(source_root)
    external = tmp_path / "external"
    snapshot = create_snapshot(
        config_path=_config(source_root), source_root=source_root,
        external_root=external, snapshot_id="sample-v1",
    )
    with pytest.raises(FileExistsError):
        create_snapshot(
            config_path=_config(source_root), source_root=source_root,
            external_root=external, snapshot_id="sample-v1",
        )
    target = tmp_path / "restored"
    target.mkdir()
    with pytest.raises(FileExistsError):
        restore_snapshot(snapshot_path=snapshot, target=target)
