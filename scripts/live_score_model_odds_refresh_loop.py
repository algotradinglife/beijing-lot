#!/usr/bin/env python3
"""Publish immutable Titan Euro/O/U capture bundles around segment freezes."""

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
from scripts.manage_nowscore_score_model_history import (  # noqa: E402
    DEFAULT_CAPTURE_ROOT,
    DEFAULT_DB,
    capture,
)
from src.multimarket_p0 import HKT  # noqa: E402
from src.nowscore_score_model_history import WILLIAM_HILL  # noqa: E402
from src.sqlite_runtime import connect_sqlite  # noqa: E402


DEFAULT_INTERVAL_SEC = 60.0
DEFAULT_PREFREEZE_MINUTES = 10.0
DEFAULT_FREEZE_GRACE_MINUTES = 20.0
DEFAULT_RETRY_BACKOFF_MINUTES = 15.0
SUCCESS_STATUSES = {"complete", "complete_with_exclusions"}


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


def checkpoint_id(issue: str, segment_idx: int, phase: str) -> str:
    return f"{issue}:segment:{segment_idx}:{phase}:titan_score_model_v1"


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
        value = str(manifest.get("collector_checkpoint_id") or "")
        if value and manifest.get("status") in SUCCESS_STATUSES:
            found.add(value)
    return found


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


def record_source_meta(db: Path, values: dict[str, str]) -> None:
    connection = connect_sqlite(db)
    try:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS source_meta(key TEXT PRIMARY KEY,value TEXT)"
        )
        connection.executemany(
            "INSERT OR REPLACE INTO source_meta(key,value) VALUES(?,?)",
            values.items(),
        )
        connection.commit()
    finally:
        connection.close()


def run_once(arguments: argparse.Namespace, *, current_time: datetime | None = None) -> dict[str, Any]:
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
        backoff_minutes=getattr(arguments, "retry_backoff_minutes", DEFAULT_RETRY_BACKOFF_MINUTES),
    )
    for segment in segments:
        issue = segment["issue"]
        completed = successful_checkpoints(arguments.output_root, issue)
        for phase, trigger in due_checkpoints(
            segment,
            now=current_time,
            prefreeze_minutes=arguments.prefreeze_minutes,
            freeze_grace_minutes=arguments.freeze_grace_minutes,
        ):
            key = checkpoint_id(issue, segment["segment_idx"], phase)
            if key in completed:
                summary["skipped"].append({"checkpoint_id": key, "reason": "already_complete"})
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
                issue=issue,
                segment_idx=[segment["segment_idx"]],
                bookmaker_key=arguments.bookmaker_key,
                euro_company_id=arguments.euro_company_id,
                over_under_company_id=arguments.over_under_company_id,
                db=arguments.db,
                output_root=arguments.output_root,
                workers=arguments.workers,
                timeout=arguments.timeout,
                retries=arguments.retries,
                allow_partial=True,
                collector_checkpoint_id=key,
                collector_trigger=trigger,
            )
            started = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            try:
                result = capture(capture_args)
                item = {
                    "checkpoint_id": key,
                    "trigger": trigger,
                    "status": result["status"],
                    "output_dir": result["output_dir"],
                    "successful_pages": result["successful_pages"],
                    "unavailable_pages": result.get("unavailable_pages", 0),
                    "failed_pages": result["failed_pages"],
                    "finished_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                }
                target = "captured" if result["status"] in SUCCESS_STATUSES else "failed"
                summary[target].append(item)
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
    source_meta = {
        "score_model_odds_last_attempt_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "score_model_odds_last_status": "failed" if summary["failed"] else "ok",
        "score_model_odds_last_summary_json": json.dumps(summary, ensure_ascii=False, sort_keys=True),
    }
    if summary["captured"]:
        source_meta["score_model_odds_last_success_at"] = summary["captured"][-1]["finished_at_utc"]
    record_source_meta(
        arguments.db,
        source_meta,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", default=["current"])
    parser.add_argument("--output-root", type=Path, default=DEFAULT_CAPTURE_ROOT)
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_SEC)
    parser.add_argument("--prefreeze-minutes", type=float, default=DEFAULT_PREFREEZE_MINUTES)
    parser.add_argument("--freeze-grace-minutes", type=float, default=DEFAULT_FREEZE_GRACE_MINUTES)
    parser.add_argument("--retry-backoff-minutes", type=float, default=DEFAULT_RETRY_BACKOFF_MINUTES)
    parser.add_argument("--bookmaker-key", default=WILLIAM_HILL["bookmaker_key"])
    parser.add_argument("--euro-company-id", type=int, default=WILLIAM_HILL["euro_company_id"])
    parser.add_argument("--over-under-company-id", type=int, default=WILLIAM_HILL["over_under_company_id"])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    while True:
        started = time.monotonic()
        try:
            print(json.dumps(run_once(arguments), ensure_ascii=False, sort_keys=True), flush=True)
        except Exception as exc:
            print(f"score_model_odds_refresh error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if arguments.once:
            return 0
        elapsed = time.monotonic() - started
        time.sleep(max(5.0, arguments.interval - elapsed))


if __name__ == "__main__":
    raise SystemExit(main())
