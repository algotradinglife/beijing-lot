#!/usr/bin/env python3
"""Execute the BJ-235 notebook and atomically persist its outputs."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "research" / "issue-235" / "bj235_bj_sp_timeseries.ipynb"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    import nbclient
    import nbformat

    notebook = nbformat.read(NOTEBOOK, as_version=4)
    client = nbclient.NotebookClient(
        notebook,
        timeout=args.timeout,
        kernel_name="python3",
        resources={"metadata": {"path": str(ROOT)}},
    )
    client.execute()
    temp = NOTEBOOK.with_suffix(".ipynb.tmp")
    temp.write_text(nbformat.writes(notebook), encoding="utf-8")
    temp.replace(NOTEBOOK)
    print(f"EXECUTED {NOTEBOOK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
