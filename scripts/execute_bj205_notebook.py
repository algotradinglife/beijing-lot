#!/usr/bin/env python3
"""Clean-run and persist the Issue #205 notebook."""
from __future__ import annotations

import argparse
from pathlib import Path

import nbformat
from nbclient import NotebookClient


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=Path("notebooks/research/issue-205/bj205_joint_n7_value_matrix.ipynb"))
    args = parser.parse_args()
    notebook = args.notebook.resolve()
    document = nbformat.read(notebook, as_version=4)
    client = NotebookClient(document, timeout=180, kernel_name="bj205", resources={"metadata": {"path": str(notebook.parent)}})
    client.execute()
    nbformat.write(document, notebook)
    code = [cell for cell in document.cells if cell.cell_type == "code"]
    if any(output.get("output_type") == "error" for cell in code for output in cell.get("outputs", [])):
        raise RuntimeError("executed notebook contains an error output")
    print(f"PASS cells={len(code)} executed={sum(cell.execution_count is not None for cell in code)} path={notebook}")


if __name__ == "__main__":
    main()
