"""SQLite persistence for the live collector.

Three tables:

- ``matches``       — one row per (issue, match_idx). Holds invariant fields.
- ``snapshots``     — append-only time series (one row per poll x match).
- ``settlements``   — one row per match, written after kaijiang fetch.

The natural key for snapshots is (match_id, snapshot_ts) so re-running a poll
within the same second is a no-op (UNIQUE constraint + INSERT OR IGNORE).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional

from .parser import MatchSnapshot, Settlement

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id        TEXT PRIMARY KEY,
    issue           TEXT NOT NULL,
    match_idx       INTEGER NOT NULL,
    league          TEXT,
    kickoff_ts      TEXT,
    home            TEXT,
    away            TEXT,
    handicap_line   REAL,
    status          TEXT DEFAULT 'open',
    fid             TEXT,
    created_ts      TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(issue, match_idx)
);
CREATE INDEX IF NOT EXISTS idx_matches_issue ON matches(issue);

CREATE TABLE IF NOT EXISTS snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        TEXT NOT NULL,
    snapshot_ts     TEXT NOT NULL,
    sp_3            REAL,
    sp_1            REAL,
    sp_0            REAL,
    vol_pct_3       REAL,
    vol_pct_1       REAL,
    vol_pct_0       REAL,
    pool_total      REAL,
    eu_h            REAL,
    eu_d            REAL,
    eu_a            REAL,
    source          TEXT,
    UNIQUE(match_id, snapshot_ts, source),
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);
CREATE INDEX IF NOT EXISTS idx_snap_match ON snapshots(match_id);

CREATE TABLE IF NOT EXISTS settlements (
    match_id        TEXT PRIMARY KEY,
    issue           TEXT NOT NULL,
    match_idx       INTEGER NOT NULL,
    fthg            INTEGER,
    ftag            INTEGER,
    result_code     TEXT,
    winning_sp      REAL,
    avg_eu_h        REAL,
    avg_eu_d        REAL,
    avg_eu_a        REAL,
    settled_ts      TEXT DEFAULT CURRENT_TIMESTAMP,
    source          TEXT,
    FOREIGN KEY(match_id) REFERENCES matches(match_id)
);
"""


