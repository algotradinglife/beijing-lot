"""Read-only adapter for the declared Nowscore/Titan historical workbook.

No result, settlement, SP, payout, or score columns are selected. The raw
workbook remains authoritative evidence; normalized rows retain its match,
bookmaker and horizon coordinates so aggregates can be replayed from its hash.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

_REQUIRED = {
    "matches": {
        "match_id",
        "issue",
        "match_idx",
        "handicap_line",
        "handicap_line_norm",
        "handicap_norm_source",
    },
    "market_snapshots": {"match_id", "market", "bookmaker", "snapshot", "v1", "v2", "v3"},
    "source_meta": {"key", "value"},
}
_HORIZONS = ("initial", "10h", "1h")


def _connect(path: str | Path) -> sqlite3.Connection:
    database = Path(path).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    con.execute("PRAGMA query_only=ON")
    return con


def _assert_layout(con: sqlite3.Connection) -> None:
    found = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table, expected in _REQUIRED.items():
        if table not in found:
            raise ValueError(f"source workbook missing table {table}")
        got = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
        missing = expected - got
        if missing:
            raise ValueError(f"source workbook {table} missing columns: {sorted(missing)}")
    receipts = dict(con.execute("SELECT key, value FROM source_meta"))
    workbook = str(receipts.get("source_path", "")).lower().endswith("beidan.xlsm")
    nowscore_update = bool(
        str(receipts.get("nowscore_update_last_run", "")).strip()
        and str(receipts.get("nowscore_update_issues", "")).strip()
    )
    if not workbook and not nowscore_update:
        raise ValueError(
            "source lacks either beidan.xlsm or Nowscore update provenance receipts"
        )


def _duplicate_slot_ledger(con: sqlite3.Connection) -> pd.DataFrame:
    records = con.execute(
        """
        SELECT issue, match_idx, group_concat(match_id, ',') AS source_match_ids
        FROM (
            SELECT issue, match_idx, match_id FROM matches
            WHERE issue IS NOT NULL AND trim(issue) <> '' AND match_idx IS NOT NULL
            ORDER BY issue, match_idx, match_id
        )
        GROUP BY issue, match_idx
        HAVING COUNT(*) > 1
        ORDER BY issue, match_idx
        """
    ).fetchall()
    return pd.DataFrame(records, columns=["issue_code", "match_idx", "source_match_ids"]).assign(
        reason="DUPLICATE_ISSUE_SLOT"
    )[["issue_code", "match_idx", "reason", "source_match_ids"]]


def _read_query() -> str:
    # Exact source grain: unique raw (source match, market, label, bookmaker)
    # linked only to a unique Beijing issue-slot. Any ambiguous source coordinate
    # is excluded before normalization rather than arbitrarily collapsed.
    return """
    WITH unique_slots AS (
        SELECT issue, match_idx
        FROM matches
        WHERE issue IS NOT NULL AND trim(issue) <> '' AND match_idx IS NOT NULL
        GROUP BY issue, match_idx
        HAVING COUNT(*) = 1
    ), unique_quotes AS (
        SELECT match_id, market, snapshot, bookmaker
        FROM market_snapshots
        WHERE market = 'euro_1x2' AND snapshot IN ('initial', '10h', '1h')
        GROUP BY match_id, market, snapshot, bookmaker
        HAVING COUNT(*) = 1
    )
    SELECT CAST(m.issue AS TEXT) AS issue_code, m.match_idx,
           m.match_id AS source_match_id, s.snapshot AS snapshot_kind,
           s.bookmaker AS bookmaker_id, s.v1, s.v2, s.v3,
           m.handicap_line AS native_handicap_line_raw,
           m.handicap_line_norm AS native_handicap_line,
           m.handicap_norm_source
    FROM market_snapshots AS s
    JOIN unique_quotes AS q
      ON q.match_id = s.match_id AND q.market = s.market
     AND q.snapshot = s.snapshot AND q.bookmaker = s.bookmaker
    JOIN matches AS m ON m.match_id = s.match_id
    JOIN unique_slots AS u ON u.issue = m.issue AND u.match_idx = m.match_idx
    WHERE s.market = 'euro_1x2' AND s.snapshot IN ('initial', '10h', '1h')
    ORDER BY m.issue, m.match_idx, s.snapshot, s.bookmaker
    """


def iter_workbook_proxy(path: str | Path, *, chunksize: int = 100_000) -> Iterator[pd.DataFrame]:
    """Yield valid-grain raw European 1X2 rows in deterministic chunks."""
    if chunksize < 1:
        raise ValueError("chunksize must be positive")
    con = _connect(path)
    try:
        _assert_layout(con)
        for frame in pd.read_sql_query(_read_query(), con, chunksize=chunksize):
            yield frame
    finally:
        con.close()


def load_workbook_proxy(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load a bounded test/probe surface and issue-slot quarantine ledger.

    Production builds use :func:`iter_workbook_proxy` to avoid loading the
    multi-million raw table into memory at once.
    """
    con = _connect(path)
    try:
        _assert_layout(con)
        ledger = _duplicate_slot_ledger(con)
        rows = pd.read_sql_query(_read_query(), con)
    finally:
        con.close()
    return rows, ledger
