#!/usr/bin/env python3
"""Build Issue #358's European-average-odds value proxy package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.low_n_eu_value import build_package


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--selector-features", type=Path, default=Path(__file__).resolve().parents[1] / "results/low_n_selector_data/features/selector_features.parquet")
    parser.add_argument("--source-sqlite", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    output = args.output or args.repo_root / "results/low_n_eu_value_proxy"
    print(json.dumps(build_package(args.repo_root, output, args.selector_features, args.source_sqlite, force=args.force), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
