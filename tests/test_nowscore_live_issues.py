"""Contract examples for reading the live board's own issue list. No network.

The board page is the only thing that decides which issues are pending, so these examples pin
its markup: the advertised list in `dropIssueNum`, the current issue in `var IssueNum`, and one
row per fixture carrying its own date beside its kickoff.
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.nowscore_live_issues import (
    LiveIssueError,
    last_kickoff,
    live_issues,
    pending_issues,
)
from scripts.capture_live_issues import capture_issues, release_issues

CST = timezone(timedelta(hours=8))


def board(*, current: str = "26096", issues=("26096", "26095", "26092"),
          fixtures=(("2026-09-21", "19:30"), ("2026-09-21", "23:30")),
          is_current: str = "True") -> bytes:
    """One live-board page carrying exactly what the parser depends on."""
    options = "".join(f"<option value='{issue}'>{issue}</option>" for issue in issues)
    rows = "".join(f"<tr name='{day}'><td>联赛</td><td>{clock}</td></tr>"
                   for day, clock in fixtures)
    return (f"<html><script>var IssueNum = \"{current}\"; "
            f"var IsCurrentIssue = \"{is_current}\";</script>"
            f"<select name='dropIssueNum' id='dropIssueNum'>{options}</select>"
            f"<table>{rows}</table></html>").encode()


def release_at(tmp: Path, issues=("26092",), name: str = "release.sqlite") -> Path:
    """A release whose carried issues the caller reads rather than supplies."""
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


def test_selects_the_advertised_issues_the_release_lacks() -> None:
    """Membership decides what is pending, oldest first."""
    assert pending_issues(["26096", "26095", "26092"], {"26092"}) == ["26095", "26096"]
    assert pending_issues(["26092"], {"26092"}) == []


def test_keeps_an_issue_a_later_one_overtook() -> None:
    """A refused issue must not be lost just because a newer one settles.

    Reading only the release's newest issue as a watermark would drop 26095 here, because
    26094 is carried; the board still advertises it, so it stays pending.
    """
    assert pending_issues(["26096", "26095", "26094"], {"26092", "26094"}) == ["26095", "26096"]


def test_refuses_when_the_gap_is_wider_than_the_list() -> None:
    """A release far behind the board must say so instead of reporting nothing."""
    with pytest.raises(LiveIssueError, match="cannot tell how many issues are missing"):
        pending_issues(["26096", "26095"], {"20011"})


def test_refuses_a_board_that_advertised_nothing() -> None:
    """No advertised issues is a broken read, not an up-to-date release."""
    with pytest.raises(LiveIssueError, match="advertised no issues"):
        pending_issues([], {"26092"})


def test_estimates_the_next_check_from_the_latest_fixture() -> None:
    """The latest paired (date, kickoff) wins, and the answer carries the source's zone."""
    assert last_kickoff(board()) == datetime(2026, 9, 21, 23, 31, tzinfo=CST)


def test_uses_each_fixtures_own_date_for_a_multi_day_round() -> None:
    """A round spanning days must not pair one row's date with another row's clock time."""
    payload = board(fixtures=(("2026-06-16", "23:46"), ("2026-06-22", "22:01")))
    assert last_kickoff(payload) == datetime(2026, 6, 22, 22, 2, tzinfo=CST)


def test_returns_no_estimate_without_a_paired_date_and_time() -> None:
    """Without both, the caller falls back to polling rather than guessing."""
    assert last_kickoff(b"<html><select id='dropIssueNum'></select></html>") is None
    assert last_kickoff(b"<html><tr name='2026-09-21'><td>x</td></tr></html>") is None


def test_release_membership_is_read_not_supplied(tmp_path: Path) -> None:
    """What the release carries is read from the release, never supplied by the caller."""
    assert release_issues(release_at(tmp_path, ("26092", "26096"), "a.sqlite")) == {
        "26092", "26096"}
    assert release_issues(release_at(tmp_path, name="b.sqlite")) == {"26092"}


