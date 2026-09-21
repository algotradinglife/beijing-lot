"""Replay contracts: reproduce every recovered value, or refuse to claim verification."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_settlement_issue_recovery import build_report, main  # noqa: E402
from src.nowscore_settlement import ARCHIVE_SLUGS, TITLE  # noqa: E402
from src.settlement_issue_recovery import recover_issues  # noqa: E402

LABELS = {5: ("胜", "2.10"), 6: ("3", "5.50"), 7: ("上+单", "3.30"),
          8: ("2:1", "8.00"), 9: ("胜-胜", "4.20")}
ADDED = "23075"


def _page(issue: str, typeid: int, fixtures, handicap: str = "+0") -> bytes:
    title = "单场进球数" if typeid == 6 else TITLE[typeid]
    rows = "".join(
        f'<tr id="row_{slot}"><td>{slot}</td><td>测试赛事</td><td>09-29 22:00</td>'
        f'<td>主{slot}队' + (f' (<b>{handicap}</b>)' if handicap else '') +
        f'</td><td>{score}</td><td>客{slot}队</td>'
        f'<td>{halftime}</td><td><span class="spitems">{label}</span></td>'
        f'<td title="开奖SP"><a href="/sp/danchang/{issue}_{slot}_{typeid}.html">'
        f'<u>{sp}</u></a></td><td>8.65</td><td>4.67</td><td>1.28</td><td>平手</td>'
        f'<td><a href="//live.nowscore.com/analysis/{1000 + slot}cn.html">析</a></td></tr>'
        for slot, score, halftime, label, sp in fixtures)
    header = "".join(f"<td>{h}</td>" for h in
                     ["场次", "赛事", "开赛时间", "主队(让球)" if typeid == 5 else "主队",
                      "比分", "客队", "半场", "彩果", "开奖SP"]) \
        + '<td colspan="3">平均欧*</td><td>Crow*</td><td>数据</td>'
    return (f'<title>{title}开奖信息</title><ul id="mymenu"><li class="myons">'
            f'<a href="/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_{issue}.html">'
            f'{title}</a></li></ul><table><tr class="ttis">{header}</tr>{rows}</table>').encode()


def _evidence(tmp: Path, issue: str, typeid: int, fixtures,
              handicap: str = "+0") -> dict:
    payload = _page(issue, typeid, fixtures, handicap)
    path = tmp / f"nowscore-archive-{typeid}-{issue}-{handicap}.html"
    path.write_bytes(payload)
    return {"typeid": typeid, "path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
            "url": f"https://cp.nowscore.com/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/"
                   f"kaijiang_dc_{typeid}_{issue}.html",
            "received_at": "2026-09-21T00:00:00+00:00", "byte_count": len(payload)}


def _database(tmp: Path) -> Path:
    path = tmp / "db.sqlite"
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE capture (issue TEXT, typeid INTEGER, source_url TEXT,
            received_at TEXT, sha256 TEXT, PRIMARY KEY(issue,typeid))""")
        con.execute("""CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT,
            slot INTEGER, play TEXT, native_match_id TEXT, status TEXT, score TEXT,
            halftime_score TEXT, expected_option TEXT, source_sha256 TEXT, source_url TEXT,
            received_at TEXT, payload_json TEXT)""")
        con.execute("""CREATE TABLE option_sp (observation_id INTEGER, option TEXT,
            raw_sp TEXT, sp REAL, cell_id TEXT)""")
        con.execute("""CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT, code TEXT,
            detail TEXT, source_sha256 TEXT)""")
        con.execute("CREATE TABLE receipt (payload_json TEXT)")
        con.execute("INSERT INTO receipt VALUES (?)",
                    (json.dumps({"schema": "nowscore_audit_v1", "data_sha256": "e" * 64}),))
        for typeid in sorted(LABELS):
            con.execute("INSERT INTO capture VALUES (?,?,?,?,?)",
                        (ADDED, typeid, "https://cp.nowscore.com/buy/DanChang.aspx?all=1",
                         "2026-09-06T13:05:51+00:00", "a" * 64))
            con.execute("INSERT INTO capture VALUES (?,?,?,?,?)",
                        ("26092", typeid, "https://cp.nowscore.com/buy/DanChang.aspx?all=1",
                         "2026-09-06T13:05:51+00:00", "a" * 64))
        # The live board published reference odds in the settlement column while unplayed,
        # for every play, so each row carries its play's whole option domain.
        domains = {"spf": ("胜", "平", "负"),
                   "jq": ("0球", "1球", "2球", "3球", "4球", "5球", "6球", "7+球"),
                   "ds": ("上+单", "上+双", "下+单", "下+双"),
                   "bf": ("1:0", "2:1", "1:1", "0:0"),
                   "bq": ("胜-胜", "胜-平", "胜-负", "平-胜", "平-平", "平-负", "负-胜", "负-平",
                          "负-负")}
        oid = 0
        for play, options in domains.items():
            oid += 1
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, "26092", 362, play, "1362", "22:25", "-", "-", None, "a" * 64,
                         "", "", json.dumps({"handicap": 0})))
            for index, option in enumerate(options):
                con.execute("INSERT INTO option_sp VALUES (?,?,?,?,?)",
                            (oid, option, f"{3.0 + index:.2f}", 3.0 + index, f"ref-{option}"))
        con.commit()
    finally:
        con.close()
    return path


