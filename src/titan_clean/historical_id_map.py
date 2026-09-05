"""Isolated 500 issue-slot to Nowscore/Titan-ID discovery ledger.

This lane is not readable by Titan feature materialization.  It retains raw
external receipts for audit, but exports only strict issue/slot provider-ID
mappings; teams, kickoff, odds, scores, and labels never enter the mapping
schema.
"""

from __future__ import annotations

from contextlib import contextmanager

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class HistoricalIdMapError(ValueError):
    """Raised when an external ID-discovery receipt cannot be safely joined."""


@dataclass(frozen=True)
class HistoricalIdMapping:
    issue_code: str
    issue_slot: int
    nowscore_provider_match_id: str
    discovery_sha256: str


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise HistoricalIdMapError("timestamps must carry a timezone")
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_raw(path: Path, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise HistoricalIdMapError("content-addressed raw collision")
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


def _valid_issue(value: str) -> bool:
    return value.isdecimal() and 5 <= len(value) <= 8


def parse_nowscore_provider_ids(payload: bytes, *, issue_code: str) -> tuple[tuple[int, str], ...]:
    """Accept only an issue-declared complete Nowscore membership matrix.

    Void rows (provider ID <= 0, e.g. cancelled/postponed/interrupted
    fixtures) carry no Nowscore provider ID and are excluded from the
    candidates; use :func:`nowscore_void_slots` to learn which slots were
    void so they can be isolated instead of mapped.
    """
    valid, void = _parse_nowscore_matrix(payload, issue_code=issue_code)
    if not valid and void:
        return ()
    return _normal_nowscore_rows(valid)


def nowscore_void_slots(payload: bytes, *, issue_code: str) -> frozenset[int]:
    """Return slots whose Nowscore provider ID is <= 0 (void rows).

    A void row is a real membership row (it has a slot, teams and often a
    deadline) whose provider ID is 0 or -1: the fixture was cancelled,
    postponed or interrupted and has no Nowscore match ID.  These slots must
    be isolated, never mapped to a Titan candidate.
    """
    _valid, void = _parse_nowscore_matrix(payload, issue_code=issue_code)
    return void


def _parse_nowscore_matrix(payload: bytes, *, issue_code: str) -> tuple[list[tuple[int, str]], frozenset[int]]:
    """Parse the M[][] matrix into (valid rows, void slots).

    Valid rows keep the *whole* provider integer (a leading '-' is part of a
    void marker, not a sign to strip: '-1' must never become '1').
    """
    text = payload.decode("utf-8", errors="strict")
    declared = re.search(
        r"<input[^>]+(?:id|name)=[\"'](?:issueNum|IssueNum)[\"'][^>]+value=[\"'](\d+)[\"']|\b(?:issueNum|IssueNum)\s*[:=]\s*[\"']?(\d+)",
        text,
        flags=re.I,
    )
    declared_issue = next((value for value in declared.groups() if value), None) if declared else None
    if declared_issue != issue_code:
        raise HistoricalIdMapError("Nowscore payload-declared issue differs from requested issue")
    matrix: dict[int, dict[int, str]] = {}
    for row, field, value in re.findall(r"M\[(\d+)\]\[(\d+)\]\s*=\s*(.*?);", text, flags=re.S):
        fields = matrix.setdefault(int(row), {})
        if int(field) in fields:
            raise HistoricalIdMapError("duplicate Nowscore matrix field")
        fields[int(field)] = value.strip()
    if not matrix:
        raise HistoricalIdMapError("Nowscore complete membership matrix is absent")
    valid: list[tuple[int, str]] = []
    void: set[int] = set()
    seen_slots: set[int] = set()
    for outer in sorted(matrix):
        fields = matrix[outer]
        slot_raw = fields.get(16, "")
        provider_raw = fields.get(0, "")
        if len(provider_raw) >= 2 and provider_raw[0] == provider_raw[-1] and provider_raw[0] in "\"'":
            provider_raw = provider_raw[1:-1]
        try:
            slot = int(slot_raw)
            provider_match = re.fullmatch(r"-?[0-9]+", provider_raw)
        except ValueError:
            raise HistoricalIdMapError("Nowscore matrix row lacks a numeric slot or provider ID") from None
        if provider_match is None:
            raise HistoricalIdMapError("Nowscore matrix row lacks a provider ID")
        if slot < 1 or slot in seen_slots:
            raise HistoricalIdMapError("Nowscore matrix has an invalid or duplicate slot")
        seen_slots.add(slot)
        provider_id = int(provider_match.group())
        if provider_id < 1:
            void.add(slot)
            continue
        valid.append((slot, provider_raw))
    return valid, frozenset(void)


def _normal_500_rows(rows: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    normalized = tuple(rows)
    if not normalized:
        raise HistoricalIdMapError("500 issue has no candidate slots")
    if any(slot < 1 or local_fid < 1 for slot, local_fid in normalized):
        raise HistoricalIdMapError("500 candidate slot or local fid is invalid")
    if len({slot for slot, _ in normalized}) != len(normalized):
        raise HistoricalIdMapError("500 issue has duplicate slots")
    return tuple(sorted(normalized))


def _normal_nowscore_rows(rows: Iterable[tuple[int, str]]) -> tuple[tuple[int, str], ...]:
    normalized = tuple(rows)
    if not normalized:
        raise HistoricalIdMapError("Nowscore issue has no provider IDs")
    if any(slot < 1 or not provider_id.isdecimal() or int(provider_id) < 1 for slot, provider_id in normalized):
        raise HistoricalIdMapError("Nowscore candidate slot or provider ID is invalid")
    if len({slot for slot, _ in normalized}) != len(normalized):
        raise HistoricalIdMapError("Nowscore issue has duplicate slots")
    return tuple(sorted(normalized))


@contextmanager
def _transaction(connection: sqlite3.Connection):
    """Nestable transaction; failed captures restore every database row."""
    connection.execute("SAVEPOINT mapping_write")
    try:
        yield
    except BaseException:
        connection.execute("ROLLBACK TO mapping_write")
        connection.execute("RELEASE mapping_write")
        raise
    else:
        connection.execute("RELEASE mapping_write")


class HistoricalIdMapStore:
    """Append-only discovery receipt store outside Titan feature control."""

    def __init__(self, root: Path, connection: sqlite3.Connection) -> None:
        self.root = root
        self.connection = connection

    @classmethod
    def open(cls, root: Path) -> "HistoricalIdMapStore":
        root = Path(root).expanduser().resolve()
        directory = root / "control" / "external_id_discovery"
        directory.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(directory / "discovery.sqlite", isolation_level=None)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS source_receipt (
              batch_id TEXT PRIMARY KEY,
              source_id TEXT NOT NULL CHECK(source_id IN ('500_issue_coverage', 'nowscore_id_mapping')),
              source_role TEXT NOT NULL CHECK(source_role = 'ID_DISCOVERY_ONLY'),
              issue_code TEXT NOT NULL,
              source_url TEXT NOT NULL,
              raw_sha256 TEXT NOT NULL CHECK(length(raw_sha256) = 64),
              raw_path TEXT NOT NULL,
              trusted_received_at_utc TEXT NOT NULL,
              parser_version TEXT NOT NULL,
              CHECK(length(issue_code) BETWEEN 5 AND 8)
            );
            CREATE TABLE IF NOT EXISTS coverage_500_slot (
              batch_id TEXT NOT NULL REFERENCES source_receipt(batch_id),
              issue_code TEXT NOT NULL,
              issue_slot INTEGER NOT NULL CHECK(issue_slot > 0),
              local_500_fid INTEGER NOT NULL CHECK(local_500_fid > 0),
              PRIMARY KEY(batch_id, issue_slot)
            );
            CREATE TABLE IF NOT EXISTS issue_slot_nowscore_map (
              issue_code TEXT NOT NULL,
              issue_slot INTEGER NOT NULL CHECK(issue_slot > 0),
              local_500_fid INTEGER NOT NULL CHECK(local_500_fid > 0),
              nowscore_provider_match_id TEXT NOT NULL CHECK(nowscore_provider_match_id GLOB '[0-9]*'),
              coverage_500_batch_id TEXT NOT NULL REFERENCES source_receipt(batch_id),
              nowscore_batch_id TEXT NOT NULL REFERENCES source_receipt(batch_id),
              discovery_sha256 TEXT NOT NULL CHECK(length(discovery_sha256) = 64),
              PRIMARY KEY(issue_code, issue_slot),
              UNIQUE(issue_code, nowscore_provider_match_id)
            );
            CREATE TABLE IF NOT EXISTS mapping_failure (
              issue_code TEXT NOT NULL,
              attempted_at_utc TEXT NOT NULL,
              error_class TEXT NOT NULL,
              error_detail TEXT NOT NULL,
              PRIMARY KEY(issue_code, attempted_at_utc)
            );
            CREATE TABLE IF NOT EXISTS conflict_isolated_slot (
              issue_code TEXT NOT NULL,
              issue_slot INTEGER NOT NULL CHECK(issue_slot > 0),
              local_500_fid INTEGER NOT NULL CHECK(local_500_fid > 0),
              nowscore_provider_match_id TEXT NOT NULL,
              isolation_reason TEXT NOT NULL,
              PRIMARY KEY(issue_code, issue_slot)
            );
            """
        )
        return cls(root, connection)

    def close(self) -> None:
        self.connection.close()

    def record_failure(self, *, issue_code: str, attempted_at_utc: str, error: Exception) -> None:
        if not _valid_issue(issue_code):
            raise HistoricalIdMapError("invalid failed issue code")
        with _transaction(self.connection):
            self.connection.execute(
                "INSERT INTO mapping_failure VALUES(?,?,?,?)",
                (issue_code, _utc(attempted_at_utc), type(error).__name__, str(error)[:1000]),
            )

    def record_500_coverage(
        self, *, batch_id: str, issue_code: str, source_url: str, payload: bytes,
        trusted_received_at_utc: str, parser_version: str, rows: Iterable[tuple[int, int]],
    ) -> str:
        if not _valid_issue(issue_code):
            raise HistoricalIdMapError("invalid 500 issue code")
        parsed_rows = _normal_500_rows(rows)
        received = _utc(trusted_received_at_utc)
        digest = hashlib.sha256(payload).hexdigest()
        raw_path = self.root / "raw" / "id_discovery_500" / digest[:2] / f"{digest}.html"
        expected = ("500_issue_coverage", issue_code, source_url, digest, str(raw_path.relative_to(self.root)), received, parser_version)
        existing = self.connection.execute(
            "SELECT source_id,issue_code,source_url,raw_sha256,raw_path,trusted_received_at_utc,parser_version FROM source_receipt WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if existing is not None:
            if tuple(existing) != expected:
                raise HistoricalIdMapError("500 receipt batch collision")
            return digest
        _write_raw(raw_path, payload)
        with _transaction(self.connection):
            self.connection.execute(
                "INSERT INTO source_receipt VALUES(?,?,?,?,?,?,?,?,?)",
                (batch_id, *expected[:1], "ID_DISCOVERY_ONLY", *expected[1:]),
            )
            self.connection.executemany(
                "INSERT INTO coverage_500_slot VALUES(?,?,?,?)",
                ((batch_id, issue_code, slot, fid) for slot, fid in parsed_rows),
            )
        return digest

    def record_nowscore_mapping(
        self, *, coverage_500_batch_id: str, batch_id: str, issue_code: str, source_url: str,
        payload: bytes, trusted_received_at_utc: str, parser_version: str,
        rows: Iterable[tuple[int, str]],
        conflict_resolution: dict[str, int] | None = None,
        slot_map: dict[int, int] | None = None,
        void_nowscore_slots: set[int] | None = None,
    ) -> str:
        if not _valid_issue(issue_code):
            raise HistoricalIdMapError("invalid Nowscore issue code")
        void_slots = set(void_nowscore_slots or ())
        supplied_rows = tuple(rows)
        parsed_rows = _normal_nowscore_rows(supplied_rows) if supplied_rows or not void_slots else ()
        if any(not isinstance(slot, int) or slot < 1 for slot in void_slots) or void_slots.intersection(slot for slot, _ in parsed_rows):
            raise HistoricalIdMapError("invalid or conflicting void slots")
        coverage = self.connection.execute(
            "SELECT issue_slot,local_500_fid FROM coverage_500_slot WHERE batch_id=? AND issue_code=? ORDER BY issue_slot",
            (coverage_500_batch_id, issue_code),
        ).fetchall()
        if not coverage:
            raise HistoricalIdMapError("Nowscore mapping requires an exact 500 coverage receipt")
        provider_by_slot = dict(parsed_rows)
        coverage_slots = {slot for slot, _ in coverage}
        if slot_map is not None:
            if len(set(slot_map.values())) != len(slot_map):
                raise HistoricalIdMapError("slot map must be one-to-one")
            if set(slot_map) != coverage_slots:
                raise HistoricalIdMapError("slot map does not cover every 500 slot")
            unmapped = sorted(ns_slot for ns_slot in slot_map.values() if ns_slot not in provider_by_slot and ns_slot not in void_slots)
            if unmapped:
                raise HistoricalIdMapError("slot map references a missing Nowscore slot: " + ",".join(map(str, unmapped)))
            ordered_join = [
                (slot, provider_by_slot[slot_map[slot]])
                for slot, _ in coverage
                if slot_map[slot] not in void_slots
            ]
        else:
            missing = sorted(coverage_slots - set(provider_by_slot) - void_slots)
            if missing:
                raise HistoricalIdMapError("Nowscore matrix misses 500 slots: " + ",".join(map(str, missing)))
            # 500 slots align 1:1 with the same Nowscore slot numbers.
            ordered_join = [(slot, provider_by_slot[slot]) for slot, _ in coverage if slot not in void_slots]
        provider_groups: dict[str, list[int]] = {}
        for slot, provider_id in ordered_join:
            provider_groups.setdefault(provider_id, []).append(slot)
        conflicts = {provider_id for provider_id, slots in provider_groups.items() if len(slots) > 1}
        resolution = {str(provider): slot for provider, slot in (conflict_resolution or {}).items()}
        if conflicts and conflict_resolution is not None:
            unknown = conflicts - set(resolution)
            if unknown:
                raise HistoricalIdMapError("conflict resolution omits providers: " + ",".join(sorted(unknown)))
        received = _utc(trusted_received_at_utc)
        digest = hashlib.sha256(payload).hexdigest()
        raw_path = self.root / "raw" / "id_discovery_nowscore" / digest[:2] / f"{digest}.html"
        expected = ("nowscore_id_mapping", issue_code, source_url, digest, str(raw_path.relative_to(self.root)), received, parser_version)
        existing = self.connection.execute(
            "SELECT source_id,issue_code,source_url,raw_sha256,raw_path,trusted_received_at_utc,parser_version FROM source_receipt WHERE batch_id=?",
            (batch_id,),
        ).fetchone()
        if existing is not None and tuple(existing) != expected:
            raise HistoricalIdMapError("Nowscore receipt batch collision")
        _write_raw(raw_path, payload)
        join_by_slot = dict(ordered_join)
        mappings = []
        isolated = []
        for slot, local_fid in coverage:
            if (slot_map[slot] if slot_map is not None else slot) in void_slots:
                isolated.append((issue_code, slot, local_fid, "0", "nowscore provider id void (cancelled/postponed/interrupted)"))
                continue
            provider_id = join_by_slot[slot]
            binding = f"{coverage_500_batch_id}|{batch_id}|{issue_code}|{slot}|{local_fid}|{provider_id}".encode()
            if provider_id in conflicts:
                verified_slot = resolution.get(provider_id)
                if verified_slot == slot:
                    mappings.append((issue_code, slot, local_fid, provider_id, coverage_500_batch_id, batch_id, hashlib.sha256(binding).hexdigest()))
                else:
                    isolated.append((issue_code, slot, local_fid, provider_id, f"duplicate provider {provider_id}"))
            else:
                mappings.append((issue_code, slot, local_fid, provider_id, coverage_500_batch_id, batch_id, hashlib.sha256(binding).hexdigest()))
        with _transaction(self.connection):
            if existing is None:
                self.connection.execute(
                    "INSERT INTO source_receipt VALUES(?,?,?,?,?,?,?,?,?)",
                    (batch_id, *expected[:1], "ID_DISCOVERY_ONLY", *expected[1:]),
                )
            for mapping in mappings:
                previous = self.connection.execute(
                    "SELECT local_500_fid,nowscore_provider_match_id,coverage_500_batch_id,nowscore_batch_id FROM issue_slot_nowscore_map WHERE issue_code=? AND issue_slot=?",
                    mapping[:2],
                ).fetchone()
                if previous is None:
                    self.connection.execute("INSERT INTO issue_slot_nowscore_map VALUES(?,?,?,?,?,?,?)", mapping)
                elif tuple(previous) != (mapping[2], mapping[3], mapping[4], mapping[5]):
                    raise HistoricalIdMapError("historical issue-slot mapping conflict")
            self.connection.executemany(
                "INSERT OR REPLACE INTO conflict_isolated_slot VALUES(?,?,?,?,?)", isolated
            )
        return digest

    def record_capture(
        self, *, issue_code: str, capture_key: str, received_at_utc: str,
        source_url_500: str, source_url_nowscore: str,
        raw_500: bytes, raw_nowscore: bytes, rows_500: Iterable[tuple[int, int]],
        slot_pairs: Iterable[tuple[int, int]],
        resolution_pairs: Iterable[tuple[str, int]] = (), rebuild: bool = False,
    ) -> dict:
        """Persist one R-parsed capture atomically; retain original source bytes.

        Exact retries are idempotent; a capture key reused with changed inputs or
        alignment is rejected. Rebuild replaces this issue's derived mapping only.
        Raw content-addressed evidence may remain after a database rollback.
        """
        if not _valid_issue(issue_code) or not capture_key:
            raise HistoricalIdMapError("explicit issue and capture key required")
        received_at_utc = _utc(received_at_utc)
        raw_500, raw_nowscore = bytes(raw_500), bytes(raw_nowscore)
        coverage = _normal_500_rows(tuple(tuple(row) for row in rows_500))
        pairs = tuple(tuple(pair) for pair in slot_pairs)
        slot_map = dict(pairs)
        if len(slot_map) != len(pairs) or len(set(slot_map.values())) != len(pairs):
            raise HistoricalIdMapError("slot map must be one-to-one")
        resolution_rows = tuple(tuple(pair) for pair in resolution_pairs)
        resolution = dict(resolution_rows)
        if len(resolution) != len(resolution_rows):
            raise HistoricalIdMapError("duplicate conflict resolution")
        candidates = parse_nowscore_provider_ids(raw_nowscore, issue_code=issue_code)
        voids = nowscore_void_slots(raw_nowscore, issue_code=issue_code)
        for provider, slot in resolution.items():
            if slot not in slot_map or dict(candidates).get(slot_map[slot]) != provider:
                raise HistoricalIdMapError("conflict resolution does not match provider and slot")
        contract = json.dumps([coverage, sorted(pairs), sorted(resolution_rows)], separators=(",", ":"))
        version = "r-mapping-v2:" + hashlib.sha256(contract.encode()).hexdigest()
        coverage_batch = f"{capture_key}:500:{issue_code}"
        mapping_batch = f"{capture_key}:nowscore:{issue_code}"
        with _transaction(self.connection):
            sha_500 = self.record_500_coverage(
                batch_id=coverage_batch, issue_code=issue_code, source_url=source_url_500,
                payload=raw_500, trusted_received_at_utc=received_at_utc,
                parser_version=version, rows=coverage,
            )
            if rebuild:
                self.connection.execute("DELETE FROM issue_slot_nowscore_map WHERE issue_code=?", (issue_code,))
                self.connection.execute("DELETE FROM conflict_isolated_slot WHERE issue_code=?", (issue_code,))
            sha_ns = self.record_nowscore_mapping(
                coverage_500_batch_id=coverage_batch, batch_id=mapping_batch,
                issue_code=issue_code, source_url=source_url_nowscore, payload=raw_nowscore,
                trusted_received_at_utc=received_at_utc, parser_version=version,
                rows=candidates, conflict_resolution=resolution or None,
                slot_map=slot_map, void_nowscore_slots=voids,
            )
        count = self.connection.execute(
            "SELECT COUNT(*) FROM issue_slot_nowscore_map WHERE issue_code=?", (issue_code,)
        ).fetchone()[0]
        return dict(issue=issue_code, mapped_slots=count, raw_500_sha256=sha_500,
                    raw_nowscore_sha256=sha_ns, capture_key=capture_key,
                    received_at_utc=received_at_utc, contract_sha256=version.split(":")[1])

    def conflicts(self) -> tuple[tuple[str, int, int, str, str], ...]:
        return tuple(
            self.connection.execute(
                "SELECT issue_code,issue_slot,local_500_fid,nowscore_provider_match_id,isolation_reason FROM conflict_isolated_slot ORDER BY issue_code,issue_slot"
            )
        )

    def mappings(self) -> tuple[HistoricalIdMapping, ...]:
        return tuple(
            HistoricalIdMapping(*row)
            for row in self.connection.execute(
                "SELECT issue_code,issue_slot,nowscore_provider_match_id,discovery_sha256 FROM issue_slot_nowscore_map ORDER BY issue_code,issue_slot"
            )
        )

    def export_titan_candidate_bridge(self) -> tuple[Path, str]:
        """Export only opaque Titan candidate IDs and discovery binding hashes.

        A Titan provider ID can legitimately be referenced by more than one
        issue (cross-issue duplicates); the bridge keeps the first binding so
        the Titan collector fetches each fixture exactly once.
        """
        candidates = []
        seen: set[str] = set()
        for row in self.mappings():
            if row.nowscore_provider_match_id in seen:
                continue
            seen.add(row.nowscore_provider_match_id)
            candidates.append(
                {"nowscore_provider_match_id": row.nowscore_provider_match_id, "discovery_sha256": row.discovery_sha256}
            )
        canonical = json.dumps(candidates, sort_keys=True, separators=(",", ":")) + "\n"
        bridge = {"schema_version": "titan_historical_candidate_bridge_v1", "candidates": candidates}
        payload = (json.dumps(bridge, sort_keys=True, separators=(",", ":")) + "\n").encode()
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        path = self.root / "handoff" / "titan_historical_candidates" / f"{digest}.json"
        _write_raw(path, payload)
        return path, digest
