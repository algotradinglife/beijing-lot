#!/usr/bin/env python3
"""Independently replay and verify the Issue #355 package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_match_selector import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output = (args.output_dir or repo_root / "results/low_n_match_selector").resolve()
    print(json.dumps(verify_package(repo_root, output, args.data_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
