#!/usr/bin/env python3
"""Execute the Issue #234 census notebook cleanly (nbclient, no kernel prompt).

Usage:
    python scripts/execute_bj234_notebook.py [--timeout 3600]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "research" / "issue-234" / "bj234_source_schema.ipynb"


def main() -> int:
    import nbclient
    import nbformat

    timeout = 3600
    if "--timeout" in sys.argv:
        timeout = int(sys.argv[sys.argv.index("--timeout") + 1])

    notebook = nbformat.read(NB, as_version=4)
    client = nbclient.NotebookClient(
        notebook,
        timeout=timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(NB.parent)}},
    )
    client.execute()
    nbformat.write(notebook, NB)
    errors = [
        cell for cell in notebook.cells
        if cell.cell_type == "code" and cell.get("outputs")
        and any(o.get("output_type") == "error" for o in cell["outputs"])
    ]
    if errors:
        print(f"NOTEBOOK ERRORS in {len(errors)} cells", file=sys.stderr)
        return 1
    executed = sum(
        1 for c in notebook.cells
        if c.cell_type == "code" and c.get("execution_count")
    )
    print(f"NOTEBOOK OK: {executed} code cells executed, 0 errors")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
