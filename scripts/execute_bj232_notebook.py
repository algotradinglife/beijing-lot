#!/usr/bin/env python3
"""Execute the Issue #232 support-waterfall notebook and persist outputs."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import nbformat  # noqa: E402
from nbclient import NotebookClient  # noqa: E402

NOTEBOOK = ROOT / "notebooks" / "research" / "issue-232" / "bj232_support_waterfall.ipynb"


def main() -> None:
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=1800,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    nbformat.write(notebook, NOTEBOOK)
    print(f"EXECUTED {NOTEBOOK}")


if __name__ == "__main__":
    main()
