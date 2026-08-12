#!/usr/bin/env python3
"""Clean-run the bounded Issue #204 Gate-A notebook in place."""

from __future__ import annotations

import argparse
from pathlib import Path

try:  # Supports direct execution and import from the focused test module.
    from scripts.execute_bj203_notebook import execute_notebook
except ModuleNotFoundError:  # pragma: no cover - direct script invocation path.
    from execute_bj203_notebook import execute_notebook


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOTEBOOK = ROOT / "notebooks/research/issue-204/bj204_track_a_gate_a.ipynb"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=DEFAULT_NOTEBOOK)
    arguments = parser.parse_args()
    execute_notebook(arguments.notebook.resolve())
    print(f"EXECUTED {arguments.notebook.resolve()}")


if __name__ == "__main__":
    main()
