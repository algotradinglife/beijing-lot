#!/usr/bin/env python3
"""Quarantine cross-issue reschedule ghost mappings.

A Titan provider ID referenced by more than one issue is a rescheduled match
(500/Nowscore keep the original issue slot plus the actual one). Each duplicate
provider is probed on Titan; its kickoff time (UTC, converted to Beijing) must
match the 500 cutoff time of exactly one issue. Rows whose issue does not match
are quarantined into conflict_isolated_slot and removed from the mapping table.
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.scrape_500_bjdc import parse_issue_rows  # noqa: E402

HKT = timezone(timedelta(hours=8))
MATCH_TOLERANCE_HOURS = 12


def fetch_titan_matchtime(provider: str, timeout: float = 25) -> datetime | None:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                f"https://1x2d.titan007.com/{provider}.js",
                headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
            )
            text = urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8-sig", errors="replace")
            match = re.search(r'MatchTime="([^"]+)"', text)
            if not match:
                return None
            parts = match.group(1).split(",")
            if len(parts) < 6:
                return None
            try:
                return datetime(int(parts[0]), int(parts[1][:2]), int(parts[2]), int(parts[3]), int(parts[4]),
                                tzinfo=timezone.utc).astimezone(HKT)
            except ValueError:
                return None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            last_error = exc
            time.sleep(5 * (attempt + 1))
    raise last_error


def parse_500_cutoff(value: str) -> datetime | None:
    try:
        return datetime.strptime(str(value), "%Y-%m-%d %H:%M").replace(tzinfo=HKT)
    except ValueError:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--rate-per-minute", type=int, default=60)
    args = parser.parse_args()

    root = Path(args.data_root)
    connection = sqlite3.connect(root / "control/external_id_discovery/discovery.sqlite")
    rows = connection.execute(
        "SELECT issue_code, issue_slot, local_500_fid, nowscore_provider_match_id FROM issue_slot_nowscore_map"
    ).fetchall()
    by_provider: dict[str, list[tuple[str, int, int]]] = {}
    for issue, slot, fid, provider in rows:
        by_provider.setdefault(provider, []).append((issue, slot, fid))
    duplicates = {provider: occ for provider, occ in by_provider.items() if len(occ) > 1}
    print({"duplicate_providers": len(duplicates), "rows": sum(len(v) for v in duplicates.values())})

    quarantined = 0
    probed = 0
    probe_failures = 0
    interval = 60.0 / args.rate_per_minute
    parsed_issues: dict[str, dict[int, dict[str, object]]] = {}
    for provider, occurrences in sorted(duplicates.items()):
        try:
            kickoff = fetch_titan_matchtime(provider)
        except (urllib.error.URLError, TimeoutError):
            probe_failures += 1
            continue
        probed += 1
        if probed % args.rate_per_minute == 0 and probed > 0:
            print({"probed": probed, "quarantined": quarantined, "probe_failures": probe_failures}, flush=True)
        if kickoff is None:
            probe_failures += 1
            continue
        for issue, slot, fid in occurrences:
            if issue not in parsed_issues:
                coverage = connection.execute(
                    "SELECT raw_path FROM source_receipt WHERE issue_code=? AND source_id='500_issue_coverage' ORDER BY trusted_received_at_utc DESC LIMIT 1",
                    (issue,),
                ).fetchone()
                if not coverage:
                    parsed_issues[issue] = {}
                else:
                    rows_500 = parse_issue_rows(issue, (root / coverage[0]).read_bytes().decode("gb18030", errors="replace"), fetched_at="x")
                    parsed_issues[issue] = {int(r["match_idx"]): r for r in rows_500 if r["match_idx"]}
            row = parsed_issues[issue].get(slot)
            if row is None:
                continue
            cutoff = parse_500_cutoff(row.get("end_time"))
            if cutoff is None:
                continue
            diff_hours = abs((kickoff - cutoff).total_seconds()) / 3600
            if diff_hours <= MATCH_TOLERANCE_HOURS:
                continue
            with connection:
                connection.execute(
                    "DELETE FROM issue_slot_nowscore_map WHERE issue_code=? AND issue_slot=?",
                    (issue, slot),
                )
                connection.execute(
                    "INSERT OR REPLACE INTO conflict_isolated_slot VALUES(?,?,?,?,?)",
                    (issue, slot, fid, provider,
                     f"cross-issue reschedule ghost: provider {provider} kickoff {kickoff:%Y-%m-%d %H:%M} HKT vs 500 {row.get('end_time')}"),
                )
            quarantined += 1
        time.sleep(interval)

    remaining = connection.execute("SELECT COUNT(*) FROM issue_slot_nowscore_map").fetchone()[0]
    print({"probed": probed, "probe_failures": probe_failures, "quarantined": quarantined, "remaining_mappings": remaining})
    connection.close()


if __name__ == "__main__":
    main()
