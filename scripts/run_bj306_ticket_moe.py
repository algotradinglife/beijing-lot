#!/usr/bin/env python3
"""Run Issue #306 after the physical surface is materialized."""

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue306.experiment import run_experiment  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reuse-fit-cache",
        action="store_true",
        help="reuse already-materialized fit outputs and rerun only policy evaluation",
    )
    args = parser.parse_args()
    print(
        run_experiment(
            ROOT,
            ROOT / "results/issue-306",
            reuse_fit_cache=args.reuse_fit_cache,
        )
    )
