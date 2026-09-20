#!/usr/bin/env python3
"""Run no-agent 500 issue-slot to Nowscore-ID mapping until index exhaustion.

Multi-worker: a bounded pool of workers pulls issues from a shared queue; each
issue reserves its two HTTP requests against the shared rolling per-minute
ledger before touching the network, so the total rate stays within the risk
acknowledgment no matter how many workers run.
"""

from __future__ import annotations

import argparse
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backfill.scraper import fetch_issue_list, make_session  # noqa: E402
from src.titan_clean.historical_id_map import HistoricalIdMapStore  # noqa: E402
from src.titan_clean.risk_acknowledgment import load_risk_acknowledgment  # noqa: E402
from src.titan_clean.store import TitanRosterStore, TitanStoreError  # noqa: E402

MAX_ATTEMPTS = 4
MAX_FAILED_ISSUES = 50
BACKOFF_BASE_SECONDS = 10


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def current_failures(root: Path) -> dict[str, int]:
    store = HistoricalIdMapStore.open(root)
    try:
        rows = store.connection.execute(
            "SELECT issue_code, COUNT(*) FROM mapping_failure GROUP BY issue_code"
        ).fetchall()
    finally:
        store.close()
    return {issue: count for issue, count in rows}


def pending_issues(root: Path) -> list[str]:
    store = HistoricalIdMapStore.open(root)
    try:
        completed = {row.issue_code for row in store.mappings()}
    finally:
        store.close()
    failed = current_failures(root)
    return [
        value for value in fetch_issue_list(make_session())
        if value not in completed and failed.get(value, 0) < MAX_ATTEMPTS
    ]


def reserve_for_issue(root: Path, receipt_sha256: str, issue: str) -> None:
    """Block until two requests are reserved in the shared rolling window."""
    while True:
        store = TitanRosterStore.open(root)
        try:
            store.reserve_low_frequency_capture(
                batch_id=f"map:{now_utc()}:{issue}",
                receipt_sha256=receipt_sha256,
                reserved_at_utc=now_utc(),
                request_count=2,
                max_requests_per_minute=60,
            )
            return
        except TitanStoreError:
            time.sleep(1)
        finally:
            store.close()


def run_issue(root: Path, issue: str) -> bool:
    attempts = current_failures(root).get(issue, 0)
    capture_key = f"historical-id-map-{now_utc()}"
    try:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "collect_historical_id_mapping.py"),
                "--data-root", str(root), "--issue", issue, "--capture-key", capture_key,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as exc:
        store = HistoricalIdMapStore.open(root)
        try:
            detail = (exc.stderr or exc.stdout or "").strip()[:1000]
            store.record_failure(
                issue_code=issue,
                attempted_at_utc=now_utc(),
                error=RuntimeError(f"{exc.returncode}: {detail}"),
            )
        finally:
            store.close()
        remaining = MAX_ATTEMPTS - attempts - 1
        if remaining > 0:
            time.sleep(BACKOFF_BASE_SECONDS * (attempts + 1))
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--risk-acknowledgment", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    risk = load_risk_acknowledgment(args.risk_acknowledgment)
    issues = pending_issues(args.data_root)
    print({"pending": len(issues), "workers": args.workers})
    work_queue: queue.Queue[str | None] = queue.Queue()
    for issue in issues:
        work_queue.put(issue)
    for _ in range(args.workers):
        work_queue.put(None)

    lock = threading.Lock()
    state = {"done": 0, "failed": 0, "last_print": time.monotonic()}

    def worker() -> None:
        while True:
            issue = work_queue.get()
            if issue is None:
                return
            reserve_for_issue(args.data_root, risk.receipt_sha256, issue)
            ok = run_issue(args.data_root, issue)
            with lock:
                state["done"] += 1
                if not ok:
                    state["failed"] += 1
                if time.monotonic() - state["last_print"] >= 10 or work_queue.empty():
                    state["last_print"] = time.monotonic()
                    print({"done": state["done"], "failed": state["failed"], "queued": work_queue.qsize()}, flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    print({"status": "ALL_ISSUES_DONE", "done": state["done"], "failed": state["failed"]})


if __name__ == "__main__":
    main()
