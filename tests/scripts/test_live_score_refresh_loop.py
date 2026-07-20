from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import live_score_refresh_loop as loop  # noqa: E402


def test_resolve_current_issue_closes_connection(monkeypatch, tmp_path: Path) -> None:
    class FakeConnection:
        closed = False

        def execute(self, _sql: str):
            return self

        def fetchall(self):
            return [("26076",)]

        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(loop, "connect_sqlite", lambda _path: connection)

    assert loop.resolve_issues(tmp_path / "live.sqlite", ["current"]) == ["26076"]
    assert connection.closed is True
