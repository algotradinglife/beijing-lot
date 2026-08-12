#!/usr/bin/env python3
"""Clean-run and atomically persist the Issue #207 notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

from execute_bj205_notebook import execute_notebook


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path("notebooks/research/issue-207/bj207_fixed_n7_bankroll.ipynb"),
    )
    parser.add_argument("--kernel", default="python3")
    args = parser.parse_args()
    execute_notebook(args.notebook, kernel_name=args.kernel)


if __name__ == "__main__":
    main()
