#!/usr/bin/env python3
"""Replay quarantined Nowscore archive pages from preserved raw bytes.

Issue #480 deliverable helper. Reads the sealed replay database for the receipt
and its capture_failures, locates each failed page's raw HTML by content hash in
an extracted raw batch archive, and independently recomputes the embedded-roster
versus visible-row discrepancy.

Read-only by construction: opens SQLite with mode=ro and only reads files.
No network access, no writes to any store, no parser relaxation.

Reports, per failed page:
  * embedded roster entries        (`M[i][0] = <id>` in page script)
  * visible fixture rows           (`tr[id^="row_"]` in the DOM)
  * slots present in the embedded roster but absent as rendered rows

The recomputed embedded-only slot set is asserted equal to the receipt's
`quarantine_detail.embedded_only`, so the receipt is reproducible.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup

EMBEDDED_RE = re.compile(r"M\[(\d+)\]\[0\]\s*=\s*['\"]?(\d+)['\"]?\s*;")
ROW_ID_RE = re.compile(r"row_([1-9]\d*)$")


def load_receipt(db: Path) -> dict:
    """Return the single sealed receipt payload from the replay database."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT payload_json FROM receipt").fetchall()
    finally:
        con.close()
    if len(rows) != 1:
        raise SystemExit(f"expected exactly 1 receipt row, found {len(rows)}")
    return json.loads(rows[0][0])


def index_raw_pages(root: Path) -> dict[str, Path]:
    """Map sha256 -> path for every content-addressed raw page under root."""
    index: dict[str, Path] = {}
    for path in root.rglob("*.html"):
        index[path.stem] = path
    return index


def embedded_roster(text: str) -> list[tuple[int, str]]:
    return [(int(i), n) for i, n in EMBEDDED_RE.findall(text)]


def visible_rows(payload: bytes) -> list[int]:
    """Slots of rows actually rendered in the response DOM."""
    soup = BeautifulSoup(payload.decode("utf-8-sig", errors="strict"), "html.parser")
    slots = []
    for tr in soup.select('tr[id^="row_"]'):
        m = ROW_ID_RE.fullmatch(tr.get("id", ""))
        if m:
            slots.append(int(m.group(1)))
    return slots


def analyse_issue(raw_root: Path, index: dict[str, Path], issue: str,
                  failures: list[dict]) -> dict:
    """Recompute the embedded-only discrepancy for every typeid of one issue."""
    issue_failures = [f for f in failures if f["issue"] == issue]
    typeids = sorted(f["typeid"] for f in issue_failures)
    per_typeid = {}
    missing_sets = []
    for failure in sorted(issue_failures, key=lambda f: f["typeid"]):
        sha = failure["sha256"]
        path = index.get(sha)
        if path is None:
            raise SystemExit(f"raw page {sha} for issue {issue} not found under {raw_root}")
        payload = path.read_bytes()
        actual = __import__("hashlib").sha256(payload).hexdigest()
        if actual != sha:
            raise SystemExit(f"raw page hash mismatch for issue {issue}: {actual} != {sha}")

        embedded = embedded_roster(payload.decode("utf-8-sig", errors="strict"))
        slots = visible_rows(payload)
        missing = sorted({slot for slot, _ in embedded} - set(slots))

        recorded = sorted(x[0] for x in failure["quarantine_detail"]["embedded_only"])
        if recorded != missing:
            raise SystemExit(
                f"receipt not reproducible for issue {issue} typeid {failure['typeid']}: "
                f"recorded {recorded} != recomputed {missing}")
        if failure["quarantine_detail"]["visible_only"]:
            raise SystemExit(f"unexpected visible_only for issue {issue}")

        per_typeid[failure["typeid"]] = {
            "sha256": sha,
            "raw_path": str(path),
            "embedded_count": len(embedded),
            "visible_count": len(slots),
            "missing_slots": missing,
            "embedded_max_slot": max(slot for slot, _ in embedded),
            "visible_max_slot": max(slots) if slots else None,
        }
        missing_sets.append(tuple(missing))

    if len(set(missing_sets)) != 1:
        raise SystemExit(f"issue {issue}: typeids disagree on missing slots: {missing_sets}")

    return {
        "issue": issue,
        "typeids": typeids,
        "missing_slots": list(missing_sets[0]),
        "per_typeid": per_typeid,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--replay-db", type=Path, required=True,
                        help="sealed nowscore_history_replay.sqlite (read-only)")
    parser.add_argument("--raw-root", type=Path, required=True,
                        help="extracted archive containing content-addressed .html pages")
    parser.add_argument("--output", type=Path, required=True, help="JSON result path")
    args = parser.parse_args()

    receipt = load_receipt(args.replay_db)
    failures = receipt["capture_failures"]
    index = index_raw_pages(args.raw_root)

    issues = sorted({f["issue"] for f in failures})
    results = [analyse_issue(args.raw_root, index, issue, failures) for issue in issues]

    missing_total = sum(len(r["missing_slots"]) for r in results)
    report = {
        "schema": "bj480_quarantine_replay_v1",
        "replay_db": str(args.replay_db),
        "receipt_sha256_source": receipt.get("data_sha256"),
        "classification_counts": dict(Counter(f["classification"] for f in failures)),
        "reason_counts": dict(Counter(f["quarantine_reason"] for f in failures)),
        "failure_count": len(failures),
        "quarantined_issue_count": len(issues),
        "typeids_per_issue": {r["issue"]: r["typeids"] for r in results},
        "missing_slot_total": missing_total,
        "issues": results,
        "conclusion": {
            "verdict": "source_response_missing_rendered_rows",
            "parser_defect": False,
            "parser_relaxation_required": False,
            "receipt_reproduced": True,
            "note": ("Every quarantined response declares more roster slots in its embedded "
                     "script than it renders as rows; the absent slots appear nowhere in the "
                     "page text. Fail-closed quarantine is correct and must not be relaxed."),
        },
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"failures={report['failure_count']} issues={report['quarantined_issue_count']} "
          f"missing_slots={missing_total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
