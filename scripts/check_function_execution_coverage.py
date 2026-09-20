"""Report audited project functions that no test executes.

Measurement is delegated to ``coverage.py``, the maintained library for Python
execution coverage.  The only capability implemented here is the one coverage
does not provide: mapping executed line numbers back to the function each line
belongs to, so the gate can assert "every function has a test that runs it"
instead of a raw line percentage.

Exit status is part of the contract: 0 means the audited test scope passed and
every audited function body executed at least once.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys
import tempfile

AUDIT_SCOPE = (
    "tests/titan_clean",
    "tests/backfill",
    "tests/scripts/test_collection_runtime_entry_points.py",
)
ENTRY_SCRIPTS = (
    "collect_500_historical_plays.py",
    "collect_500_historical_settlement.py",
    "collect_titan_historical_fixtures.py",
    "run_next_historical_id_mapping.py",
    "collect_titan_clean_roster.py",
)
# Directories handed to coverage.py; audited_files() narrows the report.
COVERAGE_SOURCES = ("src/titan_clean", "scripts")


def audited_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Return the closed audited set: titan_clean modules plus entry scripts."""
    modules = sorted((root / "src" / "titan_clean").glob("*.py"))
    return modules + [root / "scripts" / name for name in ENTRY_SCRIPTS]


def function_body_lines(source: str) -> list[tuple[str, int, tuple[int, ...]]]:
    """Return ``(name, def_lineno, body_statement_lines)`` for every function.

    The ``def`` line itself, decorators and docstrings are excluded: coverage
    marks the ``def`` line as executed at import time, so counting it would make
    every function look covered.  A nested function's body is excluded from its
    parent, because it is reported as its own site.
    """
    tree = ast.parse(source)
    sites: list[tuple[str, int, tuple[int, ...]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nested: set[int] = set()
        for inner in ast.walk(node):
            if inner is not node and isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nested.update(range(inner.lineno, (inner.end_lineno or inner.lineno) + 1))
        lines = []
        for stmt in ast.walk(node):
            if stmt is node or not isinstance(stmt, ast.stmt):
                continue
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # A nested `def` is a statement the parent body executes, so it
                # counts for the parent; only the nested body belongs to the
                # child site. Without this a function whose body is a single
                # nested definition could never be reported as covered.
                lines.append(stmt.lineno)
                continue
            if stmt.lineno in nested:
                continue
            if (
                isinstance(stmt, ast.Expr)
                and isinstance(stmt.value, ast.Constant)
                and isinstance(stmt.value.value, str)
            ):
                continue
            lines.append(stmt.lineno)
        sites.append((node.name, node.lineno, tuple(sorted(set(lines)))))
    return sites


def uncovered_functions(source: str, executed: set[int]) -> list[str]:
    """Names of functions with no executed statement in their own body."""
    return [
        name
        for name, _def_lineno, lines in function_body_lines(source)
        if not (set(lines) & executed)
    ]


def measure(python: str, root: pathlib.Path, data_file: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Run the audited test scope under coverage.py."""
    return subprocess.run(
        [
            python, "-m", "coverage", "run",
            "--data-file", str(data_file),
            f"--source={','.join(COVERAGE_SOURCES)}",
            "-m", "pytest", *AUDIT_SCOPE, "-q", "-p", "no:cacheprovider",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def audit(python: str, root: pathlib.Path) -> dict[str, object]:
    """Return ``{total, uncovered, suite_passed, output}`` for the audited set."""
    with tempfile.TemporaryDirectory() as tmp:
        data_file = pathlib.Path(tmp) / ".coverage"
        run = measure(python, root, data_file)
        if run.returncode != 0:
            return {
                "total": 0,
                "uncovered": {},
                "suite_passed": False,
                "output": (run.stdout + run.stderr).strip(),
            }
        import coverage

        data = coverage.CoverageData(basename=str(data_file))
        data.read()
        measured = {pathlib.Path(name).resolve(): lines for name, lines in
                    ((name, data.lines(name)) for name in data.measured_files())}

    uncovered: dict[str, int] = {}
    total = 0
    for path in audited_files(root):
        executed = set(measured.get(path.resolve()) or [])
        source = path.read_text(encoding="utf-8")
        for name in uncovered_functions(source, executed):
            uncovered[f"{path.relative_to(root)}::{name}"] = 1
        total += len(function_body_lines(source))
    return {"total": total, "uncovered": uncovered, "suite_passed": True, "output": ""}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="project interpreter running pytest")
    parser.add_argument("--root", required=True, help="repository root")
    args = parser.parse_args(argv)

    try:
        import coverage  # noqa: F401
    except ImportError:
        print("coverage.py is not installed in the selected interpreter", file=sys.stderr)
        return 2

    report = audit(args.python, pathlib.Path(args.root).resolve())
    if not report["suite_passed"]:
        print(report["output"], file=sys.stderr)
        print("audited test scope did not pass; coverage is unusable", file=sys.stderr)
        return 1

    uncovered = report["uncovered"]
    names = ",".join(sorted(uncovered))
    print(f"{report['total']}\t{len(uncovered)}\t{names}")
    return 0 if not uncovered else 1


if __name__ == "__main__":
    raise SystemExit(main())
