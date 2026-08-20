#!/usr/bin/env python3
"""Execute the #249 portability notebook and retain deterministic outputs."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks/research/issue-249/bj249_data_portability.ipynb"


def main() -> int:
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    for cell in notebook.cells:
        cell.metadata.pop("execution", None)
    nbformat.write(notebook, NOTEBOOK)
    text = "".join(
        str(output.get("text", ""))
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.get("outputs", [])
    )
    if "RESTORE_MATCH: PASS" not in text:
        raise RuntimeError("notebook did not reproduce the accepted restore receipt")
    print(f"EXECUTED: {NOTEBOOK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
