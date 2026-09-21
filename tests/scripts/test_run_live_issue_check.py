"""Contract examples for the scheduled live-issue check. No network, no database writes."""
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for path in (str(ROOT), str(ROOT / "tests")):
    if path not in sys.path:
        sys.path.insert(0, path)

from scripts.capture_live_issues import capture_issues  # noqa: E402,F401  (contract owner)
from scripts.run_live_issue_check import run_check  # noqa: E402
import re  # noqa: E402

from test_nowscore_live_issues import board, release_at  # noqa: E402
from test_settlement_issue_addition import live_page  # noqa: E402

NOW = lambda: datetime(2026, 9, 22, tzinfo=timezone.utc)  # noqa: E731


def transport_for(payload, *, issue="26093", status="完场", ft="3-1", ht="1-0",
                  settle=True):
    """Answer the board with `payload` and each play with a real live page.

    The check parses the captured pages to decide what is actionable, so the fixture has to be
    markup the parser accepts, not a placeholder.
    """
    def transport(url, timeout):
        if "issueNum" not in url:
            return {"status": 200, "payload": payload}
        typeid = int(re.search(r"TypeID=(\d+)", url).group(1))
        return {"status": 200, "payload": live_page(issue=issue, typeid=typeid,
                                                    status=status, ft=ft, ht=ht,
                                                    settle=settle)}
    return transport


def backups(tmp: Path, *names: str) -> Path:
    """Real snapshots: retention refuses to touch anything it cannot identify."""
    directory = tmp / "backups" / "release"
    directory.mkdir(parents=True)
    for index, name in enumerate(names):
        path = directory / name
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE observation (observation_id TEXT)")
        connection.commit()
        connection.close()
        os.utime(path, (1_700_000_000 + index * 60, 1_700_000_000 + index * 60))
    return directory


def test_captures_pending_issues_and_asks_for_approval(tmp_path: Path) -> None:
    """A pending update is captured and flagged, never applied."""
    db = release_at(tmp_path)
    result = run_check(db, tmp_path / "updates", backups(tmp_path, "a.sqlite"),
                       keep=1, timeout_seconds=5, interval_seconds=2,
                       transport=transport_for(board(current="26093",
                                                     issues=("26093", "26092"))),
                       now=NOW)
    assert result["status"] == "captured"
    assert result["needs_approval"] is True
    assert result["eligible"] == ["26093"]
    assert result["pending"] == ["26093"]
    bundle = Path(result["bundle"])
    assert (bundle / "manifest.json").exists()
    assert (bundle / "board.receipt.json").exists()
    # the release is not touched
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM observation WHERE issue='26093'").fetchone()[0] == 0
    con.close()


def test_a_round_still_in_progress_is_not_reported_as_actionable(tmp_path: Path) -> None:
    """Pending but unaddable must not ask for approval: the reasons are recorded instead."""
    db = release_at(tmp_path)
    result = run_check(db, tmp_path / "updates", None, keep=1, timeout_seconds=5,
                       interval_seconds=2,
                       transport=transport_for(board(current="26093",
                                                     issues=("26093", "26092")),
                                               status="未开赛", ft="", ht="",
                                               settle=False),
                       now=NOW)
    assert result["status"] == "captured"
    assert result["eligible"] == []
    assert result["needs_approval"] is False
    assert result["ineligible"][0]["issue"] == "26093"
    assert result["ineligible"][0]["problems"]


def test_reports_up_to_date_without_asking_for_approval(tmp_path: Path) -> None:
    """Nothing pending means nothing to approve."""
    db = release_at(tmp_path, ("26096", "26095", "26092"))
    result = run_check(db, tmp_path / "updates", None, keep=1, timeout_seconds=5,
                       interval_seconds=2, transport=transport_for(board()), now=NOW)
    assert result["status"] == "up_to_date"
    assert result["needs_approval"] is False


def test_records_a_failure_instead_of_raising(tmp_path: Path) -> None:
    """A source outage must not put the timer into a failed state."""
    db = release_at(tmp_path)
    result = run_check(db, tmp_path / "updates", None, keep=1, timeout_seconds=5,
                       interval_seconds=2,
                       transport=lambda url, timeout: {"status": 503, "payload": b""},
                       now=NOW)
    assert result["status"] == "failed"
    assert "503" in result["error"]
    assert result["needs_approval"] is False


def test_a_same_day_rerun_keeps_the_outstanding_approval(tmp_path: Path) -> None:
    """The verdict comes from the bundle already on disk, so it cannot silently clear."""
    db = release_at(tmp_path)
    updates = tmp_path / "updates"
    first = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                      transport=transport_for(board(current="26093",
                                                    issues=("26093", "26092"))), now=NOW)
    assert first["needs_approval"] is True
    second = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                       transport=transport_for(board()), now=NOW)
    assert second["status"] == "already_captured_today"
    assert second["needs_approval"] is True
    assert second["eligible"] == ["26093"]
    assert second["bindings"]["manifest_sha256"] == first["bindings"]["manifest_sha256"]


