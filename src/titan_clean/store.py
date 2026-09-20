"""Append-only raw Titan roster store for the clean database lane."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .discovery import (
    TITAN_SOURCE_ID,
    FixtureIdentity,
    Roster,
    euro_1x2_url,
    parse_euro_1x2_quotes,
    parse_fixture_identity,
    parse_schedule_ids,
)

SCHEMA_VERSION = "titan_clean_control_v1"


class TitanStoreError(ValueError):
    """Raised when a clean Titan receipt violates its provenance contract."""


@dataclass(frozen=True)
class CaptureResult:
    inserted: bool
    fixture_count: int
    raw_sha256: str


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise TitanStoreError("timestamps must carry a timezone")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise TitanStoreError(f"content-addressed raw collision: {path}")
        return
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class TitanRosterStore:
    """A store whose only normalized source role is Titan primary roster data."""

    def __init__(self, root: Path, connection: sqlite3.Connection) -> None:
        self.root = root
        self.connection = connection

    @property
    def raw_root(self) -> Path:
        return self.root / "raw" / "titan"

    @classmethod
    def open(cls, root: Path) -> "TitanRosterStore":
        root = Path(root).expanduser().resolve()
        control_dir = root / "control" / "titan"
        control_dir.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(control_dir / "control.sqlite", isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
              schema_version TEXT PRIMARY KEY,
              source_role TEXT NOT NULL CHECK(source_role = 'PRIMARY_FEATURE'),
              source_id TEXT NOT NULL CHECK(source_id = 'titan')
            );
            CREATE TABLE IF NOT EXISTS capture_batch (
              batch_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL CHECK(source_id = 'titan'),
              source_role TEXT NOT NULL CHECK(source_role = 'PRIMARY_FEATURE'),
              endpoint_kind TEXT NOT NULL CHECK(endpoint_kind = 'soccer_scheduleid'),
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              requested_at_utc TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              acquisition_result TEXT NOT NULL CHECK(acquisition_result = 'OK'),
              CHECK(requested_at_utc <= trusted_received_at_utc)
            );
            CREATE TABLE IF NOT EXISTS roster_observation (
              batch_id TEXT NOT NULL REFERENCES capture_batch(batch_id),
              source_fixture_id TEXT NOT NULL,
              ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
              PRIMARY KEY(batch_id, source_fixture_id),
              UNIQUE(batch_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS capture_authorization (
              batch_id TEXT PRIMARY KEY REFERENCES capture_batch(batch_id),
              mode TEXT NOT NULL CHECK(mode IN ('PROBE', 'AUTHORIZED', 'USER_RISK_ACKNOWLEDGED')),
              receipt_sha256 TEXT,
              CHECK((mode = 'PROBE' AND receipt_sha256 IS NULL) OR
                    (mode IN ('AUTHORIZED', 'USER_RISK_ACKNOWLEDGED') AND length(receipt_sha256) = 64))
            );
            CREATE TABLE IF NOT EXISTS low_frequency_reservation (
              batch_id TEXT PRIMARY KEY,
              receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256) = 64),
              reserved_at_utc TEXT NOT NULL,
              request_count INTEGER NOT NULL CHECK(request_count > 0)
            );
            CREATE TABLE IF NOT EXISTS fixture_capture (
              batch_id TEXT PRIMARY KEY,
              roster_batch_id TEXT NOT NULL REFERENCES capture_batch(batch_id),
              source_id TEXT NOT NULL CHECK(source_id = 'titan'),
              source_role TEXT NOT NULL CHECK(source_role = 'PRIMARY_FEATURE'),
              source_fixture_id TEXT NOT NULL,
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              requested_at_utc TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              acquisition_result TEXT NOT NULL CHECK(acquisition_result = 'OK'),
              CHECK(requested_at_utc <= trusted_received_at_utc)
            );
            CREATE TABLE IF NOT EXISTS fixture_observation (
              batch_id TEXT PRIMARY KEY REFERENCES fixture_capture(batch_id),
              source_fixture_id TEXT NOT NULL,
              kickoff_source_raw TEXT,
              home_team_source_id TEXT,
              away_team_source_id TEXT,
              competition_source_id TEXT
            );
            CREATE TABLE IF NOT EXISTS euro_1x2_quote (
              batch_id TEXT NOT NULL REFERENCES fixture_capture(batch_id),
              company_source_id TEXT NOT NULL,
              bookmaker_source_name TEXT NOT NULL,
              record_source_id TEXT NOT NULL,
              ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
              home_odds REAL, draw_odds REAL, away_odds REAL,
              market_time_source_raw TEXT,
              home_kelly REAL, draw_kelly REAL, away_kelly REAL,
              PRIMARY KEY(batch_id, record_source_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS historical_fixture_capture (
              batch_id TEXT PRIMARY KEY,
              admission_bridge_sha256 TEXT NOT NULL CHECK(length(admission_bridge_sha256) = 64),
              source_id TEXT NOT NULL CHECK(source_id = 'titan'),
              source_role TEXT NOT NULL CHECK(source_role = 'PRIMARY_FEATURE'),
              source_fixture_id TEXT NOT NULL,
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              requested_at_utc TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              acquisition_result TEXT NOT NULL CHECK(acquisition_result = 'OK'),
              CHECK(requested_at_utc <= trusted_received_at_utc)
            );
            CREATE TABLE IF NOT EXISTS historical_fixture_observation (
              batch_id TEXT PRIMARY KEY REFERENCES historical_fixture_capture(batch_id),
              source_fixture_id TEXT NOT NULL,
              kickoff_source_raw TEXT,
              home_team_source_id TEXT,
              away_team_source_id TEXT,
              competition_source_id TEXT
            );
            CREATE TABLE IF NOT EXISTS historical_euro_1x2_quote (
              batch_id TEXT NOT NULL REFERENCES historical_fixture_capture(batch_id),
              company_source_id TEXT NOT NULL,
              bookmaker_source_name TEXT NOT NULL,
              record_source_id TEXT NOT NULL,
              ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
              home_odds REAL, draw_odds REAL, away_odds REAL,
              market_time_source_raw TEXT,
              home_kelly REAL, draw_kelly REAL, away_kelly REAL,
              PRIMARY KEY(batch_id, record_source_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS historical_fixture_failure (
              source_fixture_id TEXT NOT NULL,
              attempted_at_utc TEXT NOT NULL,
              error_class TEXT NOT NULL,
              error_detail TEXT NOT NULL,
              PRIMARY KEY(source_fixture_id, attempted_at_utc)
            );
            CREATE TABLE IF NOT EXISTS historical_aux_capture (
              batch_id TEXT PRIMARY KEY,
              fixture_batch_id TEXT NOT NULL REFERENCES historical_fixture_capture(batch_id),
              endpoint_kind TEXT NOT NULL CHECK(endpoint_kind IN ('analysis', 'handicap')),
              source_fixture_id TEXT NOT NULL,
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              requested_at_utc TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              acquisition_result TEXT NOT NULL CHECK(acquisition_result = 'OK'),
              CHECK(requested_at_utc <= trusted_received_at_utc)
            );
            CREATE TABLE IF NOT EXISTS historical_fundamental (
              fixture_batch_id TEXT PRIMARY KEY REFERENCES historical_fixture_capture(batch_id),
              source_fixture_id TEXT NOT NULL,
              venue TEXT,
              weather TEXT,
              temperature TEXT,
              home_form_json TEXT,
              away_form_json TEXT,
              h2h_json TEXT,
              home_season_stats_json TEXT,
              away_season_stats_json TEXT,
              standings_link TEXT,
              fundamentals_available INTEGER NOT NULL CHECK(fundamentals_available IN (0, 1)),
              parser_version TEXT NOT NULL
            );
            """
        )
        with connection:
            connection.execute(
                "INSERT OR IGNORE INTO schema_meta VALUES(?,?,?)",
                (SCHEMA_VERSION, "PRIMARY_FEATURE", TITAN_SOURCE_ID),
            )
        return cls(root, connection)

    def close(self) -> None:
        self.connection.close()

    def reserve_low_frequency_capture(
        self, *, batch_id: str, receipt_sha256: str, reserved_at_utc: str, request_count: int, max_requests_per_minute: int
    ) -> None:
        """Atomically reserve a bounded number of Titan HTTP requests for one minute."""
        reserved = _utc(reserved_at_utc)
        if len(receipt_sha256) != 64 or request_count < 1 or not 1 <= max_requests_per_minute <= 600:
            raise TitanStoreError("invalid low-frequency reservation")
        lower = (datetime.fromisoformat(reserved.replace("Z", "+00:00")) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self.connection:
            existing = self.connection.execute(
                "SELECT receipt_sha256,reserved_at_utc,request_count FROM low_frequency_reservation WHERE batch_id=?", (batch_id,)
            ).fetchone()
            expected = (receipt_sha256, reserved, request_count)
            if existing is not None:
                if tuple(existing) != expected:
                    raise TitanStoreError("low-frequency reservation collision")
                return
            used = self.connection.execute(
                "SELECT COALESCE(SUM(request_count), 0) FROM low_frequency_reservation WHERE reserved_at_utc >= ?", (lower,)
            ).fetchone()[0]
            if int(used) + request_count > max_requests_per_minute:
                raise TitanStoreError("low-frequency per-minute request limit exceeded")
            self.connection.execute(
                "INSERT INTO low_frequency_reservation VALUES(?,?,?,?)", (batch_id, *expected)
            )

    def record_schedule(
        self,
        *,
        batch_id: str,
        payload: bytes,
        source_url: str,
        requested_at_utc: str,
        trusted_received_at_utc: str,
        parser_version: str,
        authorization_mode: str = "PROBE",
        authorization_receipt_sha256: str | None = None,
    ) -> CaptureResult:
        if authorization_mode not in {"PROBE", "AUTHORIZED", "USER_RISK_ACKNOWLEDGED"}:
            raise TitanStoreError("unsupported authorization mode")
        if (authorization_mode == "PROBE") != (authorization_receipt_sha256 is None):
            raise TitanStoreError("probe mode must not carry a receipt; operational modes require one")
        if authorization_receipt_sha256 is not None and len(authorization_receipt_sha256) != 64:
            raise TitanStoreError("authorization receipt hash must be SHA-256")
        if not batch_id or not parser_version:
            raise TitanStoreError("batch id and parser version are required")
        requested_at_utc = _utc(requested_at_utc)
        trusted_received_at_utc = _utc(trusted_received_at_utc)
        if requested_at_utc > trusted_received_at_utc:
            raise TitanStoreError("requested time cannot follow trusted receive time")
        roster: Roster = parse_schedule_ids(payload)
        raw_sha256 = _sha256(payload)
        raw_path = self.raw_root / raw_sha256[:2] / f"{raw_sha256}.js"
        expected = (
            TITAN_SOURCE_ID,
            "PRIMARY_FEATURE",
            "soccer_scheduleid",
            source_url,
            raw_sha256,
            str(raw_path.relative_to(self.root)),
            requested_at_utc,
            trusted_received_at_utc,
            parser_version,
            "OK",
        )
        existing = self.connection.execute(
            """SELECT source_id,source_role,endpoint_kind,source_url,raw_sha256,raw_path,
                      requested_at_utc,trusted_received_at_utc,parser_version,acquisition_result
                 FROM capture_batch WHERE batch_id=?""",
            (batch_id,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != expected:
                raise TitanStoreError(f"capture batch collision: {batch_id}")
            existing_authorization = self.connection.execute(
                "SELECT mode,receipt_sha256 FROM capture_authorization WHERE batch_id=?", (batch_id,)
            ).fetchone()
            if tuple(existing_authorization or ()) != (authorization_mode, authorization_receipt_sha256):
                raise TitanStoreError(f"capture authorization collision: {batch_id}")
            count = self.connection.execute(
                "SELECT COUNT(*) FROM roster_observation WHERE batch_id=?", (batch_id,)
            ).fetchone()[0]
            return CaptureResult(False, int(count), raw_sha256)
        _atomic_bytes(raw_path, payload)
        with self.connection:
            self.connection.execute(
                "INSERT INTO capture_batch VALUES(?,?,?,?,?,?,?,?,?,?,?)", (batch_id, *expected)
            )
            self.connection.executemany(
                "INSERT INTO roster_observation VALUES(?,?,?)",
                [(batch_id, fixture_id, ordinal) for ordinal, fixture_id in enumerate(roster.fixture_ids)],
            )
            self.connection.execute(
                "INSERT INTO capture_authorization VALUES(?,?,?)",
                (batch_id, authorization_mode, authorization_receipt_sha256),
            )
        return CaptureResult(True, len(roster.fixture_ids), raw_sha256)

    def record_fixture(
        self,
        *,
        batch_id: str,
        roster_batch_id: str,
        source_fixture_id: str,
        payload: bytes,
        requested_at_utc: str,
        trusted_received_at_utc: str,
        parser_version: str,
    ) -> str:
        """Append one Titan fixture payload linked to an observed Titan roster."""
        if not batch_id or not roster_batch_id or not parser_version:
            raise TitanStoreError("fixture and roster batch ids plus parser version are required")
        requested_at_utc = _utc(requested_at_utc)
        trusted_received_at_utc = _utc(trusted_received_at_utc)
        if requested_at_utc > trusted_received_at_utc:
            raise TitanStoreError("requested time cannot follow trusted receive time")
        source_membership = self.connection.execute(
            "SELECT 1 FROM roster_observation WHERE batch_id=? AND source_fixture_id=?",
            (roster_batch_id, source_fixture_id),
        ).fetchone()
        if source_membership is None:
            raise TitanStoreError("fixture is absent from its Titan roster receipt")
        identity: FixtureIdentity = parse_fixture_identity(payload, provider_fixture_id=source_fixture_id)
        quotes = parse_euro_1x2_quotes(payload)
        source_url = euro_1x2_url(source_fixture_id)
        raw_sha256 = _sha256(payload)
        raw_path = self.raw_root / raw_sha256[:2] / f"{raw_sha256}.js"
        expected = (
            roster_batch_id, TITAN_SOURCE_ID, "PRIMARY_FEATURE", source_fixture_id, source_url,
            raw_sha256, str(raw_path.relative_to(self.root)), requested_at_utc,
            trusted_received_at_utc, parser_version, "OK",
        )
        existing = self.connection.execute(
            """SELECT roster_batch_id,source_id,source_role,source_fixture_id,source_url,raw_sha256,
                      raw_path,requested_at_utc,trusted_received_at_utc,parser_version,acquisition_result
                 FROM fixture_capture WHERE batch_id=?""",
            (batch_id,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != expected:
                raise TitanStoreError(f"fixture capture batch collision: {batch_id}")
            return raw_sha256
        _atomic_bytes(raw_path, payload)
        with self.connection:
            self.connection.execute(
                "INSERT INTO fixture_capture VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (batch_id, *expected)
            )
            self.connection.execute(
                "INSERT INTO fixture_observation VALUES(?,?,?,?,?,?)",
                (batch_id, identity.provider_fixture_id, identity.kickoff_source_raw,
                 identity.home_team_source_id, identity.away_team_source_id,
                 identity.competition_source_id),
            )
            self.connection.executemany(
                "INSERT INTO euro_1x2_quote VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [(batch_id, quote.company_source_id, quote.bookmaker_source_name, quote.record_source_id,
                  quote.ordinal, quote.home_odds, quote.draw_odds, quote.away_odds,
                  quote.market_time_source_raw, quote.home_kelly, quote.draw_kelly, quote.away_kelly)
                 for quote in quotes],
            )
        return raw_sha256

    def record_historical_fixture(
        self,
        *,
        batch_id: str,
        admission_bridge_sha256: str,
        source_fixture_id: str,
        payload: bytes,
        requested_at_utc: str,
        trusted_received_at_utc: str,
        parser_version: str,
    ) -> str:
        """Append one Titan fixture payload admitted by the historical candidate bridge."""
        if not batch_id or not parser_version or len(admission_bridge_sha256) != 64:
            raise TitanStoreError("historical fixture requires batch id, parser version and a 64-char bridge hash")
        if not source_fixture_id.isdecimal() or int(source_fixture_id) <= 0:
            raise TitanStoreError("historical fixture id must be a positive decimal string")
        requested_at_utc = _utc(requested_at_utc)
        trusted_received_at_utc = _utc(trusted_received_at_utc)
        if requested_at_utc > trusted_received_at_utc:
            raise TitanStoreError("requested time cannot follow trusted receive time")
        identity: FixtureIdentity = parse_fixture_identity(payload, provider_fixture_id=source_fixture_id)
        quotes = parse_euro_1x2_quotes(payload)
        source_url = euro_1x2_url(source_fixture_id)
        raw_sha256 = _sha256(payload)
        raw_path = self.raw_root / raw_sha256[:2] / f"{raw_sha256}.js"
        expected = (
            admission_bridge_sha256, TITAN_SOURCE_ID, "PRIMARY_FEATURE", source_fixture_id, source_url,
            raw_sha256, str(raw_path.relative_to(self.root)), requested_at_utc,
            trusted_received_at_utc, parser_version, "OK",
        )
        existing = self.connection.execute(
            """SELECT admission_bridge_sha256,source_id,source_role,source_fixture_id,source_url,raw_sha256,
                      raw_path,requested_at_utc,trusted_received_at_utc,parser_version,acquisition_result
                 FROM historical_fixture_capture WHERE batch_id=?""",
            (batch_id,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != expected:
                raise TitanStoreError(f"historical fixture capture batch collision: {batch_id}")
            return raw_sha256
        _atomic_bytes(raw_path, payload)
        with self.connection:
            self.connection.execute(
                "INSERT INTO historical_fixture_capture VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (batch_id, *expected)
            )
            self.connection.execute(
                "INSERT INTO historical_fixture_observation VALUES(?,?,?,?,?,?)",
                (batch_id, identity.provider_fixture_id, identity.kickoff_source_raw,
                 identity.home_team_source_id, identity.away_team_source_id,
                 identity.competition_source_id),
            )
            self.connection.executemany(
                "INSERT INTO historical_euro_1x2_quote VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [(batch_id, quote.company_source_id, quote.bookmaker_source_name, quote.record_source_id,
                  quote.ordinal, quote.home_odds, quote.draw_odds, quote.away_odds,
                  quote.market_time_source_raw, quote.home_kelly, quote.draw_kelly, quote.away_kelly)
                 for quote in quotes],
            )
        return raw_sha256

    def record_historical_failure(self, *, source_fixture_id: str, attempted_at_utc: str, error: Exception) -> None:
        if not source_fixture_id.isdecimal() or int(source_fixture_id) <= 0:
            raise TitanStoreError("historical fixture id must be a positive decimal string")
        with self.connection:
            self.connection.execute(
                "INSERT INTO historical_fixture_failure VALUES(?,?,?,?)",
                (source_fixture_id, _utc(attempted_at_utc), type(error).__name__, str(error)[:1000]),
            )

    def historical_progress(self) -> dict[str, int]:
        captured = self.connection.execute("SELECT COUNT(*) FROM historical_fixture_capture").fetchone()[0]
        quotes = self.connection.execute("SELECT COUNT(*) FROM historical_euro_1x2_quote").fetchone()[0]
        failed_ids = self.connection.execute(
            "SELECT COUNT(DISTINCT source_fixture_id) FROM historical_fixture_failure"
        ).fetchone()[0]
        return {"captured": int(captured), "quotes": int(quotes), "failed_ids": int(failed_ids)}

    def historical_captured_ids(self) -> set[str]:
        return {
            str(row[0])
            for row in self.connection.execute("SELECT source_fixture_id FROM historical_fixture_capture")
        }

    def historical_failed_ids(self, min_attempts: int = 5) -> set[str]:
        return {
            str(row[0])
            for row in self.connection.execute(
                "SELECT source_fixture_id FROM historical_fixture_failure GROUP BY source_fixture_id HAVING COUNT(*) >= ?",
                (min_attempts,),
            )
        }

    def record_historical_aux(
        self,
        *,
        batch_id: str,
        fixture_batch_id: str,
        endpoint_kind: str,
        source_fixture_id: str,
        source_url: str,
        payload: bytes,
        requested_at_utc: str,
        trusted_received_at_utc: str,
        parser_version: str,
    ) -> str:
        """Append one analysis or handicap raw payload for a captured fixture."""
        if endpoint_kind not in {"analysis", "handicap"}:
            raise TitanStoreError("unsupported aux endpoint kind")
        requested_at_utc = _utc(requested_at_utc)
        trusted_received_at_utc = _utc(trusted_received_at_utc)
        if requested_at_utc > trusted_received_at_utc:
            raise TitanStoreError("requested time cannot follow trusted receive time")
        raw_sha256 = _sha256(payload)
        raw_path = self.raw_root / raw_sha256[:2] / f"{raw_sha256}.html"
        expected = (
            fixture_batch_id, endpoint_kind, source_fixture_id, source_url,
            raw_sha256, str(raw_path.relative_to(self.root)), requested_at_utc,
            trusted_received_at_utc, parser_version, "OK",
        )
        existing = self.connection.execute(
            "SELECT fixture_batch_id,endpoint_kind,source_fixture_id,source_url,raw_sha256,raw_path,requested_at_utc,trusted_received_at_utc,parser_version,acquisition_result FROM historical_aux_capture WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != expected:
                raise TitanStoreError(f"historical aux capture batch collision: {batch_id}")
            return raw_sha256
        _atomic_bytes(raw_path, payload)
        with self.connection:
            self.connection.execute("INSERT INTO historical_aux_capture VALUES(?,?,?,?,?,?,?,?,?,?,?)", (batch_id, *expected))
        return raw_sha256

    def record_historical_fundamental(
        self,
        *,
        fixture_batch_id: str,
        source_fixture_id: str,
        parser_version: str,
        venue: str | None = None,
        weather: str | None = None,
        temperature: str | None = None,
        home_form_json: str | None = None,
        away_form_json: str | None = None,
        h2h_json: str | None = None,
        home_season_stats_json: str | None = None,
        away_season_stats_json: str | None = None,
        standings_link: str | None = None,
        fundamentals_available: bool = False,
    ) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO historical_fundamental VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fixture_batch_id, source_fixture_id, venue, weather, temperature,
                 home_form_json, away_form_json, h2h_json, home_season_stats_json,
                 away_season_stats_json, standings_link,
                 1 if fundamentals_available else 0, parser_version),
            )

    def manifest(self) -> bytes:
        batches = [
            dict(zip(
                ("batch_id", "source_id", "source_role", "endpoint_kind", "source_url", "raw_sha256", "raw_path", "requested_at_utc", "trusted_received_at_utc", "parser_version", "acquisition_result"),
                row,
            ))
            for row in self.connection.execute("SELECT * FROM capture_batch ORDER BY batch_id")
        ]
        rows = [
            dict(zip(("batch_id", "source_fixture_id", "ordinal"), row))
            for row in self.connection.execute("SELECT * FROM roster_observation ORDER BY batch_id, ordinal")
        ]
        fixture_captures = [
            dict(zip(
                ("batch_id", "roster_batch_id", "source_id", "source_role", "source_fixture_id", "source_url", "raw_sha256", "raw_path", "requested_at_utc", "trusted_received_at_utc", "parser_version", "acquisition_result"),
                row,
            ))
            for row in self.connection.execute("SELECT * FROM fixture_capture ORDER BY batch_id")
        ]
        fixture_observations = [
            dict(zip(("batch_id", "source_fixture_id", "kickoff_source_raw", "home_team_source_id", "away_team_source_id", "competition_source_id"), row))
            for row in self.connection.execute("SELECT * FROM fixture_observation ORDER BY batch_id")
        ]
        euro_quotes = [
            dict(zip(("batch_id", "company_source_id", "bookmaker_source_name", "record_source_id", "ordinal", "home_odds", "draw_odds", "away_odds", "market_time_source_raw", "home_kelly", "draw_kelly", "away_kelly"), row))
            for row in self.connection.execute("SELECT * FROM euro_1x2_quote ORDER BY batch_id, record_source_id, ordinal")
        ]
        authorizations = [
            dict(zip(("batch_id", "mode", "receipt_sha256"), row))
            for row in self.connection.execute("SELECT * FROM capture_authorization ORDER BY batch_id")
        ]
        historical_captures = [
            dict(zip(
                ("batch_id", "admission_bridge_sha256", "source_id", "source_role", "source_fixture_id", "source_url", "raw_sha256", "raw_path", "requested_at_utc", "trusted_received_at_utc", "parser_version", "acquisition_result"),
                row,
            ))
            for row in self.connection.execute("SELECT * FROM historical_fixture_capture ORDER BY batch_id")
        ]
        historical_observations = [
            dict(zip(("batch_id", "source_fixture_id", "kickoff_source_raw", "home_team_source_id", "away_team_source_id", "competition_source_id"), row))
            for row in self.connection.execute("SELECT * FROM historical_fixture_observation ORDER BY batch_id")
        ]
        historical_quotes = [
            dict(zip(("batch_id", "company_source_id", "bookmaker_source_name", "record_source_id", "ordinal", "home_odds", "draw_odds", "away_odds", "market_time_source_raw", "home_kelly", "draw_kelly", "away_kelly"), row))
            for row in self.connection.execute("SELECT * FROM historical_euro_1x2_quote ORDER BY batch_id, record_source_id, ordinal")
        ]
        return (json.dumps({"schema_version": SCHEMA_VERSION, "batches": batches, "roster": rows,
                           "fixture_captures": fixture_captures, "fixture_observations": fixture_observations,
                            "euro_1x2_quotes": euro_quotes, "capture_authorizations": authorizations,
                            "historical_fixture_captures": historical_captures,
                            "historical_fixture_observations": historical_observations,
                            "historical_euro_1x2_quotes": historical_quotes},
                          sort_keys=True, separators=(",", ":")) + "\n").encode()
