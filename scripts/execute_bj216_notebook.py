#!/usr/bin/env python3
"""Clean and execute the bounded Issue #216 evidence notebook in place."""

from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOTEBOOK = (
    ROOT
    / "notebooks/research/issue-216/bj216_causal_p34_model_support.ipynb"
)


def execute_notebook(path: Path) -> None:
    notebook = nbformat.read(path, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
            cell.metadata.pop("execution", None)
    client = NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
        record_timing=False,
        allow_errors=False,
    )
    client.execute()
    nbformat.validate(notebook)
    nbformat.write(notebook, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=DEFAULT_NOTEBOOK)
    arguments = parser.parse_args()
    execute_notebook(arguments.notebook.resolve())
    print(f"EXECUTED {arguments.notebook.resolve()}")


if __name__ == "__main__":
    main()
