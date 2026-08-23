#!/usr/bin/env python3
"""Run Issue #340 source-backed dynamic-R research."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    from src.qeu_dynamic_r_n7 import run_experiment

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "results/qeu_dynamic_r_n7"
    )
    args = parser.parse_args()
    decision = run_experiment(args.repo_root, args.output_dir)
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

