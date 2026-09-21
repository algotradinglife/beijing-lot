#!/usr/bin/env python3
"""Replay a settled-issue addition from its raw bundle, read-only.

The verification takes its anchor from this command line: the bundle's raw bytes and the
pre-addition backup. It re-derives every expected value from those bytes and never trusts
the release's own audit tables, which the release can rewrite.

The set it checks is derived (the bundle's issues minus what the backup already carried),
never enumerated from an audit table, so a row cannot be made to disappear by deleting it
together with its audit row.
"""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.nowscore_settlement import PLAYS, canonical, expected_option, parse_page  # noqa: E402
from src.settlement_issue_addition import (  # noqa: E402
    bundle_rows,
    canonical_content_sha256,
    issue_verdict,
    read_bundle,
)
from src.settlement_issue_recovery import option_vectors_for  # noqa: E402


def _replayed(entry: dict, payload: bytes) -> list[dict]:
    """Return the rows the bundle's page carries, with its capture identity attached."""
    if payload == b"" and entry.get("classification") == "source_empty":
        return []
    rows = parse_page(payload, entry["issue"], entry["typeid"])
    for row in rows:
        row.update(source_sha256=entry["sha256"], source_url=entry["url"],
                   received_at=entry["received_at"])
    return rows


def build_report(database: Path, bundle_root: Path, backup_path: Path) -> dict:
    """Verify every issue the bundle adds, deriving each expected value from the bytes."""
    bundle = read_bundle(bundle_root)
    requested = list(bundle["manifest"]["requested_issues"])
    con = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    before = sqlite3.connect(backup_path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        # The set to check is derived from the bundle's own bytes using the declared
        # acceptance contract, not from any table the release can edit. An issue the
        # contract rejects must be absent from the release, so a batch that quietly added
        # one is caught rather than excused.
        # The applier's parsed-domain validation is reused, not reimplemented: a bundle it
        # rejects (an empty page leaving a play missing) must not look eligible here.
        parsed = bundle_rows(bundle)
        owed, already, ineligible = [], [], []
        for issue in requested:
            was_present = before.execute(
                "SELECT 1 FROM observation WHERE issue=? LIMIT 1", (issue,)).fetchone()
            if was_present:
                already.append(issue)
                continue
            resolved, problems = issue_verdict(parsed[issue])
            if problems or not resolved:
                ineligible.append({"issue": issue,
                                   "problems": problems[:5] or ["no fixture has settled"]})
                continue
            owed.append(issue)
        mismatches: list[dict] = []
        checked_observations = checked_plays = 0
        for issue in owed:
            rows_by_key = {(row["slot"], row["play"]): row for row in parsed[issue]}
            stored = con.execute(
                """SELECT observation_id, slot, play, native_match_id, status, score,
                          halftime_score, expected_option, source_sha256, payload_json,
                          source_url, received_at
                   FROM observation WHERE issue=?""", (issue,)).fetchall()
            if not stored:
                mismatches.append({"issue": issue, "reason": "issue is missing entirely"})
                continue
            vectors = option_vectors_for(con, issue)
            seen: Counter = Counter()
            for (observation_id, slot, play, native, status, score, halftime, option,
                 source, payload, source_url, received_at) in stored:
                seen[(slot, play)] += 1
                checked_observations += 1
                row = rows_by_key.get((slot, play))
                if row is None:
                    mismatches.append({"issue": issue, "slot": slot, "play": play,
                                       "reason": "the bundle carries no such fixture"})
                    continue
                # Provenance is observable through the R query interface, so it is
                # compared too: a false source URL or collection time is a defect even when
                # the payload is untouched.
                want = (row["native_match_id"], row["status"], row["score"],
                        row["halftime_score"], expected_option(row), row["source_sha256"],
                        canonical(row), row["source_url"], row["received_at"])
                held = (native, status, score, halftime, option, source, payload,
                        source_url, received_at)
                want_vector = Counter(sorted(
                    (option_row["option"], option_row["raw_sp"], option_row["sp"],
                     option_row["cell_id"]) for option_row in row["options"]))
                held_vector = Counter(sorted(
                    (option_row["option"], option_row["raw_sp"], option_row["sp"],
                     option_row["cell_id"]) for option_row in vectors.get((slot, play), [])))
                if held != want or held_vector != want_vector:
                    mismatches.append({"issue": issue, "slot": slot, "play": play,
                                       "database": list(held), "replayed": list(want),
                                       "database_options": vectors.get((slot, play), []),
                                       "replayed_options": row["options"]})
            for key, count in seen.items():
                if count != 1:
                    mismatches.append({"issue": issue, "slot": key[0], "play": key[1],
                                       "observations_at_key": count})
            for key in rows_by_key:
                if key not in seen:
                    mismatches.append({"issue": issue, "slot": key[0], "play": key[1],
                                       "reason": "the bundle's fixture is missing"})
            checked_plays += len(rows_by_key)
            # Capture identity is evidence too: it must still be the bundle's page.
            recorded = {(row[0], row[1]): (row[2], row[3], row[4]) for row in con.execute(
                "SELECT issue, typeid, source_url, received_at, sha256 FROM capture WHERE issue=?",
                (issue,))}
            for entry in bundle["manifest"]["captures"]:
                if entry["issue"] != issue:
                    continue
                if recorded.get((issue, entry["typeid"])) != (
                        entry["url"], entry["received_at"], entry["sha256"]):
                    mismatches.append({"issue": issue, "typeid": entry["typeid"],
                                       "reason": "capture record is not the bundle's page"})

        # An issue the contract rejects must still be absent from the release, so a batch
        # that quietly added one is caught rather than excused by its own claim.
        for item in ineligible:
            added_anyway = con.execute(
                "SELECT COUNT(*) FROM observation WHERE issue=?", (item["issue"],)).fetchone()[0]
            if added_anyway:
                mismatches.append({"issue": item["issue"],
                                   "reason": "the release carries an issue the contract "
                                             "rejects",
                                   "observations": added_anyway,
                                   "problems": item["problems"]})
        # The batch's own claim: content hash over the canonical order, not insertion order.
        def _has_batch_table() -> bool:
            return con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='issue_addition_batch'"
            ).fetchone() is not None

        recorded_content = None
        if _has_batch_table() and (owed or ineligible):
            row = con.execute(
                "SELECT added_issues FROM issue_addition_batch WHERE bundle_sha256=?",
                (bundle["sha256"],)).fetchone()
            if row and sorted(json.loads(row[0])) != sorted(owed):
                mismatches.append({"reason": "the batch did not add exactly the eligible set",
                                   "recorded": json.loads(row[0]),
                                   "derived": owed, "ineligible": ineligible})
        if _has_batch_table():
            row = con.execute(
                "SELECT content_sha256 FROM issue_addition_batch WHERE bundle_sha256=?",
                (bundle["sha256"],)).fetchone()
            recorded_content = row[0] if row else None
        if owed and recorded_content is not None:
            actual = canonical_content_sha256(con, owed)
            if actual != recorded_content:
                mismatches.append({"reason": "canonical content hash changed",
                                   "recorded": recorded_content, "recomputed": actual})
        return {
            "schema": "bj479_issue_addition_verification_v1",
            "database": {"path": str(database), "sha256": hashlib.sha256(
                database.read_bytes()).hexdigest()},
            "bundle": {"path": str(bundle_root), "manifest_sha256": bundle["sha256"]},
            "backup": {"path": str(backup_path)},
            "issues_owed": owed, "issues_already_present": already,
            "issues_ineligible": ineligible,
            "checked_observations": checked_observations, "checked_fixtures": checked_plays,
            "content_sha256": recorded_content,
            "mismatches": mismatches,
            "conclusion": {"verified": not mismatches and bool(owed),
                           "void": not owed,
                           "note": "an empty owed set means the backup already carried "
                                   "every bundled issue; nothing was added to verify"},
        }
    finally:
        con.close()
        before.close()


def main(argv=None):
    """Replay one addition read-only and write its report."""
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('database', 'bundle', 'backup', 'out'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.database, args.bundle, args.backup)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out),
                      "verified": report["conclusion"]["verified"]}, ensure_ascii=False))
    return 0 if report["conclusion"]["verified"] else 1


if __name__ == '__main__':
    raise SystemExit(main())
