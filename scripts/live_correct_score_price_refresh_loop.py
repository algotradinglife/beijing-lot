#!/usr/bin/env python3
"""Publish immutable correct-score price captures around segment freezes."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.live_score_refresh_loop import resolve_issues  # noqa: E402
from scripts.manage_correct_score_price_history import (  # noqa: E402
    CAPTURE_SCHEMA,
    DEFAULT_AUTH_PROFILE,
    DEFAULT_CAPTURE_ROOT,
    DEFAULT_CHROME,
    DEFAULT_DB,
    DEFAULT_REPLAY_ROOT,
    capture,
    replay,
    verify_correct_score_bundle,
)
from src.multimarket_p0 import HKT  # noqa: E402


DEFAULT_INTERVAL_SEC = 60.0
DEFAULT_PREFREEZE_MINUTES = 10.0
DEFAULT_FREEZE_GRACE_MINUTES = 20.0
DEFAULT_RETRY_BACKOFF_MINUTES = 60.0
DEFAULT_LATE_RECOVERY_MINUTES = 120.0
DEFAULT_OBSERVATION_HORIZON_MINUTES = 24 * 60.0
DEFAULT_OBSERVATION_BUCKET_MINUTES = 30.0


def now_hkt() -> datetime:
    return datetime.now(timezone.utc).astimezone(HKT)


def parse_hkt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HKT)
    return parsed.astimezone(HKT)


def load_segments(db: Path, issues: list[str]) -> list[dict[str, Any]]:
    if not issues:
        return []
    placeholders = ",".join("?" for _ in issues)
    connection = sqlite3.connect(f"file:{db.expanduser().resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            f"""
            SELECT issue,segment_idx,freeze_at,match_indices_json
            FROM segment_decision_windows
            WHERE issue IN ({placeholders})
            ORDER BY issue,segment_idx
            """,
            issues,
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "issue": str(row["issue"]),
            "segment_idx": int(row["segment_idx"]),
            "freeze_at_hkt": parse_hkt(str(row["freeze_at"])),
            "match_indices": [int(value) for value in json.loads(row["match_indices_json"])],
        }
        for row in rows
    ]


def retry_blocked_checkpoints(
    output_root: Path,
    *,
    now: datetime,
    backoff_minutes: float,
) -> dict[str, str]:
    if backoff_minutes <= 0:
        return {}
    path = output_root.expanduser().resolve() / "collector_runs.jsonl"
    if not path.is_file():
        return {}
    latest: dict[str, datetime] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            key = str(item.get("checkpoint_id") or "")
            status = str(item.get("status") or "")
            finished = datetime.fromisoformat(str(item.get("finished_at_utc") or ""))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if not key or status == "complete":
            continue
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        previous = latest.get(key)
        if previous is None or finished > previous:
            latest[key] = finished
    now_utc = now.astimezone(timezone.utc)
    backoff = timedelta(minutes=backoff_minutes)
    return {
        key: (finished + backoff).isoformat(timespec="seconds")
        for key, finished in latest.items()
        if now_utc < finished + backoff
    }


def due_checkpoints(
    segment: dict[str, Any],
    *,
    now: datetime,
    prefreeze_minutes: float,
    freeze_grace_minutes: float,
) -> list[tuple[str, str]]:
    freeze_at = segment["freeze_at_hkt"]
    prefreeze_at = freeze_at - timedelta(minutes=prefreeze_minutes)
    grace_end = freeze_at + timedelta(minutes=freeze_grace_minutes)
    if prefreeze_at <= now < freeze_at:
        return [("prefreeze", "prefreeze")]
    if freeze_at <= now <= grace_end:
        return [("freeze", "freeze")]
    if now > grace_end:
        return [("freeze", "late_recovery")]
    return []


def append_run_log(output_root: Path, payload: dict[str, Any]) -> None:
    path = output_root.expanduser().resolve() / "collector_runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def checkpoint_id(issue: str, segment_idx: int, phase: str) -> str:
    return f"{issue}:segment:{segment_idx}:{phase}:correct_score_price_v2"


def correct_score_due_checkpoints(
    segment: dict[str, Any],
    *,
    now: datetime,
    prefreeze_minutes: float,
    freeze_grace_minutes: float,
    observation_horizon_minutes: float,
    observation_bucket_minutes: float,
) -> list[tuple[str, str]]:
    checkpoints: list[tuple[str, str]] = []
    freeze_at = segment["freeze_at_hkt"]
    if (
        observation_horizon_minutes > 0
        and observation_bucket_minutes > 0
        and freeze_at - timedelta(minutes=observation_horizon_minutes) <= now < freeze_at
    ):
        bucket_seconds = int(observation_bucket_minutes * 60)
        bucket = int(now.timestamp()) // bucket_seconds
        checkpoints.append((f"observe_{bucket}", "prefreeze_observation"))
    checkpoints.extend(
        due_checkpoints(
            segment,
            now=now,
            prefreeze_minutes=prefreeze_minutes,
            freeze_grace_minutes=freeze_grace_minutes,
        )
    )
    return checkpoints


def successful_checkpoints(output_root: Path, issue: str) -> set[str]:
    issue_root = output_root.expanduser().resolve() / issue
    found: set[str] = set()
    if not issue_root.is_dir():
        return found
    for manifest_path in issue_root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        checkpoint = str(manifest.get("collector_checkpoint_id") or "")
        if checkpoint and (
            manifest.get("status") == "complete"
            or has_full_forward_observation_coverage(manifest)
        ):
            found.add(checkpoint)
    return found


def capture_bundles(output_root: Path, issue: str) -> list[Path]:
    issue_root = output_root.expanduser().resolve() / issue
    if not issue_root.is_dir():
        return []
    verified: list[Path] = []
    for manifest_path in sorted(issue_root.glob("*/manifest.json")):
        try:
            verification = verify_correct_score_bundle(
                manifest_path.parent, expected_schema=CAPTURE_SCHEMA
            )
        except (OSError, ValueError):
            continue
        manifest = verification["manifest"]
        if manifest.get("provider") != "nowscore" or manifest.get("bookmaker_key") != "crown":
            continue
        verified.append(manifest_path.parent)
    return verified


def has_full_forward_observation_coverage(result: dict[str, Any]) -> bool:
    expected = len(result.get("match_indices") or [])
    if "operational_observation_complete" in result:
        return (
            expected > 0
            and result.get("operational_observation_complete") is True
            and int(result.get("blocked_pages") or 0) == 0
        )
    return (
        expected > 0
        and int(result.get("snapshot_rows") or 0) == expected
        and int(result.get("price_rows") or 0) >= expected * 25
        and int(result.get("blocked_pages") or 0) == 0
    )


def run_once(arguments: argparse.Namespace, *, current_time=None) -> dict[str, Any]:
    current_time = current_time or now_hkt()
    requested = [part.strip() for raw in arguments.issue for part in raw.split(",") if part.strip()]
    issues = resolve_issues(arguments.db, requested)
    segments = load_segments(arguments.db, issues)
    summary: dict[str, Any] = {
        "checked_at_hkt": current_time.isoformat(timespec="seconds"),
        "issues": issues,
        "segments": len(segments),
        "captured": [],
        "skipped": [],
        "failed": [],
    }
    retry_blocked = retry_blocked_checkpoints(
        arguments.output_root,
        now=current_time,
        backoff_minutes=arguments.retry_backoff_minutes,
    )
    for segment in segments:
        completed = successful_checkpoints(arguments.output_root, segment["issue"])
        for phase, trigger in correct_score_due_checkpoints(
            segment,
            now=current_time,
            prefreeze_minutes=arguments.prefreeze_minutes,
            freeze_grace_minutes=arguments.freeze_grace_minutes,
            observation_horizon_minutes=getattr(
                arguments, "observation_horizon_minutes", DEFAULT_OBSERVATION_HORIZON_MINUTES
            ),
            observation_bucket_minutes=getattr(
                arguments, "observation_bucket_minutes", DEFAULT_OBSERVATION_BUCKET_MINUTES
            ),
        ):
            if current_time > segment["freeze_at_hkt"] + timedelta(minutes=arguments.late_recovery_minutes):
                continue
            key = checkpoint_id(segment["issue"], segment["segment_idx"], phase)
            if key in completed:
                summary["skipped"].append({"checkpoint_id": key, "reason": "already_observed"})
                continue
            if key in retry_blocked:
                summary["skipped"].append(
                    {
                        "checkpoint_id": key,
                        "reason": "retry_backoff",
                        "retry_after_utc": retry_blocked[key],
                    }
                )
                continue
            capture_args = SimpleNamespace(
                issue=segment["issue"],
                segment_idx=[segment["segment_idx"]],
                db=arguments.db,
                output_root=arguments.output_root,
                chrome=arguments.chrome,
                chrome_user_data_dir=arguments.chrome_user_data_dir,
                profile_directory=arguments.profile_directory,
                provider="nowscore",
                bookmaker_key="crown",
                provider_company_id="3",
                match_limit=None,
                page_attempts=arguments.page_attempts,
                page_retry_delay=arguments.page_retry_delay,
                allow_partial=True,
                collector_checkpoint_id=key,
                collector_trigger=trigger,
            )
            started = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            try:
                result = capture(capture_args)
                replay_result = None
                if trigger in {"freeze", "late_recovery"}:
                    bundles = capture_bundles(arguments.output_root, segment["issue"])
                    if bundles:
                        replay_result = replay(
                            SimpleNamespace(
                                issue=segment["issue"],
                                segment_idx=segment["segment_idx"],
                                capture_bundle=bundles,
                                db=arguments.db,
                                output_root=arguments.replay_output_root,
                            )
                        )
                item = {
                    "checkpoint_id": key,
                    "trigger": trigger,
                    "status": result["status"],
                    "output_dir": result["output_dir"],
                    "successful_pages": result["successful_pages"],
                    "blocked_pages": result["blocked_pages"],
                    "failed_or_missing_pages": result["failed_or_missing_pages"],
                    "snapshot_rows": result["snapshot_rows"],
                    "price_rows": result["price_rows"],
                    "observation_status": (
                        "complete_for_strict_replay"
                        if result["status"] == "complete" else
                        "captured_incomplete_outcome_schema"
                        if has_full_forward_observation_coverage(result) else
                        "capture_failed_or_missing"
                    ),
                    "replay_output_dir": replay_result["output_dir"] if replay_result else "",
                    "replay_status": replay_result["status"] if replay_result else "not_due",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                }
                summary[
                    "captured"
                    if result["status"] == "complete" or has_full_forward_observation_coverage(result)
                    else "failed"
                ].append(item)
            except Exception as exc:
                item = {
                    "checkpoint_id": key,
                    "trigger": trigger,
                    "status": "failed",
                    "error": f"{type(exc).__name__}: {exc}",
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                }
                summary["failed"].append(item)
            append_run_log(arguments.output_root, {"started_at_utc": started, **item})
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", default=["current"])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--replay-output-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    parser.add_argument("--chrome-user-data-dir", type=Path, default=DEFAULT_AUTH_PROFILE)
    parser.add_argument("--profile-directory", default="Default")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    parser.add_argument("--prefreeze-minutes", type=float, default=DEFAULT_PREFREEZE_MINUTES)
    parser.add_argument("--freeze-grace-minutes", type=float, default=DEFAULT_FREEZE_GRACE_MINUTES)
    parser.add_argument(
        "--observation-horizon-minutes",
        type=float,
        default=DEFAULT_OBSERVATION_HORIZON_MINUTES,
    )
    parser.add_argument(
        "--observation-bucket-minutes",
        type=float,
        default=DEFAULT_OBSERVATION_BUCKET_MINUTES,
    )
    parser.add_argument("--retry-backoff-minutes", type=float, default=DEFAULT_RETRY_BACKOFF_MINUTES)
    parser.add_argument("--late-recovery-minutes", type=float, default=DEFAULT_LATE_RECOVERY_MINUTES)
    parser.add_argument("--page-attempts", type=int, default=3)
    parser.add_argument("--page-retry-delay", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    while True:
        started = time.monotonic()
        try:
            print(json.dumps(run_once(arguments), ensure_ascii=False, sort_keys=True), flush=True)
        except Exception as exc:
            print(f"correct_score_price_refresh error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if arguments.once:
            return 0
        time.sleep(max(5.0, arguments.interval - (time.monotonic() - started)))


if __name__ == "__main__":
    raise SystemExit(main())
