#!/usr/bin/env python3
"""Atomically publish the BJ-SEG-DAY-001 cross-layer operational contract."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.natural_day_manifest import (  # noqa: E402
    PUBLICATION_TABLE,
    PUBLICATION_TABLE_SQL,
    NaturalDayManifestError,
    canonical,
    load_published_manifest,
    manifest_identity_payload,
    manifest_sha256,
    verify_manifest,
    verify_operational_windows,
)
from src.natural_day_segments import POLICY_ID, build_natural_day_segments  # noqa: E402

HKT = ZoneInfo("Asia/Hong_Kong")
DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
DEFAULT_OUTPUT = ROOT / "results/segment_decision_forward_artifacts"


@dataclass(frozen=True)
class Match:
    match_idx: int
    kickoff: datetime


def iso(value: datetime) -> str:
    return value.astimezone(HKT).isoformat(timespec="seconds")


def _as_hkt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return (
        parsed.replace(tzinfo=HKT) if parsed.tzinfo is None else parsed.astimezone(HKT)
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_package(
    directory: Path,
    manifest: dict[str, Any],
    incident_audit: dict[str, Any],
) -> None:
    manifest_path = directory / "segment_manifest.json"
    audit_path = directory / "incident_wrong_entire_issue_window.json"
    manifest_path.write_bytes(canonical(manifest) + b"\n")
    audit_path.write_bytes(canonical(incident_audit) + b"\n")
    sums = (
        f"{_file_sha256(manifest_path)}  segment_manifest.json\n"
        f"{_file_sha256(audit_path)}  incident_wrong_entire_issue_window.json\n"
    )
    (directory / "SHA256SUMS").write_text(sums, encoding="utf-8")
    for path in directory.iterdir():
        _fsync_file(path)
    _fsync_directory(directory)


def _verify_package(directory: Path, manifest: dict[str, Any]) -> None:
    expected_names = {
        "segment_manifest.json",
        "incident_wrong_entire_issue_window.json",
        "SHA256SUMS",
    }
    if {path.name for path in directory.iterdir()} != expected_names:
        raise NaturalDayManifestError("natural-day package file set mismatch")
    on_disk = json.loads((directory / "segment_manifest.json").read_text(encoding="utf-8"))
    if canonical(on_disk) != canonical(manifest):
        raise NaturalDayManifestError("natural-day package manifest differs from contract")
    verify_manifest(on_disk)
    entries: dict[str, str] = {}
    for line in (directory / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        sha, separator, name = line.partition("  ")
        if not separator or name in entries:
            raise NaturalDayManifestError("malformed natural-day SHA256SUMS")
        entries[name] = sha
    if set(entries) != expected_names - {"SHA256SUMS"}:
        raise NaturalDayManifestError("natural-day SHA256SUMS file set mismatch")
    for name, expected in entries.items():
        if _file_sha256(directory / name) != expected:
            raise NaturalDayManifestError("natural-day package checksum mismatch")


def _existing_result(
    conn: sqlite3.Connection,
    issue: str,
    desired_manifest: dict[str, Any],
) -> dict[str, Any] | None:
    published = load_published_manifest(conn, issue)
    if published is None:
        return None
    if str(published["manifest_sha256"]) != str(desired_manifest["manifest_sha256"]):
        raise NaturalDayManifestError(
            "issue already has a different authoritative natural-day publication"
        )
    verify_operational_windows(conn, published)
    return {
        "manifest": str(published["manifest_path"]),
        "sha256": str(published["manifest_sha256"]),
        "segments": [int(item["match_count"]) for item in published["segments"]],
        "idempotent": True,
    }


def _legacy_adoption_proof(
    legacy_path: Path,
    desired_manifest: dict[str, Any],
    *,
    earliest_freeze: datetime,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify a pre-freeze v1 publication before registering it atomically."""
    try:
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        published_at = _as_hkt(str(legacy["published_at_hkt"]))
        claimed = str(legacy["manifest_sha256"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise NaturalDayManifestError("legacy natural-day manifest is unreadable") from exc
    unhashed = dict(legacy)
    unhashed.pop("manifest_sha256", None)
    actual = hashlib.sha256(canonical(unhashed)).hexdigest()
    if claimed != actual:
        raise NaturalDayManifestError("legacy natural-day manifest hash mismatch")
    if published_at >= earliest_freeze:
        raise NaturalDayManifestError(
            "legacy natural-day manifest was not published before first freeze"
        )
    if canonical(manifest_identity_payload(legacy)) != canonical(
        manifest_identity_payload(desired_manifest)
    ):
        raise NaturalDayManifestError(
            "legacy natural-day manifest differs from current deterministic contract"
        )
    proof = {
        "mode": "adopt_verified_pre_freeze_publication",
        "legacy_manifest_path": str(legacy_path.resolve()),
        "legacy_manifest_file_sha256": _file_sha256(legacy_path),
        "legacy_manifest_sha256": claimed,
        "legacy_published_at_hkt": iso(published_at),
    }
    incident = legacy.get("incident_audit")
    return proof, incident if isinstance(incident, dict) else {}


def publish(
    *,
    issue: str,
    db_path: Path,
    output_root: Path,
    now: datetime,
    adopt_pre_freeze_manifest: Path | None = None,
) -> dict[str, Any]:
    """Publish manifest bytes, publication identity and windows as one unit.

    SQLite is the authoritative commit record. The content-addressed directory
    is renamed into visibility while the ``BEGIN IMMEDIATE`` transaction is
    open. A failed transaction removes a directory created by this invocation;
    a crash-created identical orphan is verified and adopted on retry.
    """
    now = (now.replace(tzinfo=HKT) if now.tzinfo is None else now).astimezone(HKT)
    db_path = db_path.resolve()
    output_root = output_root.resolve()
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    stage: Path | None = None
    destination_created = False
    transaction_open = False
    lock_handle = None
    try:
        rows = conn.execute(
            """
            SELECT match_idx,end_time
            FROM matches
            WHERE issue=?
            ORDER BY datetime(end_time),match_idx
            """,
            (str(issue),),
        ).fetchall()
        matches = [Match(int(row["match_idx"]), _as_hkt(str(row["end_time"]))) for row in rows]
        built = build_natural_day_segments(str(issue), matches)
        if not built.segments:
            raise NaturalDayManifestError(
                "refusing to publish an operational manifest with no eligible segments"
            )
        manifest: dict[str, Any] = {
            "schema_version": "natural_day_segment_manifest_v1",
            "capability_id": "BJ-SEG-DAY-001",
            "policy": POLICY_ID,
            "issue": str(issue),
            "denominator_match_indices": list(built.denominator_match_indices),
            "skipped": list(built.skipped),
            "segments": [
                {
                    "segment_idx": item.segment_idx,
                    "hkt_dates": list(item.hkt_dates),
                    "match_indices": list(item.match_indices),
                    "match_count": len(item.match_indices),
                    "segment_start": iso(item.first_kickoff),
                    "segment_end": iso(item.last_kickoff),
                    "freeze_at": iso(item.freeze_at),
                    "checkpoints": {
                        "t6h": iso(item.freeze_at - timedelta(hours=6)),
                        "t2h": iso(item.freeze_at - timedelta(hours=2)),
                        "t30m": iso(item.freeze_at - timedelta(minutes=30)),
                    },
                }
                for item in built.segments
            ],
        }
        manifest["manifest_sha256"] = manifest_sha256(manifest)
        verify_manifest(manifest)

        existing = _existing_result(conn, str(issue), manifest)
        if existing is not None:
            return existing

        earliest = min(item.freeze_at for item in built.segments)
        adoption_proof: dict[str, Any] | None = None
        adopted_incident: dict[str, Any] = {}
        if now >= earliest and adopt_pre_freeze_manifest is None:
            raise NaturalDayManifestError(
                f"fail closed: first freeze {iso(earliest)} has passed"
            )
        if adopt_pre_freeze_manifest is not None:
            adoption_proof, adopted_incident = _legacy_adoption_proof(
                adopt_pre_freeze_manifest,
                manifest,
                earliest_freeze=earliest,
            )
            verify_operational_windows(conn, manifest)
        else:
            ledger = ROOT / "results/research/multimarket_segment_freeze_v1/ledger"
            if ledger.exists() and any(
                str(issue) in path.read_text(encoding="utf-8", errors="ignore")
                for path in ledger.glob("*.json")
            ):
                raise NaturalDayManifestError(
                    "fail closed: existing research freeze ledger references issue"
                )

        old = [
            dict(row)
            for row in conn.execute(
                """
                SELECT issue,segment_idx,segment_start,segment_end,freeze_at,
                       match_indices_json,created_at,manual_frozen_at
                FROM segment_decision_windows
                WHERE issue=?
                ORDER BY segment_idx
                """,
                (str(issue),),
            )
        ]
        incident_audit = (
            {
                **adopted_incident,
                "adoption_proof": adoption_proof,
            }
            if adoption_proof is not None
            else {
                "replaced_window_count": len(old),
                "pre_correction_sha256": hashlib.sha256(canonical(old)).hexdigest(),
                "pre_correction_windows": old,
            }
        )

        version_root = output_root / str(issue) / "natural_day_v1"
        version_root.mkdir(parents=True, exist_ok=True)
        lock_path = version_root / ".publish.lock"
        lock_handle = lock_path.open("a+b")
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

        # Recheck after acquiring the cross-process issue lock.
        existing = _existing_result(conn, str(issue), manifest)
        if existing is not None:
            return existing

        destination = version_root / str(manifest["manifest_sha256"])
        if destination.exists():
            _verify_package(destination, manifest)
        else:
            stage = Path(tempfile.mkdtemp(prefix=".publish-", dir=version_root))
            _write_package(stage, manifest, incident_audit)
            _verify_package(stage, manifest)

        manifest_path = destination / "segment_manifest.json"
        conn.execute("BEGIN IMMEDIATE")
        transaction_open = True
        conn.execute(PUBLICATION_TABLE_SQL)
        row = conn.execute(
            f"SELECT manifest_sha256 FROM {PUBLICATION_TABLE} WHERE issue=?",
            (str(issue),),
        ).fetchone()
        if row is not None:
            if str(row[0]) != str(manifest["manifest_sha256"]):
                raise NaturalDayManifestError(
                    "concurrent conflicting natural-day publication"
                )
            raise NaturalDayManifestError(
                "publication appeared concurrently; retry idempotently"
            )

        if adoption_proof is None:
            conn.execute(
                "DELETE FROM segment_decision_windows WHERE issue=?",
                (str(issue),),
            )
            for item in built.segments:
                conn.execute(
                    """
                    INSERT INTO segment_decision_windows(
                        issue,segment_idx,segment_start,segment_end,freeze_at,
                        match_indices_json,created_at
                    ) VALUES(?,?,?,?,?,?,?)
                    """,
                    (
                        str(issue),
                        item.segment_idx,
                        iso(item.first_kickoff),
                        iso(item.last_kickoff),
                        iso(item.freeze_at),
                        json.dumps(list(item.match_indices), separators=(",", ":")),
                        iso(now),
                    ),
                )
        conn.execute(
            f"""
            INSERT INTO {PUBLICATION_TABLE}(
                issue,policy,manifest_sha256,manifest_json,manifest_path,published_at_hkt
            ) VALUES(?,?,?,?,?,?)
            """,
            (
                str(issue),
                POLICY_ID,
                str(manifest["manifest_sha256"]),
                canonical(manifest).decode("utf-8"),
                str(manifest_path),
                iso(now),
            ),
        )

        if stage is not None:
            stage.rename(destination)
            stage = None
            destination_created = True
            _fsync_directory(version_root)
        _verify_package(destination, manifest)
        verify_operational_windows(conn, manifest)
        conn.commit()
        transaction_open = False
        return {
            "manifest": str(manifest_path),
            "sha256": str(manifest["manifest_sha256"]),
            "segments": [len(item.match_indices) for item in built.segments],
            "idempotent": False,
        }
    except Exception:
        if transaction_open:
            conn.rollback()
        if destination_created:
            shutil.rmtree(destination)
            _fsync_directory(destination.parent)
        raise
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        if lock_handle is not None:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--now-hkt", default="", help="test-only ISO timestamp")
    parser.add_argument(
        "--adopt-pre-freeze-manifest",
        type=Path,
        help=(
            "register a hash-verified, semantically identical manifest that was "
            "published before the first freeze; never changes membership"
        ),
    )
    args = parser.parse_args()
    now = (
        datetime.fromisoformat(args.now_hkt)
        if args.now_hkt
        else datetime.now(timezone.utc)
    )
    try:
        result = publish(
            issue=str(args.issue),
            db_path=args.db,
            output_root=args.output_root,
            now=now,
            adopt_pre_freeze_manifest=args.adopt_pre_freeze_manifest,
        )
    except NaturalDayManifestError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
