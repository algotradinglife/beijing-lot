#!/usr/bin/env python3
"""Build Issue #358's causal 10h European-average-odds value inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_eu_value_data.pipeline import build_package, write_report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output = args.output or repo_root / "results/low_n_eu_value_data"
    receipt = build_package(repo_root, output, args.data_root, force=args.force)
    report = write_report(repo_root, output)
    print(json.dumps({"freeze_receipt": receipt, "report": str(report)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
