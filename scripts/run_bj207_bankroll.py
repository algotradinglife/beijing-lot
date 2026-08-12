#!/usr/bin/env python3
"""Run or verify Issue #207 fixed-N7 bankroll evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bankroll_policy.fixed_n7 import Inputs, run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("run")
    execute.add_argument("--source", type=Path, default=Path("results/issue-206"))
    execute.add_argument("--output", type=Path, default=Path("results/issue-207"))
    check = sub.add_parser("verify")
    check.add_argument("--output", type=Path, default=Path("results/issue-207"))
    args = parser.parse_args()
    result = run(Inputs(args.source, args.output)) if args.command == "run" else verify(args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
