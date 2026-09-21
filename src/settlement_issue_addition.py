"""Append newly settled issues to a sealed settlement release.

A sealed release is built from a captured bundle and is meant to be reproducible from
its evidence. New issues arrive as their own captured bundle; this module appends them
to the existing release instead of rebuilding every earlier issue.

Appending is legitimate only because verification here binds **content**, not insertion
order. The batch records a hash over the canonical order
``(issue, slot, play, payload_json)``, which is chronological because the two issue
encodings do not overlap in year (six digits cover 2009-2019, five digits cover 2020 on),
and which any other build of the same content reproduces. Callers must not depend on
``observation_id`` ordering; it is kept contiguous only so the release stays internally
consistent.

Two implementations, two purposes:

* :func:`add_issues` is the applier. Re-running it is a guard that runs inside the
  mutated release and can only ever be a self-consistency check.
* ``scripts/verify_settlement_issue_addition.py`` takes its evidence from its own
  arguments and is the verification.

No fetching and no historical learning happen here: the bundle is already on disk.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.nowscore_settlement import (
    ABNORMAL,
    EMPTY,
    PLAYS,
    audit_rows,
    canonical,
    expected_option,
    hash_json_texts,
    parse_page,
    source_url,
)

BUNDLE_SCHEMA = "nowscore_history_batch_v1"
_BATCH_DDL = """
CREATE TABLE IF NOT EXISTS issue_addition_batch (
    batch_id TEXT PRIMARY KEY, bundle_sha256 TEXT NOT NULL, approval_note TEXT NOT NULL,
    created_at TEXT NOT NULL, added_issues TEXT NOT NULL, skipped_issues TEXT NOT NULL,
    added_observations INTEGER NOT NULL, added_fixtures INTEGER NOT NULL,
    resolved_fixtures INTEGER NOT NULL, content_sha256 TEXT NOT NULL)
"""
_ROW_DDL = """
CREATE TABLE IF NOT EXISTS issue_addition (
    observation_id INTEGER PRIMARY KEY, batch_id TEXT NOT NULL, issue TEXT NOT NULL,
    slot INTEGER NOT NULL, play TEXT NOT NULL, native_match_id TEXT NOT NULL,
    score TEXT NOT NULL, halftime_score TEXT NOT NULL, expected_option TEXT,
    source_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL)
"""
_CAPTURE_DDL = """
CREATE TABLE IF NOT EXISTS issue_addition_capture (
    batch_id TEXT NOT NULL, issue TEXT NOT NULL, typeid INTEGER NOT NULL, url TEXT NOT NULL,
    sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
    PRIMARY KEY(batch_id, issue, typeid))
