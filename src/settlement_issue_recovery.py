"""Owner-approved recovery of quarantined issues from the source's own archive pages.

Issue #479 deliverable. Five five-digit issues were captured from the live board
(`DanChang.aspx`), which permanently hides a slice of every round's fixtures, so the
whole page raised `RosterConflict` and was quarantined with no observations at all.
Issue 26092 was captured before its last fixtures kicked off, so 27 of its fixtures
carry no result. The source's own archive board (`kaijiang_dc_<typeid>_<issue>.html`)
renders every fixture and keeps the results, so it is the recovery source.

Folding the archive into the release by rebuilding is not possible: the assembled bundle
binds every request URL into its source scope and `verify_history_replay_origin` permits
only `generated_at` / `implementation_sha256` / `plan_sha256` to change, so supplying
these issues from the archive would invalidate every batch receipt and force
re-capturing all 8,325 pages. The recovery is recorded as an audited layer instead,
following the established correction contract: an approval note, a ledger whose hash is
the batch id, hash-verified evidence, all validation before the backup, a backup taken
before the first write with its own integrity check, one transaction with rollback, and
an idempotent re-run that re-verifies every recovered row.

* additions insert the archive-derived observations for issues that hold none, and
  re-point `capture` at the archive bytes that actually back them;
* gap fills complete result fields for fixtures the live board had not yet settled,
  replace the reference odds the live board published in the settlement column with the
  archive's settlement SP, and leave cancelled fixtures alone.

Parsing, option derivation, canonical payloads and auditing all come from
`nowscore_settlement`, so the recovery shares one implementation of every business rule.
Evidence bytes stay outside the database under their recorded hashes, so the recovery
replays without trusting the mutated database. No fetching, no historical learning.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from src.nowscore_settlement import PLAYS, audit_rows, canonical, expected_option, parse_page

LEDGER_SCHEMA = "bj479_issue_recovery_ledger_v1"

# A settled score, as opposed to '' (not captured), '-' (no result) or '取消' (cancelled).
SETTLED_SCORE = re.compile(r"^\d+-\d+$")

_BATCH_DDL = """CREATE TABLE IF NOT EXISTS issue_recovery_batch (
    batch_id TEXT PRIMARY KEY, applied_at TEXT NOT NULL, note TEXT NOT NULL,
    added_fixtures INTEGER NOT NULL, added_observations INTEGER NOT NULL,
    gap_fixtures INTEGER NOT NULL, gap_observations INTEGER NOT NULL,
    original_receipt_json TEXT NOT NULL, ledger_json TEXT NOT NULL,
    evidence_manifest_json TEXT NOT NULL, backup_path TEXT NOT NULL)"""

_CAPTURE_DDL = """CREATE TABLE IF NOT EXISTS issue_recovery_capture (
    batch_id TEXT NOT NULL, issue TEXT NOT NULL, typeid INTEGER NOT NULL,
    url TEXT NOT NULL, sha256 TEXT NOT NULL, received_at TEXT NOT NULL,
    byte_count INTEGER NOT NULL, replaced_sha256 TEXT,
    PRIMARY KEY (batch_id, issue, typeid))"""

# `new_options_json` is the archive's settlement vector; `replaced_options_json` is the
# reference-odds vector the live board had published in the same column before the
# fixture settled. Both are kept: the first is what the recovery asserts, the second is
# the evidence of what it replaced.
_GAP_DDL = """CREATE TABLE IF NOT EXISTS issue_recovery_gap (
    observation_id INTEGER NOT NULL, batch_id TEXT NOT NULL, issue TEXT NOT NULL,
    slot INTEGER NOT NULL, play TEXT NOT NULL, native_match_id TEXT NOT NULL,
    old_score TEXT NOT NULL, new_score TEXT NOT NULL,
    old_halftime_score TEXT NOT NULL, new_halftime_score TEXT NOT NULL,
    old_expected_option TEXT, new_expected_option TEXT NOT NULL,
    new_options_json TEXT NOT NULL, replaced_options_json TEXT NOT NULL,
    old_payload_sha256 TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, note TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    PRIMARY KEY (observation_id))"""


def settled_option(archive_row: dict, release_row: dict) -> str | None:
    """The option an archived score implies, or None when it implies nothing.

    The archive leaves the handicap cell empty for many fixtures, settled ones included;
    the release's own record carries the line those rows were captured with, so it
    supplies the handicap when the archive omits it. The score always comes from the
    archive, and the caller requires the result to equal what the archive reports.
    """
    handicap = archive_row["handicap"]
    if handicap is None:
        handicap = release_row.get("handicap")
    return expected_option({**archive_row, "handicap": handicap})


def _evidence_bytes(entry: dict) -> bytes:
    """Read one preserved evidence file and fail closed unless the ledger's bytes match."""
    payload = Path(entry["path"]).read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != entry["sha256"]:
        raise ValueError(f"evidence hash mismatch for {entry['path']}: "
                         f"{actual} != {entry['sha256']}")
    if len(payload) != entry["byte_count"]:
        raise ValueError(f"evidence byte count mismatch for {entry['path']}: "
                         f"{len(payload)} != {entry['byte_count']}")
    return payload


