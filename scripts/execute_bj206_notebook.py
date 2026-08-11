#!/usr/bin/env python3
"""Clean-run and atomically persist the Issue #206 notebook."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

import nbformat
from nbclient import NotebookClient


def _atomic_write(document: nbformat.NotebookNode, notebook: Path) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".ipynb.tmp",
            prefix=f".{notebook.name}.",
            dir=notebook.parent,
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            nbformat.write(document, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, notebook)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def execute_notebook(notebook: Path, *, kernel_name: str = "python3") -> None:
    notebook = notebook.resolve()
    document = nbformat.read(notebook, as_version=4)
    document.metadata["kernelspec"] = {
        "display_name": "Python 3",
        "language": "python",
        "name": kernel_name,
    }
    client = NotebookClient(
        document,
        timeout=300,
        kernel_name=kernel_name,
        resources={"metadata": {"path": str(notebook.parent)}},
    )
    client.execute()
    code = [cell for cell in document.cells if cell.cell_type == "code"]
    if any(
        output.get("output_type") == "error"
        for cell in code
        for output in cell.get("outputs", [])
    ):
        raise RuntimeError("executed notebook contains an error output")
    _atomic_write(document, notebook)
    print(
        f"PASS cells={len(code)} executed={sum(cell.execution_count is not None for cell in code)} "
        f"kernel={kernel_name} path={notebook}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebook",
        type=Path,
        default=Path("notebooks/research/issue-206/bj206_fixed_n7_ticket_policy.ipynb"),
    )
    parser.add_argument("--kernel", default="python3")
    args = parser.parse_args()
    execute_notebook(args.notebook, kernel_name=args.kernel)


if __name__ == "__main__":
    main()