def test_captures_only_the_pending_issues(tmp_path: Path) -> None:
    """One board request plus five pages per pending issue, and a replayable bundle."""
    db = release_at(tmp_path)
    calls = []

    def transport(url, timeout):
        calls.append(url)
        if "issueNum" not in url:
            return {"status": 200, "payload": board(current="26093",
                                                    issues=("26093", "26092"))}
        return {"status": 200, "payload": f"<html>{url}</html>".encode()}

    result = capture_issues(db, tmp_path / "bundle", timeout_seconds=5,
                            interval_seconds=2, transport=transport,
                            now=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc))
    assert result["status"] == "captured"
    assert result["pending"] == ["26093"]
    assert result["pages"] == 5
    assert len(calls) == 1 + 5
    manifest = json.loads((tmp_path / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["requested_issues"] == ["26093"]
    assert manifest["release_carried_at_capture"] == ["26092"]
    assert len(manifest["captures"]) == 5
    assert result["next_check_after"].endswith("+08:00")


def test_preserves_the_board_response_that_authorised_the_decision(tmp_path: Path) -> None:
    """The advertised list and the scheduling reading must replay without another request."""
    db = release_at(tmp_path)
    payload = board(current="26093", issues=("26093", "26092"))
    capture_issues(db, tmp_path / "bundle", timeout_seconds=5, interval_seconds=2,
                   transport=lambda url, timeout: {"status": 200, "payload": payload}
                   if "issueNum" not in url else
                   {"status": 200, "payload": b"<html>page</html>"},
                   now=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc))
    receipt = json.loads((tmp_path / "bundle" / "board.receipt.json").read_text(encoding="utf-8"))
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["advertised"] == ["26093", "26092"]
    assert receipt["pending"] == ["26093"]
    assert receipt["received_at"] == "2026-09-21T00:00:00+00:00"
    assert (tmp_path / "bundle" / "raw" / (receipt["sha256"] + ".html")).read_bytes() == payload


def test_timestamps_each_page_when_it_arrives(tmp_path: Path) -> None:
    """A paced batch takes minutes; provenance must not claim the batch start time."""
    db = release_at(tmp_path)
    ticks = iter(range(1, 20))

    def transport(url, timeout):
        if "issueNum" not in url:
            return {"status": 200, "payload": board(current="26093",
                                                    issues=("26093", "26092"))}
        return {"status": 200, "payload": b"<html>page</html>"}

    capture_issues(db, tmp_path / "bundle", timeout_seconds=5, interval_seconds=2,
                   transport=transport,
                   now=lambda: datetime(2026, 9, 21, tzinfo=timezone.utc)
                   + timedelta(seconds=next(ticks)))
    manifest = json.loads((tmp_path / "bundle" / "manifest.json").read_text(encoding="utf-8"))
    stamps = [entry["received_at"] for entry in manifest["captures"]]
    assert len(set(stamps)) == len(stamps)


def test_reports_up_to_date_but_keeps_the_board_response(tmp_path: Path) -> None:
    """Nothing pending still keeps the response, but writes no manifest the applier would use."""
    db = release_at(tmp_path, ("26096", "26095", "26092"))
    result = capture_issues(db, tmp_path / "bundle", timeout_seconds=5, interval_seconds=2,
                            transport=lambda url, timeout: {"status": 200, "payload": board()})
    assert result["status"] == "up_to_date"
    assert result["current"] == "26096"
    assert (tmp_path / "bundle" / "board.receipt.json").exists()
    assert not (tmp_path / "bundle" / "manifest.json").exists()


def test_a_failed_page_leaves_no_manifest(tmp_path: Path) -> None:
    """A partial capture must not produce a bundle the applier would accept."""
    db = release_at(tmp_path)

    def transport(url, timeout):
        if "issueNum" not in url:
            return {"status": 200, "payload": board(current="26093",
                                                    issues=("26093", "26092"))}
        if "TypeID=8" in url:
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


def test_refuses_to_overwrite_an_existing_capture_directory(tmp_path: Path) -> None:
    """A capture directory is evidence; it is never reused."""
    (tmp_path / "bundle").mkdir()
    with pytest.raises(FileExistsError):
        capture_issues(release_at(tmp_path), tmp_path / "bundle", timeout_seconds=5,
                       interval_seconds=2, transport=lambda url, timeout: {"status": 200})
