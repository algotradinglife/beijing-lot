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
    evidence_sha256 TEXT NOT NULL, note TEXT NOT NULL, applied_at TEXT NOT NULL,
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


def settlement_vector_matches(stored: list[dict], archive_row: dict) -> bool:
    """True when a stored vector records the archive's settlement SP and nothing else.

    The archive publishes only the option that settled, while the release keeps whatever
    option domain its own source published (the live board lists every option). The
    comparison is therefore by option name: every option the archive names must carry its
    settlement SP, and every other option must carry none.
    """
    if not stored:
        return False
    archived = {o["option"]: o for o in archive_row["options"]}
    for row in stored:
        a = archived.get(row["option"])
        want = ((a["raw_sp"], a["sp"], a["cell_id"]) if a is not None else (None, None, None))
        if (row["raw_sp"], row["sp"], row["cell_id"]) != want:
            return False
    return True


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
                            halftime, expected, source, new_option))
    fixtures = {(t[1], t[2]) for t in targets}
    if len(fixtures) != item["expected_gap_fixtures"]:
        raise ValueError(f"issue {issue}: settled {len(fixtures)} gap fixtures, ledger expects "
                         f"{item['expected_gap_fixtures']}")
    if sorted({t[2] for t in targets}) != item["expected_gap_slots"]:
        raise ValueError(f"issue {issue}: settled slots differ from the ledger's expected slots")
    return targets


def _verify_applied(con, batch: str, additions: list[dict], gap_fills: list[dict]) -> dict:
    """Re-read the evidence and confirm the stored recovery still matches it.

    The idempotent path must not certify a damaged recovery, so counts alone are not
    enough: every added row, every added option and every completed value is compared
    against the bytes the ledger binds.
    """
    added = 0
    for item in additions:
        issue = item["issue"]
        stored = con.execute(
            """SELECT observation_id, slot, play, native_match_id, status, score,
                      halftime_score, expected_option, source_sha256, source_url, received_at
               FROM observation WHERE issue=?""", (issue,)).fetchall()
        rows = [row for entry in item["evidence"] for row in _parse_evidence(entry, issue)]
        if len(stored) != len(rows):
            raise ValueError(f"issue {issue}: stored {len(stored)} rows, evidence holds "
                             f"{len(rows)}")
        by_key = {(r["slot"], r["play"]): r for r in rows}
        for (observation_id, slot, play, native_id, status, score, halftime, expected,
             source_sha256, source_url, received_at) in stored:
            row = by_key.get((slot, play))
            if row is None:
                raise ValueError(f"issue {issue} slot {slot} {play}: stored row absent "
                                 f"from the evidence")
            held = (native_id, status, score, halftime, expected, source_sha256,
                    source_url, received_at)
            want = (row["native_match_id"], row["status"], row["score"],
                    row["halftime_score"], expected_option(row), row["source_sha256"],
                    row["source_url"], row["received_at"])
            if held != want:
                raise ValueError(f"issue {issue} slot {slot} {play}: recovered values changed")
            if _stored_vector(con, observation_id) != _settlement_vector(row):
                raise ValueError(f"issue {issue} slot {slot} {play}: recovered options changed")
            added += 1

    gaps = 0
    for item in gap_fills:
        issue = item["issue"]
        archive = {(row["slot"], row["play"]): row
                   for entry in item["evidence"] for row in _parse_evidence(entry, issue)}
        for (observation_id, slot, play, new_score, new_halftime, new_option,
             new_options, evidence_sha256) in con.execute(
                """SELECT observation_id, slot, play, new_score, new_halftime_score,
                          new_expected_option, new_options_json, evidence_sha256
                   FROM issue_recovery_gap WHERE batch_id=? AND issue=?""", (batch, issue)):
            source = archive.get((slot, play))
            if source is None or source["source_sha256"] != evidence_sha256:
                raise ValueError(f"issue {issue} slot {slot} {play}: gap evidence changed")
            held = con.execute(
                """SELECT score, halftime_score, expected_option FROM observation
                   WHERE observation_id=?""", (observation_id,)).fetchone()
            if held != (new_score, new_halftime, new_option):
                raise ValueError(f"issue {issue} slot {slot} {play}: completed values changed")
            if new_options != json.dumps(_settlement_vector(source), ensure_ascii=False):
                raise ValueError(f"issue {issue} slot {slot} {play}: completed options changed")
            if not settlement_vector_matches(_stored_vector(con, observation_id), source):
                raise ValueError(f"issue {issue} slot {slot} {play}: stored options changed")
            gaps += 1
    return {"added_observations": added, "gap_observations": gaps}


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
                verified = _verify_applied(con, batch, additions, gap_fills)
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
                 source, new_option) in targets:
                # The live board publishes pre-match reference odds in the settlement
                # column while a fixture is unplayed, and the single settlement SP once it
                # settles. The archive's record is the settlement one, so the whole vector
                # is replaced and the reference vector is preserved as evidence.
                replaced_vector = _stored_vector(con, observation_id)
                archived = {o["option"]: o for o in source["options"]}
                for option, raw_sp, sp, cell_id in con.execute(
                        "SELECT option, raw_sp, sp, cell_id FROM option_sp "
                        "WHERE observation_id=?", (observation_id,)).fetchall():
                    a = archived.get(option)
                    want = ((a["raw_sp"], a["sp"], a["cell_id"]) if a is not None
                            else (None, None, None))
                    if (raw_sp, sp, cell_id) != want:
                        con.execute("UPDATE option_sp SET raw_sp=?, sp=?, cell_id=? "
                                    "WHERE observation_id=? AND option=?",
                                    (want[0], want[1], want[2], observation_id, option))
                changed = con.execute(
                    """UPDATE observation SET score=?, halftime_score=?, expected_option=?
                       WHERE observation_id=? AND score=? AND halftime_score=?""",
                    (source["score"], source["halftime_score"], new_option, observation_id,
                     score, halftime))
                if changed.rowcount != 1:
                    raise ValueError("Conditional gap update did not affect exactly one row")
                con.execute("INSERT INTO issue_recovery_gap VALUES "
                            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (observation_id, batch, issue, slot, play, native_id, score,
                             source["score"], halftime, source["halftime_score"], expected,
                             new_option, json.dumps(_settlement_vector(source),
                                                    ensure_ascii=False),
                             json.dumps(replaced_vector, ensure_ascii=False),
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
