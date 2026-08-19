#!/usr/bin/env python3
"""Build #268's complete SQLite candidate and #236-compatible Parquet view."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from eu_odds_timeseries.materialize import materialize_proxy_view  # noqa: E402
from eu_proxy_backfill.sqlite_store import build_full_candidate_sqlite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--accepted-source", type=Path, required=True)
    parser.add_argument("--extension-source", type=Path, required=True)
    parser.add_argument("--recovery-source", type=Path, required=True)
    parser.add_argument("--candidate-sqlite", type=Path, required=True)
    parser.add_argument("--parquet-output", type=Path, required=True)
    parser.add_argument("--chunksize", type=int, default=100_000)
    args = parser.parse_args()
    summary = build_full_candidate_sqlite(
        inventory_path=args.inventory,
        accepted_source=args.accepted_source,
        extension_source=args.extension_source,
        recovery_source=args.recovery_source,
        target=args.candidate_sqlite,
    )
    parquet = materialize_proxy_view(
        args.candidate_sqlite,
        args.parquet_output,
        source_sha256=str(summary["sqlite_sha256"]),
        chunksize=args.chunksize,
    )
    print(json.dumps({"sqlite": summary, "parquet": parquet}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