def _ledger(tmp: Path, *, issue="26092", handicap="+0") -> Path:
    fixtures = {typeid: [(362, "2-1", "1-0", *LABELS[typeid])] for typeid in sorted(LABELS)}
    gap = {"issue": issue, "expected_fixtures": 1, "expected_gap_fixtures": 1,
           "expected_gap_slots": [362],
           "evidence": [_evidence(tmp, issue, typeid, fixtures[typeid], handicap)
                        for typeid in sorted(LABELS)]}
    addition = {"issue": ADDED, "expected_fixtures": 2,
                "evidence": [_evidence(tmp, ADDED, typeid,
                                       [(1, "2-1", "1-0", *LABELS[typeid]),
                                        (2, "2-1", "1-0", *LABELS[typeid])])
                             for typeid in sorted(LABELS)]}
    path = tmp / "ledger.json"
    path.write_text(json.dumps({"schema": "bj479_issue_recovery_ledger_v1",
                                "authorization": "owner approved",
                                "additions": [addition], "gap_fills": [gap]}), encoding="utf-8")
    return path


def _applied(tmp: Path, *, handicap="+0") -> tuple[Path, Path, Path]:
    db, ledger, backup = (_database(tmp), _ledger(tmp, handicap=handicap),
                          tmp / "backup.sqlite")
    recover_issues(db, ledger, backup, approval_note="owner approved")
    return db, ledger, backup


def test_replay_reproduces_every_recovered_value(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    report = build_report(db, ledger, backup)

    assert report["conclusion"]["verified"] is True
    assert report["replay"] == {"evidence_files_verified": 10, "all_hashes_match": True,
                                "all_values_reproduced": True}
    assert report["additions"][0]["replayed_observations"] == 10
    assert report["gap_fill"]["observations"] == 5 and report["gap_fill"]["replay_agrees"]
    assert report["recorded_evidence_files"] == 10
    assert report["capture_mismatches"] == []
    assert report["backup"]["additions_absent_before"] is True
    assert report["receipt_bound"] is True
    assert report["receipt"]["effective_source"].endswith("_and_archive_recovery")


def test_replay_catches_reference_odds_left_in_the_settlement_column(tmp_path: Path) -> None:
    """The regression that made the first delivery wrong: the live board's reference odds
    must not be readable as the settled SP."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE option_sp SET raw_sp='3.28', sp=3.28, cell_id='ref-胜' WHERE option='胜'")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["gap_fill"]["mismatches"]


def test_replay_catches_a_wrong_settlement_sp(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE option_sp SET sp=9.99 WHERE option='胜'")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False


def test_replay_catches_a_missing_or_extra_added_row(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM observation WHERE issue=? AND slot=2 AND play='spf'", (ADDED,))
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["additions"][0]["mismatch_count"] >= 1


def test_replay_catches_a_replaced_reference_vector(tmp_path: Path) -> None:
    """The replaced reference odds are evidence: rewriting them must fail the replay."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE issue_recovery_gap SET replaced_options_json='[]'")
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_catches_a_payload_only_change(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET payload_json='{\"tampered\": true}' "
                "WHERE issue=? AND slot=1 AND play='spf'", (ADDED,))
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_catches_a_deleted_winning_option(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM option_sp WHERE observation_id=1 AND option='胜'")
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_reproduces_a_gap_completed_with_the_backup_handicap(tmp_path: Path) -> None:
    """When the archive omits the line, replay must take the handicap from the backup."""
    db, ledger, backup = _applied(tmp_path, handicap="")
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is True
    assert report["gap_fill"]["replay_agrees"] is True


def test_replay_catches_a_gap_payload_changed_away_from_the_backup(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET payload_json='{\"handicap\": 2}' WHERE observation_id=1")
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_catches_an_extra_added_observation(tmp_path: Path) -> None:
    """An invented row must fail the count and identity comparison, not just a deletion."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (9999, ADDED, 7, "spf", "1007", "完场", "1-0", "0-0", "胜", "a" * 64, "", "",
                 "{}"))
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["additions"][0]["mismatch_count"] >= 1


def test_replay_catches_a_deleted_completion_with_adjusted_counts(tmp_path: Path) -> None:
    """The owed completions come from the backup and the archive, not from the audit table."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM issue_recovery_gap WHERE slot=362 AND play='spf'")
    con.execute("UPDATE issue_recovery_batch SET gap_observations=134")
    con.execute("UPDATE receipt SET payload_json=json_set(payload_json, "
                "'$.gap_filled_observations', 134)")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["gap_fill"]["mismatches"]


def test_replay_catches_a_moved_observation_key(tmp_path: Path) -> None:
    """The observation must sit at the key the evidence names."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET slot=999 WHERE observation_id=1")
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_catches_a_capture_url_change(tmp_path: Path) -> None:
    """Recorded capture provenance is validated, not merely displayed."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE issue_recovery_capture SET url='https://example.invalid/x' "
                "WHERE issue=? AND typeid=5", (ADDED,))
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["capture_mismatches"]


