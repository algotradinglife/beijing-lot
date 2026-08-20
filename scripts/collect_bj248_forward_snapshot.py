#!/usr/bin/env python3
"""Run one configured prospective Nowscore TypeID=5 collection poll.

Example (operator chooses an external data volume):
  BEIJING_LOT_DATA_ROOT=/srv/beijing-lot-data \
  python scripts/collect_bj248_forward_snapshot.py --issue 26051
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from forward_snapshot.collector import collect_issue
from forward_snapshot.store import DATA_ROOT_ENV, SnapshotStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", action="append", required=True,
                        help="active Nowscore Beijing issue; repeatable")
    parser.add_argument("--min-interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if not os.environ.get(DATA_ROOT_ENV):
        parser.error(f"{DATA_ROOT_ENV} must be explicitly set for live collection")
    store = SnapshotStore.open()
    try:
        reports = [collect_issue(store, issue, min_interval_seconds=args.min_interval_seconds)
                   for issue in args.issue]
        print(json.dumps(reports, ensure_ascii=False, indent=2, sort_keys=True))
        return 1 if any(report["failures"] for report in reports) else 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
