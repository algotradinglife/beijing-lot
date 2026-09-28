#!/usr/bin/env python3
"""Audit issue-slot mappings for 500/Nowscore team alignment.

Reads the content-addressed raw pages already stored in the discovery ledger
and verifies every mapped row: 500 team names must match the Nowscore row the
mapped provider points to. Rows whose teams differ are reported so they can be
quarantined (they may be translation differences or genuine misalignments).
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.collect_historical_id_mapping import nowscore_team_pairs  # noqa: E402
from scripts.scrape_500_bjdc import parse_issue_rows  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()

    root = Path(args.data_root)
    path = root / "control" / "external_id_discovery" / "discovery.sqlite"
    connection = sqlite3.connect(path)
    issues = [row[0] for row in connection.execute("SELECT DISTINCT issue_code FROM issue_slot_nowscore_map ORDER BY issue_code")]
    mismatches: list[tuple[str, int, str, str]] = []
    for issue in issues:
        coverage = connection.execute(
            "SELECT raw_path FROM source_receipt WHERE issue_code=? AND source_id='500_issue_coverage' ORDER BY trusted_received_at_utc DESC LIMIT 1",
            (issue,),
        ).fetchone()
        nowscore = connection.execute(
            "SELECT raw_path FROM source_receipt WHERE issue_code=? AND source_id='nowscore_id_mapping' ORDER BY trusted_received_at_utc DESC LIMIT 1",
            (issue,),
        ).fetchone()
        if not coverage or not nowscore:
            continue
        rows_500 = parse_issue_rows(issue, (root / coverage[0]).read_bytes().decode("gb18030", errors="replace"), fetched_at="x")
        by_slot = {int(row["match_idx"]): row for row in rows_500 if row["match_idx"]}
        ns_pairs = nowscore_team_pairs((root / nowscore[0]).read_bytes())
        text = (root / nowscore[0]).read_bytes().decode("utf-8", "replace")
        matrix: dict[int, dict[int, str]] = {}
        for match in re.finditer(r"M\[(\d+)\]\[(\d+)\]\s*=\s*(.*?);", text, flags=re.S):
            row, field, value = int(match.group(1)), int(match.group(2)), match.group(3).strip()
            matrix.setdefault(row, {})[field] = value
        slot_by_provider: dict[str, list[int]] = {}
        prov_by_slot: dict[int, str] = {}
        for fields in matrix.values():
            if 16 in fields and 0 in fields:
                slot_by_provider.setdefault(fields[0], []).append(int(fields[16]))
                prov_by_slot[int(fields[16])] = fields[0]
        mapped = connection.execute(
            "SELECT issue_slot, nowscore_provider_match_id FROM issue_slot_nowscore_map WHERE issue_code=?", (issue,)
        ).fetchall()
        for slot, provider in mapped:
            ns_slots = slot_by_provider.get(provider)
            if not ns_slots:
                mismatches.append((issue, slot, provider, "provider missing from Nowscore matrix"))
                continue
            ns_slot = ns_slots[0]
            row_500 = by_slot.get(slot)
            if row_500 is None:
                mismatches.append((issue, slot, provider, "500 slot missing"))
                continue
            home, away, _ = ns_pairs.get(ns_slot, ("", "", ""))
            if row_500["home"] != home or row_500["away"] != away:
                exact_elsewhere = [
                    ns for ns in ns_pairs
                    if ns in prov_by_slot
                    and ns_pairs[ns][0] == row_500["home"]
                    and ns_pairs[ns][1] == row_500["away"]
                ]
                if exact_elsewhere:
                    kind = f"MISALIGNED (500 team exists at ns slot(s) {sorted(exact_elsewhere)})"
                else:
                    kind = "TRANSLATION-DIFF"
                mismatches.append(
                    (issue, slot, provider,
                     f"{kind}: 500 {row_500['home']}/{row_500['away']} vs ns slot {ns_slot} {home}/{away}")
                )
    connection.close()

    print({"issues": len(issues), "mismatched_rows": len(mismatches)})
    for issue, slot, provider, detail in mismatches:
        print(f"{issue} slot {slot} provider {provider}: {detail}")


if __name__ == "__main__":
    main()
