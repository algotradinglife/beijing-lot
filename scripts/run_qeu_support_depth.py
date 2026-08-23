#!/usr/bin/env python3
"""Run Issue #336 QEU support-depth attribution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.qeu_support_depth import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--cell-cache", type=Path)
    args = parser.parse_args()
    output = args.output_dir or args.repo_root / "results/qeu_support_depth"
    decision = run_experiment(args.repo_root, output, cell_cache=args.cell_cache)
    print(json.dumps(decision, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
