"""SQLite schema + helpers for backfill DB."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS historical_matches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    issue           TEXT    NOT NULL,
    match_idx       INTEGER NOT NULL,
    league          TEXT,
    kickoff_ts      TEXT,           -- ISO8601 (year inferred from issue)
    home            TEXT,
    away            TEXT,
    handicap_line   INTEGER,        -- e.g. -2, -1, 0, +1; NULL if unparseable
    fthg            INTEGER,
    ftag            INTEGER,
    result_code     TEXT,           -- '3', '1', '0' (normalised)
    winning_sp      REAL,
    avg_eu_home     REAL,
    avg_eu_draw     REAL,
    avg_eu_away     REAL,
    UNIQUE(issue, match_idx)
);

CREATE INDEX IF NOT EXISTS idx_hist_issue ON historical_matches(issue);
CREATE INDEX IF NOT EXISTS idx_hist_kickoff ON historical_matches(kickoff_ts);

CREATE TABLE IF NOT EXISTS scrape_log (
    issue           TEXT PRIMARY KEY,
    fetched_at      TEXT NOT NULL,
    n_matches       INTEGER,
    status          TEXT      -- 'ok' | 'empty' | 'error:<msg>'
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def already_done_issues(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT issue FROM scrape_log WHERE status = 'ok'"
    ).fetchall()
    return {r["issue"] for r in rows}


def insert_matches(conn: sqlite3.Connection, rows: Iterable[dict]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    sql = """
    INSERT OR IGNORE INTO historical_matches
        (issue, match_idx, league, kickoff_ts, home, away,
         handicap_line, fthg, ftag, result_code, winning_sp,
         avg_eu_home, avg_eu_draw, avg_eu_away)
    VALUES
        (:issue, :match_idx, :league, :kickoff_ts, :home, :away,
         :handicap_line, :fthg, :ftag, :result_code, :winning_sp,
         :avg_eu_home, :avg_eu_draw, :avg_eu_away)
    """
    cur = conn.executemany(sql, rows)
    conn.commit()
    return cur.rowcount or 0


def log_scrape(conn: sqlite3.Connection, issue: str, n_matches: int, status: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO scrape_log (issue, fetched_at, n_matches, status) "
        "VALUES (?, datetime('now'), ?, ?)",
        (issue, n_matches, status),
    )
    conn.commit()


@contextmanager
def session(path: str | Path) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
