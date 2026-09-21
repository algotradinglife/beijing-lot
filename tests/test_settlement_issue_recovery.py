"""Recovery-layer contracts: archive evidence in, audited rows out, nothing inferred."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.nowscore_settlement import ARCHIVE_SLUGS, TITLE  # noqa: E402
from src.settlement_issue_recovery import recover_issues  # noqa: E402

RECEIPT = {"schema": "nowscore_audit_v1", "source": "nowscore", "production_enabled": False,
           "data_sha256": "e" * 64, "effective_source": "nowscore_with_audited_500_corrections"}

# A settled 2-1 fixture with a 1-0 half-time, labelled the way each play names its winner.
PLAY_LABELS = {5: ("胜", "2.10"), 6: ("3", "5.50"), 7: ("上单", "3.30"),
               8: ("2:1", "8.00"), 9: ("胜-胜", "4.20")}


def archive_page(issue: str, typeid: int, fixtures, handicap: str = "+0") -> bytes:
    """Minimal contract-valid archive page: identity, headers and settled rows."""
    title = "单场进球数" if typeid == 6 else TITLE[typeid]
    handicap_header = "主队(让球)" if typeid == 5 else "主队"
    rows = []
    for slot, score, halftime, label, sp in fixtures:
        home = f"主{slot}队 (<b>{handicap}</b>)" if handicap else f"主{slot}队"
        rows.append(
            f'<tr id="row_{slot}"><td>{slot}</td><td>测试赛事</td><td>09-29 22:00</td>'
            f'<td>{home}</td><td>{score}</td><td>客{slot}队</td>'
            f'<td>{halftime}</td><td><span class="spitems">{label}</span></td>'
            f'<td title="开奖SP"><a href="/sp/danchang/{issue}_{slot}_{typeid}.html">'
            f'<u>{sp}</u></a></td><td>8.65</td><td>4.67</td><td>1.28</td><td>平手</td>'
            f'<td><a href="//live.nowscore.com/analysis/{1000 + slot}cn.html">析</a></td></tr>')
    header = "".join(f"<td>{h}</td>" for h in
                     ["场次", "赛事", "开赛时间", handicap_header, "比分", "客队", "半场",
                      "彩果", "开奖SP"]) + '<td colspan="3">平均欧*</td><td>Crow*</td><td>数据</td>'
    return (f'<title>{title}开奖信息</title><ul id="mymenu"><li class="myons">'
            f'<a href="/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/kaijiang_dc_{typeid}_{issue}.html">'
            f'{title}</a></li></ul><table><tr class="ttis">{header}</tr>'
            + "".join(rows) + '</table>').encode()


def evidence(tmp: Path, issue: str, typeid: int, fixtures, handicap: str = "+0") -> dict:
    payload = archive_page(issue, typeid, fixtures, handicap)
    path = tmp / f"nowscore-archive-{typeid}-{issue}-{handicap}.html"
    path.write_bytes(payload)
    return {"typeid": typeid, "path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
            "url": f"https://cp.nowscore.com/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/"
                   f"kaijiang_dc_{typeid}_{issue}.html",
            "received_at": "2026-09-21T00:00:00+00:00", "byte_count": len(payload)}


def _schema(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE capture (issue TEXT, typeid INTEGER, source_url TEXT,
        received_at TEXT, sha256 TEXT, PRIMARY KEY(issue,typeid))""")
    con.execute("""CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT,
        slot INTEGER, play TEXT, native_match_id TEXT, status TEXT, score TEXT,
        halftime_score TEXT, expected_option TEXT, source_sha256 TEXT, source_url TEXT,
        received_at TEXT, payload_json TEXT)""")
    con.execute("""CREATE TABLE option_sp (observation_id INTEGER, option TEXT, raw_sp TEXT,
        sp REAL, cell_id TEXT)""")
    con.execute("""CREATE TABLE finding (issue TEXT, slot INTEGER, play TEXT, code TEXT,
        detail TEXT, source_sha256 TEXT)""")
    con.execute("CREATE TABLE receipt (payload_json TEXT)")
    con.execute("INSERT INTO receipt VALUES (?)", (json.dumps(RECEIPT),))


