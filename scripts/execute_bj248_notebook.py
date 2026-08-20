#!/usr/bin/env python3
"""Execute the #248 operational notebook top-to-bottom and save outputs.

Run with an environment providing nbformat, nbclient and ipykernel, e.g.:
  uv run --with nbformat --with nbclient --with ipykernel \
    python scripts/execute_bj248_notebook.py
"""
from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "notebooks" / "research" / "issue-248" / "bj248_forward_snapshot.ipynb"


def main() -> int:
    notebook = nbformat.read(PATH, as_version=4)
    client = NotebookClient(notebook, timeout=120, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    # Kernel timestamps are volatile instrumentation, not notebook evidence.
    # Strip them so the committed operational notebook is replay-deterministic.
    for cell in notebook.cells:
        cell.metadata.pop("execution", None)
    nbformat.write(notebook, PATH)
    outputs = [output.get("text", "") for cell in notebook.cells if cell.cell_type == "code" for output in cell.get("outputs", [])]
    if not outputs or "issue_fixture_cell_coverage" not in "".join(outputs):
        raise RuntimeError("notebook did not produce the required operational report")
    print(f"EXECUTED: {PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