def _parse_evidence(entry: dict, issue: str) -> list[dict]:
    """Parse one archived play page and stamp every row with its evidence identity."""
    payload = _evidence_bytes(entry)
    rows = parse_page(payload, issue, entry["typeid"])
    if not rows:
        raise ValueError(f"issue {issue} typeid {entry['typeid']}: archive page parsed empty")
    for row in rows:
        row.update(source_sha256=entry["sha256"], source_url=entry["url"],
                   received_at=entry["received_at"])
    return rows


def _settlement_vector(row: dict) -> list[dict]:
    """The options the archive publishes for a row, in page order."""
    return [{"option": o["option"], "raw_sp": o["raw_sp"], "sp": o["sp"],
             "cell_id": o["cell_id"]} for o in row["options"]]


def _stored_vector(con, observation_id: int) -> list[dict]:
    """The row's stored options in insertion order, as a comparable structure."""
    return [{"option": o, "raw_sp": r, "sp": s, "cell_id": c} for o, r, s, c in con.execute(
        "SELECT option, raw_sp, sp, cell_id FROM option_sp WHERE observation_id=? "
        "ORDER BY rowid", (observation_id,))]


def expected_settlement_vector(before_vector: list[dict], archive_row: dict) -> list[dict]:
    """The vector a gap-filled row must hold, derived from external evidence.

    The release keeps the option domain its own source published (the live board lists
    every option), while the archive publishes only the option that settled. The expected
    vector therefore keeps the pre-recovery domain and ordering, carries the archive's
    settlement SP for every option the archive names, and carries nothing for the rest.
    Comparing against this exact list rejects an invented option, a dropped option and a
    surviving reference odd alike.
    """
    archived = {o["option"]: o for o in archive_row["options"]}
    expected = []
    for row in before_vector:
        a = archived.get(row["option"])
        expected.append({"option": row["option"],
                         "raw_sp": a["raw_sp"] if a is not None else None,
                         "sp": a["sp"] if a is not None else None,
                         "cell_id": a["cell_id"] if a is not None else None})
    if set(archived) - {row["option"] for row in before_vector}:
        raise ValueError("archive names options the pre-recovery row does not carry")
    return expected


def option_vectors_by_id(con, issue: str) -> dict[int, list[dict]]:
    """Every option vector of one issue, keyed by observation id, in a single query.

    Reading them one row at a time probed the option table thousands of times, which
    dominated the runtime on the external disk; this keeps it to one pass per issue.
    """
    out: dict[int, list[dict]] = {}
    for oid, option, raw_sp, sp, cell_id in con.execute(
            """SELECT s.observation_id, s.option, s.raw_sp, s.sp, s.cell_id
               FROM option_sp s JOIN observation o USING(observation_id)
               WHERE o.issue=? ORDER BY s.observation_id, s.rowid""", (issue,)):
        out.setdefault(oid, []).append(
            {"option": option, "raw_sp": raw_sp, "sp": sp, "cell_id": cell_id})
    return out


def option_vectors_for(con, issue: str) -> dict[tuple[int, str], list[dict]]:
    """Every option vector of one issue, keyed by fixture, in a single query.

    Reading them one fixture at a time made the replay scan the option table thousands of
    times, which dominated its runtime; this keeps it to one pass per issue.
    """
    out: dict[tuple[int, str], list[dict]] = {}
    for slot, play, option, raw_sp, sp, cell_id in con.execute(
            """SELECT o.slot, o.play, s.option, s.raw_sp, s.sp, s.cell_id
               FROM observation o JOIN option_sp s USING(observation_id)
               WHERE o.issue=? ORDER BY o.slot, o.play, s.rowid""", (issue,)):
        out.setdefault((slot, play), []).append(
            {"option": option, "raw_sp": raw_sp, "sp": sp, "cell_id": cell_id})
    return out


