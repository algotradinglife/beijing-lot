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

from src.settlement_halftime_update import apply_halftime_update  # noqa: E402

GSA = b"""<html><body><div>Full Time 2 - 3 Cork City FC</div>
<div>1st Half 2 - 2 Killian Brouder ( 2 - 2 ) 41'</div></body></html>"""
SCORE24 = b"""<html><body><table>
<tr><td>06.08.21</td><td>Galway</td><td>Cork City</td><td class="score"><b>L 2:3 (2:2)</b></td></tr>
</table></body></html>"""

RECEIPT = {"schema": "nowscore_audit_v1", "source": "nowscore", "production_enabled": False,
           "data_sha256": "e" * 64}
PLAYS = ["bf", "bq", "ds", "jq", "spf"]


def _db(path: Path) -> Path:
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT,
            slot INTEGER, play TEXT, halftime_score TEXT, source_sha256 TEXT)""")
        con.execute("CREATE TABLE receipt (payload_json TEXT)")
        con.execute("INSERT INTO receipt VALUES (?)", (json.dumps(RECEIPT),))
        oid = 0
        for play in PLAYS:
            oid += 1
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?)",
                        (oid, "21082", 90, play, "3-2", "a" * 64))
        con.commit()
    finally:
        con.close()
    return path


def _evidence(tmp: Path, payload: bytes, name: str) -> dict:
    path = tmp / name
    path.write_bytes(payload)
    return {"source_id": "globalsportsarchive" if name.startswith("gsa") else "24score",
            "path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
            "url": "https://example.invalid/" + name}


def _ledger(tmp: Path, *, evidence=None, new="2-2", old="3-2", plays=None) -> Path:
    entry = {
        "issue": "21082", "slot": 90, "plays": plays or PLAYS,
        "old_halftime_score": old, "new_halftime_score": new, "ft_score": "2-3",
        "fixture": {"home": "甲队", "away": "乙队", "date": "2021-08-06",
                    "ft_home": 2, "ft_away": 3, "away_en": "Cork City"},
        "evidence": evidence if evidence is not None else [
            _evidence(tmp, GSA, "gsa.html"), _evidence(tmp, SCORE24, "24score.html")],
    }
    path = tmp / "ledger.json"
    path.write_text(json.dumps({"schema": "bj479_halftime_correction_ledger_v1",
                                "corrections": [entry]}), encoding="utf-8")
    return path


def _values(db: Path) -> list[str]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return [r[0] for r in con.execute("SELECT halftime_score FROM observation ORDER BY observation_id")]
    finally:
        con.close()


def test_applies_the_correction_and_records_the_audit_trail(tmp_path: Path) -> None:
    db, backup = _db(tmp_path / "db.sqlite"), tmp_path / "backup.sqlite"
    result = apply_halftime_update(db, _ledger(tmp_path), backup, approval_note="owner approved")

    assert result["status"] == "applied" and result["updated"] == 5 and result["fixtures"] == 1
    assert set(_values(db)) == {"2-2"}
    assert backup.exists()

    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        batch = con.execute("SELECT row_count, fixture_count, note, ledger_json, "
                            "evidence_manifest_json, backup_path FROM halftime_correction_batch").fetchone()
        assert batch[:3] == (5, 1, "owner approved")
        assert json.loads(batch[3])["corrections"][0]["new_halftime_score"] == "2-2"
        assert len(json.loads(batch[4])) == 2
        assert batch[5] == str(backup)
        rows = con.execute("SELECT old_halftime_score, new_halftime_score, ft_score, "
                           "corroborating_sources FROM halftime_correction ORDER BY observation_id").fetchall()
        assert len(rows) == 5
        assert rows[0] == ("3-2", "2-2", "2-3", "24score,globalsportsarchive")
        receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
    finally:
        con.close()
    assert receipt["corrected_halftime_observations"] == 5
    assert receipt["corrected_halftime_fixtures"] == 1
    assert receipt["data_sha256"] == "e" * 64, "the original build hash must survive the correction"


def test_repeating_the_same_ledger_is_a_verified_no_op(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    ledger = _ledger(tmp_path)
    apply_halftime_update(db, ledger, tmp_path / "backup.sqlite", approval_note="owner approved")
    again = apply_halftime_update(db, ledger, tmp_path / "other-backup.sqlite", approval_note="owner approved")
    assert again == {"status": "already_applied", "updated": 5}
    assert not (tmp_path / "other-backup.sqlite").exists()


def test_refuses_when_the_target_no_longer_holds_the_approved_original(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET halftime_score='9-9' WHERE observation_id=1")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="ledger approved replacing"):
        apply_halftime_update(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="owner approved")
    assert set(_values(db)) == {"3-2", "9-9"}, "a refused run must not write anything"


def test_refuses_when_evidence_bytes_do_not_match_the_ledger(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    ledger = _ledger(tmp_path)
    evidence = json.loads(ledger.read_text(encoding="utf-8"))["corrections"][0]["evidence"]
    Path(evidence[0]["path"]).write_bytes(b"<html>tampered</html>")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        apply_halftime_update(db, ledger, tmp_path / "b.sqlite", approval_note="owner approved")
    assert set(_values(db)) == {"3-2"}


def test_refuses_a_ledger_that_claims_more_than_the_evidence_corroborates(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match="evidence corroborates"):
        apply_halftime_update(db, _ledger(tmp_path, new="2-3"), tmp_path / "b.sqlite",
                              approval_note="owner approved")
    assert set(_values(db)) == {"3-2"}


def test_refuses_a_single_source_ledger(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    ledger = _ledger(tmp_path, evidence=[_evidence(tmp_path, GSA, "gsa.html")])
    with pytest.raises(ValueError, match="need >= 2 independent sources"):
        apply_halftime_update(db, ledger, tmp_path / "b.sqlite", approval_note="owner approved")
    assert set(_values(db)) == {"3-2"}


def test_refuses_without_an_explicit_approval_note(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match="approval note required"):
        apply_halftime_update(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="   ")
    assert set(_values(db)) == {"3-2"}


def test_refuses_colliding_paths(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    with pytest.raises(ValueError, match="must be distinct"):
        apply_halftime_update(db, _ledger(tmp_path), db, approval_note="owner approved")


def test_refuses_a_ledger_that_repeats_a_fixture(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    ledger = _ledger(tmp_path)
    doc = json.loads(ledger.read_text(encoding="utf-8"))
    doc["corrections"].append(doc["corrections"][0])
    ledger.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="repeats a fixture"):
        apply_halftime_update(db, ledger, tmp_path / "b.sqlite", approval_note="owner approved")
    assert set(_values(db)) == {"3-2"}


def test_refuses_an_unknown_ledger_schema(tmp_path: Path) -> None:
    db = _db(tmp_path / "db.sqlite")
    ledger = _ledger(tmp_path)
    doc = json.loads(ledger.read_text(encoding="utf-8"))
    doc["schema"] = "something_else"
    ledger.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(ValueError, match="Wrong ledger schema"):
        apply_halftime_update(db, ledger, tmp_path / "b.sqlite", approval_note="owner approved")