"""
_SETTLED_SCORE = re.compile(r"^\d+-\d+$")
# Statuses the release records for a completed fixture. The live board also uses a play
# status (下/上) while a match is running, and a running score must never be frozen.
_COMPLETED_STATUSES = {"", "完场"}


def canonical_content_sha256(con: sqlite3.Connection, issues: list[str]) -> str:
    """Hash the observation payloads of ``issues`` in canonical, insertion-free order.

    The order is ``(issue, slot, play, payload_json)``. ``issue`` sorts chronologically,
    and the payload keeps the tuple total even when a logical key repeats, so the digest
    depends only on content.
    """
    rows = con.execute(
        f"""SELECT payload_json FROM observation
            WHERE issue IN ({','.join('?' * len(issues))})
            ORDER BY issue, slot, play, payload_json COLLATE BINARY""", issues).fetchall()
    return hash_json_texts(row[0] for row in rows)


def read_bundle(root: Path) -> dict:
    """Return the bundle manifest and its raw directory after validating coverage.

    The manifest must name every page it carries: a bundle that silently misses one play
    of one issue would otherwise append a partial issue that no later run could complete.
    """
    root = Path(root)
    manifest_bytes = (root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("Wrong bundle schema")
    captures = manifest.get("captures") or []
    requested = manifest.get("requested_issues") or []
    if not captures or not requested:
        raise ValueError("Bundle carries no captures")
    if len(requested) != len(set(requested)):
        raise ValueError("Bundle repeats a requested issue")
    seen = {(entry["issue"], entry["typeid"]) for entry in captures}
    expected = {(issue, typeid) for issue in requested for typeid in PLAYS}
    if seen != expected:
        raise ValueError("Bundle does not cover requested issue/play domain")
    for entry in captures:
        # The release build validates these too; a weaker boundary here would let arbitrary
        # provenance into a release the replay then certifies.
        if entry.get("url") != source_url(entry["issue"], entry["typeid"]):
            raise ValueError(f"Capture URL is not the source's for {entry['issue']}/"
                             f"{entry['typeid']}")
        try:
            received = datetime.fromisoformat(entry["received_at"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Capture time is not an ISO timestamp for {entry['issue']}/"
                             f"{entry['typeid']}") from exc
        if received.tzinfo is None:
            raise ValueError(f"Capture time lacks a timezone for {entry['issue']}/"
                             f"{entry['typeid']}")
        payload = (root / "raw" / (entry["sha256"] + ".html")).read_bytes()
        if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
            raise ValueError(f"Bundle bytes changed for {entry['issue']}/{entry['typeid']}")
    return {"manifest": manifest, "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "root": root}


def bundle_rows(bundle: dict) -> dict[str, list[dict]]:
    """Parse every page of the bundle, keyed by issue, with its capture identity attached.

    Parsing uses the same entry point the release build uses, so an appended issue is
    byte-for-byte the row the build would have produced from the same page.
    """
    by_issue: dict[str, list[dict]] = {issue: [] for issue in bundle["manifest"]["requested_issues"]}
    for entry in bundle["manifest"]["captures"]:
        payload = (bundle["root"] / "raw" / (entry["sha256"] + ".html")).read_bytes()
        if payload == b"" and entry.get("classification") == "source_empty":
            continue
        rows = parse_page(payload, entry["issue"], entry["typeid"])
        for row in rows:
            row.update(source_sha256=entry["sha256"], source_url=entry["url"],
                       received_at=entry["received_at"])
        by_issue[entry["issue"]].extend(rows)
    for issue, rows in by_issue.items():
        if not rows:
            raise ValueError(f"Bundle carries no rows for issue {issue}")
        keys = {(row["slot"], row["play"]) for row in rows}
        if len(keys) != len(rows):
            raise ValueError(f"Bundle repeats an observation key for issue {issue}")
        # The manifest naming five plays is not enough: a page classified source_empty is
        # skipped, so the parsed rows must still cover every play of every fixture. An
        # appended issue that misses a key can never be completed, because a later run
        # skips an issue the release already carries.
        by_slot: dict[int, set[str]] = {}
        for row in rows:
            by_slot.setdefault(row["slot"], set()).add(row["play"])
        incomplete = {slot: sorted(plays) for slot, plays in by_slot.items()
                      if plays != set(PLAYS.values())}
        if incomplete:
            raise ValueError(f"Bundle's parsed rows miss a play for issue {issue}: "
                             f"{sorted(incomplete)[:5]}")
    return by_issue


def issue_verdict(rows: list[dict]) -> tuple[int, list[str]]:
    r"""Return how many *fixtures* are resolved, plus every reason the issue cannot be added.

    A fixture is judged as a whole, because its five plays are five views of one match and
    the addition must not create a fixture the release can never complete. A fixture is
    resolved when all five of its plays are settled, or when all five report no result. A
    fixture whose plays disagree -- four settled and one postponed, say -- is refused: the
    postponed play would later be skipped by the addition (the issue is already present) and
    cannot be gap-filled either, because that path requires all five plays of a fixture to
    be empty.

    Per row the rule is deliberately narrower than the release build's, because an addition
    must not freeze a transient value:

    * settled: the score matches ``\d+-\d+``, the derived option is among the options the
      play offers, and either exactly one option carries the SP and it is that one, or the
      play prices nothing for the derived bucket and the status is one the release records
      for completed rows (empty or ``完场``). The live board reports a running score under a
      play status such as ``下``, so status matters for the unpriced case;
    * no result: the status is explicitly abnormal, the score is empty or a dash, and no
      option carries an SP -- exactly what the release's 5,750 abnormal rows look like.
    """
    by_slot: dict[int, list[tuple[str, str]]] = {}
    problems: list[str] = []
    for row in rows:
        status = row.get("status") or ""
        score = row.get("score") or ""
        options = row.get("options", [])
        derived = expected_option(row)
        offered = {option["option"] for option in options}
        priced = [option for option in options if option.get("sp") is not None]
        key = f"{row['slot']}/{row['play']}"
        if status in ABNORMAL:
            if priced or score not in EMPTY:
                problems.append(f"{key}: abnormal status carries a result")
                by_slot.setdefault(row["slot"], []).append(("problem", key))
            else:
                by_slot.setdefault(row["slot"], []).append(("none", key))
            continue
        if not _SETTLED_SCORE.match(score):
            problems.append(f"{key}: no settled score")
            by_slot.setdefault(row["slot"], []).append(("problem", key))
        elif derived not in offered:
            problems.append(f"{key}: the derived result is not among the offered options")
            by_slot.setdefault(row["slot"], []).append(("problem", key))
        elif len(priced) == 1 and priced[0]["option"] == derived:
            by_slot.setdefault(row["slot"], []).append(("settled", key))
        elif not priced and status in _COMPLETED_STATUSES:
            by_slot.setdefault(row["slot"], []).append(("settled", key))
        else:
            problems.append(f"{key}: not a completed settlement")
            by_slot.setdefault(row["slot"], []).append(("problem", key))

    resolved = 0
    for slot, verdicts in by_slot.items():
        kinds = {kind for kind, _ in verdicts}
        if kinds == {"settled"} or kinds == {"none"}:
            resolved += 1
        elif "problem" not in kinds:
            problems.append(f"slot {slot}: plays disagree on whether the fixture has a result "
                            f"({sorted(kinds)})")
    return resolved, problems


def existing_issues(con: sqlite3.Connection) -> set[str]:
    """Return the issues the release already carries, read from the release itself."""
    return {row[0] for row in con.execute("SELECT DISTINCT issue FROM observation")}


def _verify_added(con: sqlite3.Connection, batch: str, issues: list[str]) -> dict:
    """Check the rows this batch claims to have added. Self-consistency only.

    Every audited row must still exist at its audited key with the capture hash the batch
    recorded and exactly one observation must sit at each such key. A caller must not
    mistake this for verification: the evidence is in the release's own audit table, while
    the bundle-side replay re-derives every value from the raw bytes and proves from the
    pre-addition backup that the issues really were absent.
    """
    audited = con.execute(
        f"""SELECT observation_id, issue, slot, play, native_match_id, score,
                   halftime_score, expected_option, source_sha256, payload_sha256
            FROM issue_addition WHERE batch_id=? AND issue IN ({','.join('?' * len(issues))})""",
        [batch, *issues]).fetchall()
    held: dict[tuple, list[tuple]] = {}
    for record in audited:
        held.setdefault((record[1], record[2], record[3]), []).append(record)
    stored = con.execute(
        f"""SELECT observation_id, issue, slot, play, native_match_id, score,
                   halftime_score, expected_option, source_sha256, payload_json
            FROM observation WHERE issue IN ({','.join('?' * len(issues))})""",
        issues).fetchall()
    mismatches: list[dict] = []
    counted: Counter = Counter()
    for observation_id, issue, slot, play, native, score, halftime, option, source, payload in stored:
        counted[(issue, slot, play)] += 1
        record = held.get((issue, slot, play)) or []
        if len(record) != 1:
            mismatches.append({"issue": issue, "slot": slot, "play": play,
                               "reason": "not exactly one audited row for this key"})
            continue
        audited_row = record[0]
        want = (audited_row[0], audited_row[4], audited_row[5], audited_row[6],
                audited_row[7], audited_row[8])
        got = (observation_id, native, score, halftime, option, source)
        if got != want:
            mismatches.append({"issue": issue, "slot": slot, "play": play,
                               "reason": "a value this batch wrote changed",
                               "database": list(got), "recorded": list(want)})
        elif audited_row[9] != hashlib.sha256(payload.encode()).hexdigest():
            mismatches.append({"issue": issue, "slot": slot, "play": play,
                               "reason": "payload changed since it was added"})
    for key, count in counted.items():
        if count != 1:
            mismatches.append({"issue": key[0], "slot": key[1], "play": key[2],
                               "observations_at_key": count})
    if len(audited) != len(stored):
        mismatches.append({"reason": "audited row count differs from stored row count",
                           "audited": len(audited), "stored": len(stored)})
    return {"added_observations": len(audited), "checked_observations": len(stored),
            "mismatches": mismatches}


def add_issues(database: Path, bundle_root: Path, backup_path: Path, *,
               approval_note: str) -> dict:
    """Append a captured bundle's new issues to the sealed release.

    Paths are explicit and must be distinct. The set to add is derived from the release
    (bundle issues minus issues the release already carries); it is never enumerated.
    The release is backed up before the first write and every write shares one
    transaction, so a failure leaves the release untouched. Re-running the same bundle
    verifies the rows it added and reports ``already_applied``.
    """
    database, bundle_root, backup_path = map(Path, (database, bundle_root, backup_path))
    if not isinstance(approval_note, str) or not approval_note.strip():
        raise ValueError("Explicit approval note required")
    if len({p.resolve() for p in (database, bundle_root, backup_path)}) != 3:
        raise ValueError("Database, bundle and backup paths must be distinct")
    bundle = read_bundle(bundle_root)
    batch = bundle["sha256"]
    requested = list(bundle["manifest"]["requested_issues"])
    rows_by_issue = bundle_rows(bundle)

    con = sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
    reserved_backup = None
    try:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='issue_addition_batch'").fetchone():
            prior = con.execute(
                "SELECT added_issues, added_observations, content_sha256 "
                "FROM issue_addition_batch WHERE batch_id=?", (batch,)).fetchone()
            if prior:
                verified = _verify_added(con, batch, json.loads(prior[0]))
                if verified["mismatches"]:
                    raise ValueError("A previously added row changed")
                if verified["added_observations"] != prior[1]:
                    raise ValueError("Previously added row count changed")
                if canonical_content_sha256(con, json.loads(prior[0])) != prior[2]:
                    raise ValueError("Previously added content changed")
                con.rollback()
                return {"status": "already_applied", "added_issues": json.loads(prior[0]),
                        **verified}

        present = existing_issues(con)
        additions, skipped = [], []
        for issue in requested:
            if issue in present:
                skipped.append({"issue": issue, "reason": "already in the release"})
                continue
            resolved, problems = issue_verdict(rows_by_issue[issue])
            if problems:
                skipped.append({"issue": issue,
                                "reason": "not a completed settlement; nothing was added",
                                "problems": problems[:10]})
                continue
            additions.append(issue)
        if not additions:
            con.rollback()
            return {"status": "nothing_to_add", "skipped": skipped}

        if not additions:
            con.rollback()
            return {"status": "nothing_to_add", "skipped": skipped}

        if not additions:
            con.rollback()
            return {"status": "nothing_to_add", "skipped": skipped}

        original_receipts = con.execute("SELECT payload_json FROM receipt").fetchall()
        if len(original_receipts) != 1:
            raise ValueError("Expected one original build receipt")

        # Reserve the backup path first, then copy the committed snapshot from a second
        # read-only connection so no active writer is copied.
        with backup_path.open("xb"):
            pass
        reserved_backup = backup_path
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
        con.execute(_ROW_DDL)
        con.execute(_CAPTURE_DDL)
        now = datetime.now(timezone.utc).isoformat()

        added_observations = added_fixtures = resolved_fixtures = 0
        for issue in additions:
            rows = rows_by_issue[issue]
            added_observations += len(rows)
            added_fixtures += len({row["slot"] for row in rows})
            resolved_fixtures += issue_verdict(rows)[0]
            for entry in bundle["manifest"]["captures"]:
                if entry["issue"] != issue:
                    continue
                con.execute("INSERT INTO issue_addition_capture VALUES (?,?,?,?,?,?)",
                            (batch, issue, entry["typeid"], entry["url"], entry["sha256"],
                             entry["received_at"]))
                # The live board is the primary source for an added issue.
                con.execute("INSERT OR REPLACE INTO capture VALUES (?,?,?,?,?)",
                            (issue, entry["typeid"], entry["url"], entry["received_at"],
                             entry["sha256"]))
            for row in rows:
                observation_id = con.execute(
                    "SELECT COALESCE(MAX(observation_id),0)+1 FROM observation").fetchone()[0]
                con.execute("INSERT INTO observation VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (observation_id, row["issue"], row["slot"], row["play"],
                             row["native_match_id"], row["status"], row["score"],
                             row["halftime_score"], expected_option(row), row["source_sha256"],
                             row["source_url"], row["received_at"], canonical(row)))
                con.executemany("INSERT INTO option_sp VALUES (?,?,?,?,?)",
                                [(observation_id, option["option"], option["raw_sp"],
                                  option["sp"], option["cell_id"])
                                 for option in row["options"]])
                con.execute("INSERT INTO issue_addition VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (observation_id, batch, row["issue"], row["slot"], row["play"],
                             row["native_match_id"], row["score"], row["halftime_score"],
                             expected_option(row), row["source_sha256"],
                             hashlib.sha256(canonical(row).encode()).hexdigest()))
            for finding in audit_rows(rows):
                con.execute("INSERT INTO finding VALUES (?,?,?,?,?,?)",
                            tuple(finding[key] for key in ("issue", "slot", "play", "code",
                                                           "detail", "source_sha256")))
        content = canonical_content_sha256(con, additions)
        con.execute("INSERT INTO issue_addition_batch VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (batch, bundle["sha256"], approval_note.strip(), now,
                     json.dumps(additions, ensure_ascii=False),
                     json.dumps(skipped, ensure_ascii=False), added_observations,
                     added_fixtures, resolved_fixtures, content))
        con.commit()
        return {"status": "added", "added_issues": additions, "skipped": skipped,
                "added_observations": added_observations, "added_fixtures": added_fixtures,
                "resolved_fixtures": resolved_fixtures, "content_sha256": content}
    except BaseException:
        con.rollback()
        if reserved_backup is not None and reserved_backup.exists():
            reserved_backup.unlink()
        raise
    finally:
        con.close()
