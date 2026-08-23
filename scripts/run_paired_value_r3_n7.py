#!/usr/bin/env python3
"""Run Issue #345 paired-value selector × fixed-R3 experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.paired_value_r3_n7 import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir or args.repo_root / "results/paired_value_r3_n7"
    print(json.dumps(build_package(args.repo_root, output, args.data_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