def _migrate(conn) -> None:
    """Idempotent schema migrations on existing DBs."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(settlements)").fetchall()}
    if "source" not in cols:
        conn.execute("ALTER TABLE settlements ADD COLUMN source TEXT")


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        # Idempotent migration: add fid column if existing table predates it
        try:
            cols = [r[1] for r in self._conn.execute(
                "PRAGMA table_info(matches)").fetchall()]
            if "fid" not in cols:
                self._conn.execute("ALTER TABLE matches ADD COLUMN fid TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            _migrate(self._conn)
        except sqlite3.OperationalError:
            pass

    def close(self):
        self._conn.close()

    @contextmanager
    def tx(self):
        cur = self._conn.cursor()
        try:
            cur.execute("BEGIN")
            yield cur
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise

    # --- writes -----------------------------------------------------------
    def upsert_match(self, snap: MatchSnapshot) -> str:
        """Insert match row if absent, else update mutable fields."""
        mid = snap.match_id
        with self.tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO matches(match_id, issue, match_idx, league, "
                "kickoff_ts, home, away, handicap_line, fid) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (mid, snap.issue, snap.match_idx, snap.league, snap.kickoff_ts,
                 snap.home, snap.away, snap.handicap_line, snap.fid),
            )
            cur.execute(
                "UPDATE matches SET league=COALESCE(?, league), "
                "kickoff_ts=COALESCE(?, kickoff_ts), home=COALESCE(?, home), "
                "away=COALESCE(?, away), handicap_line=COALESCE(?, handicap_line), "
                "fid=COALESCE(?, fid) "
                "WHERE match_id=?",
                (snap.league, snap.kickoff_ts, snap.home, snap.away,
                 snap.handicap_line, snap.fid, mid),
            )
        return mid

    def insert_snapshot(self, snap: MatchSnapshot, *, source: str,
                        snapshot_ts: Optional[str] = None) -> bool:
        """Insert a snapshot row. Idempotent on (match_id, snapshot_ts, source).

        Returns True if a new row was inserted, False on duplicate.
        """
        ts = snapshot_ts or _utcnow_iso()
        self.upsert_match(snap)
        with self.tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO snapshots(match_id, snapshot_ts, sp_3, sp_1, "
                "sp_0, vol_pct_3, vol_pct_1, vol_pct_0, pool_total, eu_h, eu_d, "
                "eu_a, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (snap.match_id, ts, snap.sp_3, snap.sp_1, snap.sp_0,
                 snap.vol_pct_3, snap.vol_pct_1, snap.vol_pct_0, snap.pool_total,
                 snap.eu_h, snap.eu_d, snap.eu_a, source),
            )
            return cur.rowcount > 0

    def insert_settlement(self, s: Settlement, *, source: str = "500") -> bool:
        with self.tx() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO settlements(match_id, issue, match_idx, "
                "fthg, ftag, result_code, winning_sp, avg_eu_h, avg_eu_d, "
                "avg_eu_a, source) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (s.match_id, s.issue, s.match_idx, s.fthg, s.ftag, s.result_code,
                 s.winning_sp, s.avg_eu_h, s.avg_eu_d, s.avg_eu_a, source),
            )
            return cur.rowcount > 0

    # --- reads ------------------------------------------------------------
    def count_snapshots(self, issue: Optional[str] = None) -> int:
        cur = self._conn.cursor()
        if issue:
            cur.execute(
                "SELECT COUNT(*) FROM snapshots s JOIN matches m ON s.match_id="
                "m.match_id WHERE m.issue=?", (issue,))
        else:
            cur.execute("SELECT COUNT(*) FROM snapshots")
        return cur.fetchone()[0]

    def count_matches(self, issue: Optional[str] = None) -> int:
        cur = self._conn.cursor()
        if issue:
            cur.execute("SELECT COUNT(*) FROM matches WHERE issue=?", (issue,))
        else:
            cur.execute("SELECT COUNT(*) FROM matches")
        return cur.fetchone()[0]

    def latest_snapshot_ts(self, issue: str) -> Optional[str]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT MAX(snapshot_ts) FROM snapshots s JOIN matches m "
            "ON s.match_id=m.match_id WHERE m.issue=?", (issue,))
        v = cur.fetchone()[0]
        return v

    def issues_needing_settlement(self) -> List[str]:
        """Issues with matches but no settlements rows."""
        cur = self._conn.cursor()
        cur.execute(
            "SELECT DISTINCT m.issue FROM matches m LEFT JOIN settlements s "
            "ON s.match_id=m.match_id WHERE s.match_id IS NULL")
        return [r[0] for r in cur.fetchall()]

    def matches_needing_per_match_settle(self, *, min_minutes_after_kickoff: int = 120):
        """Return ``[(match_id, issue, match_idx, fid, kickoff_ts, home, away)]``
        for matches that kicked off long enough ago but still have no row in
        ``settlements``. Used by the per-match livescore fallback scraper.

        Filtering is done in Python (kickoff_ts is naive ISO Beijing-ish).
        """
        cur = self._conn.cursor()
        cur.execute(
            "SELECT m.match_id, m.issue, m.match_idx, m.fid, m.kickoff_ts, "
            "m.home, m.away FROM matches m LEFT JOIN settlements s "
            "ON s.match_id=m.match_id WHERE s.match_id IS NULL "
            "AND m.kickoff_ts IS NOT NULL ORDER BY m.kickoff_ts ASC")
        rows = cur.fetchall()
        # Use UTC-naive ISO of (now - min_minutes) as cutoff string compare;
        # kickoff_ts is naive Beijing-ish so this is a rough but stable filter.
        cutoff = (datetime.now() - timedelta(minutes=min_minutes_after_kickoff)
                  ).strftime("%Y-%m-%dT%H:%M:%S")
        out = []
        for r in rows:
            if r[4] and r[4] <= cutoff:
                out.append(dict(match_id=r[0], issue=r[1], match_idx=r[2],
                                fid=r[3], kickoff_ts=r[4],
                                home=r[5], away=r[6]))
        return out
