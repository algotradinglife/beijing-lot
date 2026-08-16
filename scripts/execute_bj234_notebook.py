#!/usr/bin/env python3
"""Execute the issue-234 source-schema notebook and persist the executed file.

Follows the issue-229 executor pattern: nbclient run, then atomic persist of
the executed notebook only (the package itself is published atomically by the
build CLI and is never re-mutated here).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "research" / "issue-234" / "bj234_source_schema.ipynb"


def atomic_write_text(path: Path, content: str) -> None:
    import os
    import tempfile

    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkstemp(prefix=f".{path.name}.", dir=str(parent))[1])
    try:
        tmp.write_text(content, encoding="utf-8")
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        tmp.rename(path)
        pfd = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(pfd)
        finally:
            os.close(pfd)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def run(nb_path: Path = NOTEBOOK, timeout: int = 1800) -> Path:
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
    atomic_write_text(nb_path, nbformat.writes(notebook))
    print(f"EXECUTED {nb_path}")
    return nb_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--notebook", type=Path, default=NOTEBOOK)
    ap.add_argument("--timeout", type=int, default=1800)
    args = ap.parse_args()
    run(args.notebook, timeout=args.timeout)
