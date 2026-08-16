#!/usr/bin/env python3
"""Execute the #232 support-waterfall notebook deterministically (R2)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import nbformat  # noqa: E402
from nbclient import NotebookClient  # noqa: E402


def main() -> None:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--root", type=Path, default=ROOT)
    value.add_argument("--timeout", type=int, default=3600)
    arguments = value.parse_args()

    notebook_path = (
        arguments.root
        / "notebooks/research/issue-232/bj232_support_waterfall.ipynb"
    )
    notebook = nbformat.read(notebook_path, as_version=4)
    client = NotebookClient(
        notebook,
        timeout=arguments.timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(arguments.root)}},
    )
    client.execute()
    nbformat.write(notebook, notebook_path)
    print(f"EXECUTED {notebook_path}")


if __name__ == "__main__":
    main()
