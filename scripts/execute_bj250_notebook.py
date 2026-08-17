#!/usr/bin/env python3
"""Execute the Issue #250 notebook with the portable external data-root contract."""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema.publication import atomic_write_text  # noqa: E402

NOTEBOOK = ROOT / "notebooks" / "research" / "issue-250" / "bj250_source_census.ipynb"


def main() -> int:
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": "__main__"}
    count = 0
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        count += 1
        stream = io.StringIO()
        try:
            with contextlib.redirect_stdout(stream):
                exec("".join(cell["source"]), namespace)
        except Exception as error:
            cell["execution_count"] = count
            cell["outputs"] = [{"output_type": "error", "ename": type(error).__name__, "evalue": str(error), "traceback": []}]
            atomic_write_text(NOTEBOOK, json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")
            raise
        cell["execution_count"] = count
        cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": stream.getvalue()}]
    atomic_write_text(NOTEBOOK, json.dumps(notebook, indent=1, ensure_ascii=False) + "\n")
    print(f"EXECUTED {NOTEBOOK.relative_to(ROOT)} ({count} code cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
