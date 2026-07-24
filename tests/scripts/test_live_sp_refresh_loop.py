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
from src import multimarket_p0 as p0  # noqa: E402


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
    selected = p0.load_prospective_segment_bindings(
        tmp_path / "ledger", activation_utc=activation.astimezone().isoformat(timespec="seconds"), required_events=2,
    )
    assert [(row["issue"], row["segment_idx"], row["ordinal"]) for row in selected] == [("a", 1, 1), ("b", 2, 2)]
    assert "old" not in {row["issue"] for row in selected}

    monkeypatch.setattr(loop, "freeze_segment", lambda _c, issue, index, _root: {"event_id": next(row["event_id"] for row in selected if row["issue"] == issue and row["segment_idx"] == index)})
    second = loop.publish_due_segment_freezes(conn, [], output_root=tmp_path, now=now)
    assert [row["status"] for row in second] == ["complete", "complete"]
    attempts = [p0.json.loads((path / "manifest.json").read_text()) for path in (tmp_path / "ledger/attempts").glob("*/*")]
    assert sorted(row["status"] for row in attempts) == ["complete", "complete", "retry", "retry"]
    assert sum(row["reason"] == "capture missing" for row in attempts) == 2
    conn.close()


def test_manual_freeze_drift_is_recorded_as_retry_not_completion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    conn = _db()
    activation = datetime.fromisoformat("2026-07-24T00:00:00+08:00")
    monkeypatch.setattr(loop, "_prospective_config", lambda: (activation, 2))
    monkeypatch.setattr(loop, "freeze_segment", lambda *_args: (_ for _ in ()).throw(loop.MultimarketP0Error("missing")))
    now = datetime.fromisoformat("2026-07-24T10:00:00+08:00")
    loop.publish_due_segment_freezes(conn, [], output_root=tmp_path, now=now)
    conn.execute("UPDATE segment_decision_windows SET manual_frozen_at='2026-07-24T08:30:00+08:00' WHERE issue='a' AND segment_idx=1")
    monkeypatch.setattr(loop, "freeze_segment", lambda _c, issue, idx, _root: {"event_id": p0.segment_event_id(issue, idx, "2026-07-24T08:30:00+08:00" if issue == "a" else "2026-07-24T09:00:00+08:00")})
    result = loop.publish_due_segment_freezes(conn, [], output_root=tmp_path, now=now)
    assert result[0]["status"] == "retry"
    assert "differs from preregistered" in result[0]["reason"]
    attempts = [p0.json.loads((path / "manifest.json").read_text()) for path in (tmp_path / "ledger/attempts").glob("*/*")]
    assert [row["status"] for row in attempts].count("complete") == 1  # b remains unchanged
    assert any("differs from preregistered" in row["reason"] for row in attempts)
    conn.close()
