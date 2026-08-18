#!/usr/bin/env python3
"""Clean-execute the committed Issue #253 notebook in place."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "research" / "issue-253" / "bj253_physical_schema.ipynb"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    if args.data_root is not None:
        os.environ["BEIJING_LOT_DATA_ROOT"] = str(args.data_root.resolve())
    if not os.environ.get("BEIJING_LOT_DATA_ROOT"):
        raise SystemExit("BEIJING_LOT_DATA_ROOT or --data-root is required")
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=300,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    nbformat.write(notebook, NOTEBOOK)
    print(f"executed {NOTEBOOK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
