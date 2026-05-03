"""SQLite persistence for the webui (separate from Live Collector DB).

Tables:
    config          — singleton key/value (initial_bankroll, current_active,
                      locked_pile, peak_high_water)
    plans           — generated plans + placement state
    settlements_log — one row per reconciled week, includes ProfitLock skim
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS config (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS plans (
    plan_id        TEXT PRIMARY KEY,
    created_ts     TEXT NOT NULL,
    plan_json      TEXT NOT NULL,
    placed_ts      TEXT,
    placed_actual  TEXT
);

CREATE TABLE IF NOT EXISTS settlements_log (
    week_id         TEXT PRIMARY KEY,
    settled_ts      TEXT NOT NULL,
    n_combos        INTEGER,
    n_hits          INTEGER,
    week_stake      REAL,
    week_payout     REAL,
    week_pnl        REAL,
    bankroll_after  REAL,
    locked_after    REAL,
    skimmed         REAL DEFAULT 0
);
"""


class WebuiDB:
    """Thin wrapper around the webui SQLite DB."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, isolation_level=None,
                                     check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)

    def close(self) -> None:
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

    # ---- config (key/value) ---------------------------------------------
    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        row = self._conn.execute(
            "SELECT value FROM config WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_config(self, key: str, value: Any) -> None:
        with self.tx() as cur:
            cur.execute(
                "INSERT INTO config(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    def get_float(self, key: str, default: float = 0.0) -> float:
        v = self.get_config(key)
        return float(v) if v is not None else default

    def is_initialized(self) -> bool:
        return self.get_config("initial_bankroll") is not None

    def initialize(self, initial_bankroll: float) -> None:
        """Set initial state. Idempotent only if not already initialized."""
        if self.is_initialized():
            return
        self.set_config("initial_bankroll", initial_bankroll)
        self.set_config("current_active", initial_bankroll)
        self.set_config("locked_pile", 0.0)
        self.set_config("peak_high_water", initial_bankroll)

    def reset(self) -> None:
        """Drop all webui state (used by the Reset action / tests)."""
        with self.tx() as cur:
            cur.execute("DELETE FROM config")
            cur.execute("DELETE FROM plans")
            cur.execute("DELETE FROM settlements_log")

    # ---- plans -----------------------------------------------------------
    def upsert_plan(self, plan_id: str, created_ts: str,
                    plan_dict: Dict[str, Any]) -> None:
        with self.tx() as cur:
            cur.execute(
                "INSERT INTO plans(plan_id, created_ts, plan_json) VALUES(?,?,?) "
                "ON CONFLICT(plan_id) DO UPDATE SET "
                "created_ts=excluded.created_ts, plan_json=excluded.plan_json",
                (plan_id, created_ts,
                 json.dumps(plan_dict, ensure_ascii=False)),
            )

    def mark_placed(self, plan_id: str, placed_ts: str,
                    actual: Optional[Dict[str, Any]] = None) -> bool:
        with self.tx() as cur:
            cur.execute(
                "UPDATE plans SET placed_ts=?, placed_actual=? WHERE plan_id=?",
                (placed_ts,
                 json.dumps(actual, ensure_ascii=False) if actual else None,
                 plan_id),
            )
            return cur.rowcount > 0

    def get_plan(self, plan_id: str) -> Optional[Dict[str, Any]]:
        row = self._conn.execute(
            "SELECT plan_id, created_ts, plan_json, placed_ts, placed_actual "
            "FROM plans WHERE plan_id=?", (plan_id,)
        ).fetchone()
        if not row:
            return None
        return dict(
            plan_id=row[0], created_ts=row[1],
            plan=json.loads(row[2]),
            placed_ts=row[3],
            placed_actual=json.loads(row[4]) if row[4] else None,
        )

    def list_plans(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT plan_id, created_ts, placed_ts FROM plans "
            "ORDER BY plan_id DESC"
        ).fetchall()
        return [dict(plan_id=r[0], created_ts=r[1], placed_ts=r[2])
                for r in rows]

    # ---- settlements log -------------------------------------------------
    def record_settlement(self, *, week_id: str, settled_ts: str,
                          n_combos: int, n_hits: int,
                          week_stake: float, week_payout: float,
                          week_pnl: float, bankroll_after: float,
                          locked_after: float, skimmed: float = 0.0) -> None:
        with self.tx() as cur:
            cur.execute(
                "INSERT INTO settlements_log(week_id, settled_ts, n_combos, "
                "n_hits, week_stake, week_payout, week_pnl, bankroll_after, "
                "locked_after, skimmed) VALUES(?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(week_id) DO UPDATE SET "
                "settled_ts=excluded.settled_ts, n_combos=excluded.n_combos, "
                "n_hits=excluded.n_hits, week_stake=excluded.week_stake, "
                "week_payout=excluded.week_payout, week_pnl=excluded.week_pnl, "
                "bankroll_after=excluded.bankroll_after, "
                "locked_after=excluded.locked_after, skimmed=excluded.skimmed",
                (week_id, settled_ts, n_combos, n_hits, week_stake,
                 week_payout, week_pnl, bankroll_after, locked_after, skimmed),
            )

    def list_settlements(self) -> List[Dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT week_id, settled_ts, n_combos, n_hits, week_stake, "
            "week_payout, week_pnl, bankroll_after, locked_after, skimmed "
            "FROM settlements_log ORDER BY week_id ASC"
        ).fetchall()
        cols = ["week_id", "settled_ts", "n_combos", "n_hits", "week_stake",
                "week_payout", "week_pnl", "bankroll_after", "locked_after",
                "skimmed"]
        return [dict(zip(cols, r)) for r in rows]

    def has_settlement(self, week_id: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM settlements_log WHERE week_id=?", (week_id,)
        ).fetchone() is not None
