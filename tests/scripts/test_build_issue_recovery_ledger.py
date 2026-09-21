"""Ledger-builder contracts: bind evidence by hash, derive the gap from the release."""
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

from scripts import apply_issue_recovery, build_issue_recovery_ledger  # noqa: E402
from scripts.build_issue_recovery_ledger import build_ledger  # noqa: E402
from src.nowscore_settlement import ARCHIVE_SLUGS, TITLE  # noqa: E402

PLAY_LABELS = {5: ("胜", "2.10"), 6: ("3", "5.50"), 7: ("上单", "3.30"),
               8: ("2:1", "8.00"), 9: ("胜-胜", "4.20")}


def write_archive(directory: Path, issue: str, typeid: int, fixtures) -> None:
    title = "单场进球数" if typeid == 6 else TITLE[typeid]
    rows = "".join(
        f'<tr id="row_{slot}"><td>{slot}</td><td>测试赛事</td><td>09-29 22:00</td>'
        f'<td>主{slot}队 (<b>+0</b>)</td><td>{score}</td><td>客{slot}队</td>'
        f'<td>{halftime}</td><td><span class="spitems">{label}</span></td>'
        f'<td title="开奖SP"><a href="/sp/danchang/{issue}_{slot}_{typeid}.html">'
        f'<u>{sp}</u></a></td><td>8.65</td><td>4.67</td><td>1.28</td><td>平手</td>'
        f'<td><a href="//live.nowscore.com/analysis/{1000 + slot}cn.html">析</a></td></tr>'
        for slot, score, halftime, label, sp in fixtures)
    header = "".join(f"<td>{h}</td>" for h in
                     ["场次", "赛事", "开赛时间", "主队(让球)" if typeid == 5 else "主队",
                      "比分", "客队", "半场", "彩果", "开奖SP"]) \
        + '<td colspan="3">平均欧*</td><td>Crow*</td><td>数据</td>'
    (directory / f"nowscore-archive-{typeid}-{issue}.html").write_bytes(
        (f'<title>{title}开奖信息</title><ul id="mymenu"><li class="myons">'
         f'<a href="/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_{issue}.html">'
         f'{title}</a></li></ul><table><tr class="ttis">{header}</tr>{rows}</table>').encode())


def evidence_dir(tmp: Path, issue: str, settled=(1,), cancelled=()) -> Path:
    directory = tmp / "raw"
    directory.mkdir(exist_ok=True)
    for typeid, (label, sp) in PLAY_LABELS.items():
        fixtures = [(slot, "2-1", "1-0", label, sp) for slot in settled]
        fixtures += [(slot, "取消", "-", "", "") for slot in cancelled]
        write_archive(directory, issue, typeid, fixtures)
    return directory


def database(tmp: Path, issue: str, unsettled=(1,), cancelled=()) -> Path:
    """A release shaped like the sealed one, so the applier can run against it too."""
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
        oid = 0
        for slot in unsettled + cancelled:
            oid += 1
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, issue, slot, "spf", str(1000 + slot), "22:25", "-", "-", None,
                         "a" * 64, "", "", json.dumps({"handicap": 0})))
            con.execute("INSERT INTO option_sp VALUES (?,?,?,?,?)", (oid, "胜", "3.28", 3.28, "c1"))
        con.commit()
    finally:
        con.close()
    return path


def test_binds_each_archive_page_and_derives_the_gap_from_the_release(tmp_path: Path) -> None:
    raw = evidence_dir(tmp_path, "23075", settled=(1, 2))
    db = database(tmp_path, "23075", unsettled=(1, 2))
    ledger = build_ledger(db, raw, [("23075", 2)], [], "owner approved")

    assert ledger["schema"] == "bj479_issue_recovery_ledger_v1"
    assert ledger["authorization"] == "owner approved"
    entry = ledger["additions"][0]
    assert entry["issue"] == "23075" and entry["expected_fixtures"] == 2
    assert [e["typeid"] for e in entry["evidence"]] == [5, 6, 7, 8, 9]
    first = entry["evidence"][0]
    assert first["sha256"] == hashlib.sha256(
        (raw / "nowscore-archive-5-23075.html").read_bytes()).hexdigest()
    assert first["url"] == ("https://cp.nowscore.com/beijingdanchang/"
                            f"{ARCHIVE_SLUGS[5]}/kaijiang_dc_5_23075.html")
    assert first["byte_count"] == (raw / "nowscore-archive-5-23075.html").stat().st_size
    assert first["received_at"].endswith("+00:00")


