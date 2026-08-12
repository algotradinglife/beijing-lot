#!/usr/bin/env python3
"""Clean-run and atomically persist the Issue #206 notebook."""

from __future__ import annotations

import argparse
from pathlib import Path

# Direct script execution places ``scripts/`` (not the repository root) on
# sys.path. Import the sibling runner accordingly so the documented
# ``python scripts/execute_bj206_notebook.py`` command works from a clean clone.
from execute_bj205_notebook import execute_notebook


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path(
            "notebooks/research/issue-206/bj206_fixed_n7_ticket_policy.ipynb"
        ),
    )
    parser.add_argument("--kernel", default="python3")
    args = parser.parse_args()
    execute_notebook(args.notebook, kernel_name=args.kernel)


if __name__ == "__main__":
    main()
