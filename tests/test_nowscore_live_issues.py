"""Contract examples for reading the live board's own issue list. No network."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.nowscore_live_issues import (
    LiveIssueError,
    last_kickoff,
    live_issues,
    next_issue_after,
)
from scripts.capture_live_issues import capture_issues, release_max_issue


def board(*, current: str = "26096", issues=("26096", "26095", "26092"),
          kickoffs=("19:30", "23:30"), date: str = "2026-09-21",
          is_current: str = "True") -> bytes:
    """One live-board page carrying exactly what the parser depends on."""
    options = "".join(f"<option value='{issue}'>{issue}</option>" for issue in issues)
    cells = "".join(f"<td>{time}</td>" for time in kickoffs)
    return (f"<html><script>var IssueNum = \"{current}\"; "
            f"var IsCurrentIssue = \"{is_current}\";</script>"
            f"<select name='dropIssueNum' id='dropIssueNum'>{options}</select>"
            f"<tr name=\"{date}\">{cells}</tr></html>").encode()


def release_at(tmp: Path, issues=("26092",), name: str = "release.sqlite") -> Path:
    """A release whose newest issue the caller reads rather than supplies."""
    path = tmp / name
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE observation (observation_id INTEGER PRIMARY KEY,
                   issue TEXT, slot INTEGER, play TEXT)""")
    for index, issue in enumerate(issues, 1):
        con.execute("INSERT INTO observation VALUES (?,?,?,?)", (index, issue, 1, "spf"))
    con.commit()
    con.close()
    return path


def test_reads_the_boards_own_list() -> None:
    """The board states its issues, so no serial has to be guessed."""
    listing = live_issues(board())
    assert listing["issues"] == ["26096", "26095", "26092"]
    assert listing["current"] == "26096"
    assert listing["is_current"] is True


def test_reports_being_between_rounds() -> None:
    """A board that is not showing a live round must say so, not look empty."""
    assert live_issues(board(is_current="False"))["is_current"] is False


def test_refuses_a_page_without_its_list() -> None:
    """An absent list would otherwise read as 'no new issues'."""
    with pytest.raises(LiveIssueError, match="no issue list"):
        live_issues(b"<html><body>maintenance</body></html>")


def test_selects_only_newer_issues_oldest_first() -> None:
    """The set to add is what the board advertises beyond the release's newest."""
    assert next_issue_after(["26096", "26095", "26092", "26091"], "26092") == ["26095", "26096"]
    assert next_issue_after(["26092"], "26092") == []


def test_refuses_when_the_gap_is_wider_than_the_list() -> None:
    """A release far behind the board must say so instead of reporting nothing."""
    with pytest.raises(LiveIssueError, match="cannot tell how many issues are missing"):
        next_issue_after(["26096", "26095"], "20011")


def test_estimates_the_next_check_from_the_last_kickoff() -> None:
    """The latest kickoff bounds when the next issue can start."""
    assert last_kickoff(board()) == datetime(2026, 9, 21, 23, 31)


def test_returns_no_estimate_without_a_date_or_times() -> None:
    """Without both, the caller falls back to polling rather than guessing."""
    assert last_kickoff(b"<html><select id='dropIssueNum'></select></html>") is None
    assert last_kickoff(b'<html><tr name="2026-09-21"></tr></html>') is None


def test_release_max_issue_comes_from_the_release(tmp_path: Path) -> None:
    """The known maximum is read, never supplied by the caller."""
    assert release_max_issue(release_at(tmp_path, ("26092", "26096"), "a.sqlite")) == "26096"
    assert release_max_issue(release_at(tmp_path, name="b.sqlite")) == "26092"


def test_captures_only_the_new_issues(tmp_path: Path) -> None:
    """One board request plus five pages per new issue, and a bundle the applier accepts."""
    db = release_at(tmp_path)
    calls = []

    def transport(url, timeout):
        calls.append(url)
        if "TypeID=5" in url and "issueNum" not in url:
            return {"status": 200, "payload": board(current="26093",
                                                    issues=("26093", "26092"))}
        return {"status": 200, "payload": f"<html>{url}</html>".encode()}

    result = capture_issues(db, tmp_path / "bundle", timeout_seconds=5,
                            interval_seconds=2, transport=transport,
                            now=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc))
    assert result["status"] == "captured"
    assert result["added"] == ["26093"]
    assert result["pages"] == 5
    assert len(calls) == 1 + 5
    manifest = json.loads((tmp_path / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["requested_issues"] == ["26093"]
    assert manifest["release_max_at_capture"] == "26092"
    assert len(manifest["captures"]) == 5
    assert result["next_check_after"] == "2026-09-21T23:31:00"


def test_reports_up_to_date_without_writing_a_bundle(tmp_path: Path) -> None:
    """Nothing new means no bundle and no error."""
    db = release_at(tmp_path, ("26096",))
    result = capture_issues(db, tmp_path / "bundle", timeout_seconds=5, interval_seconds=2,
                            transport=lambda url, timeout: {"status": 200, "payload": board()})
    assert result["status"] == "up_to_date"
    assert result["current"] == "26096"
    assert not (tmp_path / "bundle").exists()


def test_a_failed_page_leaves_no_manifest(tmp_path: Path) -> None:
    """A partial capture must not produce a bundle the applier would accept."""
    db = release_at(tmp_path)

    def transport(url, timeout):
        if "issueNum" not in url:
            return {"status": 200, "payload": board(current="26093",
                                                    issues=("26093", "26092"))}
        if url.endswith("_8.html") or "TypeID=8" in url:
            return {"status": 503, "payload": b""}
        return {"status": 200, "payload": b"<html>ok</html>"}

    with pytest.raises(ValueError, match="capture failed"):
        capture_issues(db, tmp_path / "bundle", timeout_seconds=5, interval_seconds=2,
                       transport=transport)
    assert not (tmp_path / "bundle" / "manifest.json").exists()


def test_refuses_an_interval_below_the_source_pace(tmp_path: Path) -> None:
    """The source's pacing is a floor, not a preference."""
    with pytest.raises(ValueError, match="at least two seconds"):
        capture_issues(release_at(tmp_path), tmp_path / "bundle", timeout_seconds=5,
                       interval_seconds=1.5, transport=lambda url, timeout: {"status": 200})


def test_refuses_to_overwrite_an_existing_bundle(tmp_path: Path) -> None:
    """A capture directory is evidence; it is never reused."""
    (tmp_path / "bundle").mkdir()
    with pytest.raises(FileExistsError):
        capture_issues(release_at(tmp_path), tmp_path / "bundle", timeout_seconds=5,
                       interval_seconds=2, transport=lambda url, timeout: {"status": 200})
