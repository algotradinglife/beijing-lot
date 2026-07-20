#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.sqlite_runtime import connect_sqlite  # noqa: E402

DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resolve_issues(db_path: Path, requested: list[str]) -> list[str]:
    issues: list[str] = []
    explicit = [issue for issue in requested if issue != "current"]
    issues.extend(explicit)
    if "current" in requested:
        conn = connect_sqlite(db_path)
        try:
            rows = conn.execute(
                """
                SELECT issue
                FROM issues
                WHERE is_current=1
                ORDER BY ordinal ASC, issue DESC
                LIMIT 1
                """
            ).fetchall()
        finally:
            conn.close()
        issues.extend(str(row[0]) for row in rows)
    seen: set[str] = set()
    out: list[str] = []
    for issue in issues:
        if issue and issue not in seen:
            out.append(issue)
            seen.add(issue)
    return out


def refresh_once(db_path: Path, issues: list[str], timeout: int) -> int:
    command = [
        sys.executable,
        str(ROOT / "scripts/scrape_nowscore_bjdc.py"),
        "--db",
        str(db_path),
        "--issue",
        ",".join(issues),
        "--timeout",
        str(timeout),
        "--keep-going",
    ]
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if proc.stdout.strip():
        print(proc.stdout.strip(), flush=True)
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr, flush=True)
    return proc.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh live Beidan/Jiebao scores on a low-frequency loop.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--issue", action="append", default=["current"], help="Issue id, comma-separated list, or current.")
    parser.add_argument("--interval", type=float, default=120.0)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    requested = [part.strip() for raw in args.issue for part in raw.split(",") if part.strip()]
    while True:
        started = time.monotonic()
        try:
            issues = resolve_issues(args.db, requested)
            if issues:
                print(f"[{now_iso()}] live_score_refresh issues={','.join(issues)}", flush=True)
                rc = refresh_once(args.db, issues, args.timeout)
                print(f"[{now_iso()}] live_score_refresh done rc={rc}", flush=True)
            else:
                print(f"[{now_iso()}] live_score_refresh no current issue", flush=True)
        except Exception as exc:  # keep the loop alive for transient site/db errors
            print(f"[{now_iso()}] live_score_refresh error {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.once:
            return
        elapsed = time.monotonic() - started
        time.sleep(max(5.0, args.interval - elapsed))


if __name__ == "__main__":
    main()
