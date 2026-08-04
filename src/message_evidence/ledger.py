"""Append-only, timestamped evidence ledger for pre-kickoff message data.

The ledger deliberately owns evidence acquisition semantics only. It does not
score facts, rank matches, or make betting decisions. Every normalized record
points to immutable raw bytes, and every consumer read is bounded by an
explicit as-of cutoff.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence
from urllib.parse import parse_qsl, urlparse

from src.sqlite_runtime import connect_sqlite


LEDGER_SCHEMA_VERSION = "message_evidence_ledger_v1"
EXPORT_SCHEMA_VERSION = "message_evidence_asof_v1"
REPORT_SCHEMA_VERSION = "message_evidence_coverage_v1"
LATE_ARRIVAL_SECONDS = 3600
MAX_RAW_CAPTURE_BYTES = 20 * 1024 * 1024

PROVENANCE_TIERS = (
    "TIER_0_OFFICIAL",
    "TIER_1_PRIMARY",
    "TIER_2_RELIABLE",
    "TIER_3_UNVERIFIED",
)
SOURCE_TYPES = (
    "official_club",
    "official_league",
    "official_competition",
    "primary_reporter",
    "reliable_news",
    "data_provider",
    "other",
)
ENTITY_TYPES = ("team", "player", "coach", "competition", "venue", "other")
FACT_KINDS = (
    "injury",
    "suspension",
    "expected_lineup",
    "confirmed_lineup",
    "coach_change",
    "schedule",
    "travel",
    "motivation",
)
ASSERTION_STATES = ("affirmed", "denied", "unknown")
RELATION_TYPES = ("corrects", "contradicts", "retracts")
MISSING_REASON_CODES = (
    "not_published",
    "fetch_failed",
    "unresolved_entity",
    "ambiguous",
    "source_unavailable",
    "not_applicable",
    "other",
)
COLLECTION_STATUSES = ("complete", "partial")

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class MessageEvidenceError(ValueError):
    """The requested mutation or read violates the evidence contract."""


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _digest(value: object) -> str:
    return sha256_bytes(canonical_json(value))


def normalize_timestamp(value: str | datetime, field: str = "timestamp") -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise MessageEvidenceError(f"{field} is required")
        try:
            parsed = datetime.fromisoformat(
                text[:-1] + "+00:00" if text.endswith("Z") else text
            )
        except ValueError as exc:
            raise MessageEvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise MessageEvidenceError(f"{field} must include a timezone")
    return (
        parsed.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _optional_timestamp(value: str | datetime | None, field: str) -> str | None:
    return (
        None
        if value is None or str(value).strip() == ""
        else normalize_timestamp(value, field)
    )


def _safe_id(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not _SAFE_ID.fullmatch(text):
        raise MessageEvidenceError(f"{field} is not a safe identifier")
    return text


def _choice(value: object, allowed: Sequence[str], field: str) -> str:
    text = str(value or "").strip()
    if text not in allowed:
        raise MessageEvidenceError(f"{field} must be one of {', '.join(allowed)}")
    return text


def _http_url(value: object, field: str, *, optional: bool = False) -> str | None:
    text = str(value or "").strip()
    if optional and not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise MessageEvidenceError(f"{field} must be an HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise MessageEvidenceError(f"{field} must not contain URL credentials")
    sensitive_markers = (
        "api_key",
        "apikey",
        "auth",
        "credential",
        "password",
        "secret",
        "signature",
        "token",
    )
    sensitive_parameters = sorted(
        key
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() == "sig"
        or any(marker in key.casefold() for marker in sensitive_markers)
    )
    if sensitive_parameters:
        raise MessageEvidenceError(
            f"{field} must not contain sensitive query parameters"
        )
    return text


def _metadata(value: Mapping[str, Any] | None) -> str:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise MessageEvidenceError("metadata must be an object")
    try:
        return canonical_json(dict(value)).decode("utf-8")
    except (TypeError, ValueError) as exc:
        raise MessageEvidenceError("metadata must be canonical JSON") from exc


def _record_hash(record: Mapping[str, Any]) -> str:
    return _digest(dict(record))


def _verify_record_hash(
    row: sqlite3.Row,
    record: Mapping[str, Any],
    *,
    identifier_field: str | None = None,
) -> None:
    expected = _record_hash(record)
    if row["record_sha256"] != expected or (
        identifier_field is not None and row[identifier_field] != expected
    ):
        identifier = row[identifier_field] if identifier_field else expected
        raise MessageEvidenceError(f"record hash mismatch: {identifier}")


def _verify_effective_cutoff(row: sqlite3.Row, *inputs: str | None) -> None:
    expected = max(value for value in inputs if value is not None)
    if row["effective_cutoff_utc"] != expected:
        raise MessageEvidenceError(
            f"effective cutoff mismatch: {row['effective_cutoff_utc']}"
        )


def _attestation_hash(
    content_sha256: str,
    *,
    recorded_at_utc: str,
    effective_cutoff_utc: str,
    receipt_sequence: int,
    derived: Mapping[str, Any] | None = None,
) -> str:
    return _record_hash(
        {
            "content_sha256": content_sha256,
            "recorded_at_utc": recorded_at_utc,
            "effective_cutoff_utc": effective_cutoff_utc,
            "receipt_sequence": receipt_sequence,
            "derived": dict(derived or {}),
        }
    )


def _verify_attestation(
    row: sqlite3.Row,
    *,
    derived: Mapping[str, Any] | None = None,
) -> None:
    expected = _attestation_hash(
        row["record_sha256"],
        recorded_at_utc=row["recorded_at_utc"],
        effective_cutoff_utc=row["effective_cutoff_utc"],
        receipt_sequence=row["receipt_sequence"],
        derived=derived,
    )
    if row["attestation_sha256"] != expected:
        raise MessageEvidenceError(
            f"receipt attestation mismatch: {row['attestation_sha256']}"
        )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ledger_meta (
    schema_version TEXT PRIMARY KEY,
    initialized_at_utc TEXT NOT NULL,
    receipt_high_water_utc TEXT NOT NULL,
    next_receipt_sequence INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS source_registry (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    provenance_tier TEXT NOT NULL,
    base_url TEXT,
    registered_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS entity_registry (
    entity_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    registered_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS entity_aliases (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entity_registry(entity_id),
    source_id TEXT NOT NULL REFERENCES source_registry(source_id),
    alias_text TEXT NOT NULL,
    alias_key TEXT NOT NULL,
    observed_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE,
    UNIQUE(source_id, alias_key, effective_cutoff_utc)
);

CREATE TABLE IF NOT EXISTS match_registry (
    issue TEXT NOT NULL,
    match_idx INTEGER NOT NULL,
    match_id TEXT NOT NULL UNIQUE,
    kickoff_at_utc TEXT NOT NULL,
    home_team_id TEXT NOT NULL REFERENCES entity_registry(entity_id),
    away_team_id TEXT NOT NULL REFERENCES entity_registry(entity_id),
    competition_id TEXT REFERENCES entity_registry(entity_id),
    registered_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE,
    PRIMARY KEY(issue, match_idx)
);

CREATE TABLE IF NOT EXISTS raw_captures (
    capture_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_registry(source_id),
    source_url TEXT NOT NULL,
    published_at_utc TEXT,
    observed_at_utc TEXT NOT NULL,
    fetched_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    latency_seconds REAL,
    late_arriving INTEGER,
    media_type TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    raw_bytes BLOB NOT NULL,
    metadata_json TEXT NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS evidence_facts (
    fact_id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES raw_captures(capture_id),
    issue TEXT NOT NULL,
    match_idx INTEGER NOT NULL,
    entity_id TEXT REFERENCES entity_registry(entity_id),
    fact_kind TEXT NOT NULL,
    assertion_state TEXT NOT NULL,
    value_json TEXT NOT NULL,
    confidence REAL,
    effective_from_utc TEXT,
    effective_until_utc TEXT,
    observed_at_utc TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE,
    FOREIGN KEY(issue, match_idx) REFERENCES match_registry(issue, match_idx)
);

CREATE TABLE IF NOT EXISTS evidence_relations (
    relation_id TEXT PRIMARY KEY,
    source_fact_id TEXT NOT NULL REFERENCES evidence_facts(fact_id),
    target_fact_id TEXT NOT NULL REFERENCES evidence_facts(fact_id),
    relation_type TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    note TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE,
    UNIQUE(source_fact_id, target_fact_id, relation_type)
);

CREATE TABLE IF NOT EXISTS missingness_records (
    missingness_id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES raw_captures(capture_id),
    issue TEXT NOT NULL,
    match_idx INTEGER NOT NULL,
    fact_kind TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    detail TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE,
    FOREIGN KEY(issue, match_idx) REFERENCES match_registry(issue, match_idx)
);

CREATE TABLE IF NOT EXISTS collection_observations (
    observation_id TEXT PRIMARY KEY,
    capture_id TEXT NOT NULL REFERENCES raw_captures(capture_id),
    issue TEXT NOT NULL,
    match_idx INTEGER NOT NULL,
    fact_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    expected_entity_ids_json TEXT NOT NULL,
    checked_source_ids_json TEXT NOT NULL,
    note TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL,
    effective_cutoff_utc TEXT NOT NULL,
    receipt_sequence INTEGER NOT NULL,
    record_sha256 TEXT NOT NULL UNIQUE,
    attestation_sha256 TEXT NOT NULL UNIQUE,
    FOREIGN KEY(issue, match_idx) REFERENCES match_registry(issue, match_idx),
    UNIQUE(issue, match_idx, fact_kind, effective_cutoff_utc)
);

CREATE INDEX IF NOT EXISTS idx_facts_asof
    ON evidence_facts(issue, match_idx, effective_cutoff_utc, fact_kind);
CREATE INDEX IF NOT EXISTS idx_captures_asof
    ON raw_captures(effective_cutoff_utc, source_id);
CREATE INDEX IF NOT EXISTS idx_relations_asof
    ON evidence_relations(effective_cutoff_utc, relation_type);
CREATE INDEX IF NOT EXISTS idx_missing_asof
    ON missingness_records(issue, match_idx, effective_cutoff_utc, fact_kind);
CREATE INDEX IF NOT EXISTS idx_collection_asof
    ON collection_observations(issue, match_idx, effective_cutoff_utc, fact_kind);
"""

