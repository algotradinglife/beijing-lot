#!/usr/bin/env python3
"""Source-bound semantic verifier for Issue #358."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.low_n_eu_value import verify_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--selector-features", type=Path, default=Path(__file__).resolve().parents[1] / "results/low_n_selector_data/features/selector_features.parquet")
    parser.add_argument("--source-sqlite", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.repo_root / "results/low_n_eu_value_proxy"
    print(json.dumps({"status": "PASS", "checks": verify_package(args.repo_root, output, args.selector_features, args.source_sqlite)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
