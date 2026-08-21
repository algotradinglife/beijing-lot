#!/usr/bin/env python3
"""Run Issue #296 from the repository root."""

from __future__ import annotations

import argparse
from pathlib import Path

from issue296.experiment import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("results/issue-296"))
    args = parser.parse_args()
    result = run_experiment(args.root, args.output)
    print(result["decision"])


if __name__ == "__main__":
    main()
