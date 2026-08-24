#!/usr/bin/env python3
"""Regenerate Issue #359's executed notebook, figures, report and manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.low_n_eu_value_selector.pipeline import finalize_manifest, write_analysis


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / "results/low_n_eu_value_selector").resolve()
    delivery = write_analysis(repo, output)
    finalize_manifest(repo, output, delivery)
    for path in delivery:
        print(path)


if __name__ == "__main__":
    main()
