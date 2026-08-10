#!/usr/bin/env python3
"""Run or verify Issue #205 joint-N7 evidence."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from unified_value.joint_n7 import Inputs, run, verify


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    execute = sub.add_parser("run")
    execute.add_argument(
        "--ledger",
        type=Path,
        default=Path(
            "results/bj204_gate_b_retrospective_method_correction_v1/per_match_predictions.parquet"
        ),
    )
    execute.add_argument(
        "--gate-a-cells",
        type=Path,
        default=Path("results/bj204_gate_a_preoutcome_v5/common_cell_features.parquet"),
    )
    execute.add_argument("--output", type=Path, default=Path("results/issue-205"))
    check = sub.add_parser("verify")
    check.add_argument("--output", type=Path, default=Path("results/issue-205"))
    args = parser.parse_args()
    result = (
        run(Inputs(args.ledger, args.gate_a_cells, args.output))
        if args.command == "run"
        else verify(args.output)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
