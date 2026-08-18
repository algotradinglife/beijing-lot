#!/usr/bin/env python3
"""Execute the small committed #235 notebook without an external Jupyter runtime.

The runner supports ordinary Python code cells only. It records actual stdout or
last-expression representations in nbformat-compatible output objects and exits
nonzero on the first cell error. This fallback exists because the execution host
lacks nbformat/nbclient and package installation is network-blocked.
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import io
import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _execute_cell(source: str, namespace: dict[str, object]) -> tuple[list[dict[str, object]], object | None]:
    tree = ast.parse(source, mode="exec")
    final_expression = tree.body.pop() if tree.body and isinstance(tree.body[-1], ast.Expr) else None
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        if tree.body:
            exec(compile(tree, "<notebook-cell>", "exec"), namespace)
        value = eval(compile(ast.Expression(final_expression.value), "<notebook-cell>", "eval"), namespace) if final_expression else None
    records: list[dict[str, object]] = []
    if output.getvalue():
        records.append({"output_type": "stream", "name": "stdout", "text": output.getvalue()})
    if final_expression is not None:
        records.append({"output_type": "execute_result", "execution_count": None, "metadata": {}, "data": {"text/plain": repr(value)}})
    return records, value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("notebook", type=Path)
    args = parser.parse_args()
    path = args.notebook.resolve()
    document = json.loads(path.read_text(encoding="utf-8"))
    namespace: dict[str, object] = {"__name__": "__main__"}
    previous = Path.cwd()
    try:
        import os
        os.chdir(ROOT)
        for count, cell in enumerate(document.get("cells", []), start=1):
            if cell.get("cell_type") != "code":
                continue
            source = "".join(cell.get("source", []))
            try:
                outputs, _ = _execute_cell(source, namespace)
            except Exception:
                cell["execution_count"] = count
                cell["outputs"] = [{"output_type": "error", "ename": type(sys.exc_info()[1]).__name__, "evalue": str(sys.exc_info()[1]), "traceback": traceback.format_exc().splitlines()}]
                path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                raise
            cell["execution_count"] = count
            for record in outputs:
                if record["output_type"] == "execute_result":
                    record["execution_count"] = count
            cell["outputs"] = outputs
    finally:
        import os
        os.chdir(previous)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"executed {sum(cell.get('cell_type') == 'code' for cell in document.get('cells', []))} code cells: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
