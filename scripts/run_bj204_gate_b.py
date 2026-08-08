#!/usr/bin/env python3
"""Run or verify the bounded Issue #204 Gate-B model settlement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from unified_model.gate_b import GateBInputs, run_gate_b, verify_package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    run = command.add_parser("run")
    run.add_argument("--package", type=Path, required=True)
    run.add_argument("--full-3sp-source", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    verify = command.add_parser("verify")
    verify.add_argument("--package", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "run":
        result = run_gate_b(GateBInputs(args.package, args.full_3sp_source, args.output))
    else:
        result = verify_package(args.package)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
