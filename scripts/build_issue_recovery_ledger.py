"""Build the owner-approved issue-recovery ledger from preserved archive evidence.

Issue #479 deliverable. Reads the archived play pages already saved under the evidence
directory, binds each one by hash, URL and byte count, and derives the unsettled fixture
slots from the sealed release itself, so the ledger states expectations rather than
assumptions. Nothing is fetched and the database is opened read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.nowscore_settlement import ARCHIVE_SLUGS, PLAYS, parse_page  # noqa: E402
from src.settlement_issue_recovery import SETTLED_SCORE  # noqa: E402
from src.settlement_storage import validate_settlement_storage  # noqa: E402

LEDGER_SCHEMA = "bj479_issue_recovery_ledger_v1"


def _evidence(directory: Path, issue: str, typeid: int) -> dict:
    """Bind one preserved archive page by hash, URL and local receipt time."""
    path = directory / f"nowscore-archive-{typeid}-{issue}.html"
    payload = path.read_bytes()
    received_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    return {
        "typeid": typeid,
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "url": f"https://cp.nowscore.com/beijingdanchang/{ARCHIVE_SLUGS[typeid]}/"
               f"kaijiang_dc_{typeid}_{issue}.html",
        "received_at": received_at,
        "byte_count": len(payload),
    }


def _fixture_count(directory: Path, issue: str) -> int:
    counts = set()
    for typeid in sorted(PLAYS):
        payload = (directory / f"nowscore-archive-{typeid}-{issue}.html").read_bytes()
        counts.add(len({r["slot"] for r in parse_page(payload, issue, typeid)}))
    if len(counts) != 1:
        raise ValueError(f"issue {issue}: archive plays disagree on the fixture count: {counts}")
    return counts.pop()


def _settled_slots(evidence_dir: Path, issue: str) -> set[int]:
    """Slots the archive settles with a real score, across every play."""
    settled = set()
    for typeid in sorted(PLAYS):
        payload = (evidence_dir / f"nowscore-archive-{typeid}-{issue}.html").read_bytes()
        for row in parse_page(payload, issue, typeid):
            if SETTLED_SCORE.match(row["score"] or ""):
                settled.add(row["slot"])
    return settled


def _gap_slots(database: Path, evidence_dir: Path, issue: str) -> list[int]:
    """Slots the release holds without a score that the archive can actually settle.

    A cancelled fixture is unsettled in both, so it is not a gap to complete.
    """
    con = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        unsettled = {row[0] for row in con.execute(
            "SELECT slot FROM observation WHERE issue=? AND (score='' OR score='-')", (issue,))}
    finally:
        con.close()
    slots = sorted(unsettled & _settled_slots(evidence_dir, issue))
    if not slots:
        raise ValueError(f"issue {issue}: no unsettled slot that the archive settles")
    return slots


def build_ledger(database: Path, evidence_dir: Path, additions, gap_fills, authorization: str) -> dict:
    if not authorization.strip():
        raise ValueError("Explicit authorization required")
    if not additions and not gap_fills:
        raise ValueError("Nothing to recover")
    if {issue for issue, _ in additions} & {issue for issue, _ in gap_fills}:
        raise ValueError("An issue cannot be both added and gap-filled")
    addition_issues = {issue for issue, _ in additions}
    entries = []
    for issue, expected in additions + gap_fills:
        entries.append({"issue": issue, "expected_fixtures": expected,
                        "evidence": [_evidence(evidence_dir, issue, t) for t in sorted(PLAYS)]})
    for entry in entries:
        actual = _fixture_count(evidence_dir, entry["issue"])
        if actual != entry["expected_fixtures"]:
            raise ValueError(f"issue {entry['issue']}: evidence holds {actual} fixtures, "
                             f"expected {entry['expected_fixtures']}")
    gap_entries = [e for e in entries if e["issue"] not in addition_issues]
    for entry in gap_entries:
        slots = _gap_slots(database, evidence_dir, entry["issue"])
        entry["expected_gap_fixtures"] = len(slots)
        entry["expected_gap_slots"] = slots
    return {
        "schema": LEDGER_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "authorization": authorization.strip(),
        "evidence_class": (
            "Source's own archive board, captured after settlement. `received_at` is the "
            "local receipt time of the preserved bytes, not a server timestamp."),
        "additions": [e for e in entries if e["issue"] in addition_issues],
        "gap_fills": gap_entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--evidence-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--mountpoint", type=Path)
    parser.add_argument("--authorization", required=True)
    parser.add_argument("--addition", action="append", default=[], metavar="ISSUE:FIXTURES")
    parser.add_argument("--gap-fill", action="append", default=[], metavar="ISSUE:FIXTURES")
    args = parser.parse_args()

    validate_settlement_storage(args.data_root, [args.database], mountpoint=args.mountpoint)

    def pairs(values):
        return [(v.split(":")[0], int(v.split(":")[1])) for v in values]

    ledger = build_ledger(args.database, args.evidence_dir, pairs(args.addition),
                          pairs(args.gap_fill), args.authorization)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {args.output}: {len(ledger['additions'])} additions, "
          f"{len(ledger['gap_fills'])} gap fills")
    for entry in ledger["additions"] + ledger["gap_fills"]:
        extra = (f", gap {entry['expected_gap_fixtures']} fixtures "
                 f"slots {entry['expected_gap_slots'][0]}..{entry['expected_gap_slots'][-1]}"
                 if "expected_gap_fixtures" in entry else "")
        print(f"  {entry['issue']}: {entry['expected_fixtures']} fixtures{extra}")


if __name__ == "__main__":
    main()
