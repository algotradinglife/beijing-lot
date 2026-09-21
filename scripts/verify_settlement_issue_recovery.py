#!/usr/bin/env python3
"""Independently replay the #479 issue recovery and emit a verification report.

Read-only. Re-reads the preserved archive bytes, re-checks their hashes, re-parses every
play page, re-derives each recovered value and compares it to the sealed database, then
confirms the pre-recovery backup still holds the original state.

Nothing here is enumerated from the audit tables it is meant to corroborate: the added
rows must be a bijection onto the archive's fixtures, the completions are derived from the
fixtures the backup held unsettled that the archive settles, the settlement vector is
rebuilt from the backup's own option domain, and the recorded capture metadata and
evidence manifest are reconstructed from the ledger. The backup comes from this command's
own arguments rather than from the database, so it is an anchor the database cannot move.

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
    SETTLED_SCORE, expected_settlement_vector, settled_option)


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


def _vector_for(con, issue: str, slot: int, play: str) -> list[dict]:
    """A row's option vector read by fixture key, so it works on the backup as well."""
    return [{"option": o, "raw_sp": r, "sp": s, "cell_id": c} for o, r, s, c in con.execute(
        """SELECT s.option, s.raw_sp, s.sp, s.cell_id FROM option_sp s
           JOIN observation o USING(observation_id)
           WHERE o.issue=? AND o.slot=? AND o.play=? ORDER BY s.rowid""",
        (issue, slot, play))]


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
    backup_con = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
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

        # The recorded manifest must be exactly what the ledger describes, so it can be
        # presented as the verified evidence inventory.
        expected_manifest = [
            {"issue": item["issue"], "typeid": e["typeid"], "path": e["path"],
             "sha256": e["sha256"], "url": e["url"], "received_at": e["received_at"],
             "byte_count": e["byte_count"], "role": role}
            for role, entries in (("addition", ledger["additions"]),
                                  ("gap_fill", ledger["gap_fills"]))
            for item in entries for e in item["evidence"]]
        manifest_agrees = json.loads(manifest_json) == expected_manifest

        quick = backup_con.execute("PRAGMA quick_check").fetchone()[0]
        backup_tables = {row[0] for row in backup_con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        backup_is_pre_recovery = not (backup_tables & {
            "issue_recovery_batch", "issue_recovery_gap", "issue_recovery_capture"})

        additions, evidence_checked, all_agree = [], 0, True
        for entry in ledger["additions"]:
            rows, sources = _replay_evidence(entry)
            evidence_checked += len(sources)
            issue = entry["issue"]
            fixtures = {slot for slot, _ in rows}
            mismatches = []
            stored = con.execute(
                """SELECT observation_id, slot, play, native_match_id, status, score,
                          halftime_score, expected_option, source_sha256, source_url,
                          received_at, payload_json
                   FROM observation WHERE issue=?""", (issue,)).fetchall()
            # A bijection, not merely equal counts: a duplicated key must not stand in for
            # a missing archive fixture.
            if sorted((r[1], r[2]) for r in stored) != sorted(rows):
                mismatches.append({"issue": issue, "stored_rows": len(stored),
                                   "replayed_rows": len(rows)})
            for (observation_id, slot, play, native_id, status, score, halftime, option,
                 source_sha256, source_url, received_at, payload) in stored:
                row = rows.get((slot, play))
                if row is None:
                    mismatches.append({"slot": slot, "play": play, "database": None,
                                       "replayed": None})
                    continue
                held = (native_id, status, score, halftime, option, source_sha256,
                        source_url, received_at,
                        json.dumps(json.loads(payload), ensure_ascii=False))
                want = (row["native_match_id"], row["status"], row["score"],
                        row["halftime_score"], expected_option(row), row["source_sha256"],
                        row["source_url"], row["received_at"],
                        json.dumps(json.loads(canonical(row)), ensure_ascii=False))
                stored_vector = _vector_for(con, issue, slot, play)
                if held != want or stored_vector != _vector(row):
                    mismatches.append({"slot": slot, "play": play, "database": list(held),
                                       "replayed": list(want),
                                       "database_options": stored_vector,
                                       "replayed_options": _vector(row)})
            agrees = not mismatches and len(fixtures) == entry["expected_fixtures"]
            all_agree = all_agree and agrees
            additions.append({
                "issue": issue, "expected_fixtures": entry["expected_fixtures"],
                "replayed_fixtures": len(fixtures), "replayed_observations": len(rows),
                "mismatches": mismatches[:5], "mismatch_count": len(mismatches),
                "sources": sources, "replay_agrees": agrees})

        gap_reports, gap_mismatches, gap_fixtures_seen, gap_observations_seen = (
            [], [], set(), 0)
        for entry in ledger["gap_fills"]:
            issue = entry["issue"]
            rows, sources = _replay_evidence(entry)
            evidence_checked += len(sources)
            # The completions owed are the fixtures the backup held unsettled that the
            # archive settles - derived from evidence, never from the audit table.
            unsettled = {(slot, play) for slot, play in backup_con.execute(
                "SELECT slot, play FROM observation WHERE issue=? AND (score='' OR score='-')",
                (issue,))}
            required = {key for key, row in rows.items()
                        if key in unsettled and SETTLED_SCORE.match(row["score"] or "")}
            # The audit rows are read in full, then validated field by field against the
            # archive, the backup and the stored observation - their keys alone are not
            # evidence.
            audited = {(row[0], row[1]): row[2:] for row in con.execute(
                """SELECT slot, play, observation_id, native_match_id, new_score,
                          new_halftime_score, new_expected_option, new_options_json,
                          evidence_sha256, old_payload_sha256, replaced_options_json
                   FROM issue_recovery_gap WHERE batch_id=? AND issue=?""", (batch_id, issue))}
            slots = sorted({slot for slot, _ in required})
            issue_mismatches = []
            if set(audited) != required:
                issue_mismatches.append({"audit_rows": sorted(audited),
                                         "owed_completions": sorted(required)})
            if slots != entry["expected_gap_slots"]:
                issue_mismatches.append({"slots": slots,
                                         "expected": entry["expected_gap_slots"]})
            if len(required) != len(slots) * 5:
                issue_mismatches.append({"owed_completions": len(required),
                                         "owed_slots": len(slots)})
            for slot, play in sorted(required):
                row = rows[(slot, play)]
                before = backup_con.execute(
                    """SELECT payload_json, score, halftime_score, native_match_id
                       FROM observation WHERE issue=? AND slot=? AND play=?""",
                    (issue, slot, play)).fetchone()
                # Exactly one observation per owed key, so a duplicate cannot hide behind
                # the first row while the vector is read across both.
                stored_at_key = con.execute(
                    """SELECT observation_id, issue, slot, play, native_match_id, score,
                              halftime_score, expected_option, payload_json
                       FROM observation WHERE issue=? AND slot=? AND play=?""",
                    (issue, slot, play)).fetchall()
                if len(stored_at_key) != 1:
                    issue_mismatches.append({"slot": slot, "play": play,
                                             "observations_at_key": len(stored_at_key)})
                    continue
                held = stored_at_key[0]
                audit = audited.get((slot, play))
                recorded_replaced = (audit[8],) if audit is not None else None
                derived = expected_vector = None
                ok = False
                if before is not None and held is not None:
                    derived = settled_option(row, json.loads(before[0]))
                    expected_vector = expected_settlement_vector(
                        _vector_for(backup_con, issue, slot, play), row)
                    ok = (
                        # the observation must sit at the key the evidence names and hold
                        # the derived completion
                        (held[1], held[2], held[3]) == (issue, slot, play)
                        and (held[4], held[5], held[6], held[7]) == (
                            row["native_match_id"], row["score"], row["halftime_score"],
                            derived)
                        and before[3] == row["native_match_id"]
                        # the pre-recovery payload is never rewritten
                        and held[8] == before[0]
                        # and the vector is exactly what the backup's option domain implies
                        # once the archive's settlement is applied
                        and _vector_for(con, issue, slot, play) == expected_vector
                        # the preserved reference vector is evidence, so it must still be
                        # what the backup held
                        and recorded_replaced is not None
                        and recorded_replaced[0] == json.dumps(
                            _vector_for(backup_con, issue, slot, play), ensure_ascii=False)
                        # every audit binding is checked against external evidence
                        and audit is not None
                        and (audit[0], audit[1], audit[2], audit[3], audit[4]) == (
                            held[0], row["native_match_id"], row["score"],
                            row["halftime_score"], derived)
                        and audit[5] == json.dumps(_vector(row), ensure_ascii=False)
                        and audit[6] == row["source_sha256"]
                        and audit[7] == hashlib.sha256(before[0].encode()).hexdigest())
                if not ok:
                    issue_mismatches.append(
                        {"slot": slot, "play": play,
                         "database": list(held) if held else None,
                         "replayed": [issue, slot, play, row["native_match_id"], row["score"],
                                      row["halftime_score"], derived],
                         "backup_identity": before[3] if before else None,
                         "database_options": _vector_for(con, issue, slot, play),
                         "expected_options": expected_vector})
            # Anything outside the owed completions must be exactly as the backup left it,
            # so an extra completion or a stray edit cannot hide.
            for (slot, play, score, halftime, option, payload) in con.execute(
                    """SELECT slot, play, score, halftime_score, expected_option, payload_json
                       FROM observation WHERE issue=?""", (issue,)):
                if (slot, play) in required:
                    continue
                before = backup_con.execute(
                    """SELECT score, halftime_score, expected_option, payload_json
                       FROM observation WHERE issue=? AND slot=? AND play=?""",
                    (issue, slot, play)).fetchone()
                if before is None or (score, halftime, option, payload) != before:
                    issue_mismatches.append({"slot": slot, "play": play,
                                             "changed_outside_completions": True})
            gap_fixtures_seen |= {(issue, slot) for slot in slots}
            gap_observations_seen += len(required)
            gap_mismatches.extend(issue_mismatches)
            gap_reports.append({"issue": issue, "fixtures": slots,
                                "observations": len(required), "sources": sources,
                                "mismatch_count": len(issue_mismatches),
                                "replay_agrees": not issue_mismatches})
        gap_agrees = (not gap_mismatches and len(gap_fixtures_seen) == gap_fixtures
                      and gap_observations_seen == gap_observations)
        all_agree = all_agree and gap_agrees

        # Capture metadata and the recorded evidence rows are reconstructed from the ledger.
        capture, recorded_evidence = [], 0
        for role, entries in (("addition", ledger["additions"]),
                              ("gap_fill", ledger["gap_fills"])):
            for entry in entries:
                for item in entry["evidence"]:
                    row = con.execute(
                        """SELECT url, sha256, received_at, byte_count, replaced_sha256
                           FROM issue_recovery_capture
                           WHERE batch_id=? AND issue=? AND typeid=?""",
                        (batch_id, entry["issue"], item["typeid"])).fetchone()
                    if row is None or (row[0], row[1], row[2], row[3]) != (
                            item["url"], item["sha256"], item["received_at"],
                            item["byte_count"]):
                        capture.append({"issue": entry["issue"], "typeid": item["typeid"],
                                        "database": list(row) if row else None,
                                        "ledger": [item["url"], item["sha256"],
                                                   item["received_at"], item["byte_count"]]})
                        continue
                    recorded_evidence += 1
                    if role == "addition":
                        held = con.execute("SELECT source_url, sha256 FROM capture "
                                           "WHERE issue=? AND typeid=?",
                                           (entry["issue"], item["typeid"])).fetchone()
                        before = backup_con.execute(
                            "SELECT sha256 FROM capture WHERE issue=? AND typeid=?",
                            (entry["issue"], item["typeid"])).fetchone()
                        if held != (item["url"], item["sha256"]) or row[4] != (
                                before[0] if before else None):
                            capture.append({"issue": entry["issue"], "typeid": item["typeid"],
                                            "database": list(held) if held else None,
                                            "evidence": [item["url"], item["sha256"]],
                                            "replaced": row[4],
                                            "backup_sha256": before[0] if before else None})
                    elif row[4] is not None:
                        capture.append({"issue": entry["issue"], "typeid": item["typeid"],
                                        "replaced_sha256": row[4],
                                        "note": "a gap fill must not rebind capture"})
        empty_before = all(backup_con.execute(
            "SELECT COUNT(*) FROM observation WHERE issue=?",
            (e["issue"],)).fetchone()[0] == 0 for e in ledger["additions"])

        receipt = json.loads(con.execute("SELECT payload_json FROM receipt").fetchone()[0])
        con.execute("PRAGMA query_only=ON")
    finally:
        con.close()
        backup_con.close()

    receipt_bound = all(receipt.get(k) == v for k, v in (
        ("issue_recovery_batch_id", batch_id),
        ("recovered_fixtures", added_fixtures),
        ("recovered_observations", added_observations),
        ("gap_filled_fixtures", gap_fixtures),
        ("gap_filled_observations", gap_observations),
    ))
    verified = bool(all_agree and not capture and recorded_evidence == evidence_checked
                    and empty_before and quick == "ok" and receipt_bound
                    and manifest_agrees and backup_is_pre_recovery)
    return {
        "schema": "bj479_issue_recovery_verification_v1",
        "database": str(database),
        "database_sha256": _sha256(database),
        "batch_id": batch_id, "applied_at": applied_at, "note": note,
        "recorded_backup": recorded_backup,
        "evidence_manifest": json.loads(manifest_json),
        "evidence_manifest_agrees": manifest_agrees,
        "ledger_authorization": ledger["authorization"],
        "additions": additions,
        "gap_fill": {"issues": [g["issue"] for g in gap_reports],
                     "fixtures": sorted({slot for _, slot in gap_fixtures_seen}),
                     "observations": gap_observations_seen,
                     "per_issue": gap_reports, "mismatches": gap_mismatches[:5],
                     "replay_agrees": gap_agrees},
        "capture_mismatches": capture,
        "recorded_evidence_files": recorded_evidence,
        "replay": {"evidence_files_verified": evidence_checked, "all_hashes_match": True,
                   "all_values_reproduced": all_agree},
        "backup": {"path": str(backup), "quick_check": quick,
                   "additions_absent_before": empty_before,
                   "is_pre_recovery_snapshot": backup_is_pre_recovery},
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
                "archive's settlement SP over the release's own option domain, and the "
                "replaced vector is preserved in issue_recovery_gap.replaced_options_json.",
                "An archive row may legitimately settle no option (a cancelled fixture), so an "
                "added observation with no options is expected rather than a defect. The "
                "result cross-check on added rows therefore applies only where the score "
                "alone, or the score plus a published line, determines an option.",
                "The batch's recorded backup path is database content; replay ignores it and "
                "uses the backup given on the command line, and it requires that backup to "
                "still be a pre-recovery snapshot.",
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
