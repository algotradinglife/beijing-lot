#!/usr/bin/env python3
"""Regenerate the Issue #356 notebook, figures and report from its package."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_third_outcome_protection.pipeline import write_analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / "results/low_n_third_outcome_protection").resolve()
    for path in write_analysis(repo, output):
        print(path)


if __name__ == "__main__":
    main()