def test_a_malformed_manifest_still_leaves_a_status_file(tmp_path: Path) -> None:
    """Judging a broken bundle must not raise before the state is recorded."""
    db = release_at(tmp_path)
    updates = tmp_path / "updates"
    first = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                      transport=transport_for(board(current="26093",
                                                    issues=("26093", "26092"))), now=NOW)
    (Path(first["bundle"]) / "manifest.json").write_text("[]", encoding="utf-8")
    result = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                       transport=transport_for(board()), now=NOW)
    assert result["status"] == "failed"
    assert json.loads(Path(result["status_file"]).read_text(encoding="utf-8"))["status"] == "failed"


def test_an_applied_bundle_is_not_asked_for_approval_again(tmp_path: Path) -> None:
    """Once the operator applies it, the same-day check must stop requesting approval."""
    db = release_at(tmp_path)
    updates = tmp_path / "updates"
    first = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                      transport=transport_for(board(current="26093",
                                                    issues=("26093", "26092"))), now=NOW)
    assert first["needs_approval"] is True
    connection = sqlite3.connect(db)
    # Copy a real row rather than guessing the observation schema, and change only the issue.
    columns = [row[1] for row in connection.execute("PRAGMA table_info(observation)")]
    values = list(connection.execute("SELECT * FROM observation LIMIT 1").fetchone())
    values[columns.index("issue")] = "26093"
    values[columns.index("observation_id")] = connection.execute(
        "SELECT MAX(observation_id)+1 FROM observation").fetchone()[0]
    connection.execute(f"INSERT INTO observation VALUES ({','.join('?' * len(columns))})",
                       values)
    connection.commit()
    connection.close()
    second = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                       transport=transport_for(board()), now=NOW)
    assert second["eligible"] == []
    assert second["needs_approval"] is False


def test_does_not_overwrite_the_same_days_bundle(tmp_path: Path) -> None:
    """A second run on the same day keeps the first run's capture bytes."""
    db = release_at(tmp_path)
    updates = tmp_path / "updates"
    first = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                      transport=transport_for(board(current="26093",
                                                    issues=("26093", "26092"))), now=NOW)
    marker = Path(first["bundle"]) / "manifest.json"
    marker.write_text('{"kept": true}', encoding="utf-8")
    second = run_check(db, updates, None, keep=1, timeout_seconds=5, interval_seconds=2,
                       transport=transport_for(board()), now=NOW)
    assert json.loads(marker.read_text(encoding="utf-8"))["kept"] is True
    # A bundle that cannot be read is a recorded failure, not a silent skip.
    assert second["status"] == "failed"
    assert second["unjudged_bundle"] == first["bundle"]
    assert Path(second["status_file"]).exists()


def test_prunes_backups_as_part_of_the_run(tmp_path: Path) -> None:
    """Retention rides along with the scheduled check."""
    db = release_at(tmp_path, ("26096", "26095", "26092"))
    directory = backups(tmp_path, "a.sqlite", "b.sqlite", "c.sqlite")
    result = run_check(db, tmp_path / "updates", directory, keep=1, timeout_seconds=5,
                       interval_seconds=2, transport=transport_for(board()), now=NOW)
    assert result["pruned"]["keep"] == ["c.sqlite"]
    assert [path.name for path in directory.iterdir()] == ["c.sqlite"]


def test_records_a_refused_prune_instead_of_raising(tmp_path: Path) -> None:
    """A retention refusal is a state to report, not a reason to lose the status file."""
    db = release_at(tmp_path, ("26096", "26095", "26092"))
    directory = tmp_path / "backups" / "release"
    directory.mkdir(parents=True)
    (directory / "unknown.sqlite").write_bytes(b"not a database")
    result = run_check(db, tmp_path / "updates", directory, keep=1, timeout_seconds=5,
                       interval_seconds=2, transport=transport_for(board()), now=NOW)
    assert result["pruned"]["status"] == "refused"
    assert (directory / "unknown.sqlite").exists()
    assert Path(result["status_file"]).exists()


def test_status_binds_the_inputs_and_the_rules(tmp_path: Path) -> None:
    """A stored verdict must name the bundle, the release and the implementation behind it."""
    db = release_at(tmp_path)
    result = run_check(db, tmp_path / "updates", None, keep=1, timeout_seconds=5,
                       interval_seconds=2,
                       transport=transport_for(board(current="26093",
                                                     issues=("26093", "26092"))), now=NOW)
    bindings = result["bindings"]
    assert result["status"] == "captured"
    assert bindings["release"]["path"] == str(db)
    assert bindings["release"]["sha256"]
    assert bindings["manifest_sha256"]
    assert "src/settlement_issue_addition.py" in " ".join(bindings["implementation"])
    assert bindings["parameters"]["keep_backups"] == 1


def test_writes_a_status_file_even_when_nothing_is_pending(tmp_path: Path) -> None:
    """The state is the record, so the operator can see the cadence."""
    db = release_at(tmp_path, ("26096", "26095", "26092"))
    result = run_check(db, tmp_path / "updates", None, keep=1, timeout_seconds=5,
                       interval_seconds=2, transport=transport_for(board()), now=NOW)
    status = json.loads(Path(result["status_file"]).read_text(encoding="utf-8"))
    assert status["status"] == "up_to_date"
    assert status["checked_at"].startswith("2026-09-22")
