#!/usr/bin/env python3
"""Show a live-updating progress bar for the Titan historical fixture collector."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SERVICE_NAME = "beidanlot-titan-historical-collect.service"


def snapshot(root: Path, bridge: Path) -> dict[str, object]:
    with sqlite3.connect(root / "control/titan/control.sqlite") as connection:
        captured = connection.execute("SELECT COUNT(*) FROM historical_fixture_capture").fetchone()[0]
        quotes = connection.execute("SELECT COUNT(*) FROM historical_euro_1x2_quote").fetchone()[0]
        failed = connection.execute("SELECT COUNT(DISTINCT source_fixture_id) FROM historical_fixture_failure").fetchone()[0]
    total = len(json.loads(bridge.read_text())["candidates"])
    return {"captured": int(captured), "quotes": int(quotes), "failed": int(failed), "total": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--bridge", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--rate-per-minute", type=int, default=60)
    args = parser.parse_args()

    started_at = time.monotonic()
    first = True
    while True:
        try:
            state = snapshot(args.data_root, args.bridge)
        except Exception as exc:
            print(f"\r[error] {exc}".ljust(shutil.get_terminal_size((100, 20)).columns))
            time.sleep(args.interval_seconds)
            continue
        done = state["captured"] + state["failed"]
        total = state["total"]
        width = max(shutil.get_terminal_size((100, 20)).columns - 48, 20)
        filled = int(width * done / total) if total else width
        bar = "█" * filled + "░" * (width - filled)
        service = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME], capture_output=True, text=True
        ).stdout.strip()
        remaining_count = max(total - done, 0)
        if args.rate_per_minute > 0:
            eta_minutes = remaining_count / args.rate_per_minute
            eta = f"{int(eta_minutes // 60)}h{int(eta_minutes % 60)}m"
        else:
            eta = "?"
        elapsed = time.monotonic() - started_at
        line = (
            f"[{service}] 采集 {state['captured']}/{total} {bar} "
            f"报价 {state['quotes']} | 失败 {state['failed']} | 剩余 {remaining_count} | ETA {eta} | 已运行 {int(elapsed // 60)}m"
        )
        print("\r" + line.ljust(shutil.get_terminal_size((100, 20)).columns), end="", flush=True)
        if first:
            print("\n", end="", flush=True)
            first = False
        if state["captured"] + state["failed"] >= total:
            print(f"\r[完成] 全部 {total} 个候选已处理".ljust(shutil.get_terminal_size((100, 20)).columns))
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[已停止]")
