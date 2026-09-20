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

from scripts.verify_settlement_halftime_correction import build_report  # noqa: E402
from src.settlement_halftime_update import apply_halftime_update  # noqa: E402

GSA = b"""<html><body><div>Full Time 2 - 3 Cork City FC</div>
<div>1st Half 2 - 2 Killian Brouder ( 2 - 2 ) 41'</div></body></html>"""
SCORE24 = b"""<html><body><table>
<tr><td>06.08.21</td><td>Galway</td><td>Cork City</td><td class="score"><b>L 2:3 (2:2)</b></td></tr>
</table></body></html>"""
PLAYS = ["bf", "bq", "ds", "jq", "spf"]


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    evidence = []
    for name, payload, source in (("gsa.html", GSA, "globalsportsarchive"),
                                  ("24score.html", SCORE24, "24score")):
        path = tmp_path / name
        path.write_bytes(payload)
        evidence.append({"source_id": source, "path": str(path),
                         "sha256": hashlib.sha256(payload).hexdigest(),
                         "url": "https://example.invalid/" + name})
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({
        "schema": "bj479_halftime_correction_ledger_v1",
        "corrections": [{
            "issue": "21082", "slot": 90, "plays": PLAYS,
            "old_halftime_score": "3-2", "new_halftime_score": "2-2", "ft_score": "2-3",
            "fixture": {"home": "甲队", "away": "乙队", "date": "2021-08-06",
                        "ft_home": 2, "ft_away": 3, "away_en": "Cork City"},
            "evidence": evidence}],
    }), encoding="utf-8")

    db = tmp_path / "db.sqlite"
    con = sqlite3.connect(db)
    try:
        con.execute("""CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT,
            slot INTEGER, play TEXT, halftime_score TEXT, score TEXT, source_sha256 TEXT)""")
        con.execute("CREATE TABLE receipt (payload_json TEXT)")
        con.execute("INSERT INTO receipt VALUES (?)",
                    (json.dumps({"data_sha256": "e" * 64, "corrected_options": 86}),))
        for index, play in enumerate(PLAYS, start=1):
            con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?)",
                        (index, "21082", 90, play, "3-2", "2-3", "a" * 64))
        con.commit()
    finally:
        con.close()
    backup = tmp_path / "backup.sqlite"
    apply_halftime_update(db, ledger, backup, approval_note="owner approved")
    return db, ledger, backup


def test_report_replays_the_correction_from_preserved_evidence(tmp_path: Path) -> None:
    db, ledger, backup = _fixture(tmp_path)
    report = build_report(db, ledger, backup)

    assert report["schema"] == "bj479_halftime_correction_verification_v1"
    assert report["conclusion"]["verified"] is True
    assert report["conclusion"]["full_time_unchanged"] is True
    assert report["replay"] == {"evidence_files_verified": 2, "all_hashes_match": True,
                                "all_values_reproduced": True}
    assert report["backup"]["quick_check"] == "ok"
    assert report["backup"]["holds_original_values"] is True
    correction = report["corrections"][0]
    assert correction["new_half_time"] == "2-2" and correction["old_half_time"] == "3-2"
    assert correction["database_half_time"] == ["2-2"] and correction["full_time"] == "2-3"
    assert correction["corroborating_sources"] == ["24score", "globalsportsarchive"]
    assert correction["replay_agrees"] is True
    assert report["receipt"]["data_sha256"] == "e" * 64
    assert report["conclusion"]["limitations"], "limitations must be recorded"


def test_report_refuses_tampered_evidence(tmp_path: Path) -> None:
    db, ledger, backup = _fixture(tmp_path)
    first = json.loads(ledger.read_text(encoding="utf-8"))["corrections"][0]["evidence"][0]
    Path(first["path"]).write_bytes(b"<html>tampered</html>")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        build_report(db, ledger, backup)


def test_report_refuses_when_the_database_no_longer_agrees(tmp_path: Path) -> None:
    db, ledger, backup = _fixture(tmp_path)
    con = sqlite3.connect(db)
    con.execute("UPDATE observation SET halftime_score='9-9' WHERE observation_id=1")
    con.commit()
    con.close()
    report = build_report(db, ledger, backup)
    assert report["conclusion"]["verified"] is False
    assert report["replay"]["all_values_reproduced"] is False
