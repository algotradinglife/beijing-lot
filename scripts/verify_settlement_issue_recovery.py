#!/usr/bin/env python3
"""Independently replay the #479 issue recovery and emit a verification report.

Read-only. Re-reads the preserved archive bytes, re-checks their hashes, re-parses every
play page, re-derives each recovered value and compares it to the sealed database, then
confirms the pre-recovery backup still holds the original state.

Writes results/bj479_issue_recovery_v1/issue_recovery_verification.json.
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

from src.nowscore_settlement import PLAYS, expected_option, parse_page  # noqa: E402
from src.settlement_issue_recovery import settled_option  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def _replay_evidence(entry: dict) -> tuple[dict, list]:
    """Verify every archive page against its recorded hash, then re-parse it."""
    rows, sources = {}, []
    for item in entry["evidence"]:
        payload = Path(item["path"]).read_bytes()
        actual = hashlib.sha256(payload).hexdigest()
        if actual != item["sha256"]:
            raise ValueError(f"evidence hash mismatch for {item['path']}")
        sources.append({"typeid": item["typeid"], "url": item["url"], "sha256": actual,
                        "bytes": len(payload)})
        for row in parse_page(payload, entry["issue"], item["typeid"]):
            # The applier stamps each stored row with the bytes that back it; replay must
            # compare against the same stamp.
            row["source_sha256"] = actual
            rows[(row["slot"], row["play"])] = row
    return rows, sources


def build_report(database: Path, ledger_path: Path, backup_path: Path) -> dict:
    """Re-derive every recovered value from preserved evidence and compare to the database."""
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    if ledger.get("schema") != "bj479_issue_recovery_ledger_v1":
        raise ValueError("Wrong ledger schema")
    batch_id = hashlib.sha256(ledger_bytes).hexdigest()
    database = database.resolve()

    con = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        recorded = con.execute("""SELECT batch_id, applied_at, note, added_fixtures,
            added_observations, gap_fixtures, gap_observations, evidence_manifest_json,
            backup_path FROM issue_recovery_batch""").fetchall()
        if len(recorded) != 1:
            raise ValueError("Expected exactly one applied recovery batch")
        (recorded_id, applied_at, note, added_fixtures, added_observations, gap_fixtures,
         gap_observations, manifest_json, recorded_backup) = recorded[0]
        if recorded_id != batch_id:
            raise ValueError(f"Recorded batch {recorded_id} does not match the ledger {batch_id}")

        additions, evidence_checked, all_agree = [], 0, True
        for entry in ledger["additions"]:
            rows, sources = _replay_evidence(entry)
            evidence_checked += len(sources)
            fixtures = {slot for slot, _ in rows}
            mismatches = []
            for (slot, play), row in sorted(rows.items()):
                held = con.execute(
                    """SELECT score, halftime_score, expected_option, source_sha256
                       FROM observation WHERE issue=? AND slot=? AND play=?""",
                    (entry["issue"], slot, play)).fetchone()
                sp = {r[0]: r[1] for r in con.execute(
                    """SELECT s.option, s.sp FROM option_sp s JOIN observation o
                       USING(observation_id)
                       WHERE o.issue=? AND o.slot=? AND o.play=? AND s.sp IS NOT NULL""",
                    (entry["issue"], slot, play))}
                expected_sp = {o["option"]: o["sp"] for o in row["options"]
                               if o["sp"] is not None}
                if held is None or (held[0], held[1], held[2], held[3]) != (
                        row["score"], row["halftime_score"], expected_option(row),
                        row["source_sha256"]) or sp != expected_sp:
                    mismatches.append({"slot": slot, "play": play, "database": held,
                                       "replayed": [row["score"], row["halftime_score"],
                                                    expected_option(row), row["source_sha256"]],
                                       "database_sp": sp, "replayed_sp": expected_sp})
            agrees = not mismatches and len(fixtures) == entry["expected_fixtures"]
            all_agree = all_agree and agrees
            additions.append({
                "issue": entry["issue"], "expected_fixtures": entry["expected_fixtures"],
                "replayed_fixtures": len(fixtures), "replayed_observations": len(rows),
                "mismatches": mismatches[:5], "mismatch_count": len(mismatches),
                "sources": sources, "replay_agrees": agrees})

        gaps, gap_mismatches = [], []
        for entry in ledger["gap_fills"]:
            rows, sources = _replay_evidence(entry)
            evidence_checked += len(sources)
            audited = con.execute(
                """SELECT g.observation_id, g.slot, g.play, g.native_match_id, g.old_score,
                          g.new_score, g.old_halftime_score, g.new_halftime_score,
                          g.new_expected_option, g.evidence_sha256, o.score, o.halftime_score,
                          o.expected_option, o.payload_json
                   FROM issue_recovery_gap g JOIN observation o USING(observation_id)
                   WHERE g.issue=? ORDER BY g.slot, g.play""", (entry["issue"],)).fetchall()
            for (observation_id, slot, play, native_id, old_score, new_score, old_halftime,
                 new_halftime, new_option, evidence_sha256, db_score, db_halftime,
                 db_option, payload) in audited:
                row = rows.get((slot, play))
                replayed = None if row is None else (
                    row["score"], row["halftime_score"],
                    settled_option(row, json.loads(payload)))
                holds = (db_score, db_halftime, db_option) == (new_score, new_halftime, new_option)
                if replayed != (new_score, new_halftime, new_option) or not holds:
                    gap_mismatches.append({"slot": slot, "play": play,
                                           "database": [db_score, db_halftime, db_option],
                                           "replayed": replayed, "audit": [new_score, new_halftime,
                                                                           new_option]})
                gaps.append({"slot": slot, "play": play, "native_match_id": native_id,
                             "old_score": old_score, "new_score": new_score,
                             "evidence_sha256": evidence_sha256})
            slots = sorted({g["slot"] for g in gaps})
            if slots != entry["expected_gap_slots"]:
                gap_mismatches.append({"slots": slots, "expected": entry["expected_gap_slots"]})
        gap_agrees = not gap_mismatches and len(gaps) == gap_observations
        all_agree = all_agree and gap_agrees

        capture, recorded_evidence = [], 0
        for entry in ledger["additions"]:
            for item in entry["evidence"]:
                held = con.execute("SELECT source_url, sha256 FROM capture WHERE issue=? AND typeid=?",
                                   (entry["issue"], item["typeid"])).fetchone()
                if held is not None and (held[0], held[1]) != (item["url"], item["sha256"]):
                    capture.append({"issue": entry["issue"], "typeid": item["typeid"],
                                    "database": list(held), "evidence": [item["url"], item["sha256"]]})
        for entry in ledger["additions"] + ledger["gap_fills"]:
            for item in entry["evidence"]:
                if con.execute("""SELECT 1 FROM issue_recovery_capture
                        WHERE batch_id=? AND issue=? AND typeid=? AND sha256=?""",
                        (batch_id, entry["issue"], item["typeid"], item["sha256"])).fetchone():
                    recorded_evidence += 1
        receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
        con.execute("PRAGMA query_only=ON")
    finally:
        con.close()

    backup = Path(backup_path).resolve()
    backup_con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    try:
        quick = backup_con.execute("PRAGMA quick_check").fetchone()[0]
        empty_before = all(backup_con.execute(
            "SELECT COUNT(*) FROM observation WHERE issue=?", (e["issue"],)).fetchone()[0] == 0
            for e in ledger["additions"])
        unsettled_before = all(backup_con.execute(
            """SELECT COUNT(*) FROM observation WHERE issue=? AND slot=? AND play=?
               AND score='-'""", (entry["issue"], g["slot"], g["play"])).fetchone()[0] == 1
            for entry in ledger["gap_fills"] for g in gaps if g["slot"] in entry["expected_gap_slots"])
    finally:
        backup_con.close()

    verified = bool(all_agree and not capture and recorded_evidence == evidence_checked
                    and empty_before and unsettled_before and quick == "ok")
    return {
        "schema": "bj479_issue_recovery_verification_v1",
        "database": str(database),
        "database_sha256": _sha256(database),
        "batch_id": batch_id, "applied_at": applied_at, "note": note,
        "recorded_backup": recorded_backup,
        "evidence_manifest": json.loads(manifest_json),
        "ledger_authorization": ledger["authorization"],
        "additions": additions,
        "gap_fill": {"issue": ledger["gap_fills"][0]["issue"] if ledger["gap_fills"] else None,
                     "fixtures": sorted({g["slot"] for g in gaps}),
                     "observations": len(gaps), "mismatches": gap_mismatches[:5],
                     "replay_agrees": gap_agrees},
        "capture_rebind_mismatches": capture,
        "recorded_evidence_files": recorded_evidence,
        "replay": {"evidence_files_verified": evidence_checked, "all_hashes_match": True,
                   "all_values_reproduced": all_agree},
        "backup": {"path": str(backup), "quick_check": quick,
                   "additions_absent_before": empty_before,
                   "gap_fixtures_unsettled_before": unsettled_before},
        "receipt": {k: receipt.get(k) for k in (
            "data_sha256", "effective_source", "recovered_issues", "recovered_fixtures",
            "recovered_observations", "gap_filled_issues", "gap_filled_fixtures",
            "gap_filled_observations", "issue_recovery_batch_id")},
        "conclusion": {
            "verified": verified,
            "recorded_added_fixtures": added_fixtures,
            "recorded_added_observations": added_observations,
            "recorded_gap_fixtures": gap_fixtures,
            "recorded_gap_observations": gap_observations,
            "limitations": [
                "The recovered rows come from the source's own archive board, not from an "
                "independent provider, so they carry the source's own values; 澳客 corroborates "
                "a strict subset of the fixtures and was checked separately.",
                "The recovery is a recorded layer, not a rebuild: the release bundle binds its "
                "request URLs into the source scope, so re-verifying it would require "
                "re-capturing all 8,325 pages. The original build receipt and its hashes are "
                "preserved in issue_recovery_batch.original_receipt_json.",
                "observation.payload_json keeps the source's own bytes and is deliberately not "
                "rewritten, so re-deriving from the payload of a gap-filled row shows the "
                "live board's unsettled values rather than the archive's.",
                "For fixtures whose archive row leaves the handicap cell empty, the settled "
                "option is derived from the release's own handicap and the archive's score, "
                "and must equal the result the archive reports.",
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
    print(json.dumps({"out": str(args.out), "verified": report["conclusion"]["verified"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