def test_replay_catches_a_tampered_evidence_manifest(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE issue_recovery_batch SET evidence_manifest_json='[]'")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["evidence_manifest_agrees"] is False


def test_replay_catches_an_invented_losing_option(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO option_sp VALUES (1, 'bogus', NULL, NULL, NULL)")
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_catches_a_dropped_losing_option(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM option_sp WHERE observation_id=1 AND option='负'")
    con.commit()
    con.close()
    assert build_report(db, ledger, backup)["conclusion"]["verified"] is False


def test_replay_catches_a_duplicated_gap_observation(tmp_path: Path) -> None:
    """A second observation at an owed key must not hide behind the first."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("""INSERT INTO observation VALUES
        (999, '26092', 362, 'spf', '1362', '完场', '9-9', '0-0', '胜', 'x', 'x', 'x', '{}')""")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["gap_fill"]["mismatches"]


def test_replay_catches_a_changed_audit_field(tmp_path: Path) -> None:
    """The audit row is validated against evidence, not merely read for its keys."""
    for column, value in (("new_score", "'9-9'"), ("new_expected_option", "'负'"),
                          ("native_match_id", "'9999'"), ("evidence_sha256", "'f' * 64"),
                          ("new_options_json", "'[]'")):
        sub = tmp_path / column
        sub.mkdir()
        db, ledger, backup = _applied(sub)
        con = sqlite3.connect(db)
        con.execute(f"UPDATE issue_recovery_gap SET {column}={value} "
                    "WHERE slot=362 AND play='spf'")
        con.commit()
        con.close()
        assert build_report(db, ledger, backup)["conclusion"]["verified"] is False, column


def test_replay_catches_a_duplicate_audit_key(tmp_path: Path) -> None:
    """The audit table only makes observation_id unique, so multiplicity is checked."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("""INSERT INTO issue_recovery_gap VALUES
        (999, (SELECT batch_id FROM issue_recovery_batch), '26092', 362, 'spf', '1362',
         '-', '9-9', '-', '0-0', NULL, '负', '[]', '[]', 'x', 'x', 'x', 'x')""")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["gap_fill"]["mismatches"]


def test_replay_catches_the_remaining_audit_bindings(tmp_path: Path) -> None:
    for column, value in (("observation_id", "9999"), ("new_halftime_score", "'9-9'"),
                          ("old_payload_sha256", "'f' * 64"), ("old_score", "'9-9'"),
                          ("old_halftime_score", "'9-9'"), ("replaced_options_json", "'[]'")):
        sub = tmp_path / column
        sub.mkdir()
        db, ledger, backup = _applied(sub)
        con = sqlite3.connect(db)
        con.execute(f"UPDATE issue_recovery_gap SET {column}={value} "
                    "WHERE slot=362 AND play='spf'")
        con.commit()
        con.close()
        assert build_report(db, ledger, backup)["conclusion"]["verified"] is False, column


def test_replay_refuses_tampered_evidence(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    item = json.loads(ledger.read_text(encoding="utf-8"))["gap_fills"][0]["evidence"][0]
    Path(item["path"]).write_bytes(b"<html>tampered</html>")
    with pytest.raises(ValueError, match="does not match the ledger"):
        build_report(db, ledger, backup)


def test_replay_reports_a_database_that_lost_a_recovered_value(tmp_path: Path) -> None:
    """A missing completion must fail verification rather than pass on the audit row alone."""
    db, ledger, backup = _applied(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET expected_option=NULL WHERE observation_id=1")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["gap_fill"]["mismatches"]


def test_replay_refuses_a_ledger_that_does_not_match_the_recorded_batch(tmp_path: Path) -> None:
    db, ledger, backup = _applied(tmp_path)
    doc = json.loads(ledger.read_text(encoding="utf-8"))
    doc["authorization"] = "a different note"
    ledger.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match the ledger"):
        build_report(db, ledger, backup)


def test_the_command_fails_when_the_report_does_not_verify(tmp_path: Path) -> None:
    """A rejected recovery must not exit successfully from the acceptance command."""
    db, ledger, backup = _applied(tmp_path)
    out = tmp_path / "report.json"
    assert main(["--database", str(db), "--ledger", str(ledger), "--backup", str(backup),
                 "--out", str(out)]) == 0
    con = sqlite3.connect(db)
    con.execute("UPDATE option_sp SET sp=9.99 WHERE option='胜'")
    con.commit()
    con.close()
    assert main(["--database", str(db), "--ledger", str(ledger), "--backup", str(backup),
                 "--out", str(out)]) == 1
    assert json.loads(out.read_text(encoding="utf-8"))["conclusion"]["verified"] is False
