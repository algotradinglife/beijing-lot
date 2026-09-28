#!/usr/bin/env python3
"""Show a live-updating progress bar for the 500 settlement collector."""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


def snapshot(root: Path) -> dict[str, object]:
    db = root / "control" / "settlement_500" / "settlement.sqlite"
    with sqlite3.connect(db) as con:
        captured = con.execute("SELECT COUNT(DISTINCT issue_code) FROM raw_settlement_capture").fetchone()[0]
        rows = con.execute("SELECT COUNT(*) FROM raw_settlement_row").fetchone()[0]
        settled = con.execute("SELECT COUNT(*) FROM raw_settlement_row WHERE result_code IS NOT NULL").fetchone()[0]
        latest = con.execute("SELECT MAX(trusted_received_at_utc) FROM raw_settlement_capture").fetchone()[0]
    return {"captured": int(captured), "rows": int(rows), "settled": int(settled), "latest": latest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--total-issues", type=int, default=1612)
    args = parser.parse_args()

    start = time.monotonic()
    prev: dict[str, object] | None = None
    while True:
        snap = snapshot(args.data_root)
        rate = 0.0
        if prev is not None:
            dt = time.monotonic() - start
            rate = (int(snap["captured"]) - int(prev["captured"])) / max(dt, 1.0) * 60
        eta = ""
        if rate > 0:
            remaining = args.total_issues - int(snap["captured"])
            eta = f" ETA {remaining / rate:.0f}m"
        bar_len = 50
        filled = int(bar_len * int(snap["captured"]) / args.total_issues)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"\r[settle] 期次 {snap['captured']}/{args.total_issues} {bar} "
              f"行 {snap['rows']} | 结算 {snap['settled']} | 速率 {rate:.1f}期/分{eta}",
              end="", flush=True)
        prev = snap
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    main()