def _fixture_map(rows: list[dict]) -> dict[str, dict[int, str]]:
    """Play name -> slot -> native match id, the identity all five plays must agree on."""
    maps: dict[str, dict[int, str]] = {}
    for row in rows:
        maps.setdefault(row["play"], {})[row["slot"]] = row["native_match_id"]
    return maps


def _reported_result(issue: str, row: dict) -> str | None:
    """The single option the archive reports as settled, or None if it reports none."""
    settled = [o for o in row["options"] if o["sp"] is not None]
    if len(settled) > 1:
        raise ValueError(f"issue {issue} slot {row['slot']} {row['play']}: archive settles "
                         f"{len(settled)} options, expected at most one")
    return settled[0]["option"] if settled else None


def _addition_rows(con, item: dict) -> list[dict]:
    """Collect and validate one issue's archive rows before any write."""
    issue = item["issue"]
    held = con.execute("SELECT COUNT(*) FROM observation WHERE issue=?", (issue,)).fetchone()[0]
    if held:
        raise ValueError(f"issue {issue}: recovery adds an issue that already holds {held} rows")
    rows: list[dict] = []
    for entry in item["evidence"]:
        rows.extend(_parse_evidence(entry, issue))
    maps = _fixture_map(rows)
    if set(maps) != set(PLAYS.values()):
        raise ValueError(f"issue {issue}: archive evidence covers {sorted(maps)}, "
                         f"not all five plays")
    # Compare slot -> native match id, not just roster size: two plays holding equally
    # many but different fixtures must not pass.
    if len({json.dumps(m, sort_keys=True) for m in maps.values()}) != 1:
        raise ValueError(f"issue {issue}: archive plays disagree on the fixtures")
    held = len(next(iter(maps.values())))
    if held != item["expected_fixtures"]:
        raise ValueError(f"issue {issue}: archive holds {held} fixtures, ledger expects "
                         f"{item['expected_fixtures']}")
    # A settled archive row must not contradict the result its own score implies. The
    # handicap is absent from many archive rows, so the check applies wherever the score
    # alone (or the score plus a published line) determines an option.
    for row in rows:
        if not SETTLED_SCORE.match(row["score"] or ""):
            continue
        reported = _reported_result(issue, row)
        if reported is None:
            continue
        derived = expected_option(row)
        if derived is not None and derived != reported:
            raise ValueError(f"issue {issue} slot {row['slot']} {row['play']}: settled score "
                             f"{row['score']!r} derives {derived!r}, archive reports "
                             f"{reported!r}")
    return rows


