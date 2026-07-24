#!/usr/bin/env python3
"""Publish the one immutable child attempt for a missed natural-day segment."""

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
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.natural_day_manifest import (  # noqa: E402
    NaturalDayManifestError,
    load_published_manifest,
    verify_operational_windows,
)
from src.natural_day_segments import build_natural_day_segments  # noqa: E402
from src.segment_recovery import (  # noqa: E402
    POLICY_ID,
    PUBLICATION_TABLE,
    PUBLICATION_TABLE_SQL,
    WINDOW_TABLE,
    WINDOW_TABLE_SQL,
    SegmentRecoveryError,
    canonical,
    load_published_recovery,
    manifest_sha256,
    schedule_input_sha256,
    verify_manifest,
    verify_operational_window,
)

HKT = ZoneInfo("Asia/Hong_Kong")
DEFAULT_OUTPUT_ROOT = ROOT / "results/research/segment_recovery_v1"
DEFAULT_EXACT_LEDGER = ROOT / "results/research/exact_n_segment_freeze_v1/ledger"


@dataclass(frozen=True)
class Match:
    match_idx: int
    kickoff: datetime


def _hkt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return (parsed.replace(tzinfo=HKT) if parsed.tzinfo is None else parsed).astimezone(
        HKT
    )


def _iso(value: datetime) -> str:
    return value.astimezone(HKT).isoformat(timespec="microseconds")


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(payload) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_file(path: Path) -> None:
    with path.open("rb") as stream:
        os.fsync(stream.fileno())


