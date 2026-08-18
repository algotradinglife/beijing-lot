#!/usr/bin/env python3
"""Execute and atomically persist the Issue #251 evidence notebook."""

from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema import publication  # noqa: E402

NOTEBOOK = ROOT / "notebooks" / "research" / "issue-251" / "bj251_canonical_identity.ipynb"


def _execute_stdlib(notebook_path: Path) -> str:
    """Execute this plain-Python v4 notebook without unavailable Jupyter deps.

    This deliberately supports only code/markdown cells and text outputs—the
    exact surface used by the committed evidence notebook.  It keeps a clean
    checkout reproducible when nbclient is not installed, while failing closed
    on a code-cell exception rather than writing a partial notebook.
    """
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": "__main__"}
    count = 0
    for cell in notebook["cells"]:
        if cell.get("cell_type") != "code":
            continue
        count += 1
        source = "".join(cell.get("source", []))
        parsed = ast.parse(source, filename=str(notebook_path), mode="exec")
        final_expression = parsed.body.pop() if parsed.body and isinstance(parsed.body[-1], ast.Expr) else None
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(compile(parsed, str(notebook_path), "exec"), namespace)
            value = eval(compile(ast.Expression(final_expression.value), str(notebook_path), "eval"), namespace) if final_expression else None
        outputs: list[dict[str, object]] = []
        text = stream.getvalue()
        if text:
            outputs.append({"output_type": "stream", "name": "stdout", "text": text})
        if final_expression is not None:
            outputs.append(
                {
                    "output_type": "execute_result",
                    "execution_count": count,
                    "data": {"text/plain": repr(value)},
                    "metadata": {},
                }
            )
        cell["execution_count"] = count
        cell["outputs"] = outputs
    publication.atomic_write_text(notebook_path, json.dumps(notebook, ensure_ascii=False, indent=1) + "\n")
    return "stdlib-fallback"


def run(notebook_path: Path = NOTEBOOK, timeout: int = 1800) -> Path:
    try:
        import nbclient
        import nbformat
    except ModuleNotFoundError:
        mode = _execute_stdlib(notebook_path)
    else:
        notebook = nbformat.read(notebook_path, as_version=4)
        client = nbclient.NotebookClient(
            notebook,
            timeout=timeout,
            kernel_name="python3",
            resources={"metadata": {"path": str(ROOT)}},
        )
        client.execute()
        publication.atomic_write_text(notebook_path, nbformat.writes(notebook))
        mode = "nbclient"
    print(f"EXECUTED {notebook_path} mode={mode}")
    return notebook_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=NOTEBOOK)
    parser.add_argument("--timeout", type=int, default=1800)
    arguments = parser.parse_args()
    run(arguments.notebook, arguments.timeout)