def _gap_targets(con, item: dict) -> list[tuple]:
    """Pair each unsettled row with the archive row that settles it."""
    issue = item["issue"]
    archive: dict[tuple[int, str], dict] = {}
    for entry in item["evidence"]:
        for row in _parse_evidence(entry, issue):
            key = (row["slot"], row["play"])
            if key in archive:
                raise ValueError(f"issue {issue} {key}: archive evidence repeats a row")
            archive[key] = row
    slots = {slot for slot, _ in archive}
    if len(slots) != item["expected_fixtures"]:
        raise ValueError(f"issue {issue}: archive holds {len(slots)} fixtures, ledger expects "
                         f"{item['expected_fixtures']}")

    targets = []
    for play in PLAYS.values():
        rows = con.execute(
            """SELECT observation_id, slot, play, native_match_id, score, halftime_score,
                      expected_option, payload_json FROM observation
               WHERE issue=? AND play=? AND (score='' OR score='-')""",
            (issue, play)).fetchall()
        for (observation_id, slot, play_name, native_id, score, halftime, expected,
             payload) in rows:
            source = archive.get((slot, play_name))
            if source is None:
                raise ValueError(f"issue {issue} slot {slot} {play_name}: no archive row")
            if source["native_match_id"] != native_id:
                raise ValueError(
                    f"issue {issue} slot {slot} {play_name}: archive identifies match "
                    f"{source['native_match_id']}, database holds {native_id}")
            # A cancelled fixture legitimately has no result; the archive may spell that
            # '取消' where the live board left '-'. Nothing is settled, so nothing to do.
            if not SETTLED_SCORE.match(source["score"] or ""):
                continue
            reported = _reported_result(issue, source)
            if reported is None:
                raise ValueError(f"issue {issue} slot {slot} {play_name}: archive settles "
                                 f"no options")
            new_option = settled_option(source, json.loads(payload))
            if new_option is None:
                raise ValueError(f"issue {issue} slot {slot} {play_name}: settled score "
                                 f"{source['score']!r} derives no option")
            if new_option != reported:
                raise ValueError(
                    f"issue {issue} slot {slot} {play_name}: settled score "
                    f"{source['score']!r} derives {new_option!r}, archive reports "
                    f"{reported!r}")
            if set(o["option"] for o in source["options"]) - {
                    row[0] for row in con.execute(
                        "SELECT option FROM option_sp WHERE observation_id=?",
                        (observation_id,))}:
                raise ValueError(f"issue {issue} slot {slot} {play_name}: archive names options "
                                 f"the release does not carry")
            targets.append((observation_id, issue, slot, play_name, native_id, score,
                            halftime, expected, source, new_option, payload))
    fixtures = {(t[1], t[2]) for t in targets}
    if len(fixtures) != item["expected_gap_fixtures"]:
        raise ValueError(f"issue {issue}: settled {len(fixtures)} gap fixtures, ledger expects "
                         f"{item['expected_gap_fixtures']}")
    slots = sorted({t[2] for t in targets})
    if slots != item["expected_gap_slots"]:
        raise ValueError(f"issue {issue}: settled slots differ from the ledger's expected slots")
    # Every owed fixture must be completed exactly once for each of the five plays, or the
    # batch would commit a recovery the verifiers then refuse. A count is not enough: a
    # missing play plus a duplicated one keeps the total right.
    expected_product = {(slot, play) for slot in slots for play in PLAYS.values()}
    keys = [(t[2], t[3]) for t in targets]
    if len(set(keys)) != len(keys):
        raise ValueError(f"issue {issue}: two completions share a fixture key")
    if set(keys) != expected_product:
        raise ValueError(f"issue {issue}: the completions are not the expected five-play "
                         f"product for the owed slots")
    # The product must hold exactly one observation per key in the release, settled or not:
    # a settled duplicate would otherwise slip past this gate and be refused only later.
    for slot, play in sorted(expected_product):
        held = con.execute("SELECT COUNT(*) FROM observation WHERE issue=? AND slot=? AND play=?",
                           (issue, slot, play)).fetchone()[0]
        if held != 1:
            raise ValueError(f"issue {issue} slot {slot} {play}: expected exactly one "
                             f"observation, found {held}")
    return targets


def _open_pre_recovery_backup(recorded: str | None, database: Path, additions: list[dict],
                              gap_fills: list[dict]):
    """Open the batch's backup after proving it is a genuine pre-recovery snapshot.

    The recorded path is itself mutable database content, so it is only trusted once it is
    shown not to alias the release and not to contain any part of the recovery. A caller
    that wants an independent anchor should use the replay script, which takes the backup
    from its own arguments.
    """
    if not recorded:
        raise ValueError("This batch records no pre-recovery backup")
    path = Path(recorded).resolve()
    if path == database.resolve():
        raise ValueError("The recorded pre-recovery backup is the release database itself")
    if not path.is_file():
        raise ValueError(f"The recorded pre-recovery backup {path} is unavailable")
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if tables & {"issue_recovery_batch", "issue_recovery_gap", "issue_recovery_capture"}:
            raise ValueError("The recorded backup already contains a recovery batch")
        for item in additions:
            held = con.execute("SELECT COUNT(*) FROM observation WHERE issue=?",
                               (item["issue"],)).fetchone()[0]
            if held:
                raise ValueError(f"The recorded backup already holds issue {item['issue']}")
        for item in gap_fills:
            unsettled = con.execute(
                "SELECT COUNT(*) FROM observation WHERE issue=? AND (score='' OR score='-')",
                (item["issue"],)).fetchone()[0]
            if unsettled < item["expected_gap_fixtures"]:
                raise ValueError(f"The recorded backup does not hold issue "
                                 f"{item['issue']}'s gap fixtures unsettled")
    except Exception:
        con.close()
        raise
    return con