def test_gap_fill_records_only_slots_the_archive_can_settle(tmp_path: Path) -> None:
    raw = evidence_dir(tmp_path, "26092", settled=(362,), cancelled=(190,))
    db = database(tmp_path, "26092", unsettled=(362,), cancelled=(190,))
    ledger = build_ledger(db, raw, [], [("26092", 2)], "owner approved")

    entry = ledger["gap_fills"][0]
    assert ledger["additions"] == []
    assert entry["expected_gap_slots"] == [362] and entry["expected_gap_fixtures"] == 1


def test_refuses_when_the_evidence_holds_a_different_fixture_count(tmp_path: Path) -> None:
    raw = evidence_dir(tmp_path, "23075", settled=(1, 2))
    db = database(tmp_path, "23075", unsettled=(1, 2))
    with pytest.raises(ValueError, match="evidence holds 2 fixtures, expected 3"):
        build_ledger(db, raw, [("23075", 3)], [], "owner approved")


def test_refuses_when_no_gap_slot_is_settled_by_the_archive(tmp_path: Path) -> None:
    raw = evidence_dir(tmp_path, "26092", settled=(362,))
    db = database(tmp_path, "26092", unsettled=(999,))
    with pytest.raises(ValueError, match="no unsettled slot that the archive settles"):
        build_ledger(db, raw, [], [("26092", 1)], "owner approved")


@pytest.mark.parametrize("additions,gap_fills,authorization,message", [
    ([], [], "owner approved", "Nothing to recover"),
    ([("23075", 1)], [("23075", 1)], "owner approved", "both added and gap-filled"),
    ([("23075", 1)], [], "  ", "Explicit authorization required"),
])
def test_refuses_malformed_requests(tmp_path: Path, additions, gap_fills, authorization,
                                    message: str) -> None:
    raw = evidence_dir(tmp_path, "23075", settled=(1,))
    db = database(tmp_path, "23075", unsettled=(1,))
    with pytest.raises(ValueError, match=message):
        build_ledger(db, raw, additions, gap_fills, authorization)


def test_ledger_round_trips_through_json(tmp_path: Path) -> None:
    raw = evidence_dir(tmp_path, "23075", settled=(1,))
    db = database(tmp_path, "23075", unsettled=(1,))
    ledger = build_ledger(db, raw, [("23075", 1)], [], "owner approved")
    assert json.loads(json.dumps(ledger))["additions"][0]["expected_fixtures"] == 1


def test_the_ledger_command_writes_a_ledger(tmp_path: Path) -> None:
    """The entry point is thin, but it must produce a ledger the applier accepts."""
    raw = evidence_dir(tmp_path, "23075", settled=(1,))
    db = database(tmp_path, "23075", unsettled=())
    out = tmp_path / "ledger.json"
    code = build_issue_recovery_ledger.main([
        "--data-root", str(tmp_path),
        "--database", str(db), "--evidence-dir", str(raw), "--output", str(out),
        "--authorization", "owner approved", "--addition", "23075:1"])
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["schema"] == "bj479_issue_recovery_ledger_v1"
    assert doc["additions"][0]["issue"] == "23075"
    assert doc["additions"][0]["expected_fixtures"] == 1
    assert len(doc["additions"][0]["evidence"]) == 5
    assert all(e["byte_count"] > 0 for e in doc["additions"][0]["evidence"])


def test_the_apply_command_applies_a_ledger(tmp_path: Path) -> None:
    raw = evidence_dir(tmp_path, "23075", settled=(1,))
    db = database(tmp_path, "23075", unsettled=())
    out = tmp_path / "ledger.json"
    build_issue_recovery_ledger.main([
        "--data-root", str(tmp_path),
        "--database", str(db), "--evidence-dir", str(raw), "--output", str(out),
        "--authorization", "owner approved", "--addition", "23075:1"])
    backup = tmp_path / "backup.sqlite"
    code = apply_issue_recovery.main([
        "--data-root", str(tmp_path),
        "--database", str(db), "--ledger", str(out), "--backup", str(backup),
        "--approval-note", "owner approved"])
    assert code == 0
    assert backup.exists()
