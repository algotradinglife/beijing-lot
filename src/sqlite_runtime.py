from __future__ import annotations

import sqlite3
from pathlib import Path


DEFAULT_SQLITE_TIMEOUT_SECONDS = 30.0
DEFAULT_BUSY_TIMEOUT_MS = int(DEFAULT_SQLITE_TIMEOUT_SECONDS * 1000)


def connect_sqlite(
    path: str | Path,
    *,
    row_factory: bool = False,
    foreign_keys: bool = True,
    wal: bool = True,
    readonly: bool = False,
    timeout: float = DEFAULT_SQLITE_TIMEOUT_SECONDS,
) -> sqlite3.Connection:
    """Open a SQLite connection with the live-data defaults.

    The dashboard has multiple low-frequency writers and many UI reads.  SQLite
    can handle that with WAL, but the default Python connection has a zero
    busy_timeout pragma in new sessions, which makes transient writer locks
    fail too aggressively.
    """
    db_path = Path(path)
    if readonly:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=timeout)
    else:
        conn = sqlite3.connect(db_path, timeout=timeout)
    if row_factory:
        conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    conn.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
    if wal and not readonly:
        conn.execute("PRAGMA journal_mode=WAL")
    return conn