def _verify_applied(con, batch: str, additions: list[dict], gap_fills: list[dict],
                    database: Path) -> dict:
    """Re-read the evidence and confirm the stored recovery still matches it.

    The rerun must not certify a damaged recovery, so it does not enumerate the audit
    table it is meant to corroborate: the required completions are derived from the
    archive and the authenticated pre-recovery backup, and the audit rows, the recovered
    observations and their option vectors must all match that derivation exactly.
    """
    added = 0
    for item in additions:
        issue = item["issue"]
        vectors = option_vectors_by_id(con, issue)
        stored = con.execute(
            """SELECT observation_id, slot, play, native_match_id, status, score,
                      halftime_score, expected_option, source_sha256, source_url, received_at,
                      payload_json
               FROM observation WHERE issue=?""", (issue,)).fetchall()
        rows = [row for entry in item["evidence"] for row in _parse_evidence(entry, issue)]
        archive_keys = [(r["slot"], r["play"]) for r in rows]
        stored_keys = [(r[1], r[2]) for r in stored]
        # A bijection, not merely equal counts: a duplicated key must not stand in for a
        # missing archive fixture.
        if sorted(stored_keys) != sorted(archive_keys):
            raise ValueError(f"issue {issue}: stored rows are not the archive's fixtures")
        if len(set(archive_keys)) != len(archive_keys) or len(set(stored_keys)) != len(stored_keys):
            raise ValueError(f"issue {issue}: duplicate fixture keys")
        by_key = {(r["slot"], r["play"]): r for r in rows}
        for (observation_id, slot, play, native_id, status, score, halftime, expected,
             source_sha256, source_url, received_at, payload) in stored:
            row = by_key[(slot, play)]
            held = (native_id, status, score, halftime, expected, source_sha256,
                    source_url, received_at,
                    json.dumps(json.loads(payload), ensure_ascii=False))
            want = (row["native_match_id"], row["status"], row["score"],
                    row["halftime_score"], expected_option(row), row["source_sha256"],
                    row["source_url"], row["received_at"],
                    json.dumps(json.loads(canonical(row)), ensure_ascii=False))
            if held != want:
                raise ValueError(f"issue {issue} slot {slot} {play}: recovered values changed")
            if vectors.get(observation_id, []) != _settlement_vector(row):
                raise ValueError(f"issue {issue} slot {slot} {play}: recovered options changed")
            added += 1

    if not gap_fills:
        return {"added_observations": added, "gap_observations": 0}
    recorded_backup = con.execute("SELECT backup_path FROM issue_recovery_batch "
                                  "WHERE batch_id=?", (batch,)).fetchone()
    before_con = _open_pre_recovery_backup(recorded_backup[0] if recorded_backup else None,
                                          database, additions, gap_fills)
    try:
        gaps = 0
        for item in gap_fills:
            issue = item["issue"]
            archive = {(row["slot"], row["play"]): row
                       for entry in item["evidence"] for row in _parse_evidence(entry, issue)}
            if len({slot for slot, _ in archive}) != item["expected_fixtures"]:
                raise ValueError(f"issue {issue}: archive holds "
                                 f"{len({slot for slot, _ in archive})} fixtures, ledger "
                                 f"expects {item['expected_fixtures']}")
            # The completions this batch owes are exactly the fixtures the backup held
            # unsettled that the archive settles.
            unsettled = {(slot, play) for slot, play in before_con.execute(
                "SELECT slot, play FROM observation WHERE issue=? AND (score='' OR score='-')",
                (issue,))}
            required = {key for key, row in archive.items()
                        if key in unsettled and SETTLED_SCORE.match(row["score"] or "")}
            owed_slots = sorted({slot for slot, _ in required})
            if owed_slots != item["expected_gap_slots"]:
                raise ValueError(f"issue {issue}: owed slots differ from the ledger's")
            if len(required) != len(owed_slots) * len(PLAYS):
                raise ValueError(f"issue {issue}: {len(required)} completions are owed for "
                                 f"{len(owed_slots)} fixtures, so a play is missing")

            audited = {(row[0], row[1]): row[2:] for row in con.execute(
                """SELECT slot, play, observation_id, native_match_id, new_score,
                          new_halftime_score, new_expected_option, new_options_json,
                          evidence_sha256, old_payload_sha256, replaced_options_json,
                          old_score, old_halftime_score
                   FROM issue_recovery_gap WHERE batch_id=? AND issue=?""", (batch, issue))}
            # A dictionary would silently drop a duplicate key, so multiplicity is checked
            # before the mapping is used.
            audit_rows = con.execute("SELECT COUNT(*) FROM issue_recovery_gap "
                                     "WHERE batch_id=? AND issue=?", (batch, issue)).fetchone()[0]
            if audit_rows != len(audited):
                raise ValueError(f"issue {issue}: two audit rows share a fixture key")
            if set(audited) != required:
                raise ValueError(f"issue {issue}: the audit rows are not the owed completions")
            # One pass over each side's option vectors, keyed by fixture.
            vectors_now, vectors_before = option_vectors_for(con, issue), option_vectors_for(before_con, issue)
            # Iterate the owed keys, not the surviving observations, so a deleted row cannot
            # shrink the check.
            for slot, play in sorted(required):
                source = archive[(slot, play)]
                (audit_id, audit_native, audit_score, audit_halftime, audit_option,
                 audit_options, audit_evidence, audit_payload_sha256,
                 audit_replaced, audit_old_score, audit_old_halftime) = audited[(slot, play)]
                stored = con.execute(
                    """SELECT observation_id, native_match_id, score, halftime_score,
                              expected_option, payload_json FROM observation
                       WHERE issue=? AND slot=? AND play=?""", (issue, slot, play)).fetchall()
                if len(stored) != 1:
                    raise ValueError(f"issue {issue} slot {slot} {play}: expected exactly one "
                                     f"observation, found {len(stored)}")
                (observation_id, native_id, score, halftime, option, payload) = stored[0]
                before = before_con.execute(
                    """SELECT score, halftime_score, payload_json FROM observation
                       WHERE issue=? AND slot=? AND play=?""", (issue, slot, play)).fetchone()
                if before is None:
                    raise ValueError(f"issue {issue} slot {slot} {play}: absent from the "
                                     f"pre-recovery backup")
                derived = settled_option(source, json.loads(before[2]))
                expected_vector = expected_settlement_vector(
                    vectors_before.get((slot, play), []), source)
                # The observation, and the audit row that records it, must both agree with
                # evidence the recovery cannot have rewritten.
                if (native_id, score, halftime, option) != (
                        source["native_match_id"], source["score"], source["halftime_score"],
                        derived) or derived != _reported_result(issue, source):
                    raise ValueError(f"issue {issue} slot {slot} {play}: the completion "
                                     f"disagrees with the archive")
                if payload != before[2]:
                    raise ValueError(f"issue {issue} slot {slot} {play}: pre-recovery payload "
                                     f"changed")
                if vectors_now.get((slot, play), []) != expected_vector:
                    raise ValueError(f"issue {issue} slot {slot} {play}: stored options changed")
                if (audit_id, audit_native, audit_score, audit_halftime, audit_option) != (
                        observation_id, native_id, score, halftime, option):
                    raise ValueError(f"issue {issue} slot {slot} {play}: the audit row does not "
                                     f"record the stored observation")
                if audit_options != json.dumps(_settlement_vector(source), ensure_ascii=False):
                    raise ValueError(f"issue {issue} slot {slot} {play}: recorded settlement "
                                     f"vector changed")
                if audit_evidence != source["source_sha256"]:
                    raise ValueError(f"issue {issue} slot {slot} {play}: recorded evidence "
                                     f"changed")
                if audit_payload_sha256 != hashlib.sha256(before[2].encode()).hexdigest():
                    raise ValueError(f"issue {issue} slot {slot} {play}: recorded payload "
                                     f"binding changed")
                if audit_replaced != json.dumps(vectors_before.get((slot, play), []),
                                                ensure_ascii=False):
                    raise ValueError(f"issue {issue} slot {slot} {play}: recorded replaced "
                                     f"vector changed")
                if audit_old_score != before[0] or audit_old_halftime != before[1]:
                    raise ValueError(f"issue {issue} slot {slot} {play}: recorded pre-recovery "
                                     f"values changed")
                gaps += 1
            # Everything outside the owed completions must be exactly as the backup left it
            # - same keys, same multiplicity, same values, same vectors - so a deletion, a
            # duplicate or an edit to an untouched fixture cannot hide behind the owed-key
            # loop.
            def outside(con, vectors):
                # A Counter, not a dict: a duplicated key must not overwrite its twin.
                return Counter(
                    (slot, play, native, score, halftime, option, payload,
                     json.dumps(vectors.get((slot, play), []), ensure_ascii=False))
                    for (slot, play, native, score, halftime, option, payload) in con.execute(
                        """SELECT slot, play, native_match_id, score, halftime_score,
                                  expected_option, payload_json FROM observation
                           WHERE issue=?""", (issue,))
                    if (slot, play) not in required)
            if outside(con, vectors_now) != outside(before_con, vectors_before):
                raise ValueError(f"issue {issue}: an observation outside the owed completions "
                                 f"was changed")
        return {"added_observations": added, "gap_observations": gaps}
    finally:
        before_con.close()