def verify_directory(root: Path) -> dict[str, object]:
    root = root.resolve()
    sums = (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    if len(sums) != 1:
        raise SegmentRecoveryError("recovery SHA256SUMS file set mismatch")
    claimed, name = sums[0].split("  ", 1)
    if name != "recovery_manifest.json":
        raise SegmentRecoveryError("recovery SHA256SUMS path mismatch")
    path = root / name
    if _file_hash(path) != claimed:
        raise SegmentRecoveryError("recovery SHA256SUMS digest mismatch")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    semantic = verify_manifest(manifest)
    return {
        "status": "PASS",
        "recovery_manifest_sha256": semantic,
        "recovery_manifest_file_sha256": claimed,
        "package_sha256s_sha256": _file_hash(root / "SHA256SUMS"),
    }


def _parent_event_key(issue: str, parent_segment_idx: int) -> str:
    return hashlib.sha256(
        canonical({"issue": str(issue), "segment_idx": int(parent_segment_idx)})
    ).hexdigest()


def publish(
    *,
    issue: str,
    parent_segment_idx: int,
    db_path: Path,
    output_root: Path,
    exact_ledger_root: Path,
    observed_at: datetime | None = None,
    hard_stop_at: datetime | None = None,
) -> dict[str, object]:
    """Publish one attempt, with the caller-injected clock reserved for tests."""
    db_path = db_path.resolve()
    output_root = output_root.resolve()
    child_identity = f"segment_{int(parent_segment_idx)}_recovery_1"
    issue_root = output_root / str(issue) / child_identity
    issue_root.mkdir(parents=True, exist_ok=True)
    lock = (issue_root / ".publish.lock").open("a+b")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    conn = sqlite3.connect(db_path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    stage: Path | None = None
    destination_created = False
    transaction_open = False
    attempt_path = issue_root / "attempt.json"
    attempt_reserved = False
    try:
        existing = load_published_recovery(conn, str(issue), int(parent_segment_idx))
        if existing is not None:
            verify_operational_window(conn, existing)
            receipt = verify_directory(Path(str(existing["manifest_path"])).parent)
            return {
                "status": str(existing["status"]),
                "idempotent": True,
                "child_identity": child_identity,
                "manifest": str(existing["manifest_path"]),
                "sha256": str(existing["manifest_sha256"]),
                "included_match_count": int(existing["included_match_count"]),
                "excluded_match_count": int(existing["excluded_match_count"]),
                "freeze_at": str(existing["recovery_freeze_at"]),
                "verification": receipt,
            }

        parent_contract = load_published_manifest(conn, str(issue))
        if parent_contract is None:
            raise SegmentRecoveryError(
                "canonical natural-day parent publication is missing"
            )
        verify_operational_windows(conn, parent_contract)
        parent = next(
            (
                item
                for item in parent_contract["segments"]
                if int(item["segment_idx"]) == int(parent_segment_idx)
            ),
            None,
        )
        if parent is None:
            raise SegmentRecoveryError("parent segment is absent")
        parent_event = exact_ledger_root / (
            _parent_event_key(str(issue), int(parent_segment_idx)) + ".json"
        )
        if parent_event.is_file():
            ledger = json.loads(parent_event.read_text(encoding="utf-8"))
            if ledger.get("state") == "PUBLISHED":
                raise SegmentRecoveryError(
                    "parent has a published exact-N event and is not recoverable"
                )

        parent_ids = [int(value) for value in parent["match_indices"]]
        placeholders = ",".join("?" for _ in parent_ids)
        rows = conn.execute(
            f"""
            SELECT match_idx,end_time
            FROM matches
            WHERE issue=? AND match_idx IN ({placeholders})
            ORDER BY datetime(end_time),match_idx
            """,
            (str(issue), *parent_ids),
        ).fetchall()
        matches = [
            Match(int(row["match_idx"]), _hkt(str(row["end_time"]))) for row in rows
        ]
        if {item.match_idx for item in matches} != set(parent_ids):
            raise SegmentRecoveryError("parent schedule denominator is incomplete")
        now = (observed_at or datetime.now(timezone.utc)).astimezone(HKT)
        if now <= _hkt(str(parent["freeze_at"])):
            raise SegmentRecoveryError("parent segment has not missed its freeze")
        if attempt_path.exists():
            raise SegmentRecoveryError(
                "recovery attempt already consumed without a canonical publication"
            )
        attempt_payload = {
            "schema_version": "segment_recovery_attempt_v1",
            "issue": str(issue),
            "parent_segment_idx": int(parent_segment_idx),
            "child_identity": child_identity,
            "attempt_key": hashlib.sha256(
                canonical(
                    {
                        "issue": str(issue),
                        "parent_segment_idx": int(parent_segment_idx),
                        "recovery_ordinal": 1,
                    }
                )
            ).hexdigest(),
            "state": "RESERVED",
            "reserved_at_hkt": _iso(now),
        }
        fd = os.open(attempt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(attempt_payload) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        _fsync_directory(issue_root)
        attempt_reserved = True
        eligible = [
            item
            for item in matches
            if item.kickoff.timestamp() - 25 * 60 > now.timestamp()
        ]
        built = build_natural_day_segments(str(issue), eligible)
        published = (
            len(built.segments) == 1
            and not built.skipped
            and list(built.segments[0].match_indices)
            == [item.match_idx for item in eligible]
        )
        hard_stop = hard_stop_at.astimezone(HKT) if hard_stop_at is not None else None
        status = (
            "MISSED_RECOVERY_FREEZE"
            if hard_stop is not None and now >= hard_stop
            else (
                "PUBLISHED_RECOVERY"
                if published
                else "SKIPPED_RECOVERY_INSUFFICIENT_MATCHES"
            )
        )
        published = status == "PUBLISHED_RECOVERY"
        eligible_ids = {item.match_idx for item in eligible}
        included = [
            {
                "match_idx": item.match_idx,
                "kickoff_at_hkt": _iso(item.kickoff),
                "freeze_boundary_at_hkt": _iso(item.kickoff - timedelta(minutes=25)),
            }
            for item in matches
            if item.match_idx in eligible_ids
        ]
        excluded = [
            {
                "match_idx": item.match_idx,
                "kickoff_at_hkt": _iso(item.kickoff),
                "freeze_boundary_at_hkt": _iso(item.kickoff - timedelta(minutes=25)),
                "reason": "excluded_freeze_window_passed",
            }
            for item in matches
            if item.match_idx not in eligible_ids
        ]
        segment = built.segments[0] if published else None
        manifest: dict[str, object] = {
            "schema_version": "segment_recovery_manifest_v1",
            "capability_id": "BJ-SEG-RECOVERY-001",
            "policy": POLICY_ID,
            "issue": str(issue),
            "parent_segment_idx": int(parent_segment_idx),
            "parent_segment_identity": f"segment_{int(parent_segment_idx)}",
            "parent_segment_manifest_sha256": str(parent_contract["manifest_sha256"]),
            "parent_status": "MISSED_FREEZE",
            "parent_match_indices": parent_ids,
            "child_identity": child_identity,
            "recovery_ordinal": 1,
            "status": status,
            "recovery_published_at_hkt": _iso(now),
            "included": included,
            "included_match_count": len(included),
            "excluded": excluded,
            "excluded_match_count": len(excluded),
            "recovery_freeze_at": (
                _iso(segment.freeze_at) if published and segment else ""
            ),
            "hard_stop_at_hkt": _iso(hard_stop) if hard_stop is not None else "",
            "selection_inputs": [
                "matches.issue",
                "matches.match_idx",
                "matches.end_time",
            ],
            "market_or_model_inputs_used": False,
            "immutable": True,
        }
        manifest["schedule_input_sha256"] = schedule_input_sha256(manifest)
        manifest["manifest_sha256"] = manifest_sha256(manifest)
        verify_manifest(manifest)
        destination = issue_root / str(manifest["manifest_sha256"])
        if destination.exists():
            receipt = verify_directory(destination)
        else:
            stage = Path(tempfile.mkdtemp(prefix=".publish-", dir=issue_root))
            (stage / "recovery_manifest.json").write_bytes(canonical(manifest) + b"\n")
            (stage / "SHA256SUMS").write_text(
                f"{_file_hash(stage / 'recovery_manifest.json')}  recovery_manifest.json\n",
                encoding="utf-8",
            )
            _fsync_file(stage / "recovery_manifest.json")
            _fsync_file(stage / "SHA256SUMS")
            _fsync_directory(stage)
            receipt = verify_directory(stage)

        conn.execute("BEGIN IMMEDIATE")
        transaction_open = True
        conn.execute(PUBLICATION_TABLE_SQL)
        conn.execute(WINDOW_TABLE_SQL)
        if conn.execute(
            f"SELECT 1 FROM {PUBLICATION_TABLE} WHERE issue=? AND parent_segment_idx=?",
            (str(issue), int(parent_segment_idx)),
        ).fetchone():
            raise SegmentRecoveryError("concurrent recovery publication")
        if (
            observed_at is None
            and published
            and datetime.now(timezone.utc).astimezone(HKT)
            >= _hkt(str(manifest["recovery_freeze_at"]))
        ):
            raise SegmentRecoveryError(
                "MISSED_RECOVERY_FREEZE: atomic visibility missed child freeze"
            )
        if stage is not None:
            os.replace(stage, destination)
            stage = None
            destination_created = True
            _fsync_directory(issue_root)
        visible_receipt = verify_directory(destination)
        if visible_receipt != receipt:
            raise SegmentRecoveryError(
                "visible recovery verification differs from stage"
            )
        manifest_path = destination / "recovery_manifest.json"
        conn.execute(
            f"""
            INSERT INTO {PUBLICATION_TABLE}(
                issue,parent_segment_idx,child_identity,state,
                parent_manifest_sha256,recovery_manifest_sha256,
                manifest_json,manifest_path,recovery_published_at_hkt
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            (
                str(issue),
                int(parent_segment_idx),
                child_identity,
                status,
                str(parent_contract["manifest_sha256"]),
                str(manifest["manifest_sha256"]),
                canonical(manifest).decode("utf-8"),
                str(manifest_path),
                str(manifest["recovery_published_at_hkt"]),
            ),
        )
        if published:
            conn.execute(
                f"""
                INSERT INTO {WINDOW_TABLE}(
                    issue,parent_segment_idx,child_identity,segment_start,
                    segment_end,freeze_at,match_indices_json,created_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    str(issue),
                    int(parent_segment_idx),
                    child_identity,
                    str(included[0]["kickoff_at_hkt"]),
                    str(included[-1]["kickoff_at_hkt"]),
                    str(manifest["recovery_freeze_at"]),
                    json.dumps(
                        [int(item["match_idx"]) for item in included],
                        separators=(",", ":"),
                    ),
                    str(manifest["recovery_published_at_hkt"]),
                ),
            )
        verify_operational_window(conn, manifest)
        conn.execute("COMMIT")
        transaction_open = False
        _atomic_json(
            attempt_path,
            {
                **attempt_payload,
                "state": status,
                "manifest_sha256": str(manifest["manifest_sha256"]),
                "manifest_path": str(manifest_path),
                "verification": visible_receipt,
            },
        )
        return {
            "status": status,
            "idempotent": False,
            "child_identity": child_identity,
            "manifest": str(manifest_path),
            "sha256": str(manifest["manifest_sha256"]),
            "included_match_count": len(included),
            "excluded_match_count": len(excluded),
            "freeze_at": str(manifest["recovery_freeze_at"]),
            "verification": visible_receipt,
        }
    except BaseException as exc:
        if transaction_open:
            conn.execute("ROLLBACK")
        if destination_created:
            shutil.rmtree(destination, ignore_errors=True)
            _fsync_directory(issue_root)
        if attempt_reserved:
            _atomic_json(
                attempt_path,
                {
                    **attempt_payload,
                    "state": "MISSED_RECOVERY_FREEZE",
                    "error": f"{type(exc).__name__}: {exc}",
                },
            )
        raise
    finally:
        if stage is not None:
            shutil.rmtree(stage, ignore_errors=True)
        conn.close()
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", required=True)
    parser.add_argument("--parent-segment", type=int, required=True)
    parser.add_argument(
        "--db", type=Path, default=ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--exact-ledger-root", type=Path, default=DEFAULT_EXACT_LEDGER)
    parser.add_argument("--hard-stop-hkt")
    args = parser.parse_args()
    try:
        result = publish(
            issue=str(args.issue),
            parent_segment_idx=int(args.parent_segment),
            db_path=args.db,
            output_root=args.output_root,
            exact_ledger_root=args.exact_ledger_root,
            hard_stop_at=(
                _hkt(str(args.hard_stop_hkt)) if args.hard_stop_hkt else None
            ),
        )
    except (
        NaturalDayManifestError,
        SegmentRecoveryError,
        sqlite3.Error,
        OSError,
        ValueError,
    ) as exc:
        raise SystemExit(f"fail closed: {exc}") from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
