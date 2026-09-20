from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.settlement_finding_supersession import supersede_findings  # noqa: E402

CODE = "halftime_exceeds_fulltime"
NEW_CODE = "halftime_exceeds_fulltime_superseded"


def _database(tmp_path: Path, *, half_time: str = "2-2", score: str = "2-3",
              code: str = CODE) -> Path:
    path = tmp_path / "settlement.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT,"
                " slot INTEGER, play TEXT, halftime_score TEXT, score TEXT)")
    con.execute("CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT, code TEXT,"
                " detail TEXT, source_sha256 TEXT)")
    con.execute("CREATE TABLE receipt (payload_json TEXT)")
    for index, play in enumerate(("bf", "bq"), start=1):
        con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?)",
                    (index, "21082", 90, play, half_time, score))
        con.execute("INSERT INTO finding VALUES ('21082',90,?,?,'','aa')", (play, code))
    con.execute("INSERT INTO receipt VALUES (?)",
                (json.dumps({"findings_by_code": {CODE: 2, "other": 5}}),))
    con.commit()
    con.close()
    return path


def _ledger(tmp_path: Path, **overrides) -> Path:
    entry = {"code": CODE, "superseded_code": NEW_CODE, "reason": "resolved by correction",
             "expected_rows": 2, "detail": {"resolution": "half time corrected"}}
    entry.update(overrides)
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"schema": "bj479_finding_supersession_ledger_v1",
                                  "supersessions": [entry]}, ensure_ascii=False),
                      encoding="utf-8")
    return ledger


def test_recodes_the_findings_and_keeps_the_originals(tmp_path: Path) -> None:
    db = _database(tmp_path)
    result = supersede_findings(db, _ledger(tmp_path), tmp_path / "backup.sqlite",
                                approval_note="owner approved")
    assert result["status"] == "applied" and result["rows"] == 2
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    assert con.execute(f"SELECT COUNT(*) FROM finding WHERE code='{CODE}'").fetchone()[0] == 0
    assert con.execute(f"SELECT COUNT(*) FROM finding WHERE code='{NEW_CODE}'").fetchone()[0] == 2
    detail = json.loads(con.execute("SELECT detail FROM finding LIMIT 1").fetchone()[0])
    assert detail["superseded_code"] == CODE
    assert detail["resolution"] == "half time corrected"
    audited = con.execute("SELECT old_code, new_code FROM finding_supersession").fetchall()
    assert {tuple(r) for r in audited} == {(CODE, NEW_CODE)}
    receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
    assert receipt["findings_by_code"] == {NEW_CODE: 2, "other": 5}
    assert receipt["finding_supersession_batch_id"]
    con.close()
    assert (tmp_path / "backup.sqlite").is_file()


def test_repeat_run_is_idempotent(tmp_path: Path) -> None:
    db = _database(tmp_path)
    ledger, backup = _ledger(tmp_path), tmp_path / "backup.sqlite"
    supersede_findings(db, ledger, backup, approval_note="owner approved")
    assert supersede_findings(db, ledger, backup,
                              approval_note="owner approved")["status"] == "already_applied"
    assert sqlite3.connect(db).execute(
        "SELECT COUNT(*) FROM finding_supersession").fetchone()[0] == 2


def test_refuses_when_the_subject_still_contradicts(tmp_path: Path) -> None:
    """A finding must not be marked resolved while its observation still asserts it."""
    db = _database(tmp_path, half_time="3-2", score="2-3")
    with pytest.raises(ValueError, match="still contradicts"):
        supersede_findings(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="x")
    con = sqlite3.connect(db)
    assert con.execute(f"SELECT COUNT(*) FROM finding WHERE code='{CODE}'").fetchone()[0] == 2


def test_refuses_when_the_row_count_is_not_what_the_ledger_expects(tmp_path: Path) -> None:
    db = _database(tmp_path)
    with pytest.raises(ValueError, match="ledger expects 5 findings"):
        supersede_findings(db, _ledger(tmp_path, expected_rows=5), tmp_path / "b.sqlite",
                           approval_note="x")


def test_refuses_without_an_approval_note(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="approval note"):
        supersede_findings(_database(tmp_path), _ledger(tmp_path), tmp_path / "b.sqlite",
                           approval_note="")


def test_refuses_a_code_with_no_resolution_predicate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no resolution predicate"):
        supersede_findings(_database(tmp_path, code="mystery_code"),
                           _ledger(tmp_path, code="mystery_code", expected_rows=2),
                           tmp_path / "b.sqlite", approval_note="x")


def test_refuses_identical_paths(tmp_path: Path) -> None:
    db = _database(tmp_path)
    with pytest.raises(ValueError, match="must all differ"):
        supersede_findings(db, _ledger(tmp_path), db, approval_note="x")


def test_refuses_a_ledger_for_the_wrong_schema(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"schema": "nope", "supersessions": [{}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported ledger schema"):
        supersede_findings(_database(tmp_path), ledger, tmp_path / "b.sqlite", approval_note="x")


def test_refuses_when_the_receipt_does_not_agree(tmp_path: Path) -> None:
    db = _database(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE receipt SET payload_json=?",
                (json.dumps({"findings_by_code": {CODE: 9}}),))
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="receipt records 9"):
        supersede_findings(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="x")