def recover_issues(database, ledger_path, backup_path, *, approval_note):
    """Apply an approved recovery ledger; back up first and roll back on any failure.

    Paths are explicit. Every inserted or completed value must be reproducible from the
    preserved archive bytes named in the ledger, and each target row must still hold the
    value the ledger recorded. Repeating the same ledger is a no-op only after verifying
    every recovered row. No fetching, no historical learning.
    """
    database, ledger_path, backup_path = map(Path, (database, ledger_path, backup_path))
    if not isinstance(approval_note, str) or not approval_note.strip():
        raise ValueError("Explicit approval note required")
    if len({p.resolve() for p in (database, ledger_path, backup_path)}) != 3:
        raise ValueError("Database, ledger and backup paths must be distinct")
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    batch = hashlib.sha256(ledger_bytes).hexdigest()
    if ledger.get("schema") != LEDGER_SCHEMA:
        raise ValueError("Wrong ledger schema")
    additions, gap_fills = ledger.get("additions") or [], ledger.get("gap_fills") or []
    if not additions and not gap_fills:
        raise ValueError("Empty ledger")
    issues = [i["issue"] for i in additions] + [i["issue"] for i in gap_fills]
    if len(set(issues)) != len(issues):
        raise ValueError("Ledger repeats an issue")

    con = sqlite3.connect(database.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
    reserved_backup = None
    try:
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM sqlite_master WHERE name='issue_recovery_batch'").fetchone():
            prior = con.execute(
                "SELECT added_observations, gap_observations FROM issue_recovery_batch "
                "WHERE batch_id=?", (batch,)).fetchone()
            if prior:
                verified = _verify_applied(con, batch, additions, gap_fills, database)
                if (verified["added_observations"] != prior[0]
                        or verified["gap_observations"] != prior[1]):
                    raise ValueError("Previously recovered row counts changed")
                con.rollback()
                return {"status": "already_applied", **verified}

        prepared_additions = [(item, _addition_rows(con, item)) for item in additions]
        prepared_gaps = [(item, _gap_targets(con, item)) for item in gap_fills]

        original_receipts = con.execute("SELECT payload_json FROM receipt").fetchall()
        if len(original_receipts) != 1:
            raise ValueError("Expected one original build receipt")

        # Reserve the backup path first; a second read-only connection can then back up
        # the stable committed snapshot without copying an active writer.
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
        con.execute(_CAPTURE_DDL)
        con.execute(_GAP_DDL)
        now = datetime.now(timezone.utc).isoformat()
        note = approval_note.strip()

        added_observations = added_fixtures = 0
        for item, rows in prepared_additions:
            issue = item["issue"]
            added_observations += len(rows)
            added_fixtures += len({r["slot"] for r in rows})
            for entry in item["evidence"]:
                replaced = con.execute("SELECT sha256 FROM capture WHERE issue=? AND typeid=?",
                                       (issue, entry["typeid"])).fetchone()
                con.execute("INSERT INTO issue_recovery_capture VALUES (?,?,?,?,?,?,?,?)",
                            (batch, issue, entry["typeid"], entry["url"], entry["sha256"],
                             entry["received_at"], entry["byte_count"],
                             replaced[0] if replaced else None))
                # The archive bytes are what now back this issue's observations.
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
                                [(observation_id, o["option"], o["raw_sp"], o["sp"], o["cell_id"])
                                 for o in row["options"]])
            for finding in audit_rows(rows):
                con.execute("INSERT INTO finding VALUES (?,?,?,?,?,?)",
                            tuple(finding[k] for k in ("issue", "slot", "play", "code",
                                                       "detail", "source_sha256")))

        gap_observations = 0
        for item, targets in prepared_gaps:
            # The gap-filled rows keep the live board as their primary source, so `capture`
            # is not rebound; the archive bytes that settled them are recorded here.
            for entry in item["evidence"]:
                con.execute("INSERT INTO issue_recovery_capture VALUES (?,?,?,?,?,?,?,?)",
                            (batch, item["issue"], entry["typeid"], entry["url"],
                             entry["sha256"], entry["received_at"], entry["byte_count"], None))
            for (observation_id, issue, slot, play, native_id, score, halftime, expected,
                 source, new_option, payload) in targets:
                # The live board publishes pre-match reference odds in the settlement
                # column while a fixture is unplayed, and the single settlement SP once it
                # settles. The archive's record is the settlement one, so the whole vector
                # is replaced and the reference vector is preserved as evidence.
                replaced_vector = _stored_vector(con, observation_id)
                for want in expected_settlement_vector(replaced_vector, source):
                    con.execute("UPDATE option_sp SET raw_sp=?, sp=?, cell_id=? "
                                "WHERE observation_id=? AND option=?",
                                (want["raw_sp"], want["sp"], want["cell_id"],
                                 observation_id, want["option"]))
                changed = con.execute(
                    """UPDATE observation SET score=?, halftime_score=?, expected_option=?
                       WHERE observation_id=? AND score=? AND halftime_score=?""",
                    (source["score"], source["halftime_score"], new_option, observation_id,
                     score, halftime))
                if changed.rowcount != 1:
                    raise ValueError("Conditional gap update did not affect exactly one row")
                con.execute("INSERT INTO issue_recovery_gap VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (observation_id, batch, issue, slot, play, native_id, score,
                             source["score"], halftime, source["halftime_score"], expected,
                             new_option, json.dumps(_settlement_vector(source),
                                                    ensure_ascii=False),
                             json.dumps(replaced_vector, ensure_ascii=False),
                             hashlib.sha256(payload.encode()).hexdigest(),
                             source["source_sha256"], note, now))
                gap_observations += 1

        manifest = [
            {"issue": item["issue"], "typeid": e["typeid"], "path": e["path"],
             "sha256": e["sha256"], "url": e["url"], "received_at": e["received_at"],
             "byte_count": e["byte_count"], "role": role}
            for role, entries in (("addition", additions), ("gap_fill", gap_fills))
            for item in entries for e in item["evidence"]
        ]
        con.execute("INSERT INTO issue_recovery_batch VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (batch, now, note, added_fixtures, added_observations, len(
                        {(g[1], g[2]) for _, targets in prepared_gaps for g in targets}),
                     gap_observations, original_receipts[0][0], ledger_bytes.decode(),
                     json.dumps(manifest, ensure_ascii=False), str(backup_path.resolve())))

        receipt = json.loads(original_receipts[0][0])
        receipt.update(
            issue_recovery_batch_id=batch,
            recovered_issues=sorted({i["issue"] for i in additions}),
            recovered_fixtures=added_fixtures,
            recovered_observations=added_observations,
            gap_filled_issues=sorted({i["issue"] for i in gap_fills}),
            gap_filled_fixtures=len({(g[1], g[2]) for _, targets in prepared_gaps
                                     for g in targets}),
            gap_filled_observations=gap_observations,
            issue_recovered_at=now,
            issue_recovery_note=(
                "The original build hashes describe the pre-recovery snapshot; see "
                "issue_recovery_batch.original_receipt_json and the SQLite backup. The "
                "recovered rows come from the source's own archive board, which renders "
                "fixtures the live board hides and settles fixtures captured before "
                "kickoff. Gap-filled rows also had the reference odds the live board "
                "published in the settlement column replaced by the archive's settlement "
                "SP; the replaced vector is kept in "
                "issue_recovery_gap.replaced_options_json."),
            effective_source="nowscore_with_audited_500_corrections_and_archive_recovery",
        )
        con.execute("UPDATE receipt SET payload_json=?", (json.dumps(receipt, ensure_ascii=False),))
        con.commit()
        return {"status": "applied", "batch_id": batch, "added_observations": added_observations,
                "added_fixtures": added_fixtures, "gap_observations": gap_observations,
                "backup": str(backup_path)}
    except Exception:
        con.rollback()
        # A run that failed before the backup completed must not leave a zero-byte file
        # that would block the retry.
        if reserved_backup is not None and reserved_backup.exists() \
                and reserved_backup.stat().st_size == 0:
            reserved_backup.unlink()
        raise
    finally:
        con.close()
