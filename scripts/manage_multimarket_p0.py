#!/usr/bin/env python3
"""Manage P0 multimarket schema, 10h research freezes, and settlement truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.multimarket_p0 import (  # noqa: E402
    DEFAULT_FREEZE_ROOT,
    build_settlement_truth,
    ensure_schema,
    freeze_10h,
    verify_freeze,
)
from src.sqlite_runtime import connect_sqlite  # noqa: E402


DEFAULT_DB = ROOT / "data/derived/500_bjdc/500_bjdc.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    migrate = subparsers.add_parser("migrate")
    migrate.add_argument("--db", type=Path, default=DEFAULT_DB)
    freeze = subparsers.add_parser("freeze-10h")
    freeze.add_argument("--db", type=Path, default=DEFAULT_DB)
    freeze.add_argument("--issue", required=True)
    freeze.add_argument("--output-dir", type=Path)
    settle = subparsers.add_parser("settle")
    settle.add_argument("--db", type=Path, default=DEFAULT_DB)
    settle.add_argument("--issue", required=True)
    verify = subparsers.add_parser("verify-freeze")
    verify.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    if arguments.command == "verify-freeze":
        print(json.dumps(verify_freeze(arguments.output_dir), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    with connect_sqlite(arguments.db, row_factory=True) as conn:
        ensure_schema(conn)
        conn.commit()
        if arguments.command == "migrate":
            result = {"status": "schema_ready", "database": str(arguments.db.resolve())}
        elif arguments.command == "freeze-10h":
            output = arguments.output_dir or DEFAULT_FREEZE_ROOT / arguments.issue
            result = freeze_10h(conn, arguments.issue, output)
        else:
            result = build_settlement_truth(conn, arguments.issue)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
