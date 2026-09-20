#!/usr/bin/env python3
"""Independently replay the #479 corrections and emit a verification report.

Read-only. Re-reads the preserved evidence bytes, re-checks their hashes, re-extracts
every source's claim and re-corroborates it, then confirms the sealed database now holds
exactly those values and that the pre-correction backups still hold the originals.

Both batches are replayed when their ledgers are supplied: the half-time correction and
the dependent half/full settlement correction. Writes
results/bj479_halftime_correction_v1/correction_verification.json.
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

from src.settlement_halftime_evidence import (  # noqa: E402
    EXTRACTORS,
    HALF_FULL_EXTRACTORS,
    corroborate,
    corroborate_half_full,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_evidence(entry: dict, key: str, extractors: dict) -> tuple[dict, list]:
    """Verify every evidence file against its recorded hash, then re-extract its claim."""
    claims, sources = {}, []
    for item in entry[key]:
        payload = Path(item["path"]).read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != item["sha256"]:
            raise ValueError(f"evidence hash mismatch for {item['path']}")
        claims[item["source_id"]] = extractors[item["source_id"]](payload, entry["_fixture"])
        sources.append({"source_id": item["source_id"], "url": item["url"],
                        "sha256": actual, "bytes": len(payload)})
    return claims, sources


def _half_full_section(database: Path, ledger_path: Path, backup_path: Path) -> dict:
    """Replay the half/full settlement correction against preserved evidence."""
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema") != "bj479_half_full_correction_ledger_v1":
        raise ValueError("Wrong half/full ledger schema")
    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        batch = con.execute("""SELECT batch_id, applied_at, note, row_count, fixture_count
            FROM half_full_correction_batch""").fetchall()
        if len(batch) != 1:
            raise ValueError("Expected exactly one applied half/full correction batch")
        batch_id, applied_at, note, row_count, fixture_count = batch[0]
        corrections, evidence_checked, all_agree = [], 0, True
        for entry in ledger["corrections"]:
            fixture = dict(entry["fixture"])
            fixture["slot"] = entry["slot"]
            fixture["ft_home"], fixture["ft_away"] = (int(x) for x in entry["full_time"].split("-"))
            entry = dict(entry, _fixture=fixture)
            half_claims, half_sources = _read_evidence(entry, "half_time_evidence", EXTRACTORS)
            full_claims, full_sources = _read_evidence(entry, "half_full_evidence",
                                                       HALF_FULL_EXTRACTORS)
            evidence_checked += len(half_sources) + len(full_sources)
            half_time = corroborate(half_claims)
            settled = corroborate_half_full(half_time,
                                            (fixture["ft_home"], fixture["ft_away"]), full_claims)
            row = con.execute("""SELECT observation_id, expected_option FROM observation
                WHERE issue=? AND slot=? AND play=?""",
                              (entry["issue"], entry["slot"], entry["play"])).fetchone()
            sp_rows = [r for r in con.execute(
                """SELECT s.option, s.sp FROM option_sp s JOIN observation o USING(observation_id)
                   WHERE o.issue=? AND o.slot=? AND o.play=? AND s.sp IS NOT NULL""",
                (entry["issue"], entry["slot"], entry["play"]))]
            db_sp = {r[0]: r[1] for r in sp_rows}
            agrees = (row is not None and row[1] == settled["option"] == entry["new_option"]
                      and db_sp == {settled["option"]: settled["sp"]})
            all_agree = all_agree and agrees
            corrections.append({
                "issue": entry["issue"], "slot": entry["slot"], "play": entry["play"],
                "half_time": f"{half_time[0]}-{half_time[1]}", "full_time": entry["full_time"],
                "old_option": entry["old_option"], "new_option": settled["option"],
                "settlement_sp": settled["sp"],
                "database_option": row[1] if row else None,
                "database_sp": db_sp,
                "corroborating_sources": sorted(set(half_claims) | set(full_claims)),
                "sources": half_sources + full_sources, "replay_agrees": agrees})
    finally:
        con.close()

    backup = Path(backup_path).resolve()
    backup_con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    try:
        quick = backup_con.execute("PRAGMA quick_check").fetchone()[0]
        holds_original = all(
            backup_con.execute("""SELECT expected_option FROM observation
                WHERE issue=? AND slot=? AND play=?""",
                               (e["issue"], e["slot"], e["play"])).fetchone()[0] == e["old_option"]
            for e in ledger["corrections"])
    finally:
        backup_con.close()

    return {
        "schema": "bj479_half_full_correction_verification_v1",
        "batch_id": batch_id, "applied_at": applied_at, "note": note,
        "batch_rows": row_count, "batch_fixtures": fixture_count,
        "corrections": corrections,
        "replay": {"evidence_files_verified": evidence_checked,
                   "all_hashes_match": True, "all_values_reproduced": all_agree},
        "backup": {"path": str(backup), "quick_check": quick,
                   "holds_original_options": holds_original},
        "verified": bool(all_agree and holds_original and quick == "ok"),
    }


def build_report(database: Path, ledger_path: Path, backup_path: Path,
                 half_full_ledger: Path | None = None,
                 half_full_backup: Path | None = None) -> dict:
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

    half_full = None
    if half_full_ledger is not None and half_full_backup is not None:
        half_full = _half_full_section(database, Path(half_full_ledger), Path(half_full_backup))

    limitations = [
        "Corroboration is external: the 500 and Nowscore sources carry the same wrong "
        "half-time value, so neither can corroborate its own correction.",
        "Replaying the build from the archived raw bytes reproduces the source's original "
        "values by design; both corrections are separately recorded layers, exactly as the "
        "earlier SP correction is.",
        "observation.payload_json keeps the source's own bytes and is deliberately not "
        "rewritten, so any re-derivation from the payload shows the source's original values.",
        "The half-time score IS an input to the bq half/full derivation "
        "(src/nowscore_settlement.py expected_option), so the half-time batch alone left two "
        "fixtures whose half/full settlement contradicted the corrected half time. The second "
        "batch corrects those options and relocates the settlement SP, whose value both sites "
        "publish identically; the remaining rows were already consistent.",
    ]

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
        "half_full": half_full,
        "receipt": {k: receipt.get(k) for k in (
            "data_sha256", "halftime_correction_batch_id", "corrected_halftime_observations",
            "corrected_halftime_fixtures", "correction_batch_id", "corrected_options",
            "half_full_correction_batch_id", "corrected_half_full_observations")},
        "conclusion": {
            "verified": bool(all_agree and holds_original and quick == "ok"
                             and (half_full is None or half_full["verified"])),
            "fixtures": fixture_count, "observations": row_count,
            "half_full_verified": None if half_full is None else half_full["verified"],
            "full_time_unchanged": all(c["full_time"] ==
                                       next(e["ft_score"] for e in ledger["corrections"]
                                            if e["issue"] == c["issue"] and e["slot"] == c["slot"])
                                       for c in corrections),
            "limitations": limitations,
        },
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--half-full-ledger", type=Path)
    parser.add_argument("--half-full-backup", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.database, args.ledger, args.backup,
                          half_full_ledger=args.half_full_ledger,
                          half_full_backup=args.half_full_backup)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"out": str(args.out), **report["conclusion"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
