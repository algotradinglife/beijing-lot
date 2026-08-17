#!/usr/bin/env python3
"""Run or verify Issue #206 fixed-N7 ticket-policy evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ticket_policy.fixed_n7 import Inputs, run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("run")
    execute.add_argument(
        "--value-matrix",
        type=Path,
        default=Path("results/issue-205/value_matrix.parquet"),
    )
    execute.add_argument(
        "--value-schema",
        type=Path,
        default=Path("results/issue-205/value_matrix_schema.json"),
    )
    execute.add_argument("--output", type=Path, default=Path("results/issue-206"))
    check = sub.add_parser("verify")
    check.add_argument("--output", type=Path, default=Path("results/issue-206"))
    args = parser.parse_args()
    result = (
        run(Inputs(args.value_matrix, args.value_schema, args.output))
        if args.command == "run"
        else verify(args.output)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
