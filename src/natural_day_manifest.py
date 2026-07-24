"""Published natural-day segment contract shared by every runtime consumer."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo


SCHEMA_VERSION = "natural_day_segment_manifest_v1"
PUBLICATION_TABLE = "natural_day_segment_publications"
PUBLICATION_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PUBLICATION_TABLE} (
    issue TEXT PRIMARY KEY,
    policy TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL UNIQUE,
    manifest_json TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    published_at_hkt TEXT NOT NULL
)
"""


class NaturalDayManifestError(RuntimeError):
    """Raised when a published segment contract is absent or inconsistent."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def manifest_identity_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable semantic fields covered by ``manifest_sha256``."""
    return {
        key: manifest[key]
        for key in (
            "schema_version",
            "capability_id",
            "policy",
            "issue",
            "denominator_match_indices",
            "skipped",
            "segments",
        )
        if key in manifest
    }


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(manifest_identity_payload(manifest))).hexdigest()


def verify_manifest(manifest: Mapping[str, Any]) -> str:
    required = {
        "schema_version",
        "capability_id",
        "policy",
        "issue",
        "denominator_match_indices",
        "skipped",
        "segments",
        "manifest_sha256",
    }
    if not required.issubset(manifest):
        raise NaturalDayManifestError("natural-day manifest is incomplete")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise NaturalDayManifestError("unsupported natural-day manifest schema")
    claimed = str(manifest["manifest_sha256"])
    actual = manifest_sha256(manifest)
    if claimed != actual:
        raise NaturalDayManifestError("natural-day manifest hash mismatch")

    denominator = [int(value) for value in manifest["denominator_match_indices"]]
    covered: list[int] = []
    ordinals: list[int] = []
    for segment in manifest["segments"]:
        ordinal = int(segment["segment_idx"])
        indices = [int(value) for value in segment["match_indices"]]
        if int(segment["match_count"]) != len(indices):
            raise NaturalDayManifestError("natural-day segment count mismatch")
        ordinals.append(ordinal)
        covered.extend(indices)
    skipped = [
        int(value)
        for record in manifest["skipped"]
        for value in record["match_indices"]
    ]
    if ordinals != list(range(1, len(ordinals) + 1)):
        raise NaturalDayManifestError("natural-day segment ordinals are not contiguous")
    if len(covered) != len(set(covered)):
        raise NaturalDayManifestError("natural-day segment membership overlaps")
    if sorted(covered + skipped) != sorted(denominator):
        raise NaturalDayManifestError("natural-day denominator is incomplete")
    return claimed


def publication_table_exists(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (PUBLICATION_TABLE,),
    ).fetchone() is not None


def load_published_manifest(
    conn: sqlite3.Connection,
    issue: str,
    *,
    verify_file: bool = True,
) -> dict[str, Any] | None:
    """Load the canonical issue contract recorded by the atomic publisher."""
    if not publication_table_exists(conn):
        return None
    row = conn.execute(
        f"""
        SELECT manifest_sha256,manifest_json,manifest_path,published_at_hkt
        FROM {PUBLICATION_TABLE}
        WHERE issue=?
        """,
        (str(issue),),
    ).fetchone()
    if row is None:
        return None
    manifest = json.loads(str(row[1]))
    claimed = verify_manifest(manifest)
    if claimed != str(row[0]):
        raise NaturalDayManifestError("publication record hash differs from manifest")
    manifest_path = Path(str(row[2]))
    if verify_file:
        try:
            file_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise NaturalDayManifestError("published natural-day manifest file is unavailable") from exc
        if canonical(file_manifest) != canonical(manifest):
            raise NaturalDayManifestError("published natural-day manifest file differs from SQLite")
        verify_manifest(file_manifest)
    return {
        **manifest,
        "manifest_path": str(manifest_path),
        "published_at_hkt": str(row[3]),
    }


def expected_window_rows(manifest: Mapping[str, Any]) -> list[tuple[int, str, list[int]]]:
    return [
        (
            int(segment["segment_idx"]),
            str(segment["freeze_at"]),
            [int(value) for value in segment["match_indices"]],
        )
        for segment in manifest["segments"]
    ]


def verify_operational_windows(
    conn: sqlite3.Connection,
    manifest: Mapping[str, Any],
) -> None:
    rows = conn.execute(
        """
        SELECT segment_idx,freeze_at,match_indices_json
        FROM segment_decision_windows
        WHERE issue=?
        ORDER BY segment_idx
        """,
        (str(manifest["issue"]),),
    ).fetchall()
    hkt = ZoneInfo("Asia/Hong_Kong")

    def normalized(value: str) -> str:
        parsed = datetime.fromisoformat(value)
        aware = parsed.replace(tzinfo=hkt) if parsed.tzinfo is None else parsed
        return aware.astimezone(hkt).isoformat(timespec="seconds")

    observed = [
        (
            int(row[0]),
            normalized(str(row[1])),
            [int(value) for value in json.loads(str(row[2]))],
        )
        for row in rows
    ]
    expected = [
        (segment_idx, normalized(freeze_at), indices)
        for segment_idx, freeze_at, indices in expected_window_rows(manifest)
    ]
    if observed != expected:
        raise NaturalDayManifestError(
            "operational windows differ from the published natural-day manifest"
        )


def segment_membership(
    manifest: Mapping[str, Any],
) -> list[tuple[int, tuple[int, ...]]]:
    return [
        (
            int(segment["segment_idx"]),
            tuple(int(value) for value in segment["match_indices"]),
        )
        for segment in manifest["segments"]
    ]
