from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sqlite_runtime import connect_sqlite


def test_connect_sqlite_applies_live_defaults(tmp_path: Path) -> None:
    db_path = tmp_path / "live.sqlite"
    with connect_sqlite(db_path, row_factory=True, timeout=7.5) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES ('ok')")
        row = conn.execute("SELECT value FROM sample").fetchone()
        assert row["value"] == "ok"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 7500
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_connect_sqlite_readonly_mode_reads_existing_db(tmp_path: Path) -> None:
    db_path = tmp_path / "readonly.sqlite"
    with connect_sqlite(db_path) as conn:
        conn.execute("CREATE TABLE sample (value TEXT)")
        conn.execute("INSERT INTO sample(value) VALUES ('seen')")

    with connect_sqlite(db_path, readonly=True, row_factory=True) as conn:
        row = conn.execute("SELECT value FROM sample").fetchone()
        assert row["value"] == "seen"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] > 0
        with pytest.raises(Exception):
            conn.execute("INSERT INTO sample(value) VALUES ('blocked')")