_APPEND_ONLY_TABLES = (
    "source_registry",
    "entity_registry",
    "entity_aliases",
    "match_registry",
    "raw_captures",
    "evidence_facts",
    "evidence_relations",
    "missingness_records",
    "collection_observations",
)


class MessageEvidenceLedger:
    """SQLite-backed append-only evidence ledger and read-only consumer API."""

    def __init__(
        self,
        database: str | Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
        readonly_replica: bool = False,
    ) -> None:
        self.database = Path(database)
        self._clock = clock
        self._readonly_replica = bool(readonly_replica)

    def _system_now(self) -> str:
        return normalize_timestamp(self._clock(), "system clock")

    def initialize(self) -> None:
        if self._readonly_replica:
            raise MessageEvidenceError("readonly replica cannot be initialized")
        self.database.parent.mkdir(parents=True, exist_ok=True)
        initialized = self._system_now()
        with connect_sqlite(self.database, row_factory=True) as conn:
            conn.executescript(SCHEMA_SQL)
            for table in _APPEND_ONLY_TABLES:
                conn.executescript(
                    f"""
                    CREATE TRIGGER IF NOT EXISTS {table}_no_update
                    BEFORE UPDATE ON {table}
                    BEGIN SELECT RAISE(ABORT, 'append-only table: {table}'); END;
                    CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                    BEFORE DELETE ON {table}
                    BEGIN SELECT RAISE(ABORT, 'append-only table: {table}'); END;
                    """
                )
            existing = conn.execute("SELECT schema_version FROM ledger_meta").fetchall()
            if existing and {row["schema_version"] for row in existing} != {
                LEDGER_SCHEMA_VERSION
            }:
                raise MessageEvidenceError("incompatible ledger schema")
            conn.execute(
                """
                INSERT OR IGNORE INTO ledger_meta(
                    schema_version, initialized_at_utc,
                    receipt_high_water_utc, next_receipt_sequence
                ) VALUES(?, ?, ?, 1)
                """,
                (LEDGER_SCHEMA_VERSION, initialized, initialized),
            )

    def _connect(self, *, readonly: bool = False) -> sqlite3.Connection:
        if self._readonly_replica and not readonly:
            raise MessageEvidenceError("readonly replica cannot append records")
        if not self.database.is_file():
            raise MessageEvidenceError(f"ledger does not exist: {self.database}")
        conn: sqlite3.Connection | None = None
        try:
            conn = connect_sqlite(
                self.database,
                row_factory=True,
                readonly=readonly,
                wal=not readonly,
            )
            row = conn.execute("SELECT schema_version FROM ledger_meta").fetchone()
            if row is None or row["schema_version"] != LEDGER_SCHEMA_VERSION:
                raise MessageEvidenceError("incompatible or uninitialized ledger")
            return conn
        except BaseException:
            if conn is not None:
                conn.close()
            raise

    @contextmanager
    def _export_snapshot(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect(readonly=self._readonly_replica)
        try:
            conn.execute("BEGIN" if self._readonly_replica else "BEGIN IMMEDIATE")
            yield conn
        finally:
            if conn.in_transaction:
                conn.rollback()
            conn.close()

    def _reserve_receipt(self, conn: sqlite3.Connection) -> tuple[str, int]:
        conn.execute("BEGIN IMMEDIATE")
        candidate = self._system_now()
        row = conn.execute(
            """
            SELECT receipt_high_water_utc, next_receipt_sequence
            FROM ledger_meta WHERE schema_version=?
            """,
            (LEDGER_SCHEMA_VERSION,),
        ).fetchone()
        if row is None:
            raise MessageEvidenceError("ledger receipt state is unavailable")
        high_water = row["receipt_high_water_utc"]
        if candidate < high_water:
            raise MessageEvidenceError(
                "system clock regressed behind ledger receipt high-water mark"
            )
        if candidate == high_water:
            candidate = normalize_timestamp(
                _parse_timestamp(high_water) + timedelta(microseconds=1),
                "receipt high-water",
            )
        sequence = int(row["next_receipt_sequence"])
        conn.execute(
            """
            UPDATE ledger_meta
            SET receipt_high_water_utc=?, next_receipt_sequence=?
            WHERE schema_version=?
            """,
            (candidate, sequence + 1, LEDGER_SCHEMA_VERSION),
        )
        return candidate, sequence

    @staticmethod
    def _insert_idempotent(
        conn: sqlite3.Connection,
        *,
        table: str,
        id_column: str,
        identifier: str,
        columns: Sequence[str],
        values: Sequence[Any],
        record_sha256: str,
    ) -> str:
        placeholders = ",".join("?" for _ in columns)
        try:
            conn.execute(
                f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders})",
                values,
            )
        except sqlite3.IntegrityError as exc:
            existing = conn.execute(
                f"SELECT record_sha256 FROM {table} WHERE {id_column}=?",
                (identifier,),
            ).fetchone()
            if existing is None or existing["record_sha256"] != record_sha256:
                raise MessageEvidenceError(
                    f"immutable identity collision in {table}: {identifier}"
                ) from exc
        return identifier

    def register_source(
        self,
        *,
        source_id: str,
        name: str,
        source_type: str,
        provenance_tier: str,
        registered_at: str | datetime,
        base_url: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        source_id = _safe_id(source_id, "source_id")
        name = str(name or "").strip()
        if not name:
            raise MessageEvidenceError("source name is required")
        source_type = _choice(source_type, SOURCE_TYPES, "source_type")
        provenance_tier = _choice(provenance_tier, PROVENANCE_TIERS, "provenance_tier")
        base_url = _http_url(base_url, "base_url", optional=True)
        if provenance_tier == "TIER_0_OFFICIAL" and base_url is None:
            raise MessageEvidenceError("official sources require base_url")
        registered = normalize_timestamp(registered_at, "registered_at")
        metadata_json = _metadata(metadata)
        record = {
            "source_id": source_id,
            "name": name,
            "source_type": source_type,
            "provenance_tier": provenance_tier,
            "base_url": base_url,
            "registered_at_utc": registered,
            "metadata": json.loads(metadata_json),
        }
        checksum = _record_hash(record)
        with self._connect() as conn:
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(registered, recorded)
            attestation = _attestation_hash(
                checksum,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="source_registry",
                id_column="source_id",
                identifier=source_id,
                columns=(
                    "source_id",
                    "name",
                    "source_type",
                    "provenance_tier",
                    "base_url",
                    "registered_at_utc",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "metadata_json",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    source_id,
                    name,
                    source_type,
                    provenance_tier,
                    base_url,
                    registered,
                    recorded,
                    effective_cutoff,
                    receipt_sequence,
                    metadata_json,
                    checksum,
                    attestation,
                ),
                record_sha256=checksum,
            )

    def register_entity(
        self,
        *,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        registered_at: str | datetime,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        entity_id = _safe_id(entity_id, "entity_id")
        entity_type = _choice(entity_type, ENTITY_TYPES, "entity_type")
        canonical_name = str(canonical_name or "").strip()
        if not canonical_name:
            raise MessageEvidenceError("canonical_name is required")
        registered = normalize_timestamp(registered_at, "registered_at")
        metadata_json = _metadata(metadata)
        record = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "canonical_name": canonical_name,
            "registered_at_utc": registered,
            "metadata": json.loads(metadata_json),
        }
        checksum = _record_hash(record)
        with self._connect() as conn:
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(registered, recorded)
            attestation = _attestation_hash(
                checksum,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="entity_registry",
                id_column="entity_id",
                identifier=entity_id,
                columns=(
                    "entity_id",
                    "entity_type",
                    "canonical_name",
                    "registered_at_utc",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "metadata_json",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    entity_id,
                    entity_type,
                    canonical_name,
                    registered,
                    recorded,
                    effective_cutoff,
                    receipt_sequence,
                    metadata_json,
                    checksum,
                    attestation,
                ),
                record_sha256=checksum,
            )

    def register_alias(
        self,
        *,
        entity_id: str,
        source_id: str,
        alias_text: str,
        observed_at: str | datetime,
    ) -> str:
        entity_id = _safe_id(entity_id, "entity_id")
        source_id = _safe_id(source_id, "source_id")
        alias_text = str(alias_text or "").strip()
        if not alias_text:
            raise MessageEvidenceError("alias_text is required")
        observed = normalize_timestamp(observed_at, "observed_at")
        alias_key = " ".join(alias_text.casefold().split())
        record = {
            "entity_id": entity_id,
            "source_id": source_id,
            "alias_text": alias_text,
            "alias_key": alias_key,
            "observed_at_utc": observed,
        }
        alias_id = _record_hash(record)
        with self._connect() as conn:
            entity = conn.execute(
                "SELECT effective_cutoff_utc FROM entity_registry WHERE entity_id=?",
                (entity_id,),
            ).fetchone()
            source = conn.execute(
                "SELECT effective_cutoff_utc FROM source_registry WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if entity is None or source is None:
                raise MessageEvidenceError("alias source and entity must be registered")
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(
                observed,
                recorded,
                entity["effective_cutoff_utc"],
                source["effective_cutoff_utc"],
            )
            attestation = _attestation_hash(
                alias_id,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="entity_aliases",
                id_column="alias_id",
                identifier=alias_id,
                columns=(
                    "alias_id",
                    "entity_id",
                    "source_id",
                    "alias_text",
                    "alias_key",
                    "observed_at_utc",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    alias_id,
                    entity_id,
                    source_id,
                    alias_text,
                    alias_key,
                    observed,
                    recorded,
                    effective_cutoff,
                    receipt_sequence,
                    alias_id,
                    attestation,
                ),
                record_sha256=alias_id,
            )

    def register_match(
        self,
        *,
        issue: str,
        match_idx: int,
        match_id: str,
        kickoff_at: str | datetime,
        home_team_id: str,
        away_team_id: str,
        registered_at: str | datetime,
        competition_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        issue = _safe_id(issue, "issue")
        try:
            match_idx = int(match_idx)
        except (TypeError, ValueError) as exc:
            raise MessageEvidenceError("match_idx must be an integer") from exc
        if match_idx <= 0:
            raise MessageEvidenceError("match_idx must be positive")
        match_id = _safe_id(match_id, "match_id")
        home_team_id = _safe_id(home_team_id, "home_team_id")
        away_team_id = _safe_id(away_team_id, "away_team_id")
        if home_team_id == away_team_id:
            raise MessageEvidenceError("home and away teams must be distinct")
        competition_id = (
            _safe_id(competition_id, "competition_id")
            if competition_id is not None
            else None
        )
        kickoff = normalize_timestamp(kickoff_at, "kickoff_at")
        registered = normalize_timestamp(registered_at, "registered_at")
        metadata_json = _metadata(metadata)
        record = {
            "issue": issue,
            "match_idx": match_idx,
            "match_id": match_id,
            "kickoff_at_utc": kickoff,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "competition_id": competition_id,
            "registered_at_utc": registered,
            "metadata": json.loads(metadata_json),
        }
        checksum = _record_hash(record)
        identifier = f"{issue}:{match_idx}"
        with self._connect() as conn:
            referenced_entities = [home_team_id, away_team_id]
            if competition_id is not None:
                referenced_entities.append(competition_id)
            placeholders = ",".join("?" for _ in referenced_entities)
            entity_rows = conn.execute(
                f"""
                SELECT entity_id, entity_type, effective_cutoff_utc
                FROM entity_registry
                WHERE entity_id IN ({placeholders})
                """,
                referenced_entities,
            ).fetchall()
            if {row["entity_id"] for row in entity_rows} != set(referenced_entities):
                raise MessageEvidenceError("match contains unknown entities")
            entity_types = {row["entity_id"]: row["entity_type"] for row in entity_rows}
            if (
                entity_types[home_team_id] != "team"
                or entity_types[away_team_id] != "team"
            ):
                raise MessageEvidenceError(
                    "home_team_id and away_team_id must be teams"
                )
            if (
                competition_id is not None
                and entity_types[competition_id] != "competition"
            ):
                raise MessageEvidenceError("competition_id must be a competition")
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(
                registered,
                recorded,
                *(row["effective_cutoff_utc"] for row in entity_rows),
            )
            attestation = _attestation_hash(
                checksum,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            try:
                conn.execute(
                    """
                    INSERT INTO match_registry(
                        issue, match_idx, match_id, kickoff_at_utc,
                        home_team_id, away_team_id, competition_id,
                        registered_at_utc, recorded_at_utc,
                        effective_cutoff_utc, receipt_sequence,
                        metadata_json, record_sha256, attestation_sha256
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        issue,
                        match_idx,
                        match_id,
                        kickoff,
                        home_team_id,
                        away_team_id,
                        competition_id,
                        registered,
                        recorded,
                        effective_cutoff,
                        receipt_sequence,
                        metadata_json,
                        checksum,
                        attestation,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                existing = conn.execute(
                    "SELECT record_sha256 FROM match_registry WHERE issue=? AND match_idx=?",
                    (issue, match_idx),
                ).fetchone()
                if existing is None or existing["record_sha256"] != checksum:
                    raise MessageEvidenceError(
                        f"immutable identity collision in match_registry: {identifier}"
                    ) from exc
        return identifier

    def append_capture(
        self,
        *,
        source_id: str,
        source_url: str,
        raw_bytes: bytes,
        observed_at: str | datetime,
        fetched_at: str | datetime,
        published_at: str | datetime | None = None,
        media_type: str = "application/octet-stream",
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        source_id = _safe_id(source_id, "source_id")
        source_url = str(_http_url(source_url, "source_url"))
        if not isinstance(raw_bytes, bytes):
            raise MessageEvidenceError("raw_bytes must be bytes")
        if len(raw_bytes) > MAX_RAW_CAPTURE_BYTES:
            raise MessageEvidenceError(
                f"raw capture exceeds {MAX_RAW_CAPTURE_BYTES} bytes"
            )
        observed = normalize_timestamp(observed_at, "observed_at")
        fetched = normalize_timestamp(fetched_at, "fetched_at")
        published = _optional_timestamp(published_at, "published_at")
        observed_dt = _parse_timestamp(observed)
        fetched_dt = _parse_timestamp(fetched)
        if observed_dt > fetched_dt:
            raise MessageEvidenceError("observed_at cannot be after fetched_at")
        published_dt = _parse_timestamp(published) if published else None
        if published_dt is not None and published_dt > fetched_dt:
            raise MessageEvidenceError("published_at cannot be after fetched_at")
        effective = max(
            value
            for value in (published_dt, observed_dt, fetched_dt)
            if value is not None
        )
        effective_text = normalize_timestamp(effective, "effective_cutoff")
        latency = (
            (fetched_dt - published_dt).total_seconds()
            if published_dt is not None
            else None
        )
        late_arriving = (
            int(latency > LATE_ARRIVAL_SECONDS) if latency is not None else None
        )
        media_type = str(media_type or "").strip().lower()
        if not media_type or len(media_type) > 160:
            raise MessageEvidenceError("media_type is invalid")
        metadata_json = _metadata(metadata)
        raw_sha256 = sha256_bytes(raw_bytes)
        identity = {
            "source_id": source_id,
            "source_url": source_url,
            "published_at_utc": published,
            "observed_at_utc": observed,
            "fetched_at_utc": fetched,
            "media_type": media_type,
            "raw_sha256": raw_sha256,
            "metadata": json.loads(metadata_json),
        }
        with self._connect() as conn:
            source = conn.execute(
                """
                SELECT provenance_tier, base_url, effective_cutoff_utc
                FROM source_registry WHERE source_id=?
                """,
                (source_id,),
            ).fetchone()
            if source is None:
                raise MessageEvidenceError("source_id is not registered")
            if source["provenance_tier"] == "TIER_0_OFFICIAL":
                registered_origin = urlparse(source["base_url"])
                capture_origin = urlparse(source_url)
                if (
                    registered_origin.scheme.lower(),
                    registered_origin.netloc.lower(),
                ) != (
                    capture_origin.scheme.lower(),
                    capture_origin.netloc.lower(),
                ):
                    raise MessageEvidenceError(
                        "official capture URL must match registered base_url origin"
                    )
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_text = max(
                effective_text,
                source["effective_cutoff_utc"],
                recorded,
            )
            capture_id = _record_hash(identity)
            attestation = _attestation_hash(
                capture_id,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_text,
                receipt_sequence=receipt_sequence,
                derived={
                    "latency_seconds": latency,
                    "late_arriving": late_arriving,
                },
            )
            return self._insert_idempotent(
                conn,
                table="raw_captures",
                id_column="capture_id",
                identifier=capture_id,
                columns=(
                    "capture_id",
                    "source_id",
                    "source_url",
                    "published_at_utc",
                    "observed_at_utc",
                    "fetched_at_utc",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "latency_seconds",
                    "late_arriving",
                    "media_type",
                    "raw_sha256",
                    "raw_bytes",
                    "metadata_json",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    capture_id,
                    source_id,
                    source_url,
                    published,
                    observed,
                    fetched,
                    recorded,
                    effective_text,
                    receipt_sequence,
                    latency,
                    late_arriving,
                    media_type,
                    raw_sha256,
                    raw_bytes,
                    metadata_json,
                    capture_id,
                    attestation,
                ),
                record_sha256=capture_id,
            )

    def append_fact(
        self,
        *,
        capture_id: str,
        issue: str,
        match_idx: int,
        fact_kind: str,
        value: object,
        assertion_state: str = "affirmed",
        entity_id: str | None = None,
        confidence: float | None = None,
        effective_from: str | datetime | None = None,
        effective_until: str | datetime | None = None,
    ) -> str:
        capture_id = _safe_id(capture_id, "capture_id")
        issue = _safe_id(issue, "issue")
        fact_kind = _choice(fact_kind, FACT_KINDS, "fact_kind")
        assertion_state = _choice(assertion_state, ASSERTION_STATES, "assertion_state")
        entity_id = _safe_id(entity_id, "entity_id") if entity_id else None
        try:
            match_idx = int(match_idx)
        except (TypeError, ValueError) as exc:
            raise MessageEvidenceError("match_idx must be an integer") from exc
        if match_idx <= 0:
            raise MessageEvidenceError("match_idx must be positive")
        if confidence is not None:
            confidence = float(confidence)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise MessageEvidenceError("confidence must be between 0 and 1")
        effective_from_text = _optional_timestamp(effective_from, "effective_from")
        effective_until_text = _optional_timestamp(effective_until, "effective_until")
        if (
            effective_from_text
            and effective_until_text
            and _parse_timestamp(effective_from_text)
            > _parse_timestamp(effective_until_text)
        ):
            raise MessageEvidenceError("effective_from cannot be after effective_until")
        if not isinstance(value, Mapping) or not value:
            raise MessageEvidenceError("fact value must be a non-empty JSON object")
        normalized_value = dict(value)
        if fact_kind == "schedule" and "kickoff_at_utc" in normalized_value:
            normalized_value["kickoff_at_utc"] = normalize_timestamp(
                normalized_value["kickoff_at_utc"], "schedule kickoff_at_utc"
            )
        try:
            value_json = canonical_json(normalized_value).decode("utf-8")
        except (TypeError, ValueError) as exc:
            raise MessageEvidenceError("fact value must be canonical JSON") from exc
        with self._connect() as conn:
            capture = conn.execute(
                """
                SELECT observed_at_utc, effective_cutoff_utc
                FROM raw_captures WHERE capture_id=?
                """,
                (capture_id,),
            ).fetchone()
            if capture is None:
                raise MessageEvidenceError("capture_id is not registered")
            match = conn.execute(
                """
                SELECT effective_cutoff_utc FROM match_registry
                WHERE issue=? AND match_idx=?
                """,
                (issue, match_idx),
            ).fetchone()
            if match is None:
                raise MessageEvidenceError("issue/match_idx is not registered")
            entity_registered: str | None = None
            if entity_id is not None:
                entity = conn.execute(
                    """
                    SELECT effective_cutoff_utc FROM entity_registry
                    WHERE entity_id=?
                    """,
                    (entity_id,),
                ).fetchone()
                if entity is None:
                    raise MessageEvidenceError("entity_id is not registered")
                entity_registered = entity["effective_cutoff_utc"]
            coverage_entity_ids_raw = value.get("coverage_entity_ids", [])
            if not isinstance(coverage_entity_ids_raw, list):
                raise MessageEvidenceError("coverage_entity_ids must be an array")
            coverage_entity_ids = sorted(
                {
                    _safe_id(item, "coverage_entity_id")
                    for item in coverage_entity_ids_raw
                }
            )
            coverage_entity_cutoffs: list[str] = []
            if coverage_entity_ids:
                placeholders = ",".join("?" for _ in coverage_entity_ids)
                coverage_entities = conn.execute(
                    f"""
                    SELECT entity_id, effective_cutoff_utc FROM entity_registry
                    WHERE entity_id IN ({placeholders})
                    """,
                    coverage_entity_ids,
                ).fetchall()
                if {row["entity_id"] for row in coverage_entities} != set(
                    coverage_entity_ids
                ):
                    raise MessageEvidenceError(
                        "coverage_entity_ids contain unknown entities"
                    )
                coverage_entity_cutoffs = [
                    row["effective_cutoff_utc"] for row in coverage_entities
                ]
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(
                timestamp
                for timestamp in (
                    capture["effective_cutoff_utc"],
                    match["effective_cutoff_utc"],
                    entity_registered,
                    recorded,
                    *coverage_entity_cutoffs,
                )
                if timestamp is not None
            )
            record = {
                "capture_id": capture_id,
                "issue": issue,
                "match_idx": match_idx,
                "entity_id": entity_id,
                "fact_kind": fact_kind,
                "assertion_state": assertion_state,
                "value": json.loads(value_json),
                "confidence": confidence,
                "effective_from_utc": effective_from_text,
                "effective_until_utc": effective_until_text,
                "observed_at_utc": capture["observed_at_utc"],
            }
            fact_id = _record_hash(record)
            attestation = _attestation_hash(
                fact_id,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="evidence_facts",
                id_column="fact_id",
                identifier=fact_id,
                columns=(
                    "fact_id",
                    "capture_id",
                    "issue",
                    "match_idx",
                    "entity_id",
                    "fact_kind",
                    "assertion_state",
                    "value_json",
                    "confidence",
                    "effective_from_utc",
                    "effective_until_utc",
                    "observed_at_utc",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    fact_id,
                    capture_id,
                    issue,
                    match_idx,
                    entity_id,
                    fact_kind,
                    assertion_state,
                    value_json,
                    confidence,
                    effective_from_text,
                    effective_until_text,
                    capture["observed_at_utc"],
                    recorded,
                    effective_cutoff,
                    receipt_sequence,
                    fact_id,
                    attestation,
                ),
                record_sha256=fact_id,
            )

    def append_relation(
        self,
        *,
        source_fact_id: str,
        target_fact_id: str,
        relation_type: str,
        note: str = "",
    ) -> str:
        source_fact_id = _safe_id(source_fact_id, "source_fact_id")
        target_fact_id = _safe_id(target_fact_id, "target_fact_id")
        if source_fact_id == target_fact_id:
            raise MessageEvidenceError("a fact cannot relate to itself")
        relation_type = _choice(relation_type, RELATION_TYPES, "relation_type")
        note = str(note or "").strip()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fact_id, issue, match_idx, entity_id, fact_kind,
                       effective_cutoff_utc, receipt_sequence
                FROM evidence_facts WHERE fact_id IN (?, ?)
                """,
                (source_fact_id, target_fact_id),
            ).fetchall()
            facts = {row["fact_id"]: row for row in rows}
            if set(facts) != {source_fact_id, target_fact_id}:
                raise MessageEvidenceError("relation facts must already exist")
            source = facts[source_fact_id]
            target = facts[target_fact_id]
            identity_fields = ("issue", "match_idx", "entity_id", "fact_kind")
            if any(source[field] != target[field] for field in identity_fields):
                raise MessageEvidenceError(
                    "related facts must describe the same match/entity/kind"
                )
            if (
                source["effective_cutoff_utc"],
                source["receipt_sequence"],
            ) <= (
                target["effective_cutoff_utc"],
                target["receipt_sequence"],
            ):
                raise MessageEvidenceError(
                    "relation source must be strictly later than its target"
                )
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(source["effective_cutoff_utc"], recorded)
            record = {
                "source_fact_id": source_fact_id,
                "target_fact_id": target_fact_id,
                "relation_type": relation_type,
                "note": note,
            }
            relation_id = _record_hash(record)
            attestation = _attestation_hash(
                relation_id,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="evidence_relations",
                id_column="relation_id",
                identifier=relation_id,
                columns=(
                    "relation_id",
                    "source_fact_id",
                    "target_fact_id",
                    "relation_type",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "note",
                    "receipt_sequence",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    relation_id,
                    source_fact_id,
                    target_fact_id,
                    relation_type,
                    recorded,
                    effective_cutoff,
                    note,
                    receipt_sequence,
                    relation_id,
                    attestation,
                ),
                record_sha256=relation_id,
            )

    def append_missingness(
        self,
        *,
        capture_id: str,
        issue: str,
        match_idx: int,
        fact_kind: str,
        reason_code: str,
        detail: str = "",
    ) -> str:
        capture_id = _safe_id(capture_id, "capture_id")
        issue = _safe_id(issue, "issue")
        fact_kind = _choice(fact_kind, FACT_KINDS, "fact_kind")
        reason_code = _choice(reason_code, MISSING_REASON_CODES, "reason_code")
        detail = str(detail or "").strip()
        try:
            match_idx = int(match_idx)
        except (TypeError, ValueError) as exc:
            raise MessageEvidenceError("match_idx must be an integer") from exc
        if match_idx <= 0:
            raise MessageEvidenceError("match_idx must be positive")
        with self._connect() as conn:
            capture = conn.execute(
                "SELECT effective_cutoff_utc FROM raw_captures WHERE capture_id=?",
                (capture_id,),
            ).fetchone()
            if capture is None:
                raise MessageEvidenceError("capture_id is not registered")
            match = conn.execute(
                """
                SELECT effective_cutoff_utc FROM match_registry
                WHERE issue=? AND match_idx=?
                """,
                (issue, match_idx),
            ).fetchone()
            if match is None:
                raise MessageEvidenceError("issue/match_idx is not registered")
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(
                capture["effective_cutoff_utc"],
                match["effective_cutoff_utc"],
                recorded,
            )
            record = {
                "capture_id": capture_id,
                "issue": issue,
                "match_idx": match_idx,
                "fact_kind": fact_kind,
                "reason_code": reason_code,
                "detail": detail,
            }
            missingness_id = _record_hash(record)
            attestation = _attestation_hash(
                missingness_id,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="missingness_records",
                id_column="missingness_id",
                identifier=missingness_id,
                columns=(
                    "missingness_id",
                    "capture_id",
                    "issue",
                    "match_idx",
                    "fact_kind",
                    "reason_code",
                    "detail",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    missingness_id,
                    capture_id,
                    issue,
                    match_idx,
                    fact_kind,
                    reason_code,
                    detail,
                    recorded,
                    effective_cutoff,
                    receipt_sequence,
                    missingness_id,
                    attestation,
                ),
                record_sha256=missingness_id,
            )

    def append_collection_observation(
        self,
        *,
        capture_id: str,
        issue: str,
        match_idx: int,
        fact_kind: str,
        status: str,
        expected_entity_ids: Sequence[str],
        checked_source_ids: Sequence[str],
        note: str = "",
    ) -> str:
        """Append an audited statement about collection completeness."""

        capture_id = _safe_id(capture_id, "capture_id")
        issue = _safe_id(issue, "issue")
        fact_kind = _choice(fact_kind, FACT_KINDS, "fact_kind")
        status = _choice(status, COLLECTION_STATUSES, "status")
        try:
            match_idx = int(match_idx)
        except (TypeError, ValueError) as exc:
            raise MessageEvidenceError("match_idx must be an integer") from exc
        if match_idx <= 0:
            raise MessageEvidenceError("match_idx must be positive")
        expected_entities = sorted(
            {_safe_id(value, "expected_entity_id") for value in expected_entity_ids}
        )
        checked_sources = sorted(
            {_safe_id(value, "checked_source_id") for value in checked_source_ids}
        )
        if not expected_entities:
            raise MessageEvidenceError("expected_entity_ids cannot be empty")
        if not checked_sources:
            raise MessageEvidenceError("checked_source_ids cannot be empty")
        note = str(note or "").strip()
        with self._connect() as conn:
            capture = conn.execute(
                """
                SELECT source_id, effective_cutoff_utc
                FROM raw_captures WHERE capture_id=?
                """,
                (capture_id,),
            ).fetchone()
            if capture is None:
                raise MessageEvidenceError("capture_id is not registered")
            if capture["source_id"] not in checked_sources:
                raise MessageEvidenceError(
                    "capture source must appear in checked_source_ids"
                )
            match = conn.execute(
                """
                SELECT effective_cutoff_utc, home_team_id, away_team_id
                FROM match_registry
                WHERE issue=? AND match_idx=?
                """,
                (issue, match_idx),
            ).fetchone()
            if match is None:
                raise MessageEvidenceError("issue/match_idx is not registered")
            match_teams = {match["home_team_id"], match["away_team_id"]}
            if not match_teams.issubset(expected_entities):
                raise MessageEvidenceError(
                    "expected_entity_ids must include both match teams"
                )
            entity_placeholders = ",".join("?" for _ in expected_entities)
            known_entities = conn.execute(
                f"""
                SELECT entity_id, effective_cutoff_utc FROM entity_registry
                WHERE entity_id IN ({entity_placeholders})
                """,
                expected_entities,
            ).fetchall()
            if {row["entity_id"] for row in known_entities} != set(expected_entities):
                raise MessageEvidenceError(
                    "expected_entity_ids contain unknown entities"
                )
            source_placeholders = ",".join("?" for _ in checked_sources)
            known_sources = conn.execute(
                f"""
                SELECT source_id, effective_cutoff_utc FROM source_registry
                WHERE source_id IN ({source_placeholders})
                """,
                checked_sources,
            ).fetchall()
            if {row["source_id"] for row in known_sources} != set(checked_sources):
                raise MessageEvidenceError("checked_source_ids contain unknown sources")
            recorded, receipt_sequence = self._reserve_receipt(conn)
            effective_cutoff = max(
                capture["effective_cutoff_utc"],
                match["effective_cutoff_utc"],
                recorded,
                *(row["effective_cutoff_utc"] for row in known_entities),
                *(row["effective_cutoff_utc"] for row in known_sources),
            )
            record = {
                "capture_id": capture_id,
                "issue": issue,
                "match_idx": match_idx,
                "fact_kind": fact_kind,
                "status": status,
                "expected_entity_ids": expected_entities,
                "checked_source_ids": checked_sources,
                "note": note,
            }
            observation_id = _record_hash(record)
            attestation = _attestation_hash(
                observation_id,
                recorded_at_utc=recorded,
                effective_cutoff_utc=effective_cutoff,
                receipt_sequence=receipt_sequence,
            )
            return self._insert_idempotent(
                conn,
                table="collection_observations",
                id_column="observation_id",
                identifier=observation_id,
                columns=(
                    "observation_id",
                    "capture_id",
                    "issue",
                    "match_idx",
                    "fact_kind",
                    "status",
                    "expected_entity_ids_json",
                    "checked_source_ids_json",
                    "note",
                    "recorded_at_utc",
                    "effective_cutoff_utc",
                    "receipt_sequence",
                    "record_sha256",
                    "attestation_sha256",
                ),
                values=(
                    observation_id,
                    capture_id,
                    issue,
                    match_idx,
                    fact_kind,
                    status,
                    canonical_json(expected_entities).decode("utf-8"),
                    canonical_json(checked_sources).decode("utf-8"),
                    note,
                    recorded,
                    effective_cutoff,
                    receipt_sequence,
                    observation_id,
                    attestation,
                ),
                record_sha256=observation_id,
            )

    @staticmethod
    def _where_scope(
        *, issue: str | None, match_idx: int | None, prefix: str = "f"
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if issue is not None:
            clauses.append(f"{prefix}.issue=?")
            params.append(_safe_id(issue, "issue"))
        if match_idx is not None:
            if issue is None:
                raise MessageEvidenceError("match_idx scope requires issue")
            try:
                match_idx = int(match_idx)
            except (TypeError, ValueError) as exc:
                raise MessageEvidenceError("match_idx must be an integer") from exc
            if match_idx <= 0:
                raise MessageEvidenceError("match_idx must be positive")
            clauses.append(f"{prefix}.match_idx=?")
            params.append(match_idx)
        return (" AND " + " AND ".join(clauses) if clauses else ""), params

    def export_as_of(
        self,
        *,
        cutoff: str | datetime,
        issue: str | None = None,
        match_idx: int | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic read-only projection available at ``cutoff``."""

        cutoff_text = normalize_timestamp(cutoff, "cutoff")
        issue = _safe_id(issue, "issue") if issue is not None else None
        if match_idx is not None:
            try:
                match_idx = int(match_idx)
            except (TypeError, ValueError) as exc:
                raise MessageEvidenceError("match_idx must be an integer") from exc
            if match_idx <= 0:
                raise MessageEvidenceError("match_idx must be positive")
        fact_scope, fact_scope_params = self._where_scope(
            issue=issue, match_idx=match_idx, prefix="f"
        )
        match_scope, match_scope_params = self._where_scope(
            issue=issue, match_idx=match_idx, prefix="m"
        )
        missing_scope, missing_scope_params = self._where_scope(
            issue=issue, match_idx=match_idx, prefix="x"
        )
        observation_scope, observation_scope_params = self._where_scope(
            issue=issue, match_idx=match_idx, prefix="o"
        )
        # A live ledger reserves the writer slot to serialize with appends.
        # Only an explicitly declared immutable replica uses a plain read
        # transaction; silently falling back could race a differently
        # credentialed writer on a shared live database.
        with self._export_snapshot() as conn:
            match_rows = conn.execute(
                f"""
                SELECT m.* FROM match_registry m
                WHERE m.effective_cutoff_utc<=? {match_scope}
                ORDER BY m.issue, m.match_idx
                """,
                [cutoff_text, *match_scope_params],
            ).fetchall()
            fact_rows = conn.execute(
                f"""
                SELECT f.*, c.source_id, c.source_url, c.published_at_utc,
                       c.fetched_at_utc, c.raw_sha256, s.provenance_tier
                FROM evidence_facts f
                JOIN raw_captures c ON c.capture_id=f.capture_id
                JOIN source_registry s ON s.source_id=c.source_id
                WHERE f.effective_cutoff_utc<=? {fact_scope}
                ORDER BY f.issue, f.match_idx, f.fact_kind,
                         f.effective_cutoff_utc, f.fact_id
                """,
                [cutoff_text, *fact_scope_params],
            ).fetchall()
            fact_ids = {row["fact_id"] for row in fact_rows}
            relation_rows = conn.execute(
                """
                SELECT * FROM evidence_relations
                WHERE effective_cutoff_utc<=?
                ORDER BY effective_cutoff_utc, relation_id
                """,
                (cutoff_text,),
            ).fetchall()
            relation_rows = [
                row
                for row in relation_rows
                if row["source_fact_id"] in fact_ids
                and row["target_fact_id"] in fact_ids
            ]
            missing_rows = conn.execute(
                f"""
                SELECT x.* FROM missingness_records x
                WHERE x.effective_cutoff_utc<=? {missing_scope}
                ORDER BY x.issue, x.match_idx, x.fact_kind,
                         x.effective_cutoff_utc, x.missingness_id
                """,
                [cutoff_text, *missing_scope_params],
            ).fetchall()
            observation_rows = conn.execute(
                f"""
                SELECT o.* FROM collection_observations o
                WHERE o.effective_cutoff_utc<=? {observation_scope}
                ORDER BY o.issue, o.match_idx, o.fact_kind,
                         o.effective_cutoff_utc, o.observation_id
                """,
                [cutoff_text, *observation_scope_params],
            ).fetchall()
            capture_ids = sorted(
                {row["capture_id"] for row in fact_rows}
                | {row["capture_id"] for row in missing_rows}
                | {row["capture_id"] for row in observation_rows}
            )
            capture_rows: list[sqlite3.Row] = []
            if capture_ids:
                placeholders = ",".join("?" for _ in capture_ids)
                capture_rows = conn.execute(
                    f"""
                    SELECT * FROM raw_captures
                    WHERE capture_id IN ({placeholders})
                    ORDER BY effective_cutoff_utc, capture_id
                    """,
                    capture_ids,
                ).fetchall()
            for row in capture_rows:
                if sha256_bytes(bytes(row["raw_bytes"])) != row["raw_sha256"]:
                    raise MessageEvidenceError(
                        f"raw capture hash mismatch: {row['capture_id']}"
                    )
            entity_ids = sorted(
                {
                    entity_id
                    for row in match_rows
                    for entity_id in (
                        row["home_team_id"],
                        row["away_team_id"],
                        row["competition_id"],
                    )
                    if entity_id is not None
                }
                | {
                    row["entity_id"]
                    for row in fact_rows
                    if row["entity_id"] is not None
                }
                | {
                    entity_id
                    for row in fact_rows
                    for entity_id in json.loads(row["value_json"]).get(
                        "coverage_entity_ids", []
                    )
                }
                | {
                    entity_id
                    for row in observation_rows
                    for entity_id in json.loads(row["expected_entity_ids_json"])
                }
            )
            entity_rows: list[sqlite3.Row] = []
            alias_rows: list[sqlite3.Row] = []
            if entity_ids:
                placeholders = ",".join("?" for _ in entity_ids)
                entity_rows = conn.execute(
                    f"""
                    SELECT * FROM entity_registry
                    WHERE entity_id IN ({placeholders})
                      AND effective_cutoff_utc<=?
                    ORDER BY entity_id
                    """,
                    [*entity_ids, cutoff_text],
                ).fetchall()
                visible_entity_ids = [row["entity_id"] for row in entity_rows]
                if visible_entity_ids:
                    placeholders = ",".join("?" for _ in visible_entity_ids)
                    alias_seeds = conn.execute(
                        f"""
                        SELECT a.* FROM entity_aliases a
                        WHERE a.entity_id IN ({placeholders})
                          AND a.effective_cutoff_utc<=?
                        """,
                        [*visible_entity_ids, cutoff_text],
                    ).fetchall()
                    alias_keys = sorted(
                        {(row["source_id"], row["alias_key"]) for row in alias_seeds}
                    )
                    if alias_keys:
                        key_clause = " OR ".join(
                            "(a.source_id=? AND a.alias_key=?)" for _ in alias_keys
                        )
                        key_params = [value for pair in alias_keys for value in pair]
                        alias_rows = conn.execute(
                            f"""
                            SELECT a.* FROM entity_aliases a
                            WHERE a.effective_cutoff_utc<=?
                              AND ({key_clause})
                            ORDER BY a.source_id, a.alias_key,
                                     a.effective_cutoff_utc,
                                     a.receipt_sequence, a.alias_id
                            """,
                            [cutoff_text, *key_params],
                        ).fetchall()
                        alias_entity_ids = sorted(
                            {row["entity_id"] for row in alias_rows}
                            - set(visible_entity_ids)
                        )
                        if alias_entity_ids:
                            placeholders = ",".join("?" for _ in alias_entity_ids)
                            entity_rows.extend(
                                conn.execute(
                                    f"""
                                    SELECT * FROM entity_registry
                                    WHERE entity_id IN ({placeholders})
                                      AND effective_cutoff_utc<=?
                                    ORDER BY entity_id
                                    """,
                                    [*alias_entity_ids, cutoff_text],
                                ).fetchall()
                            )
                            entity_rows.sort(key=lambda row: row["entity_id"])
            source_ids = sorted(
                {row["source_id"] for row in capture_rows}
                | {row["source_id"] for row in alias_rows}
                | {
                    source_id
                    for row in observation_rows
                    for source_id in json.loads(row["checked_source_ids_json"])
                }
            )
            source_rows: list[sqlite3.Row] = []
            if source_ids:
                placeholders = ",".join("?" for _ in source_ids)
                source_rows = conn.execute(
                    f"""
                    SELECT * FROM source_registry
                    WHERE source_id IN ({placeholders})
                      AND effective_cutoff_utc<=?
                    ORDER BY source_id
                    """,
                    [*source_ids, cutoff_text],
                ).fetchall()
            source_by_id = {row["source_id"]: row for row in source_rows}
            entity_by_id = {row["entity_id"]: row for row in entity_rows}
            match_by_key = {(row["issue"], row["match_idx"]): row for row in match_rows}
            capture_by_id = {row["capture_id"]: row for row in capture_rows}
            fact_by_id = {row["fact_id"]: row for row in fact_rows}
            for row in source_rows:
                _verify_record_hash(
                    row,
                    {
                        "source_id": row["source_id"],
                        "name": row["name"],
                        "source_type": row["source_type"],
                        "provenance_tier": row["provenance_tier"],
                        "base_url": row["base_url"],
                        "registered_at_utc": row["registered_at_utc"],
                        "metadata": json.loads(row["metadata_json"]),
                    },
                )
                _verify_effective_cutoff(
                    row, row["registered_at_utc"], row["recorded_at_utc"]
                )
                _verify_attestation(row)
            for row in entity_rows:
                _verify_record_hash(
                    row,
                    {
                        "entity_id": row["entity_id"],
                        "entity_type": row["entity_type"],
                        "canonical_name": row["canonical_name"],
                        "registered_at_utc": row["registered_at_utc"],
                        "metadata": json.loads(row["metadata_json"]),
                    },
                )
                _verify_effective_cutoff(
                    row, row["registered_at_utc"], row["recorded_at_utc"]
                )
                _verify_attestation(row)
            for row in alias_rows:
                _verify_record_hash(
                    row,
                    {
                        "entity_id": row["entity_id"],
                        "source_id": row["source_id"],
                        "alias_text": row["alias_text"],
                        "alias_key": row["alias_key"],
                        "observed_at_utc": row["observed_at_utc"],
                    },
                    identifier_field="alias_id",
                )
                _verify_effective_cutoff(
                    row,
                    row["observed_at_utc"],
                    row["recorded_at_utc"],
                    entity_by_id[row["entity_id"]]["effective_cutoff_utc"],
                    source_by_id[row["source_id"]]["effective_cutoff_utc"],
                )
                _verify_attestation(row)
            for row in match_rows:
                _verify_record_hash(
                    row,
                    {
                        "issue": row["issue"],
                        "match_idx": row["match_idx"],
                        "match_id": row["match_id"],
                        "kickoff_at_utc": row["kickoff_at_utc"],
                        "home_team_id": row["home_team_id"],
                        "away_team_id": row["away_team_id"],
                        "competition_id": row["competition_id"],
                        "registered_at_utc": row["registered_at_utc"],
                        "metadata": json.loads(row["metadata_json"]),
                    },
                )
                match_entities = [row["home_team_id"], row["away_team_id"]]
                if row["competition_id"] is not None:
                    match_entities.append(row["competition_id"])
                _verify_effective_cutoff(
                    row,
                    row["registered_at_utc"],
                    row["recorded_at_utc"],
                    *(
                        entity_by_id[entity_id]["effective_cutoff_utc"]
                        for entity_id in match_entities
                    ),
                )
                _verify_attestation(row)
            for row in capture_rows:
                _verify_record_hash(
                    row,
                    {
                        "source_id": row["source_id"],
                        "source_url": row["source_url"],
                        "published_at_utc": row["published_at_utc"],
                        "observed_at_utc": row["observed_at_utc"],
                        "fetched_at_utc": row["fetched_at_utc"],
                        "media_type": row["media_type"],
                        "raw_sha256": row["raw_sha256"],
                        "metadata": json.loads(row["metadata_json"]),
                    },
                    identifier_field="capture_id",
                )
                _verify_effective_cutoff(
                    row,
                    row["published_at_utc"],
                    row["observed_at_utc"],
                    row["fetched_at_utc"],
                    row["recorded_at_utc"],
                    source_by_id[row["source_id"]]["effective_cutoff_utc"],
                )
                published_at = row["published_at_utc"]
                expected_latency = (
                    (
                        _parse_timestamp(row["fetched_at_utc"])
                        - _parse_timestamp(published_at)
                    ).total_seconds()
                    if published_at is not None
                    else None
                )
                expected_late = (
                    int(expected_latency > LATE_ARRIVAL_SECONDS)
                    if expected_latency is not None
                    else None
                )
                if (
                    row["latency_seconds"] != expected_latency
                    or row["late_arriving"] != expected_late
                ):
                    raise MessageEvidenceError(
                        f"capture timing derivation mismatch: {row['capture_id']}"
                    )
                _verify_attestation(
                    row,
                    derived={
                        "latency_seconds": expected_latency,
                        "late_arriving": expected_late,
                    },
                )
            for row in fact_rows:
                _verify_record_hash(
                    row,
                    {
                        "capture_id": row["capture_id"],
                        "issue": row["issue"],
                        "match_idx": row["match_idx"],
                        "entity_id": row["entity_id"],
                        "fact_kind": row["fact_kind"],
                        "assertion_state": row["assertion_state"],
                        "value": json.loads(row["value_json"]),
                        "confidence": row["confidence"],
                        "effective_from_utc": row["effective_from_utc"],
                        "effective_until_utc": row["effective_until_utc"],
                        "observed_at_utc": row["observed_at_utc"],
                    },
                    identifier_field="fact_id",
                )
                value = json.loads(row["value_json"])
                fact_entities = list(value.get("coverage_entity_ids", []))
                if row["entity_id"] is not None:
                    fact_entities.append(row["entity_id"])
                _verify_effective_cutoff(
                    row,
                    row["recorded_at_utc"],
                    capture_by_id[row["capture_id"]]["effective_cutoff_utc"],
                    match_by_key[(row["issue"], row["match_idx"])][
                        "effective_cutoff_utc"
                    ],
                    *(
                        entity_by_id[entity_id]["effective_cutoff_utc"]
                        for entity_id in fact_entities
                    ),
                )
                _verify_attestation(row)
            for row in relation_rows:
                _verify_record_hash(
                    row,
                    {
                        "source_fact_id": row["source_fact_id"],
                        "target_fact_id": row["target_fact_id"],
                        "relation_type": row["relation_type"],
                        "note": row["note"],
                    },
                    identifier_field="relation_id",
                )
                _verify_effective_cutoff(
                    row,
                    row["recorded_at_utc"],
                    fact_by_id[row["source_fact_id"]]["effective_cutoff_utc"],
                )
                _verify_attestation(row)
            for row in missing_rows:
                _verify_record_hash(
                    row,
                    {
                        "capture_id": row["capture_id"],
                        "issue": row["issue"],
                        "match_idx": row["match_idx"],
                        "fact_kind": row["fact_kind"],
                        "reason_code": row["reason_code"],
                        "detail": row["detail"],
                    },
                    identifier_field="missingness_id",
                )
                _verify_effective_cutoff(
                    row,
                    row["recorded_at_utc"],
                    capture_by_id[row["capture_id"]]["effective_cutoff_utc"],
                    match_by_key[(row["issue"], row["match_idx"])][
                        "effective_cutoff_utc"
                    ],
                )
                _verify_attestation(row)
            for row in observation_rows:
                _verify_record_hash(
                    row,
                    {
                        "capture_id": row["capture_id"],
                        "issue": row["issue"],
                        "match_idx": row["match_idx"],
                        "fact_kind": row["fact_kind"],
                        "status": row["status"],
                        "expected_entity_ids": json.loads(
                            row["expected_entity_ids_json"]
                        ),
                        "checked_source_ids": json.loads(
                            row["checked_source_ids_json"]
                        ),
                        "note": row["note"],
                    },
                    identifier_field="observation_id",
                )
                expected_entities = json.loads(row["expected_entity_ids_json"])
                checked_sources = json.loads(row["checked_source_ids_json"])
                _verify_effective_cutoff(
                    row,
                    row["recorded_at_utc"],
                    capture_by_id[row["capture_id"]]["effective_cutoff_utc"],
                    match_by_key[(row["issue"], row["match_idx"])][
                        "effective_cutoff_utc"
                    ],
                    *(
                        entity_by_id[entity_id]["effective_cutoff_utc"]
                        for entity_id in expected_entities
                    ),
                    *(
                        source_by_id[source_id]["effective_cutoff_utc"]
                        for source_id in checked_sources
                    ),
                )
                _verify_attestation(row)

        deactivators: dict[str, set[str]] = defaultdict(set)
        for row in relation_rows:
            if row["relation_type"] in {"corrects", "retracts"}:
                deactivators[row["target_fact_id"]].add(row["source_fact_id"])
        active_ids: set[str] = set()
        for row in sorted(
            fact_rows,
            key=lambda value: (
                value["effective_cutoff_utc"],
                value["receipt_sequence"],
                value["fact_id"],
            ),
            reverse=True,
        ):
            if not (deactivators[row["fact_id"]] & active_ids):
                active_ids.add(row["fact_id"])
        conflicts: dict[str, set[str]] = defaultdict(set)
        for row in relation_rows:
            if (
                row["relation_type"] == "contradicts"
                and row["source_fact_id"] in active_ids
                and row["target_fact_id"] in active_ids
            ):
                conflicts[row["source_fact_id"]].add(row["target_fact_id"])
                conflicts[row["target_fact_id"]].add(row["source_fact_id"])

        facts: list[dict[str, Any]] = []
        for row in fact_rows:
            fact = {
                "fact_id": row["fact_id"],
                "capture_id": row["capture_id"],
                "issue": row["issue"],
                "match_idx": row["match_idx"],
                "entity_id": row["entity_id"],
                "fact_kind": row["fact_kind"],
                "assertion_state": row["assertion_state"],
                "value": json.loads(row["value_json"]),
                "confidence": row["confidence"],
                "effective_from_utc": row["effective_from_utc"],
                "effective_until_utc": row["effective_until_utc"],
                "observed_at_utc": row["observed_at_utc"],
                "effective_cutoff_utc": row["effective_cutoff_utc"],
                "source_id": row["source_id"],
                "source_url": row["source_url"],
                "published_at_utc": row["published_at_utc"],
                "fetched_at_utc": row["fetched_at_utc"],
                "raw_sha256": row["raw_sha256"],
                "provenance_tier": row["provenance_tier"],
                "recorded_at_utc": row["recorded_at_utc"],
                "receipt_sequence": row["receipt_sequence"],
                "record_sha256": row["record_sha256"],
                "attestation_sha256": row["attestation_sha256"],
                "active": row["fact_id"] in active_ids,
                "conflicts_with": sorted(conflicts.get(row["fact_id"], set())),
            }
            facts.append(fact)

        latest_alias_ids: set[str] = set()
        latest_aliases: dict[tuple[str, str], sqlite3.Row] = {}
        for row in alias_rows:
            key = (row["source_id"], row["alias_key"])
            current = latest_aliases.get(key)
            if current is None or (
                row["effective_cutoff_utc"],
                row["receipt_sequence"],
                row["alias_id"],
            ) > (
                current["effective_cutoff_utc"],
                current["receipt_sequence"],
                current["alias_id"],
            ):
                latest_aliases[key] = row
        latest_alias_ids.update(row["alias_id"] for row in latest_aliases.values())

        return {
            "schema_version": EXPORT_SCHEMA_VERSION,
            "as_of_utc": cutoff_text,
            "scope": {"issue": issue, "match_idx": match_idx},
            "matches": [
                {
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "match_id": row["match_id"],
                    "kickoff_at_utc": row["kickoff_at_utc"],
                    "home_team_id": row["home_team_id"],
                    "away_team_id": row["away_team_id"],
                    "competition_id": row["competition_id"],
                    "registered_at_utc": row["registered_at_utc"],
                    "recorded_at_utc": row["recorded_at_utc"],
                    "effective_cutoff_utc": row["effective_cutoff_utc"],
                    "receipt_sequence": row["receipt_sequence"],
                    "record_sha256": row["record_sha256"],
                    "attestation_sha256": row["attestation_sha256"],
                }
                for row in match_rows
            ],
            "sources": [
                {
                    "source_id": row["source_id"],
                    "name": row["name"],
                    "source_type": row["source_type"],
                    "provenance_tier": row["provenance_tier"],
                    "base_url": row["base_url"],
                    "registered_at_utc": row["registered_at_utc"],
                    "recorded_at_utc": row["recorded_at_utc"],
                    "effective_cutoff_utc": row["effective_cutoff_utc"],
                    "receipt_sequence": row["receipt_sequence"],
                    "record_sha256": row["record_sha256"],
                    "attestation_sha256": row["attestation_sha256"],
                }
                for row in source_rows
            ],
            "entities": [
                {
                    "entity_id": row["entity_id"],
                    "entity_type": row["entity_type"],
                    "canonical_name": row["canonical_name"],
                    "registered_at_utc": row["registered_at_utc"],
                    "recorded_at_utc": row["recorded_at_utc"],
                    "effective_cutoff_utc": row["effective_cutoff_utc"],
                    "receipt_sequence": row["receipt_sequence"],
                    "record_sha256": row["record_sha256"],
                    "attestation_sha256": row["attestation_sha256"],
                }
                for row in entity_rows
            ],
            "entity_aliases": [
                {
                    "alias_id": row["alias_id"],
                    "entity_id": row["entity_id"],
                    "source_id": row["source_id"],
                    "alias_text": row["alias_text"],
                    "alias_key": row["alias_key"],
                    "observed_at_utc": row["observed_at_utc"],
                    "recorded_at_utc": row["recorded_at_utc"],
                    "effective_cutoff_utc": row["effective_cutoff_utc"],
                    "receipt_sequence": row["receipt_sequence"],
                    "record_sha256": row["record_sha256"],
                    "attestation_sha256": row["attestation_sha256"],
                    "active": row["alias_id"] in latest_alias_ids,
                }
                for row in alias_rows
            ],
            "captures": [
                {
                    "capture_id": row["capture_id"],
                    "source_id": row["source_id"],
                    "source_url": row["source_url"],
                    "published_at_utc": row["published_at_utc"],
                    "observed_at_utc": row["observed_at_utc"],
                    "fetched_at_utc": row["fetched_at_utc"],
                    "recorded_at_utc": row["recorded_at_utc"],
                    "effective_cutoff_utc": row["effective_cutoff_utc"],
                    "receipt_sequence": row["receipt_sequence"],
                    "record_sha256": row["record_sha256"],
                    "attestation_sha256": row["attestation_sha256"],
                    "latency_seconds": row["latency_seconds"],
                    "late_arriving": (
                        bool(row["late_arriving"])
                        if row["late_arriving"] is not None
                        else None
                    ),
                    "media_type": row["media_type"],
                    "raw_sha256": row["raw_sha256"],
                }
                for row in capture_rows
            ],
            "facts": facts,
            "relations": [dict(row) for row in relation_rows],
            "missingness": [dict(row) for row in missing_rows],
            "collection_observations": [
                {
                    "observation_id": row["observation_id"],
                    "capture_id": row["capture_id"],
                    "issue": row["issue"],
                    "match_idx": row["match_idx"],
                    "fact_kind": row["fact_kind"],
                    "status": row["status"],
                    "expected_entity_ids": json.loads(row["expected_entity_ids_json"]),
                    "checked_source_ids": json.loads(row["checked_source_ids_json"]),
                    "note": row["note"],
                    "recorded_at_utc": row["recorded_at_utc"],
                    "effective_cutoff_utc": row["effective_cutoff_utc"],
                    "receipt_sequence": row["receipt_sequence"],
                    "record_sha256": row["record_sha256"],
                    "attestation_sha256": row["attestation_sha256"],
                }
                for row in observation_rows
            ],
            "counts": {
                "matches": len(match_rows),
                "entities": len(entity_rows),
                "entity_aliases": len(alias_rows),
                "captures": len(capture_rows),
                "facts": len(facts),
                "active_facts": sum(fact["active"] for fact in facts),
                "relations": len(relation_rows),
                "missingness": len(missing_rows),
                "collection_observations": len(observation_rows),
            },
        }

    def coverage_report(
        self,
        *,
        cutoff: str | datetime,
        required_fact_kinds: Iterable[str],
        max_age_seconds: int,
        issue: str | None = None,
        allowed_provenance_tiers: Iterable[str] = PROVENANCE_TIERS,
    ) -> dict[str, Any]:
        required = sorted(
            {
                _choice(kind, FACT_KINDS, "required_fact_kind")
                for kind in required_fact_kinds
            }
        )
        if not required:
            raise MessageEvidenceError("at least one required fact kind is needed")
        allowed_tiers = sorted(
            {
                _choice(tier, PROVENANCE_TIERS, "allowed_provenance_tier")
                for tier in allowed_provenance_tiers
            }
        )
        if not allowed_tiers:
            raise MessageEvidenceError("at least one allowed provenance tier is needed")
        if int(max_age_seconds) < 0:
            raise MessageEvidenceError("max_age_seconds cannot be negative")
        max_age_seconds = int(max_age_seconds)
        export = self.export_as_of(cutoff=cutoff, issue=issue)
        cutoff_dt = _parse_timestamp(export["as_of_utc"])
        capture_freshness_at = {
            row["capture_id"]: row["published_at_utc"] or row["fetched_at_utc"]
            for row in export["captures"]
        }
        active_by_match: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
        for fact in export["facts"]:
            applicable = (
                fact["effective_from_utc"] is None
                or fact["effective_from_utc"] <= export["as_of_utc"]
            ) and (
                fact["effective_until_utc"] is None
                or fact["effective_until_utc"] >= export["as_of_utc"]
            )
            if (
                fact["active"]
                and fact["assertion_state"] != "unknown"
                and fact["provenance_tier"] in allowed_tiers
                and applicable
            ):
                active_by_match[(fact["issue"], fact["match_idx"])].append(fact)
        missing_by_match: dict[tuple[str, int], dict[str, tuple[str, int]]] = (
            defaultdict(dict)
        )
        for row in export["missingness"]:
            key = (row["issue"], row["match_idx"])
            kind = row["fact_kind"]
            position = (row["effective_cutoff_utc"], row["receipt_sequence"])
            current = missing_by_match[key].get(kind)
            if current is None or position > current:
                missing_by_match[key][kind] = position
        source_tiers = {
            row["source_id"]: row["provenance_tier"] for row in export["sources"]
        }
        observation_by_match: dict[tuple[str, int], dict[str, dict[str, Any]]] = (
            defaultdict(dict)
        )
        for observation in export["collection_observations"]:
            key = (observation["issue"], observation["match_idx"])
            kind = observation["fact_kind"]
            current = observation_by_match[key].get(kind)
            if current is None or (
                observation["effective_cutoff_utc"],
                observation["receipt_sequence"],
                observation["observation_id"],
            ) > (
                current["effective_cutoff_utc"],
                current["receipt_sequence"],
                current["observation_id"],
            ):
                observation_by_match[key][kind] = observation
        rows: list[dict[str, Any]] = []
        for match in export["matches"]:
            key = (match["issue"], match["match_idx"])
            facts = active_by_match.get(key, [])
            latest_by_kind: dict[str, dict[str, Any]] = {}
            for fact in facts:
                kind = fact["fact_kind"]
                if kind not in required:
                    continue
                current = latest_by_kind.get(kind)
                if current is None or (
                    fact["effective_cutoff_utc"],
                    fact["receipt_sequence"],
                ) > (
                    current["effective_cutoff_utc"],
                    current["receipt_sequence"],
                ):
                    latest_by_kind[kind] = fact
            available = sorted(latest_by_kind)
            absent = sorted(set(required) - set(available))
            observations = observation_by_match.get(key, {})
            covered_entities_by_kind: dict[str, set[str]] = defaultdict(set)
            latest_fact_by_kind_entity: dict[tuple[str, str], dict[str, Any]] = {}
            for fact in facts:
                fact_entities: set[str] = set()
                if fact["entity_id"] is not None:
                    fact_entities.add(fact["entity_id"])
                declared_entities = fact["value"].get("coverage_entity_ids", [])
                if isinstance(declared_entities, list):
                    fact_entities.update(
                        str(entity_id) for entity_id in declared_entities
                    )
                covered_entities_by_kind[fact["fact_kind"]].update(fact_entities)
                for entity_id in fact_entities:
                    entity_key = (fact["fact_kind"], entity_id)
                    current = latest_fact_by_kind_entity.get(entity_key)
                    if current is None or (
                        fact["effective_cutoff_utc"],
                        fact["receipt_sequence"],
                    ) > (
                        current["effective_cutoff_utc"],
                        current["receipt_sequence"],
                    ):
                        latest_fact_by_kind_entity[entity_key] = fact
            uncovered_entities_by_kind = {
                kind: sorted(
                    set(observations[kind]["expected_entity_ids"])
                    - covered_entities_by_kind[kind]
                )
                for kind in required
                if kind in observations
            }
            observation_ages = {
                kind: (
                    cutoff_dt
                    - _parse_timestamp(
                        capture_freshness_at[observations[kind]["capture_id"]]
                    )
                ).total_seconds()
                for kind in required
                if kind in observations
            }
            stale_observations = sorted(
                kind for kind, age in observation_ages.items() if age > max_age_seconds
            )
            complete_observations = sorted(
                kind
                for kind in required
                if kind in observations
                and observations[kind]["status"] == "complete"
                and kind not in stale_observations
                and all(
                    source_tiers.get(source_id) in allowed_tiers
                    for source_id in observations[kind]["checked_source_ids"]
                )
                and not uncovered_entities_by_kind[kind]
            )
            incomplete_observations = sorted(set(required) - set(complete_observations))
            explicit_missing = sorted(
                kind
                for kind, missing_position in missing_by_match.get(key, {}).items()
                if kind in required
                and (
                    kind not in latest_by_kind
                    or missing_position
                    >= (
                        latest_by_kind[kind]["effective_cutoff_utc"],
                        latest_by_kind[kind]["receipt_sequence"],
                    )
                )
            )
            stale: list[str] = []
            ages: dict[str, float] = {}
            stale_entities_by_kind: dict[str, list[str]] = {}
            conflict_ids: set[str] = set()
            for kind in required:
                expected_entities = (
                    observations[kind]["expected_entity_ids"]
                    if kind in observations
                    else []
                )
                entity_ages = {
                    entity_id: (
                        cutoff_dt
                        - _parse_timestamp(
                            latest_fact_by_kind_entity[(kind, entity_id)][
                                "published_at_utc"
                            ]
                            or latest_fact_by_kind_entity[(kind, entity_id)][
                                "fetched_at_utc"
                            ]
                        )
                    ).total_seconds()
                    for entity_id in expected_entities
                    if (kind, entity_id) in latest_fact_by_kind_entity
                }
                if entity_ages:
                    ages[kind] = max(entity_ages.values())
                elif kind in latest_by_kind:
                    ages[kind] = (
                        cutoff_dt
                        - _parse_timestamp(
                            latest_by_kind[kind]["published_at_utc"]
                            or latest_by_kind[kind]["fetched_at_utc"]
                        )
                    ).total_seconds()
                stale_entities = sorted(
                    entity_id
                    for entity_id, age in entity_ages.items()
                    if age > max_age_seconds
                )
                if stale_entities:
                    stale.append(kind)
                    stale_entities_by_kind[kind] = stale_entities
            active_ids = {fact["fact_id"] for fact in facts}
            for fact in facts:
                affects_kickoff_gate = (
                    fact["fact_kind"] == "schedule"
                    and fact["assertion_state"] == "affirmed"
                    and isinstance(fact["value"].get("kickoff_at_utc"), str)
                )
                if fact["fact_kind"] not in required and not affects_kickoff_gate:
                    continue
                conflict_ids.update(
                    other for other in fact["conflicts_with"] if other in active_ids
                )
            schedule_revisions = [
                fact
                for fact in facts
                if fact["fact_kind"] == "schedule"
                and fact["assertion_state"] == "affirmed"
                and isinstance(fact["value"].get("kickoff_at_utc"), str)
            ]
            effective_kickoff = match["kickoff_at_utc"]
            if schedule_revisions:
                latest_schedule = max(
                    schedule_revisions,
                    key=lambda fact: (
                        fact["effective_cutoff_utc"],
                        fact["receipt_sequence"],
                        fact["fact_id"],
                    ),
                )
                effective_kickoff = latest_schedule["value"]["kickoff_at_utc"]
            pre_kickoff = cutoff_dt < _parse_timestamp(effective_kickoff)
            eligible = (
                pre_kickoff
                and not absent
                and not incomplete_observations
                and not explicit_missing
                and not stale
                and not conflict_ids
            )
            rows.append(
                {
                    "issue": match["issue"],
                    "match_idx": match["match_idx"],
                    "match_id": match["match_id"],
                    "kickoff_at_utc": effective_kickoff,
                    "required_fact_kinds": required,
                    "available_fact_kinds": available,
                    "missing_fact_kinds": absent,
                    "complete_observation_fact_kinds": complete_observations,
                    "incomplete_observation_fact_kinds": incomplete_observations,
                    "stale_observation_fact_kinds": stale_observations,
                    "observation_age_seconds_by_kind": dict(
                        sorted(observation_ages.items())
                    ),
                    "uncovered_entity_ids_by_kind": dict(
                        sorted(uncovered_entities_by_kind.items())
                    ),
                    "explicit_missing_fact_kinds": explicit_missing,
                    "stale_fact_kinds": sorted(stale),
                    "stale_entity_ids_by_kind": dict(
                        sorted(stale_entities_by_kind.items())
                    ),
                    "age_seconds_by_kind": dict(sorted(ages.items())),
                    "unresolved_conflict_fact_ids": sorted(conflict_ids),
                    "cutoff_strictly_before_kickoff": pre_kickoff,
                    "decision_chain_eligible": eligible,
                }
            )
        issue_counts: dict[str, dict[str, int | float]] = {}
        for issue_value in sorted({row["issue"] for row in rows}):
            issue_rows = [row for row in rows if row["issue"] == issue_value]
            eligible_count = sum(row["decision_chain_eligible"] for row in issue_rows)
            issue_counts[issue_value] = {
                "match_count": len(issue_rows),
                "eligible_match_count": eligible_count,
                "eligible_rate": (
                    eligible_count / len(issue_rows) if issue_rows else 0.0
                ),
            }
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "as_of_utc": export["as_of_utc"],
            "required_fact_kinds": required,
            "allowed_provenance_tiers": allowed_tiers,
            "max_age_seconds": max_age_seconds,
            "issues": issue_counts,
            "matches": rows,
        }
