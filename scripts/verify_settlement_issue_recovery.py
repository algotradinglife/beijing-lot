#!/usr/bin/env python3
"""Independently replay the #479 issue recovery and emit a verification report.

Read-only. Re-reads the preserved archive bytes, re-checks their hashes, re-parses every
play page, re-derives each recovered value and compares it to the sealed database, then
confirms the pre-recovery backup still holds the original state.

The comparison is deliberately complete: for additions it checks every stored column and
the whole option vector and rejects missing or extra rows; for gap fills it checks the
completed score, half-time score, derived option and the whole settlement SP vector, and
takes the fallback handicap from the backup rather than from the database the recovery
mutated.

Writes results/bj479_issue_recovery_v1/issue_recovery_verification.json and exits
non-zero when the report does not verify.
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

from src.nowscore_settlement import canonical, expected_option, parse_page  # noqa: E402
from src.settlement_issue_recovery import (  # noqa: E402
    settled_option, settlement_vector_matches)


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
        if actual != item["sha256"] or len(payload) != item["byte_count"]:
            raise ValueError(f"evidence does not match the ledger for {item['path']}")
        sources.append({"typeid": item["typeid"], "url": item["url"], "sha256": actual,
                        "bytes": len(payload)})
        for row in parse_page(payload, entry["issue"], item["typeid"]):
            # The applier stamps each stored row with the bytes that back it; replay must
            # compare against the same stamp.
            row["source_sha256"] = actual
            row["source_url"] = item["url"]
            row["received_at"] = item["received_at"]
            rows[(row["slot"], row["play"])] = row
    return rows, sources


def _vector(row: dict) -> list[dict]:
    return [{"option": o["option"], "raw_sp": o["raw_sp"], "sp": o["sp"],
             "cell_id": o["cell_id"]} for o in row["options"]]


def build_report(database: Path, ledger_path: Path, backup_path: Path) -> dict:
    """Re-derive every recovered value from preserved evidence and compare to the database."""
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    if ledger.get("schema") != "bj479_issue_recovery_ledger_v1":
        raise ValueError("Wrong ledger schema")
    batch_id = hashlib.sha256(ledger_bytes).hexdigest()
    database = database.resolve()
    backup = Path(backup_path).resolve()

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
            issue = entry["issue"]
            fixtures = {slot for slot, _ in rows}
            mismatches = []
            for (slot, play), row in sorted(rows.items()):
                held = con.execute(
                    """SELECT observation_id, native_match_id, status, score, halftime_score,
                              expected_option, source_sha256, source_url, received_at,
                              payload_json
                       FROM observation WHERE issue=? AND slot=? AND play=?""",
                    (issue, slot, play)).fetchone()
                if held is None:
                    mismatches.append({"slot": slot, "play": play, "database": None,
                                       "replayed": row["native_match_id"]})
                    continue
                (observation_id, native_id, status, score, halftime, option, source_sha256,
                 source_url, received_at, payload) = held
                stored_vector = [
                    {"option": o, "raw_sp": r, "sp": s, "cell_id": c}
                    for o, r, s, c in con.execute(
                        "SELECT option, raw_sp, sp, cell_id FROM option_sp "
                        "WHERE observation_id=? ORDER BY rowid", (observation_id,))]
                # The stored payload is the canonical form the applier wrote, so replay
                # rebuilds it from the re-parsed row rather than trusting the database.
                want = (row["native_match_id"], row["status"], row["score"],
                        row["halftime_score"], expected_option(row), row["source_sha256"],
                        row["source_url"], row["received_at"],
                        json.dumps(json.loads(canonical(row)), ensure_ascii=False))
                held_key = (native_id, status, score, halftime, option, source_sha256,
                            source_url, received_at,
                            json.dumps(json.loads(payload), ensure_ascii=False))
                if held_key != want or stored_vector != _vector(row):
                    mismatches.append({"slot": slot, "play": play,
                                       "database": [native_id, status, score, halftime, option,
                                                    source_sha256, source_url, received_at],
                                       "replayed": [row["native_match_id"], row["status"],
                                                    row["score"], row["halftime_score"],
                                                    expected_option(row), row["source_sha256"],
                                                    row["source_url"], row["received_at"]],
                                       "database_options": stored_vector,
                                       "replayed_options": _vector(row)})
            stored_count = con.execute(
                "SELECT COUNT(*) FROM observation WHERE issue=?", (issue,)).fetchone()[0]
            if stored_count != len(rows):
                mismatches.append({"issue": issue, "stored_observations": stored_count,
                                   "replayed_observations": len(rows)})
            agrees = not mismatches and len(fixtures) == entry["expected_fixtures"]
            all_agree = all_agree and agrees
            additions.append({
                "issue": issue, "expected_fixtures": entry["expected_fixtures"],
                "replayed_fixtures": len(fixtures), "replayed_observations": len(rows),
                "mismatches": mismatches[:5], "mismatch_count": len(mismatches),
                "sources": sources, "replay_agrees": agrees})

        # The fallback handicap must come from the pre-recovery snapshot, not from the
        # database the recovery mutated, so the derivation is bound to evidence the
        # recovery cannot have touched.
        backup_con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
        try:
            quick = backup_con.execute("PRAGMA quick_check").fetchone()[0]
            gap_reports, gap_mismatches, gap_fixtures_seen, gap_observations_seen = (
                [], [], set(), 0)
            for entry in ledger["gap_fills"]:
                issue = entry["issue"]
                rows, sources = _replay_evidence(entry)
                evidence_checked += len(sources)
                audited = con.execute(
                    """SELECT g.observation_id, g.slot, g.play, g.native_match_id, g.old_score,
                              g.new_score, g.old_halftime_score, g.new_halftime_score,
                              g.new_expected_option, g.new_options_json, g.evidence_sha256,
                              o.score, o.halftime_score, o.expected_option
                       FROM issue_recovery_gap g JOIN observation o USING(observation_id)
                       WHERE g.batch_id=? AND g.issue=? ORDER BY g.slot, g.play""",
                    (batch_id, issue)).fetchall()
                issue_mismatches, slots = [], set()
                for (observation_id, slot, play, native_id, old_score, new_score, old_halftime,
                     new_halftime, new_option, new_options, evidence_sha256, db_score,
                     db_halftime, db_option) in audited:
                    row = rows.get((slot, play))
                    before = backup_con.execute(
                        """SELECT payload_json, score, halftime_score FROM observation
                           WHERE issue=? AND slot=? AND play=?""", (issue, slot, play)).fetchone()
                    slots.add(slot)
                    gap_observations_seen += 1
                    if row is None or before is None:
                        issue_mismatches.append({"slot": slot, "play": play,
                                                 "evidence_row": row is not None,
                                                 "backup_row": before is not None})
                        continue
                    replayed = (row["score"], row["halftime_score"],
                                settled_option(row, json.loads(before[0])))
                    stored_vector = [
                        {"option": o, "raw_sp": r, "sp": s, "cell_id": c}
                        for o, r, s, c in con.execute(
                            "SELECT option, raw_sp, sp, cell_id FROM option_sp "
                            "WHERE observation_id=? ORDER BY rowid", (observation_id,))]
                    ok = (replayed == (new_score, new_halftime, new_option)
                          and (db_score, db_halftime, db_option) == (new_score, new_halftime,
                                                                    new_option)
                          and new_options == json.dumps(_vector(row), ensure_ascii=False)
                          and settlement_vector_matches(stored_vector, row)
                          and row["source_sha256"] == evidence_sha256
                          and before[1] in ("", "-")
                          and before[2] == old_halftime and old_score == before[1])
                    if not ok:
                        issue_mismatches.append(
                            {"slot": slot, "play": play,
                             "database": [db_score, db_halftime, db_option],
                             "replayed": replayed, "audit": [new_score, new_halftime,
                                                             new_option],
                             "stored_options": stored_vector,
                             "replayed_options": _vector(row)})
                if sorted(slots) != entry["expected_gap_slots"]:
                    issue_mismatches.append({"slots": sorted(slots),
                                             "expected": entry["expected_gap_slots"]})
                gap_fixtures_seen |= {(issue, slot) for slot in slots}
                gap_mismatches.extend(issue_mismatches)
                gap_reports.append({"issue": issue, "fixtures": sorted(slots),
                                    "observations": len(audited), "sources": sources,
                                    "mismatch_count": len(issue_mismatches),
                                    "replay_agrees": not issue_mismatches})
            gap_agrees = (not gap_mismatches and len(gap_fixtures_seen) == gap_fixtures
                          and gap_observations_seen == gap_observations)
            all_agree = all_agree and gap_agrees

            capture, recorded_evidence = [], 0
            for entry in ledger["additions"]:
                for item in entry["evidence"]:
                    held = con.execute(
                        "SELECT source_url, sha256 FROM capture WHERE issue=? AND typeid=?",
                        (entry["issue"], item["typeid"])).fetchone()
                    if held is None or (held[0], held[1]) != (item["url"], item["sha256"]):
                        capture.append({"issue": entry["issue"], "typeid": item["typeid"],
                                        "database": list(held) if held else None,
                                        "evidence": [item["url"], item["sha256"]]})
            for entry in ledger["additions"] + ledger["gap_fills"]:
                for item in entry["evidence"]:
                    if con.execute("""SELECT 1 FROM issue_recovery_capture
                            WHERE batch_id=? AND issue=? AND typeid=? AND sha256=?""",
                            (batch_id, entry["issue"], item["typeid"],
                             item["sha256"])).fetchone():
                        recorded_evidence += 1
            empty_before = all(backup_con.execute(
                "SELECT COUNT(*) FROM observation WHERE issue=?",
                (e["issue"],)).fetchone()[0] == 0 for e in ledger["additions"])
        finally:
            backup_con.close()

        receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
        con.execute("PRAGMA query_only=ON")
    finally:
        con.close()

    receipt_bound = all(receipt.get(k) == v for k, v in (
        ("issue_recovery_batch_id", batch_id),
        ("recovered_fixtures", added_fixtures),
        ("recovered_observations", added_observations),
        ("gap_filled_fixtures", gap_fixtures),
        ("gap_filled_observations", gap_observations),
    ))
    verified = bool(all_agree and not capture and recorded_evidence == evidence_checked
                    and empty_before and quick == "ok" and receipt_bound)
    return {
        "schema": "bj479_issue_recovery_verification_v1",
        "database": str(database),
        "database_sha256": _sha256(database),
        "batch_id": batch_id, "applied_at": applied_at, "note": note,
        "recorded_backup": recorded_backup,
        "evidence_manifest": json.loads(manifest_json),
        "ledger_authorization": ledger["authorization"],
        "additions": additions,
        "gap_fill": {"issues": [g["issue"] for g in gap_reports],
                     "fixtures": sorted({slot for _, slot in gap_fixtures_seen}),
                     "observations": gap_observations_seen,
                     "per_issue": gap_reports, "mismatches": gap_mismatches[:5],
                     "replay_agrees": gap_agrees},
        "capture_rebind_mismatches": capture,
        "recorded_evidence_files": recorded_evidence,
        "replay": {"evidence_files_verified": evidence_checked, "all_hashes_match": True,
                   "all_values_reproduced": all_agree},
        "backup": {"path": str(backup), "quick_check": quick,
                   "additions_absent_before": empty_before},
        "receipt": {k: receipt.get(k) for k in (
            "data_sha256", "effective_source", "recovered_issues", "recovered_fixtures",
            "recovered_observations", "gap_filled_issues", "gap_filled_fixtures",
            "gap_filled_observations", "issue_recovery_batch_id")},
        "receipt_bound": receipt_bound,
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
                "and must equal the result the archive reports. Replay takes that handicap "
                "from the pre-recovery backup.",
                "The live board publishes pre-match reference odds in the settlement column "
                "while a fixture is unplayed; gap-filled rows had that vector replaced by the "
                "archive's settlement SP, and the replaced vector is preserved in "
                "issue_recovery_gap.replaced_options_json.",
            ],
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.database, args.ledger, args.backup)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    verified = report["conclusion"]["verified"]
    print(json.dumps({"out": str(args.out), "verified": verified}, ensure_ascii=False))
    # A rejected recovery must fail the acceptance command, not just report itself.
    return 0 if verified else 1


if __name__ == "__main__":
    sys.exit(main())
