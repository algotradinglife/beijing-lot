"""Isolated 500 settlement label store; it cannot write Titan features."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class SettlementStoreError(ValueError):
    """Raised when a settlement label lacks frozen Titan identity evidence."""


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SettlementStoreError("timestamps must carry a timezone")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_bytes(path: Path, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise SettlementStoreError("content-addressed raw collision")
        return digest
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return digest


class SettlementStore:
    """Separate physical store for the PI-accepted 500 settlement evidence lane."""

    def __init__(self, root: Path, connection: sqlite3.Connection) -> None:
        self.root = root
        self.connection = connection

    @classmethod
    def open(cls, root: Path) -> "SettlementStore":
        root = Path(root).expanduser().resolve()
        directory = root / "control" / "settlement_500"
        directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(directory / "settlement.sqlite", isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS capture_batch (
              batch_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL CHECK(source_id = 'trusted_500_settlement'),
              source_role TEXT NOT NULL CHECK(source_role = 'SETTLEMENT_ONLY'),
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              acquisition_result TEXT NOT NULL CHECK(acquisition_result = 'FINAL_OR_SETTLED')
            );
            CREATE TABLE IF NOT EXISTS frozen_binding (
              canonical_fixture_id TEXT NOT NULL,
              canonical_issue_id TEXT NOT NULL,
              canonical_issue_slot_id TEXT NOT NULL,
              crosswalk_sha256 TEXT NOT NULL CHECK(length(crosswalk_sha256) = 64),
              bridge_sha256 TEXT NOT NULL CHECK(length(bridge_sha256) = 64),
              PRIMARY KEY(canonical_fixture_id, canonical_issue_id, canonical_issue_slot_id)
            );
            CREATE TABLE IF NOT EXISTS settlement_revision (
              revision_id TEXT PRIMARY KEY,
              canonical_fixture_id TEXT NOT NULL,
              canonical_issue_id TEXT NOT NULL,
              canonical_issue_slot_id TEXT NOT NULL,
              crosswalk_sha256 TEXT NOT NULL CHECK(length(crosswalk_sha256) = 64),
              result_code TEXT NOT NULL CHECK(result_code IN ('3', '1', '0')),
              winning_sp REAL CHECK(winning_sp IS NULL OR winning_sp > 0),
              label_available_at_utc TEXT NOT NULL,
              batch_id TEXT NOT NULL REFERENCES capture_batch(batch_id),
              supersedes_revision_id TEXT REFERENCES settlement_revision(revision_id),
              UNIQUE(canonical_fixture_id, canonical_issue_id, canonical_issue_slot_id, batch_id)
            );
            -- 原始结算捕获：先按 500 原生 ID 抓取，最后再与 Titan 映射 join 匹配。
            -- 本表不要求 Titan 侧任何东西，允许与 Titan 历史采集并行进行。
            CREATE TABLE IF NOT EXISTS raw_settlement_capture (
              batch_id TEXT PRIMARY KEY,
              issue_code TEXT NOT NULL CHECK(length(issue_code) BETWEEN 5 AND 8),
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              rows_parsed INTEGER NOT NULL CHECK(rows_parsed >= 0),
              acquisition_result TEXT NOT NULL CHECK(acquisition_result = 'OK')
            );
            CREATE TABLE IF NOT EXISTS raw_settlement_row (
              issue_code TEXT NOT NULL CHECK(length(issue_code) BETWEEN 5 AND 8),
              issue_slot INTEGER NOT NULL CHECK(issue_slot > 0),
              local_500_fid INTEGER NOT NULL CHECK(local_500_fid > 0),
              handicap_line INTEGER,
              home_score INTEGER,
              away_score INTEGER,
              result_code TEXT CHECK(result_code IS NULL OR result_code IN ('3', '1', '0')),
              winning_sp REAL CHECK(winning_sp IS NULL OR winning_sp > 0),
              settlement_state TEXT NOT NULL DEFAULT 'settled'
                CHECK(settlement_state IN ('settled', 'postponed', 'cancelled', 'no_result')),
              batch_id TEXT NOT NULL REFERENCES raw_settlement_capture(batch_id),
              PRIMARY KEY(issue_code, issue_slot)
            );
            -- 其他玩法结算（总进球/上下单双/半全场/比分），按 500 原生 ID + play_type。
            CREATE TABLE IF NOT EXISTS raw_settlement_play_row (
              issue_code TEXT NOT NULL CHECK(length(issue_code) BETWEEN 5 AND 8),
              issue_slot INTEGER NOT NULL CHECK(issue_slot > 0),
              local_500_fid INTEGER NOT NULL CHECK(local_500_fid > 0),
              play_type TEXT NOT NULL CHECK(play_type IN ('jq', 'ds', 'bq', 'bf')),
              handicap_line INTEGER,
              home_score INTEGER,
              away_score INTEGER,
              winning_option TEXT,
              winning_sp REAL CHECK(winning_sp IS NULL OR winning_sp > 0),
              settlement_state TEXT NOT NULL DEFAULT 'settled'
                CHECK(settlement_state IN ('settled', 'postponed', 'cancelled', 'no_result')),
              batch_id TEXT NOT NULL REFERENCES raw_settlement_capture(batch_id),
              PRIMARY KEY(issue_code, issue_slot, play_type)
            );
            """
        )
        # 老库迁移：raw_settlement_row 增加 settlement_state 列
        columns = [row[1] for row in connection.execute("PRAGMA table_info(raw_settlement_row)")]
        if "settlement_state" not in columns:
            with connection:
                connection.execute(
                    "ALTER TABLE raw_settlement_row ADD COLUMN settlement_state TEXT NOT NULL DEFAULT 'settled' "
                    "CHECK(settlement_state IN ('settled', 'postponed', 'cancelled', 'no_result'))"
                )
        if "handicap_line" not in columns:
            with connection:
                connection.execute("ALTER TABLE raw_settlement_row ADD COLUMN handicap_line INTEGER")
        # play 表迁移
        play_cols = [row[1] for row in connection.execute("PRAGMA table_info(raw_settlement_play_row)")]
        if "handicap_line" not in play_cols:
            with connection:
                connection.execute("ALTER TABLE raw_settlement_play_row ADD COLUMN handicap_line INTEGER")
        return cls(root, connection)

    def close(self) -> None:
        self.connection.close()

    def import_frozen_bridge(self, payload: bytes) -> str:
        """Accept a minimal, verified-shape Titan handoff without opening Titan storage."""
        bridge_sha256 = hashlib.sha256(payload).hexdigest()
        try:
            bridge = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise SettlementStoreError("frozen bridge is not valid JSON") from exc
        if bridge.get("schema_version") != "titan_settlement_bridge_v1":
            raise SettlementStoreError("unsupported frozen bridge schema")
        crosswalk = bridge.get("crosswalk_sha256")
        bindings = bridge.get("bindings")
        if not isinstance(crosswalk, str) or len(crosswalk) != 64 or not isinstance(bindings, list) or not bindings:
            raise SettlementStoreError("frozen bridge is incomplete")
        canonical = json.dumps(bindings, sort_keys=True, separators=(",", ":")) + "\n"
        if hashlib.sha256(canonical.encode()).hexdigest() != crosswalk:
            raise SettlementStoreError("frozen bridge crosswalk hash mismatch")
        rows = []
        for binding in bindings:
            if set(binding) != {"canonical_fixture_id", "canonical_issue_id", "canonical_issue_slot_id"}:
                raise SettlementStoreError("frozen bridge exposes unsupported fields")
            row = (binding["canonical_fixture_id"], binding["canonical_issue_id"], binding["canonical_issue_slot_id"])
            if not all(isinstance(value, str) and value for value in row):
                raise SettlementStoreError("frozen bridge identity is invalid")
            rows.append((*row, crosswalk, bridge_sha256))
        if len({row[:3] for row in rows}) != len(rows):
            raise SettlementStoreError("frozen bridge contains duplicate identity")
        with self.connection:
            self.connection.executemany("INSERT OR IGNORE INTO frozen_binding VALUES(?,?,?,?,?)", rows)
        return bridge_sha256

    def record_final_payload(
        self,
        *,
        batch_id: str,
        payload: bytes,
        trusted_received_at_utc: str,
        parser_version: str,
    ) -> str:
        received = _utc(trusted_received_at_utc)
        raw_sha = hashlib.sha256(payload).hexdigest()
        raw_path = self.root / "raw" / "settlement_500" / raw_sha[:2] / f"{raw_sha}.bin"
        existing = self.connection.execute(
            "SELECT raw_sha256,raw_path,trusted_received_at_utc,parser_version FROM capture_batch WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        expected = (raw_sha, str(raw_path.relative_to(self.root)), received, parser_version)
        if existing is not None:
            if tuple(existing) != expected:
                raise SettlementStoreError(f"capture batch collision: {batch_id}")
            return raw_sha
        _atomic_bytes(raw_path, payload)
        with self.connection:
            self.connection.execute(
                "INSERT INTO capture_batch VALUES(?,?,?,?,?,?,?,?)",
                (batch_id, "trusted_500_settlement", "SETTLEMENT_ONLY", *expected, "FINAL_OR_SETTLED"),
            )
        return raw_sha

    def export_label(
        self,
        *,
        revision_id: str,
        canonical_fixture_id: str,
        canonical_issue_id: str,
        canonical_issue_slot_id: str,
        crosswalk_sha256: str,
        decision_at_utc: str,
    ) -> dict[str, object] | None:
        """Export the only permitted settlement bridge record for one frozen identity."""
        decision_at_utc = _utc(decision_at_utc)
        row = self.connection.execute(
            """SELECT canonical_fixture_id,canonical_issue_id,canonical_issue_slot_id,crosswalk_sha256,
                      result_code,winning_sp,label_available_at_utc,batch_id,supersedes_revision_id
                 FROM settlement_revision WHERE revision_id=?""",
            (revision_id,),
        ).fetchone()
        if row is None:
            return None
        expected = (canonical_fixture_id, canonical_issue_id, canonical_issue_slot_id, crosswalk_sha256)
        if tuple(row[:4]) != expected:
            raise SettlementStoreError("frozen label identity binding mismatch")
        if row[6] >= decision_at_utc:
            return None
        return {
            "canonical_fixture_id": row[0],
            "canonical_issue_id": row[1],
            "canonical_issue_slot_id": row[2],
            "crosswalk_sha256": row[3],
            "result_code": row[4],
            "winning_sp": row[5],
            "label_available_at_utc": row[6],
            "batch_id": row[7],
            "supersedes_revision_id": row[8],
        }

    def append_label(
        self,
        *,
        revision_id: str,
        canonical_fixture_id: str,
        canonical_issue_id: str,
        canonical_issue_slot_id: str,
        crosswalk_sha256: str,
        result_code: str,
        winning_sp: float | None,
        label_available_at_utc: str,
        batch_id: str,
        supersedes_revision_id: str | None = None,
    ) -> None:
        if not all((revision_id, canonical_fixture_id, canonical_issue_id, canonical_issue_slot_id)):
            raise SettlementStoreError("frozen canonical identity binding is required")
        if len(crosswalk_sha256) != 64:
            raise SettlementStoreError("crosswalk hash must be SHA-256")
        binding = self.connection.execute(
            """SELECT 1 FROM frozen_binding WHERE canonical_fixture_id=? AND canonical_issue_id=?
               AND canonical_issue_slot_id=? AND crosswalk_sha256=?""",
            (canonical_fixture_id, canonical_issue_id, canonical_issue_slot_id, crosswalk_sha256),
        ).fetchone()
        if binding is None:
            raise SettlementStoreError("label requires an imported frozen Titan bridge")
        received = self.connection.execute(
            "SELECT trusted_received_at_utc FROM capture_batch WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if received is None:
            raise SettlementStoreError("label requires a successful raw settlement batch")
        available = _utc(label_available_at_utc)
        if available != received[0]:
            raise SettlementStoreError("label availability must equal raw receipt time")
        with self.connection:
            self.connection.execute(
                "INSERT INTO settlement_revision VALUES(?,?,?,?,?,?,?,?,?,?)",
                (revision_id, canonical_fixture_id, canonical_issue_id, canonical_issue_slot_id,
                 crosswalk_sha256, result_code, winning_sp, available, batch_id, supersedes_revision_id),
            )

    # ------------------------------------------------------------ 原始结算捕获 ----

    def record_raw_settlement(
        self,
        *,
        batch_id: str,
        issue_code: str,
        source_url: str,
        payload: bytes,
        trusted_received_at_utc: str,
        parser_version: str,
        rows: Iterable[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]],
    ) -> str:
        """Record one 500 issue settlement page parsed by 500-native IDs.

        ``rows`` items are ``(issue_slot, local_500_fid, home_score, away_score,
        result_code, winning_sp, settlement_state, handicap_line)`` where
        settlement_state is one of 'settled' / 'postponed' / 'cancelled' /
        'no_result', and handicap_line is the 让球数 (positive=home concedes,
        negative=away concedes).  This lane is independent of Titan: matching
        to canonical fixtures happens later via the mapping library.
        """
        if not batch_id or not issue_code or not _valid_issue_code(issue_code):
            raise SettlementStoreError("settlement batch requires issue and batch ids")
        received = _utc(trusted_received_at_utc)
        digest = hashlib.sha256(payload).hexdigest()
        raw_path = self.root / "raw" / "settlement_500" / digest[:2] / f"{digest}.html"
        rel_path = str(raw_path.relative_to(self.root))
        existing = self.connection.execute(
            "SELECT source_url,raw_sha256,raw_path,trusted_received_at_utc,parser_version FROM raw_settlement_capture WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        expected = (source_url, digest, rel_path, received, parser_version)
        if existing is not None:
            if tuple(existing) != expected:
                raise SettlementStoreError(f"raw settlement batch collision: {batch_id}")
            return digest
        _atomic_bytes(raw_path, payload)
        normalized: list[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]] = []
        seen: set[int] = set()
        for slot, fid, home, away, code, sp, state, handicap in rows:
            if slot < 1 or fid < 1:
                raise SettlementStoreError("raw settlement row needs slot and fid >= 1")
            if code is not None and code not in ("3", "1", "0"):
                raise SettlementStoreError(f"invalid result code {code!r}")
            if sp is not None and sp <= 0:
                raise SettlementStoreError("winning sp must be positive")
            if state not in ("settled", "postponed", "cancelled", "no_result"):
                raise SettlementStoreError(f"invalid settlement state {state!r}")
            if state == "settled" and code is None:
                raise SettlementStoreError("settled row requires a result code")
            if slot in seen:
                raise SettlementStoreError(f"duplicate slot {slot} in settlement rows")
            seen.add(slot)
            normalized.append((slot, fid, home, away, code, sp, state, handicap))
        with self.connection:
            self.connection.execute(
                "INSERT INTO raw_settlement_capture VALUES(?,?,?,?,?,?,?,?,?)",
                (batch_id, issue_code, source_url, digest, rel_path, received, parser_version, len(normalized), "OK"),
            )
            self.connection.executemany(
                "INSERT OR REPLACE INTO raw_settlement_row "
                "(issue_code, issue_slot, local_500_fid, handicap_line, home_score, away_score, "
                "result_code, winning_sp, settlement_state, batch_id) VALUES(?,?,?,?,?,?,?,?,?,?)",
                [(issue_code, slot, fid, handicap, home, away, code, sp, state, batch_id) for slot, fid, home, away, code, sp, state, handicap in normalized],
            )
        return digest

    def raw_settlement_issues(self) -> set[str]:
        return {row[0] for row in self.connection.execute("SELECT DISTINCT issue_code FROM raw_settlement_capture")}

    def record_raw_play_settlement(
        self,
        *,
        batch_id: str,
        issue_code: str,
        play_type: str,
        rows: Iterable[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]],
    ) -> None:
        """Record one play-type settlement (总进球 jq / 上下单双 ds / 半全场 bq / 比分 bf).

        ``rows`` items are ``(issue_slot, local_500_fid, home_score, away_score,
        winning_option, winning_sp, settlement_state, handicap_line)``.  Keyed
        by 500-native IDs; Titan matching happens later via the mapping library.
        """
        if not issue_code or not _valid_issue_code(issue_code):
            raise SettlementStoreError("play settlement requires a valid issue code")
        if play_type not in ("jq", "ds", "bq", "bf"):
            raise SettlementStoreError(f"invalid play type {play_type!r}")
        batch_exists = self.connection.execute(
            "SELECT 1 FROM raw_settlement_capture WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if batch_exists is None:
            raise SettlementStoreError("play settlement requires an existing raw batch")
        normalized: list[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]] = []
        seen: set[int] = set()
        for slot, fid, home, away, option, sp, state, handicap in rows:
            if slot < 1 or fid < 1:
                raise SettlementStoreError("play settlement row needs slot and fid >= 1")
            if sp is not None and sp <= 0:
                raise SettlementStoreError("winning sp must be positive")
            if state not in ("settled", "postponed", "cancelled", "no_result"):
                raise SettlementStoreError(f"invalid settlement state {state!r}")
            if slot in seen:
                raise SettlementStoreError(f"duplicate slot {slot} in play settlement rows")
            seen.add(slot)
            normalized.append((slot, fid, home, away, option, sp, state, handicap))
        with self.connection:
            self.connection.executemany(
                "INSERT OR REPLACE INTO raw_settlement_play_row "
                "(issue_code, issue_slot, local_500_fid, play_type, handicap_line, home_score, away_score, "
                "winning_option, winning_sp, settlement_state, batch_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                [(issue_code, slot, fid, play_type, handicap, home, away, option, sp, state, batch_id)
                 for slot, fid, home, away, option, sp, state, handicap in normalized],
            )

    def raw_play_issues(self, play_type: str) -> set[str]:
        return {row[0] for row in self.connection.execute(
            "SELECT DISTINCT issue_code FROM raw_settlement_play_row WHERE play_type=?", (play_type,)
        )}


def _valid_issue_code(value: str) -> bool:
    return value.isdecimal() and 5 <= len(value) <= 8
