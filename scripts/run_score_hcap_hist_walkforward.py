#!/usr/bin/env python3
"""Run and freeze the sole formal B0/B1 score-history walk-forward."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.score_hcap_hist.runner import run_and_freeze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g0-freeze-dir", type=Path, required=True)
    parser.add_argument("--source-db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--freeze-dir", type=Path, required=True)
    parser.add_argument("--frozen-at-utc", required=True)
    parser.add_argument("--git-commit", required=True)
    args = parser.parse_args()
    result = run_and_freeze(
        g0_freeze_dir=args.g0_freeze_dir,
        source_db=args.source_db,
        output_dir=args.output_dir,
        freeze_dir=args.freeze_dir,
        frozen_at_utc=args.frozen_at_utc,
        git_commit=args.git_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
