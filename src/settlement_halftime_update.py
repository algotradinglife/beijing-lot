"""Transactional owner-approved half-time correction with SQLite backup and audit.

Issue #479 deliverable, following the `settlement_sp_update` contract. Applies only
half-time values that independent external sources corroborate, only onto rows that
still hold the exact value the ledger recorded, and never onto a full-time score.

The correction is external by construction: both the Nowscore and 500 sources carry
the same wrong half-time value, so the ledger binds third-party result archives
instead (see `src.settlement_halftime_evidence`). The preserved evidence bytes stay in
their hashed location outside the database; the batch row records that manifest so the
correction can be replayed and re-verified without trusting the mutated database.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.settlement_halftime_evidence import EXTRACTORS, corroborate

_BATCH_DDL = """CREATE TABLE IF NOT EXISTS halftime_correction_batch (
    batch_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL,
    row_count INTEGER NOT NULL, fixture_count INTEGER NOT NULL,
    original_receipt_json TEXT NOT NULL, ledger_json TEXT NOT NULL,
    evidence_manifest_json TEXT NOT NULL, backup_path TEXT NOT NULL)"""

_CORRECTION_DDL = """CREATE TABLE IF NOT EXISTS halftime_correction (
    observation_id INTEGER NOT NULL, batch_id TEXT NOT NULL, issue TEXT NOT NULL,
    slot INTEGER NOT NULL, play TEXT NOT NULL,
    old_halftime_score TEXT NOT NULL, new_halftime_score TEXT NOT NULL,
    ft_score TEXT NOT NULL, corroborating_sources TEXT NOT NULL,
    original_source_sha256 TEXT NOT NULL, note TEXT NOT NULL, applied_at TEXT NOT NULL,
    PRIMARY KEY (observation_id))"""


def _verify_evidence(evidence: list[dict], fixture: dict) -> dict[str, dict]:
    """Re-read every preserved evidence file, check its hash, and extract its claim."""
    claims = {}
    for item in evidence:
        path = Path(item["path"])
        payload = path.read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != item["sha256"]:
            raise ValueError(f"evidence hash mismatch for {path}: {actual} != {item['sha256']}")
        if item["source_id"] in claims:
            raise ValueError(f"duplicate source in ledger: {item['source_id']}")
        claims[item["source_id"]] = EXTRACTORS[item["source_id"]](payload, fixture)
    return claims


def apply_halftime_update(database, ledger_path, backup_path, *, approval_note):
    """Apply an exact corroborated half-time ledger; backup first, roll back on failure.

    Paths are explicit. Every correction must be reproducible from the preserved
    evidence bytes named in the ledger, and its target row must still hold the
    recorded original value. Repeating the same ledger is a no-op only after verifying
    all corrected rows. No fetching, no historical learning.
    """
    database, ledger_path, backup_path = map(Path, (database, ledger_path, backup_path))
    if not isinstance(approval_note, str) or not approval_note.strip():
        raise ValueError("Explicit approval note required")
    if len({p.resolve() for p in (database, ledger_path, backup_path)}) != 3:
        raise ValueError("Database, ledger and backup paths must be distinct")
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    batch = hashlib.sha256(ledger_bytes).hexdigest()
    if ledger.get("schema") != "bj479_halftime_correction_ledger_v1":
        raise ValueError("Wrong ledger schema")
    corrections = ledger["corrections"]
    if not corrections:
        raise ValueError("Empty ledger")
    if len({(c["issue"], c["slot"]) for c in corrections}) != len(corrections):
        raise ValueError("Ledger repeats a fixture")

    con = sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
    try:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='halftime_correction_batch'").fetchone():
            prior = con.execute("SELECT row_count FROM halftime_correction_batch WHERE batch_id=?",
                                (batch,)).fetchone()
            if prior:
                rows = con.execute("""SELECT a.new_halftime_score, o.halftime_score
                    FROM halftime_correction a JOIN observation o USING(observation_id)
                    WHERE a.batch_id=?""", (batch,)).fetchall()
                if len(rows) != prior[0] or any(a != b for a, b in rows):
                    raise ValueError("Previously applied values changed")
                con.rollback()
                return {"status": "already_applied", "updated": prior[0]}

        targets, fixtures = [], set()
        for c in corrections:
            fixture = dict(c["fixture"])
            claims = _verify_evidence(c["evidence"], fixture)
            home, away = corroborate(claims)
            if f"{home}-{away}" != c["new_halftime_score"]:
                raise ValueError(
                    f"issue {c['issue']} slot {c['slot']}: evidence corroborates "
                    f"{home}-{away}, ledger claims {c['new_halftime_score']}")
            if f"{fixture['ft_home']}-{fixture['ft_away']}" != c["ft_score"]:
                raise ValueError(f"issue {c['issue']} slot {c['slot']}: fixture full time mismatch")
            fixtures.add((c["issue"], c["slot"]))
            for play in c["plays"]:
                rows = con.execute("""SELECT observation_id, halftime_score, source_sha256
                    FROM observation WHERE issue=? AND slot=? AND play=?""",
                    (c["issue"], c["slot"], play)).fetchall()
                if len(rows) != 1:
                    raise ValueError(f"issue {c['issue']} slot {c['slot']} {play}: expected one row")
                oid, current, source_sha = rows[0]
                if current != c["old_halftime_score"]:
                    raise ValueError(
                        f"issue {c['issue']} slot {c['slot']} {play}: holds {current!r}, "
                        f"ledger approved replacing {c['old_halftime_score']!r}")
                targets.append((oid, c, play, source_sha))

        original_receipts = con.execute("SELECT payload_json FROM receipt").fetchall()
        if len(original_receipts) != 1:
            raise ValueError("Expected one original build receipt")

        # Reserve the backup path first; a second read-only connection can then back up
        # the stable committed snapshot without copying an active writer.
        with backup_path.open("xb"):
            pass
        source = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        dest = sqlite3.connect(backup_path)
        try:
            source.backup(dest)
            if dest.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Backup integrity check failed")
        finally:
            dest.close()
            source.close()

        con.execute(_BATCH_DDL)
        con.execute(_CORRECTION_DDL)
        now = datetime.now(timezone.utc).isoformat()
        note = approval_note.strip()
        manifest = [
            {"source_id": e["source_id"], "path": e["path"], "sha256": e["sha256"], "url": e["url"]}
            for c in corrections for e in c["evidence"]
        ]
        con.execute("INSERT INTO halftime_correction_batch VALUES (?,?,?,?,?,?,?,?,?)",
                    (batch, now, note, len(targets), len(fixtures), original_receipts[0][0],
                     ledger_bytes.decode(), json.dumps(manifest, ensure_ascii=False),
                     str(backup_path.resolve())))
        for oid, c, play, source_sha in targets:
            sources = ",".join(sorted({e["source_id"] for e in c["evidence"]}))
            con.execute("INSERT INTO halftime_correction VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, batch, c["issue"], c["slot"], play, c["old_halftime_score"],
                         c["new_halftime_score"], c["ft_score"], sources, source_sha, note, now))
            updated = con.execute(
                "UPDATE observation SET halftime_score=? WHERE observation_id=? AND halftime_score=?",
                (c["new_halftime_score"], oid, c["old_halftime_score"]))
            if updated.rowcount != 1:
                raise ValueError("Conditional update did not affect exactly one row")

        receipt = json.loads(original_receipts[0][0])
        receipt.update(
            halftime_correction_batch_id=batch,
            corrected_halftime_observations=len(targets),
            corrected_halftime_fixtures=len(fixtures),
            halftime_corrected_at=now,
            halftime_correction_note=(
                "Original build hashes describe the pre-correction snapshot; see "
                "halftime_correction_batch.original_receipt_json and the SQLite backup. "
                "The half-time values recorded here were contradicted by the source's own "
                "full-time score and were corroborated by independent external result archives."),
        )
        con.execute("UPDATE receipt SET payload_json=?", (json.dumps(receipt, ensure_ascii=False),))
        con.commit()
        return {"status": "applied", "updated": len(targets), "fixtures": len(fixtures),
                "batch_id": batch, "backup": str(backup_path)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