def addition_db(tmp: Path, *, slots=(1, 2), held=0) -> Path:
    """A release that holds a quarantined issue's capture rows but no observations."""
    path = tmp / "db.sqlite"
    con = sqlite3.connect(path)
    try:
        _schema(con)
        for typeid in sorted(PLAY_LABELS):
            con.execute("INSERT INTO capture VALUES (?,?,?,?,?)",
                        ("23075", typeid, "https://cp.nowscore.com/buy/DanChang.aspx?all=1",
                         "2026-09-06T13:05:51+00:00", "a" * 64))
        oid = 0
        for _ in range(held):
            oid += 1
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, "23075", 99, "spf", "9999", "完场", "0-0", "0-0", "平", "a" * 64,
                         "", "", "{}"))
        con.commit()
    finally:
        con.close()
    return path


def gap_db(tmp: Path, *, unsettled=((1, "2-1"),), cancelled=(2,), handicap=0) -> Path:
    """A release whose live-board capture left some fixtures unplayed and cancelled others.

    The live board fills the settlement column with pre-match reference odds while a
    fixture is unplayed, so every unsettled row carries a full three-option vector.
    """
    path = tmp / "db.sqlite"
    con = sqlite3.connect(path)
    try:
        _schema(con)
        con.execute("INSERT INTO capture VALUES (?,?,?,?,?)",
                    ("26092", 5, "https://cp.nowscore.com/buy/DanChang.aspx?all=1",
                     "2026-09-06T13:05:51+00:00", "a" * 64))
        oid = 0
        for slot, _ in unsettled:
            oid += 1
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, "26092", slot, "spf", str(1000 + slot), "22:25", "-", "-", None,
                         "a" * 64, "", "", json.dumps({"handicap": handicap})))
            for option, sp in (("胜", 3.28), ("平", 2.49), ("负", 3.40)):
                con.execute("INSERT INTO option_sp VALUES (?,?,?,?,?)",
                            (oid, option, f"{sp:.2f}", sp, f"ref-{option}"))
        for slot in cancelled:
            oid += 1
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, "26092", slot, "spf", str(1000 + slot), "取消", "-", "-", None,
                         "a" * 64, "", "", "{}"))
        con.commit()
    finally:
        con.close()
    return path


def ledger(tmp: Path, doc: dict, name: str = "ledger.json") -> Path:
    path = tmp / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def addition_ledger(tmp: Path, *, issue="23075", expected=2, slots=(1, 2),
                    handicap="+0") -> Path:
    """Evidence per play, each labelled the way that play names a settled 2-1."""
    entry = {"issue": issue, "expected_fixtures": expected,
             "evidence": [evidence(tmp, issue, typeid,
                                   [(slot, "2-1", "1-0", *PLAY_LABELS[typeid]) for slot in slots],
                                   handicap)
                          for typeid in sorted(PLAY_LABELS)]}
    return ledger(tmp, {"schema": "bj479_issue_recovery_ledger_v1", "additions": [entry],
                        "gap_fills": []}, f"ledger-{issue}-{expected}-{handicap}.json")


def gap_ledger(tmp: Path, *, fixtures=None, expected=2, gap_fixtures=1, gap_slots=(1,),
               handicap="+0") -> Path:
    if fixtures is None:
        fixtures = {typeid: [(1, "2-1", "1-0", *PLAY_LABELS[typeid]), (2, "取消", "-", "", "")]
                    for typeid in sorted(PLAY_LABELS)}
    entry = {"issue": "26092", "expected_fixtures": expected,
             "expected_gap_fixtures": gap_fixtures, "expected_gap_slots": list(gap_slots),
             "evidence": [evidence(tmp, "26092", typeid, fixtures[typeid], handicap)
                          for typeid in sorted(PLAY_LABELS)]}
    return ledger(tmp, {"schema": "bj479_issue_recovery_ledger_v1", "additions": [],
                        "gap_fills": [entry]}, f"gap-{expected}-{gap_fixtures}-{handicap}.json")


