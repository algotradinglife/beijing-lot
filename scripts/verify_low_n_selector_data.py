#!/usr/bin/env python3
"""Source-bound semantic verifier for Issue #354."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_selector_data import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.repo_root / "results/low_n_selector_data"
    checks = verify_package(args.repo_root, output, args.data_root)
    print(json.dumps({"status": "PASS", "checks": checks}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
