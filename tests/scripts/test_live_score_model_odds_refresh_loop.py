from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import live_score_model_odds_refresh_loop as loop  # noqa: E402
from src.multimarket_p0 import HKT  # noqa: E402


def test_due_checkpoints_respect_prefreeze_and_late_recovery() -> None:
    segment = {"freeze_at_hkt": datetime(2026, 7, 17, 10, 0, tzinfo=HKT)}
    assert loop.due_checkpoints(
        segment,
        now=datetime(2026, 7, 17, 9, 49, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
    ) == []
    assert loop.due_checkpoints(
        segment,
        now=datetime(2026, 7, 17, 9, 55, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
    ) == [("prefreeze", "prefreeze")]
    assert loop.due_checkpoints(
        segment,
        now=datetime(2026, 7, 17, 10, 5, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
    ) == [("freeze", "freeze")]
    assert loop.due_checkpoints(
        segment,
        now=datetime(2026, 7, 17, 10, 30, tzinfo=HKT),
        prefreeze_minutes=10,
        freeze_grace_minutes=20,
    ) == [("freeze", "late_recovery")]


def test_successful_checkpoint_is_idempotent(tmp_path: Path) -> None:
    issue_root = tmp_path / "26075" / "batch"
    issue_root.mkdir(parents=True)
    key = loop.checkpoint_id("26075", 1, "freeze")
    (issue_root / "manifest.json").write_text(
        json.dumps({"collector_checkpoint_id": key, "status": "complete"}),
        encoding="utf-8",
    )
    assert loop.successful_checkpoints(tmp_path, "26075") == {key}


def test_checkpoint_with_declared_exclusions_is_idempotent(tmp_path: Path) -> None:
    issue_root = tmp_path / "26075" / "batch"
    issue_root.mkdir(parents=True)
    key = loop.checkpoint_id("26075", 1, "freeze")
    (issue_root / "manifest.json").write_text(
        json.dumps(
            {
                "collector_checkpoint_id": key,
                "status": "complete_with_exclusions",
                "unavailable_pages": 2,
            }
        ),
        encoding="utf-8",
    )
    assert loop.successful_checkpoints(tmp_path, "26075") == {key}


def test_failed_checkpoint_obeys_retry_backoff(tmp_path: Path) -> None:
    key = loop.checkpoint_id("26075", 1, "freeze")
    (tmp_path / "collector_runs.jsonl").write_text(
        json.dumps(
            {
                "checkpoint_id": key,
                "status": "partial",
                "finished_at_utc": "2026-07-17T02:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert loop.retry_blocked_checkpoints(
        tmp_path,
        now=datetime(2026, 7, 17, 10, 5, tzinfo=HKT),
        backoff_minutes=15,
    ) == {key: "2026-07-17T02:15:00+00:00"}
    assert loop.retry_blocked_checkpoints(
        tmp_path,
        now=datetime(2026, 7, 17, 10, 16, tzinfo=HKT),
        backoff_minutes=15,
    ) == {}


def test_run_once_skips_completed_checkpoint_without_capture(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "db.sqlite"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE source_meta(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE segment_decision_windows(
          issue TEXT,segment_idx INTEGER,freeze_at TEXT,match_indices_json TEXT
        );
        INSERT INTO segment_decision_windows VALUES('26075',1,'2026-07-17 10:00:00','[1,2]');
        """
    )
    connection.commit()
    connection.close()
    output = tmp_path / "captures"
    manifest = output / "26075/batch/manifest.json"
    manifest.parent.mkdir(parents=True)
    key = loop.checkpoint_id("26075", 1, "freeze")
    manifest.write_text(json.dumps({"collector_checkpoint_id": key, "status": "complete"}), encoding="utf-8")
    monkeypatch.setattr(loop, "resolve_issues", lambda *args: ["26075"])
    monkeypatch.setattr(loop, "capture", lambda args: (_ for _ in ()).throw(AssertionError("capture must not run")))
    args = argparse.Namespace(
        db=db,
        issue=["current"],
        output_root=output,
        prefreeze_minutes=10.0,
        freeze_grace_minutes=20.0,
        bookmaker_key="william_hill",
        euro_company_id=115,
        over_under_company_id=9,
        workers=1,
        timeout=1,
        retries=0,
    )
    result = loop.run_once(args, current_time=datetime(2026, 7, 17, 10, 5, tzinfo=HKT))
    assert result["captured"] == []
    assert result["skipped"] == [{"checkpoint_id": key, "reason": "already_complete"}]


def test_record_source_meta_closes_connection(monkeypatch, tmp_path: Path) -> None:
    class FakeConnection:
        committed = False
        closed = False

        def execute(self, *_args):
            return self

        def executemany(self, *_args):
            return self

        def commit(self):
            self.committed = True

        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(loop, "connect_sqlite", lambda _path: connection)

    loop.record_source_meta(tmp_path / "live.sqlite", {"key": "value"})

    assert connection.committed is True
    assert connection.closed is True
