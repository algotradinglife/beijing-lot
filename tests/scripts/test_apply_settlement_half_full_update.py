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

from src.settlement_half_full_update import apply_half_full_update  # noqa: E402

ISSUE, SLOT = "21082", 90
OLD_OPTION, NEW_OPTION, SP = "胜-负", "平-负", 16.07
SOURCE_SHA = "aa" * 32


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence(tmp_path: Path) -> dict:
    """Minimal stand-in pages for the two extractor families this batch binds."""
    gsa = tmp_path / "gsa.html"
    gsa.write_text("<p>1st Half 2 - 2</p><p>Full Time 2 - 3</p>", encoding="utf-8")
    okooo_half = tmp_path / "okooo-half.html"
    okooo_half.write_text(
        '<table><tr><td>90</td><td>爱甲</td><td>02:45</td><td>完</td><td>[2] 主队</td>'
        '<td>2 - 3</td><td class="dzname">[9] 客队'
        '<td><span class="font_red">2-2</span></td></td>'
        '<td class="weather_icon"></td><td class="blockbox"></td>'
        '<td class="ctrl_result">0</td></tr></table>', encoding="gbk")
    okooo_full = tmp_path / "okooo-full.html"
    okooo_full.write_text(
        "<table><tr><td>90 爱甲</td><td>02:40</td><td>主队 客队</td><td>16.07</td><td>投注区</td>"
        "<td>全</td><td></td><td>2-3</td><td>1-0</td><td>析</td></tr></table>", encoding="gbk")
    return {
        "half_time_evidence": [
            {"source_id": "globalsportsarchive", "path": str(gsa), "sha256": _sha256(gsa),
             "url": "https://example.invalid/gsa"},
            {"source_id": "okooo", "path": str(okooo_half), "sha256": _sha256(okooo_half),
             "url": "https://example.invalid/okooo"},
        ],
        "half_full_evidence": [
            {"source_id": "okooo_half_full", "path": str(okooo_full),
             "sha256": _sha256(okooo_full), "url": "https://example.invalid/okooo-full"},
        ],
    }


def _ledger(tmp_path: Path, **overrides) -> Path:
    entry = {
        "issue": ISSUE, "slot": SLOT, "play": "bq",
        "old_option": OLD_OPTION, "new_option": NEW_OPTION, "sp": SP,
        "half_time": "2-2", "full_time": "2-3",
        "fixture": {"home": "主队", "away": "客队", "date": "2021-08-06"},
        "original_source_sha256": SOURCE_SHA,
        **_evidence(tmp_path),
    }
    entry.update(overrides)
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"schema": "bj479_half_full_correction_ledger_v1",
                                  "corrections": [entry]}, ensure_ascii=False),
                      encoding="utf-8")
    return ledger


def _database(tmp_path: Path, *, option: str = OLD_OPTION, sp: float | None = SP,
              target_sp: float | None = None) -> Path:
    path = tmp_path / "settlement.sqlite"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE observation (observation_id INTEGER PRIMARY KEY, issue TEXT,"
                " slot INTEGER, play TEXT, expected_option TEXT, source_sha256 TEXT)")
    con.execute("CREATE TABLE option_sp (observation_id INTEGER, option TEXT, raw_sp TEXT,"
                " sp REAL, cell_id TEXT)")
    con.execute("CREATE TABLE receipt (payload_json TEXT)")
    con.execute("INSERT INTO observation VALUES (1,?,?,'bq',?,?)", (ISSUE, SLOT, option, SOURCE_SHA))
    con.execute("INSERT INTO option_sp VALUES (1,?,?,?,'c1')", (OLD_OPTION, str(sp), sp))
    con.execute("INSERT INTO option_sp VALUES (1,?,?,?,'c2')",
                (NEW_OPTION, "" if target_sp is None else str(target_sp), target_sp))
    con.execute("INSERT INTO receipt VALUES (?)", (json.dumps({"schema": "nowscore_audit_v1",
                                                               "data_sha256": "bb" * 32}),))
    con.commit()
    con.close()
    return path


