#!/usr/bin/env python3
"""Build the complete Issue #356 package and analysis delivery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_third_outcome_protection.pipeline import (
    build_package,
    finalize_manifest,
    write_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / "results/low_n_third_outcome_protection").resolve()
    decision = build_package(repo, output, args.data_root, force=args.force)
    delivery = write_analysis(repo, output)
    finalize_manifest(repo, output, delivery)
    print(
        json.dumps(
            {"decision": decision, "delivery": [str(path) for path in delivery]},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
