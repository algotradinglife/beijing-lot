"""Transactional owner-approved half/full settlement correction with backup and audit.

Issue #479, second batch. The half-time error corrected by ``settlement_halftime_update``
is not display-only: the build derives the ``bq`` (half/full) winning option from the
half-time score, so Nowscore's wrong half time also produced a wrong half/full settlement
and hung the settlement SP on the wrong option.

This module corrects the *projection* only -- ``observation.expected_option`` and the
``option_sp`` row that carries the settlement SP. ``observation.payload_json`` keeps the
source's own bytes and is never rewritten, exactly as the missing-SP correction does; a
rebuild from the preserved payload therefore reproduces the source's original values and
the corrections stay a recorded layer on top.

Every change must be proved before it is written:

* the ledger names the evidence files and their SHA-256, and the files must still match;
* the half time is re-corroborated from independent sources and must equal the ledger's;
* the half/full option must equal the one derived from that corrected half time and the
  full time, so the source cannot re-assert the option it inherited from its own error;
* the settlement SP must be published identically by every evidence source, and must equal
  the SP already recorded for the fixture -- this batch relocates a correct SP, it never
  invents one;
* the database must still hold the approved original option, with the SP on it and absent
  from the target option.

Any failure refuses the whole batch before a single row is written.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.settlement_halftime_evidence import (
    EXTRACTORS,
    HALF_FULL_EXTRACTORS,
    corroborate,
    corroborate_half_full,
)

LEDGER_SCHEMA = "bj479_half_full_correction_ledger_v1"
BATCH_TABLE = "half_full_correction_batch"
ROW_TABLE = "half_full_correction"

BATCH_DDL = f"""CREATE TABLE IF NOT EXISTS {BATCH_TABLE} (
    batch_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL,
    row_count INTEGER NOT NULL, fixture_count INTEGER NOT NULL,
    original_receipt_json TEXT NOT NULL, ledger_json TEXT NOT NULL,
    evidence_manifest_json TEXT NOT NULL, backup_path TEXT NOT NULL)"""

ROW_DDL = f"""CREATE TABLE IF NOT EXISTS {ROW_TABLE} (
    observation_id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL, issue TEXT NOT NULL,
    slot INTEGER NOT NULL, play TEXT NOT NULL, half_time TEXT NOT NULL,
    full_time TEXT NOT NULL, old_option TEXT NOT NULL, new_option TEXT NOT NULL,
    sp REAL NOT NULL, corroborating_sources TEXT NOT NULL,
    original_source_sha256 TEXT NOT NULL, note TEXT NOT NULL, applied_at TEXT NOT NULL)"""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _score(text: str) -> tuple[int, int]:
    home, away = text.split("-")
    return int(home), int(away)


def _claims(entries: list[dict], extractors: dict, fixture: dict, root: Path) -> dict[str, dict]:
    """Re-extract every evidence entry after checking it against its recorded hash."""
    claims: dict[str, dict] = {}
    for entry in entries:
        path = Path(entry["path"])
        if not path.is_file():
            raise ValueError(f"evidence file is missing: {path}")
        actual = _sha256_file(path)
        if actual != entry["sha256"]:
            raise ValueError(f"evidence changed on disk: {path} ({actual} != {entry['sha256']})")
        source_id = entry["source_id"]
        if source_id not in extractors:
            raise ValueError(f"unknown evidence source {source_id!r}")
        if source_id in claims:
            raise ValueError(f"duplicate evidence source {source_id!r}")
        claims[source_id] = extractors[source_id](path.read_bytes(), fixture)
    return claims


def _already_applied(connection: sqlite3.Connection, batch_id: str) -> dict | None:
    """Return the prior result when this exact ledger was already applied."""
    present = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (BATCH_TABLE,)).fetchone()
    if present is None:
        return None
    prior = connection.execute(
        f"SELECT row_count FROM {BATCH_TABLE} WHERE batch_id=?", (batch_id,)).fetchone()
    if prior is None:
        return None
    rows = connection.execute(
        f"SELECT o.expected_option, a.new_option FROM {ROW_TABLE} a "
        "JOIN observation o USING(observation_id) WHERE a.batch_id=?", (batch_id,)).fetchall()
    if len(rows) != prior["row_count"] or any(r["expected_option"] != r["new_option"]
                                              for r in rows):
        raise ValueError("this batch was applied before but the database no longer agrees")
    fixtures = connection.execute(
        f"SELECT COUNT(DISTINCT issue || '/' || slot) FROM {ROW_TABLE} WHERE batch_id=?",
        (batch_id,)).fetchone()[0]
    return {"status": "already_applied", "batch_id": batch_id,
            "rows": prior["row_count"], "fixtures": fixtures}


def apply_half_full_update(database, ledger_path, backup_path, *, approval_note: str) -> dict:
    """Correct the half/full settlement of every fixture in ``ledger_path``.

    Returns ``{"status": "applied"|"already_applied", "batch_id", "rows", "fixtures"}``.
    """
    if not isinstance(approval_note, str) or not approval_note.strip():
        raise ValueError("an explicit owner approval note is required")
    database, ledger_path, backup_path = (Path(database), Path(ledger_path), Path(backup_path))
    if len({database.resolve(), ledger_path.resolve(), backup_path.resolve()}) != 3:
        raise ValueError("database, ledger and backup paths must all differ")
    if not database.is_file():
        raise ValueError(f"database not found: {database}")

    ledger_bytes = ledger_path.read_bytes()
    batch_id = hashlib.sha256(ledger_bytes).hexdigest()
    ledger = json.loads(ledger_bytes)
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError(f"unsupported ledger schema {ledger.get('schema')!r}")
    corrections = ledger.get("corrections") or []
    if not corrections:
        raise ValueError("ledger contains no corrections")

    # Every claim is proved against preserved evidence before anything is written.
    planned = []
    for entry in corrections:
        fixture = dict(entry["fixture"])
        fixture["slot"] = entry["slot"]
        half_time = _score(entry["half_time"])
        full_time = _score(entry["full_time"])
        fixture["ft_home"], fixture["ft_away"] = full_time
        half_time_claims = _claims(entry["half_time_evidence"], EXTRACTORS, fixture,
                                   ledger_path.parent)
        if corroborate(half_time_claims) != half_time:
            raise ValueError(f"{entry['issue']}/{entry['slot']}: half time is not corroborated")
        half_full_claims = _claims(entry["half_full_evidence"], HALF_FULL_EXTRACTORS, fixture,
                                   ledger_path.parent)
        settled = corroborate_half_full(half_time, full_time, half_full_claims)
        if settled["option"] != entry["new_option"] or settled["sp"] != entry["sp"]:
            raise ValueError(
                f"{entry['issue']}/{entry['slot']}: ledger claims {entry['new_option']} @ "
                f"{entry['sp']} but evidence proves {settled['option']} @ {settled['sp']}")
        planned.append((entry, half_time, full_time, settled, half_time_claims, half_full_claims))

    # A repeated run must not touch the first backup or rewrite an applied batch.
    probe = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    probe.row_factory = sqlite3.Row
    try:
        prior_result = _already_applied(probe, batch_id)
    finally:
        probe.close()
    if prior_result is not None:
        return prior_result

    # The backup is taken before the first write so a failed batch can always be reverted.
    if backup_path.exists():
        raise ValueError(f"backup path already exists: {backup_path}")
    source = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    target = sqlite3.connect(backup_path)
    try:
        source.backup(target)
        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("backup failed its integrity check")
    finally:
        target.close()
        source.close()

    applied_at = datetime.now(timezone.utc).isoformat()
    connection = sqlite3.connect(database, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(BATCH_DDL)
        connection.execute(ROW_DDL)
        prior_result = _already_applied(connection, batch_id)
        if prior_result is not None:
            connection.execute("ROLLBACK")
            return prior_result

        for entry, half_time, full_time, settled, half_claims, half_full_claims in planned:
            row = connection.execute(
                "SELECT observation_id, expected_option, source_sha256 FROM observation "
                "WHERE issue=? AND slot=? AND play=?", (entry["issue"], entry["slot"],
                                                        entry["play"])).fetchone()
            if row is None:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: no {entry['play']} observation")
            if row["expected_option"] != entry["old_option"]:
                raise ValueError(
                    f"{entry['issue']}/{entry['slot']}: expected original option "
                    f"{entry['old_option']!r}, database holds {row['expected_option']!r}")
            if row["source_sha256"] != entry["original_source_sha256"]:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: source hash changed")
            observation_id = row["observation_id"]

            held = connection.execute(
                "SELECT option, raw_sp, sp FROM option_sp WHERE observation_id=?", (observation_id,))
            sp_by_option = {r["option"]: r for r in held}
            old = sp_by_option.get(entry["old_option"])
            new = sp_by_option.get(entry["new_option"])
            if old is None or new is None:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: half/full option rows missing")
            if old["sp"] is None or float(old["sp"]) != settled["sp"]:
                raise ValueError(
                    f"{entry['issue']}/{entry['slot']}: recorded SP {old['sp']} is not the "
                    f"corroborated {settled['sp']}")
            if new["sp"] is not None:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: target option already carries an SP")

            updated = connection.execute(
                "UPDATE observation SET expected_option=? WHERE observation_id=? AND expected_option=?",
                (settled["option"], observation_id, entry["old_option"])).rowcount
            if updated != 1:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: option update lost its target")
            moved = connection.execute(
                "UPDATE option_sp SET raw_sp='', sp=NULL WHERE observation_id=? AND option=? "
                "AND sp IS NOT NULL", (observation_id, entry["old_option"])).rowcount
            if moved != 1:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: SP could not be cleared")
            placed = connection.execute(
                "UPDATE option_sp SET raw_sp=?, sp=? WHERE observation_id=? AND option=? "
                "AND sp IS NULL", (str(settled["sp"]), settled["sp"], observation_id,
                                   settled["option"])).rowcount
            if placed != 1:
                raise ValueError(f"{entry['issue']}/{entry['slot']}: SP could not be relocated")

            connection.execute(
                f"INSERT INTO {ROW_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (observation_id, batch_id, entry["issue"], entry["slot"], entry["play"],
                 entry["half_time"], entry["full_time"], entry["old_option"], settled["option"],
                 settled["sp"], json.dumps(sorted(set(half_claims) | set(half_full_claims)),
                                           ensure_ascii=False),
                 row["source_sha256"], approval_note.strip(), applied_at))

        row_count = len(planned)
        fixture_count = len({(e[0]["issue"], e[0]["slot"]) for e in planned})
        receipt_row = connection.execute("SELECT payload_json FROM receipt").fetchone()
        original_receipt = receipt_row["payload_json"] if receipt_row else "{}"
        evidence_manifest = [
            {"issue": e[0]["issue"], "slot": e[0]["slot"],
             "half_time_evidence": e[0]["half_time_evidence"],
             "half_full_evidence": e[0]["half_full_evidence"]}
            for e in planned]
        connection.execute(
            f"INSERT INTO {BATCH_TABLE} VALUES (?,?,?,?,?,?,?,?,?)",
            (batch_id, applied_at, approval_note.strip(), row_count, fixture_count,
             original_receipt, ledger_bytes.decode("utf-8"),
             json.dumps(evidence_manifest, ensure_ascii=False), str(backup_path.resolve())))
        if receipt_row is not None:
            receipt = json.loads(original_receipt)
            receipt["half_full_correction_batch_id"] = batch_id
            receipt["corrected_half_full_observations"] = row_count
            receipt["corrected_half_full_fixtures"] = fixture_count
            receipt["half_full_corrected_at"] = applied_at
            receipt["half_full_correction_note"] = (
                "Original build hashes describe the pre-correction snapshot; see "
                "half_full_correction_batch.original_receipt_json and the SQLite backup.")
            connection.execute("UPDATE receipt SET payload_json=?",
                               (json.dumps(receipt, ensure_ascii=False),))
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()

    return {"status": "applied", "batch_id": batch_id, "rows": row_count,
            "fixtures": fixture_count, "backup": str(backup_path)}
