#!/usr/bin/env python3
"""Show a live-updating progress bar for the historical ID mapping backfill."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backfill.scraper import fetch_issue_list, make_session  # noqa: E402

SERVICE_NAME = "beidanlot-historical-id-map.service"


def snapshot(root: Path) -> dict[str, object]:
    path = root / "control" / "external_id_discovery" / "discovery.sqlite"
    with sqlite3.connect(path) as connection:
        mapped_issues = {row[0] for row in connection.execute("SELECT DISTINCT issue_code FROM issue_slot_nowscore_map")}
        mapped_slots = connection.execute("SELECT COUNT(*) FROM issue_slot_nowscore_map").fetchone()[0]
        failures = connection.execute(
            "SELECT issue_code, COUNT(*) FROM mapping_failure GROUP BY issue_code ORDER BY issue_code"
        ).fetchall()
    known = fetch_issue_list(make_session())
    remaining = [issue for issue in known if issue not in mapped_issues and issue not in {row[0] for row in failures}]
    return {
        "known": len(known),
        "mapped_issues": len(mapped_issues),
        "mapped_slots": mapped_slots,
        "failed": failures,
        "remaining": remaining,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    args = parser.parse_args()

    first = True
    prev_count: int | None = None
    prev_time = time.monotonic()
    while True:
        try:
            state = snapshot(args.data_root)
        except Exception as exc:
            print(f"\r[error] {exc}".ljust(shutil.get_terminal_size((100, 20)).columns))
            time.sleep(args.interval_seconds)
            continue
        now = time.monotonic()
        rate_per_min = 0.0
        eta = "?"
        if prev_count is not None:
            elapsed_min = (now - prev_time) / 60.0
            delta = state["mapped_issues"] - prev_count
            if elapsed_min > 0 and delta > 0:
                rate_per_min = delta / elapsed_min
            remaining = len(state["remaining"])
            if rate_per_min > 0:
                eta_minutes = remaining / rate_per_min
                eta = f"{int(eta_minutes // 60)}h{int(eta_minutes % 60)}m"
        prev_count = state["mapped_issues"]
        prev_time = now

        done = state["mapped_issues"]
        total = state["known"]
        width = max(shutil.get_terminal_size((100, 20)).columns - 52, 20)
        filled = int(width * done / total) if total else width
        bar = "█" * filled + "░" * (width - filled)
        service = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME], capture_output=True, text=True
        ).stdout.strip()
        failures = ", ".join(f"{issue}×{count}" for issue, count in state["failed"]) or "无"
        line = (
            f"[{service}] 期次 {done}/{total} {bar} "
            f"场次 {state['mapped_slots']} | 速率 {rate_per_min:.0f}期/分 | ETA {eta} | 失败 {failures}"
        )
        print("\r" + line.ljust(shutil.get_terminal_size((100, 20)).columns), end="", flush=True)
        if first:
            print("\n", end="", flush=True)
            first = False
        if state["remaining"]:
            print(f"\r[即将处理] {', '.join(state['remaining'][:8])}".ljust(shutil.get_terminal_size((100, 20)).columns))
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[已停止]")
