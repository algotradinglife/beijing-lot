"""Immutable missed-freeze child segment contract (BJ-SEG-RECOVERY-001)."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "segment_recovery_manifest_v1"
POLICY_ID = "BJ-SEG-RECOVERY-001/deterministic_recovery_v1"
PUBLICATION_TABLE = "segment_recovery_publications"
WINDOW_TABLE = "segment_recovery_windows"
PUBLICATION_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {PUBLICATION_TABLE} (
    issue TEXT NOT NULL,
    parent_segment_idx INTEGER NOT NULL,
    child_identity TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL,
    parent_manifest_sha256 TEXT NOT NULL,
    recovery_manifest_sha256 TEXT NOT NULL UNIQUE,
    manifest_json TEXT NOT NULL,
    manifest_path TEXT NOT NULL,
    recovery_published_at_hkt TEXT NOT NULL,
    PRIMARY KEY(issue,parent_segment_idx)
)
"""
WINDOW_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {WINDOW_TABLE} (
    issue TEXT NOT NULL,
    parent_segment_idx INTEGER NOT NULL,
    child_identity TEXT NOT NULL UNIQUE,
    segment_start TEXT NOT NULL,
    segment_end TEXT NOT NULL,
    freeze_at TEXT NOT NULL,
    match_indices_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(issue,parent_segment_idx)
)
"""


class SegmentRecoveryError(RuntimeError):
    """Raised when recovery identity, timing, or storage is inconsistent."""


def canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def manifest_sha256(manifest: Mapping[str, Any]) -> str:
    unsigned = {
        key: value for key, value in manifest.items() if key != "manifest_sha256"
    }
    return hashlib.sha256(canonical(unsigned)).hexdigest()


def _aware(value: object) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise SegmentRecoveryError("recovery clock lacks timezone")
    if parsed.utcoffset() != timedelta(hours=8):
        raise SegmentRecoveryError("recovery clock is not normalized to HKT")
    return parsed


def schedule_input_sha256(manifest: Mapping[str, Any]) -> str:
    by_idx = {
        int(item["match_idx"]): {
            "match_idx": int(item["match_idx"]),
            "kickoff_at_hkt": str(item["kickoff_at_hkt"]),
        }
        for item in [*manifest["included"], *manifest["excluded"]]
    }
    return hashlib.sha256(
        canonical(
            {
                "issue": str(manifest["issue"]),
                "parent_segment_idx": int(manifest["parent_segment_idx"]),
                "matches": [
                    by_idx[int(match_idx)]
                    for match_idx in manifest["parent_match_indices"]
                ],
            }
        )
    ).hexdigest()


def verify_manifest(manifest: Mapping[str, Any]) -> str:
    required = {
        "schema_version",
        "capability_id",
        "policy",
        "issue",
        "parent_segment_idx",
        "parent_segment_identity",
        "parent_segment_manifest_sha256",
        "parent_status",
        "child_identity",
        "recovery_ordinal",
        "status",
        "recovery_published_at_hkt",
        "parent_match_indices",
        "included",
        "excluded",
        "recovery_freeze_at",
        "schedule_input_sha256",
        "manifest_sha256",
    }
    if not required.issubset(manifest):
        raise SegmentRecoveryError("recovery manifest is incomplete")
    if (
        manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("capability_id") != "BJ-SEG-RECOVERY-001"
        or manifest.get("policy") != POLICY_ID
        or manifest.get("parent_status") != "MISSED_FREEZE"
        or int(manifest.get("recovery_ordinal", 0)) != 1
        or manifest.get("market_or_model_inputs_used") is not False
        or manifest.get("immutable") is not True
        or manifest.get("selection_inputs")
        != ["matches.issue", "matches.match_idx", "matches.end_time"]
    ):
        raise SegmentRecoveryError("unsupported recovery contract")
    parent_idx = int(manifest["parent_segment_idx"])
    child_identity = str(manifest["child_identity"])
    if (
        child_identity != f"segment_{parent_idx}_recovery_1"
        or str(manifest["parent_segment_identity"]) != f"segment_{parent_idx}"
        or not re.fullmatch(
            r"[0-9a-f]{64}", str(manifest["parent_segment_manifest_sha256"])
        )
    ):
        raise SegmentRecoveryError("recovery child identity mismatch")
    claimed = str(manifest["manifest_sha256"])
    if claimed != manifest_sha256(manifest):
        raise SegmentRecoveryError("recovery manifest hash mismatch")

    parent = [int(value) for value in manifest["parent_match_indices"]]
    included = list(manifest["included"])
    excluded = list(manifest["excluded"])
    included_ids = [int(item["match_idx"]) for item in included]
    excluded_ids = [int(item["match_idx"]) for item in excluded]
    included_set = set(included_ids)
    if (
        len(parent) != len(set(parent))
        or len(included_ids) != len(set(included_ids))
        or set(included_ids) & set(excluded_ids)
        or sorted(included_ids + excluded_ids) != sorted(parent)
    ):
        raise SegmentRecoveryError("parent/recovery denominator is not a partition")
    if int(manifest.get("included_match_count", -1)) != len(included) or int(
        manifest.get("excluded_match_count", -1)
    ) != len(excluded):
        raise SegmentRecoveryError("recovery membership counts mismatch")

    published = _aware(manifest["recovery_published_at_hkt"])
    for item in included + excluded:
        kickoff = _aware(item["kickoff_at_hkt"])
        boundary = _aware(item["freeze_boundary_at_hkt"])
        if boundary != kickoff - timedelta(minutes=25):
            raise SegmentRecoveryError("per-match T-25 boundary mismatch")
        should_include = boundary > published
        if (int(item["match_idx"]) in included_set) != should_include:
            raise SegmentRecoveryError("recovery time eligibility mismatch")
    for item in excluded:
        if item.get("reason") != "excluded_freeze_window_passed":
            raise SegmentRecoveryError("recovery exclusion reason mismatch")
    for items in (included, excluded):
        observed_order = [
            (_aware(item["kickoff_at_hkt"]), int(item["match_idx"])) for item in items
        ]
        if observed_order != sorted(observed_order):
            raise SegmentRecoveryError("recovery matches are not schedule ordered")
    if str(manifest["schedule_input_sha256"]) != schedule_input_sha256(manifest):
        raise SegmentRecoveryError("recovery schedule input hash mismatch")

    status = str(manifest["status"])
    if status == "PUBLISHED_RECOVERY":
        if len(included) < 20:
            raise SegmentRecoveryError("published recovery has fewer than 20 matches")
        first = _aware(included[0]["kickoff_at_hkt"])
        last = _aware(included[-1]["kickoff_at_hkt"])
        freeze_at = _aware(manifest["recovery_freeze_at"])
        if (
            freeze_at != first - timedelta(minutes=25)
            or not published < freeze_at
            or last - first > timedelta(hours=36)
        ):
            raise SegmentRecoveryError("recovery window policy mismatch")
    elif status in {
        "SKIPPED_RECOVERY_INSUFFICIENT_MATCHES",
        "MISSED_RECOVERY_FREEZE",
    }:
        if len(included) >= 20 or manifest["recovery_freeze_at"] not in {"", None}:
            raise SegmentRecoveryError("invalid insufficient recovery conclusion")
        if status == "MISSED_RECOVERY_FREEZE":
            if not manifest.get("hard_stop_at_hkt"):
                raise SegmentRecoveryError("missed recovery lacks hard stop")
            hard_stop = _aware(manifest.get("hard_stop_at_hkt"))
            if published < hard_stop:
                raise SegmentRecoveryError(
                    "recovery was marked missed before hard stop"
                )
    else:
        raise SegmentRecoveryError("invalid recovery status")
    return claimed


def load_published_recovery(
    conn: sqlite3.Connection,
    issue: str,
    parent_segment_idx: int,
    *,
    verify_file: bool = True,
) -> dict[str, Any] | None:
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (PUBLICATION_TABLE,),
        ).fetchone()
        is None
    ):
        return None
    row = conn.execute(
        f"""
        SELECT state,parent_manifest_sha256,recovery_manifest_sha256,
               manifest_json,manifest_path,recovery_published_at_hkt
        FROM {PUBLICATION_TABLE}
        WHERE issue=? AND parent_segment_idx=?
        """,
        (str(issue), int(parent_segment_idx)),
    ).fetchone()
    if row is None:
        return None
    manifest = json.loads(str(row[3]))
    claimed = verify_manifest(manifest)
    if (
        str(row[0]) != str(manifest["status"])
        or str(row[1]) != str(manifest["parent_segment_manifest_sha256"])
        or str(row[2]) != claimed
        or str(row[5]) != str(manifest["recovery_published_at_hkt"])
    ):
        raise SegmentRecoveryError("SQLite recovery publication differs from manifest")
    path = Path(str(row[4]))
    if verify_file:
        try:
            file_manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SegmentRecoveryError("recovery manifest file is unavailable") from exc
        if canonical(file_manifest) != canonical(manifest):
            raise SegmentRecoveryError("recovery manifest file differs from SQLite")
        verify_manifest(file_manifest)
    return {**manifest, "manifest_path": str(path)}


def verify_operational_window(
    conn: sqlite3.Connection, manifest: Mapping[str, Any]
) -> None:
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (WINDOW_TABLE,),
        ).fetchone()
        is None
    ):
        raise SegmentRecoveryError("recovery operational window table is missing")
    row = conn.execute(
        f"""
        SELECT child_identity,segment_start,segment_end,freeze_at,match_indices_json
        FROM {WINDOW_TABLE}
        WHERE issue=? AND parent_segment_idx=?
        """,
        (str(manifest["issue"]), int(manifest["parent_segment_idx"])),
    ).fetchone()
    if manifest["status"] != "PUBLISHED_RECOVERY":
        if row is not None:
            raise SegmentRecoveryError("skipped recovery has an operational window")
        return
    expected = (
        str(manifest["child_identity"]),
        str(manifest["included"][0]["kickoff_at_hkt"]),
        str(manifest["included"][-1]["kickoff_at_hkt"]),
        str(manifest["recovery_freeze_at"]),
        [int(item["match_idx"]) for item in manifest["included"]],
    )
    observed = (
        (
            str(row[0]),
            str(row[1]),
            str(row[2]),
            str(row[3]),
            [int(value) for value in json.loads(str(row[4]))],
        )
        if row is not None
        else None
    )
    if observed != expected:
        raise SegmentRecoveryError(
            "recovery operational window differs from publication"
        )
