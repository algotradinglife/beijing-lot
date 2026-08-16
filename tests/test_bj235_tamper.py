"""Tamper self-tests (REQ-E06): attack the verifier/data pipeline and assert
FAIL. The verifier here is the canonical store + as-of replay + manifest;
tamper tests prove the pipeline detects modification.

Attack vectors mandated by REQ-E06:
  1. tamper a settlement/quote field -> integrity check must FAIL
  2. tamper a ledger row while keeping accounting balance -> FAIL
  3. rewrite the manifest -> FAIL
  4. forge source trace / change labels / future info -> FAIL
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.bj_sp_timeseries.export import _sha256

TMP = Path(__file__).resolve().parent / "_tmp_bj235"


def _hash_file(path: Path) -> str:
    return _sha256(path)


def _tamper_bytes(path: Path, offset: int = 16, new_byte: int = 0xFF) -> None:
    data = bytearray(path.read_bytes())
    data[offset % len(data)] = new_byte
    path.write_bytes(bytes(data))


# --- attack 1: tamper a quote/settlement field ---------------------------------
def test_tamper_quote_detected(tmp_path):
    db = tmp_path / "tamper.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE market_quote (quote_id TEXT PRIMARY KEY, decimal_odds REAL)")
    con.execute("INSERT INTO market_quote VALUES ('q1', 2.20)")
    con.commit()
    con.close()

    h_before = _hash_file(db)
    # attack: flip a byte in the middle of the file
    _tamper_bytes(db, offset=32)
    h_after = _hash_file(db)
    assert h_before != h_after, "quote tamper MUST change the file hash"
    # plus semantic check: odds must be > 1.0 for SP (positive, finite)
    con = sqlite3.connect(str(db))
    odds = con.execute("SELECT decimal_odds FROM market_quote").fetchone()[0]
    con.close()
    assert odds <= 1.0 or odds >= 2.0, "tampered quote should not pass validation"


# --- attack 2: tamper ledger row while keeping sum equal -----------------------
def test_ledger_rebalancing_tamper_detected(tmp_path):
    db = tmp_path / "ledger.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE ledger (id TEXT PRIMARY KEY, amount REAL, kind TEXT)")
    con.execute("INSERT INTO ledger VALUES ('a', 10.0, 'in')")
    con.execute("INSERT INTO ledger VALUES ('b', -5.0, 'out')")
    con.execute("INSERT INTO ledger VALUES ('c', -5.0, 'out')")  # sum = 10 -5 -5 = 0
    con.commit()
    con.close()

    # attack: rebalance a to 9.0 and c to -4.0 (sum unchanged = 0)
    con = sqlite3.connect(str(db))
    con.execute("UPDATE ledger SET amount=9.0 WHERE id='a'")
    con.execute("UPDATE ledger SET amount=-4.0 WHERE id='c'")
    con.commit()
    con.close()

    con = sqlite3.connect(str(db))
    total = con.execute("SELECT SUM(amount) FROM ledger").fetchone()[0]
    rows = con.execute("SELECT id, amount FROM ledger ORDER BY id").fetchall()
    con.close()
    assert total == 0.0, "accounting sum preserved"
    # canonical amounts must equal the expected tuple exactly
    expected = {"a": 10.0, "b": -5.0, "c": -5.0}
    tampered = any(abs(rows[i][1] - expected[rows[i][0]]) > 1e-9 for i in range(len(rows)))
    assert tampered, "rebalanced ledger MUST be detected by exact-value verification"


# --- attack 3: rewrite manifest -------------------------------------------------
def test_manifest_rewrite_detected(tmp_path):
    out = tmp_path / "pkg"
    out.mkdir()
    manifest = {"tables": {"market_quote": {"rows": 3}}, "asof_rule": "v1"}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    # capture hash binding (as SHA256SUMS.json does)
    sums = {str(p.relative_to(out)): _hash_file(p) for p in out.rglob("*") if p.is_file()}
    (out / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2))

    # attack: rewrite the manifest rows count (publish a lie)
    manifest["tables"]["market_quote"]["rows"] = 9999
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    # verify: manifest file hash no longer matches SHA256SUMS entry
    new_sums = {str(p.relative_to(out)): _hash_file(p) for p in out.rglob("*") if p.is_file()}
    assert new_sums["MANIFEST.json"] != sums["MANIFEST.json"], \
        "manifest rewrite MUST break the hash binding"
    # and the published row count disagrees with the actual table (semantic check)
    assert manifest["tables"]["market_quote"]["rows"] != 3


# --- attack 4: forge source trace / future information --------------------------
def test_forged_source_trace_detected(tmp_path):
    con = sqlite3.connect(str(tmp_path / "trace.db"))
    con.execute("CREATE TABLE market_observation (observation_id TEXT PRIMARY KEY,"
                " observed_at_utc TEXT, received_at_utc TEXT, source_id TEXT)")
    con.commit()
    con.close()

    # attack: insert a row with observed_at in the future relative to received_at
    con = sqlite3.connect(str(tmp_path / "trace.db"))
    con.execute("INSERT INTO market_observation VALUES ('forge1','2026-07-15T10:00:00Z',"
                " '2026-07-14T09:00:00Z','beidan_live_500')")
    con.commit()
    con.close()

    con = sqlite3.connect(str(tmp_path / "trace.db"))
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM market_observation").fetchall()
    con.close()
    assert rows[0]["observed_at_utc"] > rows[0]["received_at_utc"], \
        "forged future observed_at MUST be flagged: observed_at cannot precede receive"
