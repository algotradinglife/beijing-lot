from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from scripts import live_sp_refresh_loop as loop  # noqa: E402
from src.multimarket_p0 import HKT  # noqa: E402


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE segment_decision_windows(issue TEXT,segment_idx INTEGER,freeze_at TEXT,manual_frozen_at TEXT)")
    conn.executemany(
        "INSERT INTO segment_decision_windows VALUES(?,?,?,NULL)",
        [
            ("old", 1, "2026-07-23T17:00:00+08:00"),
            ("late", 2, "2026-07-24T12:00:00+08:00"),
            ("b", 2, "2026-07-24T09:00:00+08:00"),
            ("a", 1, "2026-07-24T08:00:00+08:00"),
        ],
    )
    return conn


def test_prospective_selection_is_ordered_persisted_and_append_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    conn = _db()
    activation = datetime.fromisoformat("2026-07-24T00:00:00+08:00")
    monkeypatch.setattr(loop, "_prospective_config", lambda: (activation, 2))
    calls: list[tuple[str, int]] = []

    def fail_once(_conn, issue: str, segment_idx: int, _root: Path):
        calls.append((issue, segment_idx))
        raise loop.MultimarketP0Error("capture missing")

    monkeypatch.setattr(loop, "freeze_segment", fail_once)
    now = datetime.fromisoformat("2026-07-24T10:00:00+08:00")
    first = loop.publish_due_segment_freezes(conn, [], output_root=tmp_path, now=now)
    assert [row["status"] for row in first] == ["retry", "retry"]
    selected = conn.execute("SELECT issue,segment_idx,ordinal FROM multimarket_segment_freeze_events ORDER BY ordinal").fetchall()
    assert [tuple(row) for row in selected] == [("a", 1, 1), ("b", 2, 2)]
    assert "old" not in {row[0] for row in selected}

    monkeypatch.setattr(loop, "freeze_segment", lambda _c, issue, index, _root: {"event_id": conn.execute("SELECT event_id FROM multimarket_segment_freeze_events WHERE issue=? AND segment_idx=?", (issue, index)).fetchone()[0]})
    second = loop.publish_due_segment_freezes(conn, [], output_root=tmp_path, now=now)
    assert [row["status"] for row in second] == ["complete", "complete"]
    attempts = conn.execute("SELECT status,reason FROM multimarket_segment_freeze_attempts ORDER BY attempt_id").fetchall()
    assert [row["status"] for row in attempts] == ["retry", "retry", "complete", "complete"]
    assert all(row["reason"] == "capture missing" for row in attempts[:2])
    assert conn.execute("SELECT COUNT(*) FROM multimarket_segment_freeze_events").fetchone()[0] == 2
    conn.close()
