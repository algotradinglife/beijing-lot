#!/usr/bin/env python3
"""Verify Issue #345 package and exact matched design."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.paired_value_r3_n7 import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output = args.output_dir or args.repo_root / "results/paired_value_r3_n7"
    print(json.dumps(verify_package(args.repo_root, output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