def rows(db: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_adds_a_quarantined_issue_from_its_archive_evidence(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    result = recover_issues(db, addition_ledger(tmp_path), tmp_path / "backup.sqlite",
                            approval_note="owner approved")

    assert result["status"] == "applied"
    assert result["added_observations"] == 10 and result["added_fixtures"] == 2
    assert (tmp_path / "backup.sqlite").exists()
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='23075'")[0][0] == 10
    assert rows(db, "SELECT COUNT(DISTINCT play) FROM observation WHERE issue='23075'")[0][0] == 5
    assert rows(db, "SELECT DISTINCT expected_option FROM observation WHERE play='bq'") == [("胜-胜",)]
    assert rows(db, "SELECT DISTINCT expected_option FROM observation WHERE play='bf'") == [("2:1",)]
    assert rows(db, "SELECT COUNT(*) FROM option_sp")[0][0] == 10
    assert rows(db, "SELECT DISTINCT sp FROM option_sp WHERE option='胜'") == [(2.10,)]
    # The archive bytes are what now back the issue, and the superseded live fetch is kept.
    assert rows(db, "SELECT source_url, sha256 FROM capture WHERE issue='23075' AND typeid=5") == [
        (f"https://cp.nowscore.com/beijingdanchang/{ARCHIVE_SLUGS[5]}/kaijiang_dc_5_23075.html",
         hashlib.sha256(archive_page("23075", 5, [(1, "2-1", "1-0", *PLAY_LABELS[5]),
                                                   (2, "2-1", "1-0", *PLAY_LABELS[5])])).hexdigest())]
    assert rows(db, "SELECT COUNT(*) FROM issue_recovery_capture WHERE replaced_sha256 IS NOT NULL")[0][0] == 5

    batch = rows(db, "SELECT added_fixtures, added_observations, gap_observations, note, "
                     "ledger_json, evidence_manifest_json, backup_path FROM issue_recovery_batch")[0]
    assert batch[:4] == (2, 10, 0, "owner approved")
    assert json.loads(batch[4])["additions"][0]["issue"] == "23075"
    manifest = json.loads(batch[5])
    assert len(manifest) == 5 and {m["role"] for m in manifest} == {"addition"}
    assert batch[6] == str((tmp_path / "backup.sqlite").resolve())

    receipt = json.loads(rows(db, "SELECT payload_json FROM receipt")[0][0])
    assert receipt["data_sha256"] == "e" * 64, "the original build hash must survive recovery"
    assert receipt["recovered_issues"] == ["23075"] and receipt["recovered_observations"] == 10
    assert receipt["effective_source"].endswith("_and_archive_recovery")


def test_replaces_the_reference_odds_the_live_board_published(tmp_path: Path) -> None:
    """The live board puts pre-match reference odds in the settlement column; the archive
    record is the settlement one, so the whole vector is replaced and the old one kept."""
    db = gap_db(tmp_path)
    recover_issues(db, gap_ledger(tmp_path), tmp_path / "backup.sqlite",
                   approval_note="owner approved")

    assert rows(db, "SELECT score, halftime_score, expected_option FROM observation "
                    "WHERE slot=1")[0] == ("2-1", "1-0", "胜")
    assert rows(db, "SELECT option, raw_sp, sp, cell_id FROM option_sp "
                    "WHERE observation_id=1 ORDER BY rowid") == [
        ("胜", "2.10", 2.10, "archive_result_1"),
        ("平", None, None, None),
        ("负", None, None, None)]
    new_options, replaced = rows(
        db, "SELECT new_options_json, replaced_options_json FROM issue_recovery_gap")[0]
    assert json.loads(new_options) == [{"option": "胜", "raw_sp": "2.10", "sp": 2.10,
                                        "cell_id": "archive_result_1"}]
    assert [o["sp"] for o in json.loads(replaced)] == [3.28, 2.49, 3.40]


def test_completes_unsettled_fixtures_and_leaves_cancelled_ones_alone(tmp_path: Path) -> None:
    db = gap_db(tmp_path)
    result = recover_issues(db, gap_ledger(tmp_path), tmp_path / "backup.sqlite",
                            approval_note="owner approved")

    assert result["status"] == "applied" and result["gap_observations"] == 1
    gap = rows(db, "SELECT old_score, new_score, old_expected_option, new_expected_option "
                   "FROM issue_recovery_gap")[0]
    assert gap == ("-", "2-1", None, "胜")
    # The archive bytes that settled the gap are recorded, but `capture` still points at
    # the live board, which remains the primary source for those rows.
    assert rows(db, "SELECT COUNT(*), SUM(replaced_sha256 IS NULL) "
                    "FROM issue_recovery_capture")[0] == (5, 5)
    assert rows(db, "SELECT COUNT(*) FROM capture WHERE issue='26092'")[0][0] == 1
    # A cancelled fixture legitimately has no result, so it is neither completed nor recorded.
    assert rows(db, "SELECT score FROM observation WHERE slot=2")[0] == ("-",)
    assert rows(db, "SELECT COUNT(*) FROM issue_recovery_gap")[0][0] == 1


def test_uses_the_release_handicap_when_the_archive_leaves_the_line_empty(
        tmp_path: Path) -> None:
    """The archive omits the line for many fixtures; the release's own record supplies it."""
    db = gap_db(tmp_path, handicap=0)
    recover_issues(db, gap_ledger(tmp_path, handicap=""), tmp_path / "backup.sqlite",
                   approval_note="owner approved")
    assert rows(db, "SELECT score, expected_option FROM observation WHERE slot=1")[0] == ("2-1", "胜")


def test_refuses_when_the_derived_result_disagrees_with_the_archive(tmp_path: Path) -> None:
    """A settled row whose score derives a different winner than the archive reports fails."""
    db = gap_db(tmp_path, handicap=-1)  # 2-1 with a -1 line implies 平, not 胜
    with pytest.raises(ValueError, match="archive reports"):
        recover_issues(db, gap_ledger(tmp_path, handicap=""), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT score FROM observation WHERE slot=1")[0] == ("-",)


def test_refuses_a_settled_addition_that_contradicts_its_own_score(tmp_path: Path) -> None:
    """The result cross-check applies to added issues, not only to gap fills."""
    db = addition_db(tmp_path)
    entry = {"issue": "23075", "expected_fixtures": 2,
             "evidence": [evidence(tmp_path, "23075", typeid,
                                   [(1, "2-1", "1-0", "负" if typeid == 5 else PLAY_LABELS[typeid][0],
                                     "2.10"),
                                    (2, "2-1", "1-0", PLAY_LABELS[typeid][0], "2.10")])
                          for typeid in sorted(PLAY_LABELS)]}
    with pytest.raises(ValueError, match="archive reports"):
        recover_issues(db, ledger(tmp_path, {"schema": "bj479_issue_recovery_ledger_v1",
                                             "additions": [entry], "gap_fills": []}, "contra.json"),
                       tmp_path / "b.sqlite", approval_note="owner approved")
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='23075'")[0][0] == 0


def test_refuses_when_the_plays_disagree_on_the_fixtures(tmp_path: Path) -> None:
    """Equal roster sizes with different slots or match ids must not pass."""
    db = addition_db(tmp_path)
    path = addition_ledger(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    # spf holds slots 1 and 2; the other plays hold slots 1 and 3 - same count, other roster.
    for item in doc["additions"][0]["evidence"]:
        if item["typeid"] != 5:
            fixtures = [(1, "2-1", "1-0", *PLAY_LABELS[item["typeid"]]),
                        (3, "2-1", "1-0", *PLAY_LABELS[item["typeid"]])]
            item.update(evidence(tmp_path, "23075", item["typeid"], fixtures))
    with pytest.raises(ValueError, match="disagree on the fixtures"):
        recover_issues(db, ledger(tmp_path, doc, "mixed.json"), tmp_path / "b.sqlite",
                       approval_note="owner approved")


def test_repeating_the_same_ledger_is_a_verified_no_op(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    path = addition_ledger(tmp_path)
    recover_issues(db, path, tmp_path / "backup.sqlite", approval_note="owner approved")
    again = recover_issues(db, path, tmp_path / "other.sqlite", approval_note="owner approved")
    assert again == {"status": "already_applied", "added_observations": 10, "gap_observations": 0}
    assert not (tmp_path / "other.sqlite").exists()


def test_repeating_a_gap_ledger_is_a_verified_no_op(tmp_path: Path) -> None:
    """The gap path keeps the release's own option domain, so its rerun must still pass."""
    db = gap_db(tmp_path)
    path = gap_ledger(tmp_path)
    recover_issues(db, path, tmp_path / "backup.sqlite", approval_note="owner approved")
    again = recover_issues(db, path, tmp_path / "other.sqlite", approval_note="owner approved")
    assert again == {"status": "already_applied", "added_observations": 0, "gap_observations": 1}
    assert not (tmp_path / "other.sqlite").exists()


def test_a_changed_recovered_value_refuses_the_rerun(tmp_path: Path) -> None:
    """Counts alone must not certify a damaged recovery."""
    db = addition_db(tmp_path)
    path = addition_ledger(tmp_path)
    recover_issues(db, path, tmp_path / "backup.sqlite", approval_note="owner approved")
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET score='9-9' WHERE issue='23075' AND slot=1 AND play='spf'")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="recovered values changed"):
        recover_issues(db, path, tmp_path / "other.sqlite", approval_note="owner approved")


def test_a_changed_recovered_option_refuses_the_rerun(tmp_path: Path) -> None:
    db = gap_db(tmp_path)
    path = gap_ledger(tmp_path)
    recover_issues(db, path, tmp_path / "backup.sqlite", approval_note="owner approved")
    con = sqlite3.connect(db)
    con.execute("UPDATE option_sp SET sp=99.9 WHERE option='胜'")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="stored options changed"):
        recover_issues(db, path, tmp_path / "other.sqlite", approval_note="owner approved")


def test_a_failure_during_the_write_rolls_everything_back(tmp_path: Path) -> None:
    """A mid-write failure must leave the release untouched, recovery tables included."""
    db = addition_db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("""CREATE TRIGGER boom BEFORE INSERT ON option_sp
                   WHEN NEW.option='胜' BEGIN SELECT RAISE(ABORT,'boom'); END""")
    con.commit()
    con.close()
    with pytest.raises(sqlite3.IntegrityError, match="boom"):
        recover_issues(db, addition_ledger(tmp_path), tmp_path / "backup.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='23075'")[0][0] == 0
    assert rows(db, "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE name LIKE 'issue_recovery%'")[0][0] == 0
    assert rows(db, "SELECT payload_json FROM receipt")[0][0] == json.dumps(RECEIPT)
    # The backup was taken before the write, so it is kept rather than deleted.
    assert (tmp_path / "backup.sqlite").exists()


def test_refuses_when_evidence_bytes_do_not_match_the_ledger(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    path = addition_ledger(tmp_path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    Path(doc["additions"][0]["evidence"][0]["path"]).write_bytes(b"<html>tampered</html>")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        recover_issues(db, path, tmp_path / "b.sqlite", approval_note="owner approved")
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='23075'")[0][0] == 0


def test_refuses_an_addition_for_an_issue_that_already_holds_rows(tmp_path: Path) -> None:
    db = addition_db(tmp_path, held=1)
    with pytest.raises(ValueError, match="already holds 1 rows"):
        recover_issues(db, addition_ledger(tmp_path), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='23075'")[0][0] == 1


def test_refuses_when_the_archive_fixture_count_differs_from_the_ledger(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    with pytest.raises(ValueError, match="ledger expects 3"):
        recover_issues(db, addition_ledger(tmp_path, expected=3), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT COUNT(*) FROM observation WHERE issue='23075'")[0][0] == 0


def test_refuses_when_the_archive_identifies_a_different_match(tmp_path: Path) -> None:
    """The native match ID is the identity gate, so a shifted archive row cannot fill a slot."""
    db = gap_db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET native_match_id='9999' WHERE slot=1")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="archive identifies match"):
        recover_issues(db, gap_ledger(tmp_path), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT score FROM observation WHERE slot=1")[0] == ("-",)


def test_refuses_an_archive_option_the_release_does_not_carry(tmp_path: Path) -> None:
    """The archive may report only a settled subset, never an option the release lacks."""
    db = gap_db(tmp_path)
    con = sqlite3.connect(db)
    con.execute("DELETE FROM option_sp WHERE option='胜'")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="does not carry"):
        recover_issues(db, gap_ledger(tmp_path), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT score FROM observation WHERE slot=1")[0] == ("-",)


def test_a_refused_run_leaves_no_backup_behind(tmp_path: Path) -> None:
    """A zero-byte reservation would block the retry, so a refused run removes it."""
    db = addition_db(tmp_path, held=1)
    with pytest.raises(ValueError, match="already holds"):
        recover_issues(db, addition_ledger(tmp_path), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert not (tmp_path / "b.sqlite").exists()


def test_refuses_a_gap_fill_whose_slots_differ_from_the_ledger(tmp_path: Path) -> None:
    db = gap_db(tmp_path)
    with pytest.raises(ValueError, match="differ from the ledger"):
        recover_issues(db, gap_ledger(tmp_path, gap_slots=(2,)), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT score FROM observation WHERE slot=1")[0] == ("-",)


def test_refuses_when_the_archive_settles_no_odds(tmp_path: Path) -> None:
    db = gap_db(tmp_path)
    fixtures = {typeid: [(1, "2-1", "1-0", PLAY_LABELS[typeid][0], ""),
                         (2, "取消", "-", "", "")]
                for typeid in sorted(PLAY_LABELS)}
    with pytest.raises(ValueError, match="settles no options"):
        recover_issues(db, gap_ledger(tmp_path, fixtures=fixtures), tmp_path / "b.sqlite",
                       approval_note="owner approved")
    assert rows(db, "SELECT score FROM observation WHERE slot=1")[0] == ("-",)


@pytest.mark.parametrize("doc,message", [
    ({"schema": "bj479_issue_recovery_ledger_v1", "additions": [], "gap_fills": []}, "Empty ledger"),
    ({"schema": "something_else", "additions": [{"issue": "1"}], "gap_fills": []},
     "Wrong ledger schema"),
])
def test_refuses_malformed_ledgers(tmp_path: Path, doc: dict, message: str) -> None:
    db = addition_db(tmp_path)
    with pytest.raises(ValueError, match=message):
        recover_issues(db, ledger(tmp_path, doc, "bad.json"), tmp_path / "b.sqlite",
                       approval_note="owner approved")


def test_refuses_a_ledger_that_repeats_an_issue(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    doc = json.loads(addition_ledger(tmp_path).read_text(encoding="utf-8"))
    doc["gap_fills"] = [dict(doc["additions"][0])]
    with pytest.raises(ValueError, match="repeats an issue"):
        recover_issues(db, ledger(tmp_path, doc, "dup.json"), tmp_path / "b.sqlite",
                       approval_note="owner approved")


def test_refuses_without_an_explicit_approval_note(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    with pytest.raises(ValueError, match="approval note required"):
        recover_issues(db, addition_ledger(tmp_path), tmp_path / "b.sqlite", approval_note="  ")


def test_refuses_colliding_paths(tmp_path: Path) -> None:
    db = addition_db(tmp_path)
    with pytest.raises(ValueError, match="must be distinct"):
        recover_issues(db, addition_ledger(tmp_path), db, approval_note="owner approved")
