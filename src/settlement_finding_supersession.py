"""Transactional owner-approved supersession of findings the corrections resolved.

Issue #479. A finding records what the *build* observed in the source bytes, so the
corrections deliberately leave the source record alone. But a finding whose subject no
longer holds is worse than useless: a consumer filtering on its code is told about a
contradiction that the sealed database no longer contains.

Superseding rewrites the finding's code and detail to say so, and it refuses to do that
unless the subject really is resolved: every affected row's observation must now satisfy
the predicate the finding asserted. Findings are never deleted -- the original code and
the reason are recorded in the audit table and in the new detail.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

LEDGER_SCHEMA = "bj479_finding_supersession_ledger_v1"
BATCH_TABLE = "finding_supersession_batch"
ROW_TABLE = "finding_supersession"

BATCH_DDL = f"""CREATE TABLE IF NOT EXISTS {BATCH_TABLE} (
    batch_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL,
    row_count INTEGER NOT NULL, original_receipt_json TEXT NOT NULL,
    ledger_json TEXT NOT NULL, backup_path TEXT NOT NULL)"""

ROW_DDL = f"""CREATE TABLE IF NOT EXISTS {ROW_TABLE} (
    issue TEXT NOT NULL, slot INTEGER NOT NULL, play TEXT NOT NULL,
    old_code TEXT NOT NULL, new_code TEXT NOT NULL, old_detail TEXT NOT NULL,
    batch_id TEXT NOT NULL, applied_at TEXT NOT NULL, PRIMARY KEY (issue, slot, play, old_code))"""


def _score(text: str) -> tuple[int, int] | None:
    parts = (text or "").strip().replace(":", "-").split("-")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _halftime_within_fulltime(half: str, full: str) -> bool:
    """The predicate behind halftime_exceeds_fulltime: neither side may exceed the full time."""
    h, f = _score(half), _score(full)
    return h is not None and f is not None and h[0] <= f[0] and h[1] <= f[1]


PREDICATES = {"halftime_exceeds_fulltime": _halftime_within_fulltime}


def supersede_findings(database, ledger_path, backup_path, *, approval_note: str) -> dict:
    """Supersede every finding named by ``ledger_path`` once its subject is resolved."""
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
    supersessions = ledger.get("supersessions") or []
    if not supersessions:
        raise ValueError("ledger contains no supersessions")

    applied_at = datetime.now(timezone.utc).isoformat()
    probe = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    probe.row_factory = sqlite3.Row
    try:
        present = probe.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                                (BATCH_TABLE,)).fetchone()
        if present is not None:
            prior = probe.execute(f"SELECT row_count FROM {BATCH_TABLE} WHERE batch_id=?",
                                  (batch_id,)).fetchone()
            if prior is not None:
                return {"status": "already_applied", "batch_id": batch_id,
                        "rows": prior["row_count"]}

        planned = []
        for entry in supersessions:
            code, new_code = entry["code"], entry["superseded_code"]
            if code not in PREDICATES:
                raise ValueError(f"no resolution predicate is defined for finding {code!r}")
            rows = probe.execute(
                "SELECT issue, slot, play, detail FROM finding WHERE code=?", (code,)).fetchall()
            if len(rows) != entry["expected_rows"]:
                raise ValueError(
                    f"{code}: ledger expects {entry['expected_rows']} findings, database holds "
                    f"{len(rows)}")
            for row in rows:
                observation = probe.execute(
                    "SELECT halftime_score, score FROM observation "
                    "WHERE issue=? AND slot=? AND play=?",
                    (row["issue"], row["slot"], row["play"])).fetchone()
                if observation is None:
                    raise ValueError(f"{code}: {row['issue']}/{row['slot']} has no observation")
                if not PREDICATES[code](observation["halftime_score"], observation["score"]):
                    raise ValueError(
                        f"{code}: {row['issue']}/{row['slot']}/{row['play']} still contradicts "
                        "its own score; refusing to supersede")
            planned.append((entry, code, new_code, rows))
    finally:
        probe.close()

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

    connection = sqlite3.connect(database, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(BATCH_DDL)
        connection.execute(ROW_DDL)
        row_count = 0
        for entry, code, new_code, rows in planned:
            detail = json.dumps({**entry["detail"], "superseded_code": code,
                                 "supersession_batch_id": batch_id},
                                ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for row in rows:
                connection.execute(
                    f"INSERT INTO {ROW_TABLE} VALUES (?,?,?,?,?,?,?,?)",
                    (row["issue"], row["slot"], row["play"], code, new_code, row["detail"],
                     batch_id, applied_at))
                updated = connection.execute(
                    "UPDATE finding SET code=?, detail=? WHERE issue=? AND slot=? AND play=? "
                    "AND code=?", (new_code, detail, row["issue"], row["slot"], row["play"],
                                   code)).rowcount
                if updated != 1:
                    raise ValueError(f"{code}: {row['issue']}/{row['slot']} lost its target")
                row_count += 1
            entry["_new_code"], entry["_moved"] = new_code, len(rows)

        receipt_row = connection.execute("SELECT payload_json FROM receipt").fetchone()
        original_receipt = receipt_row["payload_json"] if receipt_row else "{}"
        connection.execute(f"INSERT INTO {BATCH_TABLE} VALUES (?,?,?,?,?,?,?)",
                           (batch_id, applied_at, approval_note.strip(), row_count,
                            original_receipt, ledger_bytes.decode("utf-8"),
                            str(backup_path.resolve())))
        if receipt_row is not None:
            receipt = json.loads(original_receipt)
            counts = receipt.get("findings_by_code", {})
            for entry in supersessions:
                code, new_code = entry["code"], entry["superseded_code"]
                moved = counts.pop(code, 0)
                if moved != entry["expected_rows"]:
                    raise ValueError(
                        f"{code}: receipt records {moved} findings, ledger expects "
                        f"{entry['expected_rows']}")
                counts[new_code] = counts.get(new_code, 0) + moved
            receipt["findings_by_code"] = counts
            receipt["finding_supersession_batch_id"] = batch_id
            receipt["findings_superseded_at"] = applied_at
            receipt["finding_supersession_note"] = (
                "Findings whose subject a later owner-approved correction resolved keep their "
                "original rows in finding_supersession and are re-coded here.")
            connection.execute("UPDATE receipt SET payload_json=?",
                               (json.dumps(receipt, ensure_ascii=False),))
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()

    return {"status": "applied", "batch_id": batch_id, "rows": row_count,
            "backup": str(backup_path)}
