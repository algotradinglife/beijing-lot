#!/usr/bin/env python3
"""Run the file-driven automated research freeze scheduler."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research_freeze_automation import run_due_jobs  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="scheduler JSON config")
    parser.add_argument("--now-utc", help="explicit scheduler clock for reproducible smoke tests")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loop", action="store_true", help="continue polling instead of running due jobs once")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_due_jobs(
        args.config,
        now_utc=args.now_utc,
        once=not args.loop,
        poll_seconds=args.poll_seconds,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
