#!/usr/bin/env python3
"""Execute the issue-234 notebook and durably persist the executed file.

The notebook's package build is already an atomic whole-directory publication.
This executor therefore performs only one additional write: the executed
notebook itself, through the shared fail-closed file writer.  It never mutates
a live package manifest after publication.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema import publication  # noqa: E402

NOTEBOOK = ROOT / "notebooks" / "research" / "issue-234" / "bj234_source_schema.ipynb"


def run(nb_path: Path = NOTEBOOK, timeout: int = 1800) -> Path:
    """Execute all notebook cells with nbclient and atomically persist it."""
    import nbclient
    import nbformat

    notebook = nbformat.read(nb_path, as_version=4)
    client = nbclient.NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    # No wall-clock metadata: source-cell semantic hash remains stable while
    # retained outputs prove that every cell actually executed.
    publication.atomic_write_text(nb_path, nbformat.writes(notebook))
    print(f"EXECUTED {nb_path}")
    return nb_path


if __name__ == "__main__":
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--notebook", type=Path, default=NOTEBOOK)
    value.add_argument("--timeout", type=int, default=1800)
    arguments = value.parse_args()
    run(arguments.notebook, timeout=arguments.timeout)