def test_applies_and_relocates_the_settlement_sp(tmp_path: Path) -> None:
    db = _database(tmp_path)
    result = apply_half_full_update(db, _ledger(tmp_path), tmp_path / "backup.sqlite",
                                    approval_note="owner approved")
    assert result["status"] == "applied" and result["rows"] == 1
    con = sqlite3.connect(db)
    assert con.execute("SELECT expected_option FROM observation").fetchone()[0] == NEW_OPTION
    assert con.execute("SELECT sp FROM option_sp WHERE option=?", (OLD_OPTION,)).fetchone()[0] is None
    assert con.execute("SELECT sp FROM option_sp WHERE option=?", (NEW_OPTION,)).fetchone()[0] == SP
    assert con.execute("SELECT COUNT(*) FROM half_full_correction").fetchone()[0] == 1
    receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
    assert receipt["data_sha256"] == "bb" * 32          # pre-correction snapshot is kept
    assert receipt["corrected_half_full_observations"] == 1
    con.close()
    assert (tmp_path / "backup.sqlite").is_file()


def test_repeat_run_is_idempotent(tmp_path: Path) -> None:
    db = _database(tmp_path)
    ledger, backup = _ledger(tmp_path), tmp_path / "backup.sqlite"
    apply_half_full_update(db, ledger, backup, approval_note="owner approved")
    assert apply_half_full_update(db, ledger, backup,
                                  approval_note="owner approved")["status"] == "already_applied"
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM half_full_correction").fetchone()[0] == 1


def test_refuses_without_an_approval_note(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="approval note"):
        apply_half_full_update(_database(tmp_path), _ledger(tmp_path), tmp_path / "b.sqlite",
                               approval_note="  ")


def test_refuses_identical_paths(tmp_path: Path) -> None:
    db = _database(tmp_path)
    with pytest.raises(ValueError, match="must all differ"):
        apply_half_full_update(db, _ledger(tmp_path), db, approval_note="x")


def test_refuses_evidence_that_changed_on_disk(tmp_path: Path) -> None:
    db = _database(tmp_path)
    ledger = _ledger(tmp_path)
    evidence = json.loads(ledger.read_text(encoding="utf-8"))["corrections"][0]
    Path(evidence["half_full_evidence"][0]["path"]).write_text("tampered", encoding="gbk")
    with pytest.raises(ValueError, match="evidence changed on disk"):
        apply_half_full_update(db, ledger, tmp_path / "b.sqlite", approval_note="x")


def test_refuses_a_ledger_that_contradicts_the_evidence(tmp_path: Path) -> None:
    """The option the source inherited from its own wrong half time cannot be re-asserted."""
    db = _database(tmp_path)
    ledger = _ledger(tmp_path, new_option="胜-负")
    with pytest.raises(ValueError, match="evidence proves"):
        apply_half_full_update(db, ledger, tmp_path / "b.sqlite", approval_note="x")
    assert sqlite3.connect(db).execute("SELECT expected_option FROM observation").fetchone()[0] == OLD_OPTION


def test_refuses_a_single_half_time_source(tmp_path: Path) -> None:
    db = _database(tmp_path)
    ledger = _ledger(tmp_path)
    entry = json.loads(ledger.read_text(encoding="utf-8"))["corrections"][0]
    entry["half_time_evidence"] = entry["half_time_evidence"][:1]
    ledger.write_text(json.dumps({"schema": "bj479_half_full_correction_ledger_v1",
                                  "corrections": [entry]}, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="independent sources"):
        apply_half_full_update(db, ledger, tmp_path / "b.sqlite", approval_note="x")


def test_refuses_when_the_database_no_longer_holds_the_original_option(tmp_path: Path) -> None:
    db = _database(tmp_path, option="平-负", sp=None, target_sp=SP)
    with pytest.raises(ValueError, match="expected original option"):
        apply_half_full_update(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="x")


def test_refuses_when_the_recorded_sp_is_not_the_corroborated_one(tmp_path: Path) -> None:
    db = _database(tmp_path, sp=9.99)
    with pytest.raises(ValueError, match="not the corroborated"):
        apply_half_full_update(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="x")


def test_refuses_when_the_target_option_already_carries_an_sp(tmp_path: Path) -> None:
    db = _database(tmp_path, target_sp=4.2)
    with pytest.raises(ValueError, match="already carries an SP"):
        apply_half_full_update(db, _ledger(tmp_path), tmp_path / "b.sqlite", approval_note="x")


def test_refuses_a_ledger_for_the_wrong_schema(tmp_path: Path) -> None:
    ledger = _ledger(tmp_path)
    ledger.write_text(json.dumps({"schema": "something_else", "corrections": [{}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported ledger schema"):
        apply_half_full_update(_database(tmp_path), ledger, tmp_path / "b.sqlite", approval_note="x")


def test_refuses_an_existing_backup_path(tmp_path: Path) -> None:
    db = _database(tmp_path)
    backup = tmp_path / "b.sqlite"
    backup.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="backup path already exists"):
        apply_half_full_update(db, _ledger(tmp_path), backup, approval_note="x")
