#!/usr/bin/env python3
"""Independently replay the #479 half-time correction and emit a verification report.

Read-only. Re-reads the preserved evidence bytes, re-checks their hashes, re-extracts
each source's half-time claim and re-corroborates it, then confirms the sealed database
now holds exactly those values and that the pre-correction backup still holds the
originals. Writes results/bj479_halftime_correction_v1/correction_verification.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.settlement_halftime_evidence import EXTRACTORS, corroborate  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def build_report(database: Path, ledger_path: Path, backup_path: Path) -> dict:
    """Re-derive every corrected value from preserved evidence and compare to the database."""
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema") != "bj479_halftime_correction_ledger_v1":
        raise ValueError("Wrong ledger schema")
    database = database.resolve()
    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        batch = con.execute("""SELECT batch_id, applied_at, note, row_count, fixture_count,
            evidence_manifest_json, backup_path FROM halftime_correction_batch""").fetchall()
        if len(batch) != 1:
            raise ValueError("Expected exactly one applied half-time correction batch")
        batch_id, applied_at, note, row_count, fixture_count, manifest_json, recorded_backup = batch[0]
        audited = {(r[0], r[1]): r[2] for r in con.execute(
            "SELECT issue, slot, batch_id FROM halftime_correction GROUP BY issue, slot")}
        if len(audited) != fixture_count or any(v != batch_id for v in audited.values()):
            raise ValueError("Audit rows do not match the recorded batch")

        corrections, evidence_checked, all_agree = [], 0, True
        for entry in ledger["corrections"]:
            fixture = dict(entry["fixture"])
            claims, sources = {}, []
            for item in entry["evidence"]:
                payload = Path(item["path"]).read_bytes()
                actual = hashlib.sha256(payload).hexdigest()
                if actual != item["sha256"]:
                    raise ValueError(f"evidence hash mismatch for {item['path']}")
                evidence_checked += 1
                claim = EXTRACTORS[item["source_id"]](payload, fixture)
                claims[item["source_id"]] = claim
                sources.append({"source_id": item["source_id"], "url": item["url"],
                                "sha256": actual, "bytes": len(payload),
                                "half_time": f"{claim['home']}-{claim['away']}",
                                "full_time": f"{claim['ft_home']}-{claim['ft_away']}"})
            home, away = corroborate(claims)
            replayed = f"{home}-{away}"
            rows = con.execute("""SELECT DISTINCT halftime_score, score FROM observation
                WHERE issue=? AND slot=?""", (entry["issue"], entry["slot"])).fetchall()
            db_values = sorted({r[0] for r in rows})
            db_full = sorted({r[1] for r in rows})
            plays = con.execute("""SELECT COUNT(*) FROM observation WHERE issue=? AND slot=?""",
                                (entry["issue"], entry["slot"])).fetchone()[0]
            agrees = (db_values == [entry["new_halftime_score"]] == [replayed]
                      and db_full == [entry["ft_score"]] and plays == len(entry["plays"]))
            all_agree = all_agree and agrees
            corrections.append({
                "issue": entry["issue"], "slot": entry["slot"], "plays": plays,
                "old_half_time": entry["old_halftime_score"], "new_half_time": replayed,
                "ledger_new_half_time": entry["new_halftime_score"],
                "full_time": db_full[0] if len(db_full) == 1 else db_full,
                "database_half_time": db_values,
                "corroborating_sources": sorted(claims),
                "sources": sources, "replay_agrees": agrees})

        con.execute("PRAGMA query_only=ON")
        receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
    finally:
        con.close()

    backup = Path(backup_path).resolve()
    backup_con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    try:
        quick = backup_con.execute("PRAGMA quick_check").fetchone()[0]
        holds_original = all(
            [r[0] for r in backup_con.execute(
                "SELECT DISTINCT halftime_score FROM observation WHERE issue=? AND slot=?",
                (entry["issue"], entry["slot"]))] == [entry["old_halftime_score"]]
            for entry in ledger["corrections"])
    finally:
        backup_con.close()

    return {
        "schema": "bj479_halftime_correction_verification_v1",
        "database": str(database),
        "database_sha256": _sha256(database),
        "batch_id": batch_id, "applied_at": applied_at, "note": note,
        "batch_rows": row_count, "batch_fixtures": fixture_count,
        "recorded_backup": recorded_backup,
        "evidence_manifest": json.loads(manifest_json),
        "corrections": corrections,
        "replay": {"evidence_files_verified": evidence_checked,
                   "all_hashes_match": True, "all_values_reproduced": all_agree},
        "backup": {"path": str(backup), "quick_check": quick,
                   "holds_original_values": holds_original},
        "receipt": {k: receipt.get(k) for k in (
            "data_sha256", "halftime_correction_batch_id", "corrected_halftime_observations",
            "corrected_halftime_fixtures", "correction_batch_id", "corrected_options")},
        "conclusion": {
            "verified": bool(all_agree and holds_original and quick == "ok"),
            "fixtures": fixture_count, "observations": row_count,
            "full_time_unchanged": all(c["full_time"] ==
                                       next(e["ft_score"] for e in ledger["corrections"]
                                            if e["issue"] == c["issue"] and e["slot"] == c["slot"])
                                       for c in corrections),
            "limitations": [
                "Corroboration is external: the 500 and Nowscore sources carry the same wrong "
                "half-time value, so neither can corroborate its own correction.",
                "Replaying the build from the archived raw bytes reproduces the source's wrong "
                "half-time value by design; this correction is a separately recorded layer, "
                "exactly as the earlier SP correction is.",
                "Half-time is excluded from the decision basis (see src/decision_api); no "
                "betting, SP or settlement derivation consumes the corrected field.",
            ],
        },
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.database, args.ledger, args.backup)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(args.out), **report["conclusion"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
