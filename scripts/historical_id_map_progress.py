#!/usr/bin/env python3
"""Print the no-agent historical ID mapping backfill progress summary."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backfill.scraper import fetch_issue_list, make_session  # noqa: E402

SERVICE_NAME = "beidanlot-historical-id-map.service"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()

    path = args.data_root / "control" / "external_id_discovery" / "discovery.sqlite"
    if not path.exists():
        print({"error": f"discovery ledger missing: {path}"})
        sys.exit(1)

    with sqlite3.connect(path) as connection:
        mapped_issues = {row[0] for row in connection.execute("SELECT DISTINCT issue_code FROM issue_slot_nowscore_map")}
        mapped_slots = connection.execute("SELECT COUNT(*) FROM issue_slot_nowscore_map").fetchone()[0]
        failed_issues = {row[0] for row in connection.execute("SELECT DISTINCT issue_code FROM mapping_failure")}
        failed_detail = connection.execute(
            "SELECT issue_code, COUNT(*), MAX(error_detail) FROM mapping_failure GROUP BY issue_code ORDER BY issue_code"
        ).fetchall()

    known_issues = fetch_issue_list(make_session())
    remaining = [issue for issue in known_issues if issue not in mapped_issues and issue not in failed_issues]
    service = subprocess.run(
        ["systemctl", "--user", "is-active", SERVICE_NAME], capture_output=True, text=True
    ).stdout.strip()

    print({
        "service_active": service,
        "known_500_issues": len(known_issues),
        "mapped_issues": len(mapped_issues),
        "mapped_slots": mapped_slots,
        "failed_issues": len(failed_issues),
        "remaining_issues": len(remaining),
        "next_issues": remaining[:8],
        "failures": failed_detail,
    })


if __name__ == "__main__":
    main()
