#!/usr/bin/env python3
"""Audit which runtime functions are never executed by the test suite.

Naming a function in a test proves nothing: the text ``main`` appears in almost
every test file, so a name search certifies coverage it does not have.  This
tool measures *execution* instead.  For every function in the audited set it
injects an unconditional ``raise AssertionError`` as the first statement and
re-runs the acceptance command; if the suite still passes, no test ever reached
that function.

An "uncovered" verdict is recomputed once and reported only when both runs
agree, because a single run can be perturbed by an unrelated flaky result.

The audited set is deliberately closed: ``src/titan_clean/`` plus the five
collection entry scripts.  This auditor is not part of its own set.

Usage::

    python scripts/audit_execution_coverage.py --python .venv/bin/python \\
        --root . [--jobs 1]

Exit code 0 means the audited set has no execution-coverage gap; 1 means gaps
were found or the audit itself could not run cleanly.  The last stdout line is
a machine-readable tab-separated summary::

    total <TAB> injection_errors <TAB> gaps <TAB> file::function|...
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

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
MUTATION = "raise AssertionError('__execution_coverage_probe__')"


@dataclass(frozen=True)
class FunctionSite:
    """Where one function starts, and where its first statement starts."""

    name: str
    lineno: int
    body_lineno: int
    body_col: int

    @property
    def label(self) -> str:
        return self.name


def audited_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Return the closed audited set: titan_clean modules plus entry scripts."""
    modules = sorted((root / "src" / "titan_clean").glob("*.py"))
    return modules + [root / "scripts" / name for name in ENTRY_SCRIPTS]


def function_sites(source: str) -> list[FunctionSite]:
    """Locate every function in ``source``, including nested closures.

    The first statement's position is recorded rather than the ``def`` line so
    the probe can be inserted *before* the body without deleting anything.  A
    replacement that overwrites a multi-line statement's opening line produces
    a syntax error, which would be misread as "the tests caught it".
    """
    tree = ast.parse(source)
    sites: list[FunctionSite] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0]
            sites.append(
                FunctionSite(
                    name=node.name,
                    lineno=node.lineno,
                    body_lineno=first.lineno,
                    body_col=first.col_offset,
                )
            )
    return sites


def mutated_source(source: str, site: FunctionSite) -> str:
    """Insert the probe as the function's first statement, deleting nothing."""
    lines = source.split("\n")
    probe = " " * site.body_col + MUTATION
    return "\n".join(lines[: site.body_lineno - 1] + [probe] + lines[site.body_lineno - 1 :])


def run_scope(python: str, root: pathlib.Path) -> int:
    """Run the acceptance command; -1 marks an unusable (syntax-error) probe."""
    completed = subprocess.run(
        [python, "-m", "pytest", *AUDIT_SCOPE, "-x", "-q", "-p", "no:cacheprovider"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    combined = completed.stdout + completed.stderr
    if "SyntaxError" in combined or "errors during collection" in combined:
        return -1
    return completed.returncode


def probe(python: str, root: pathlib.Path, path: pathlib.Path, site: FunctionSite) -> int:
    """Run the acceptance command once with ``site`` disabled."""
    original = path.read_text(encoding="utf-8")
    path.write_text(mutated_source(original, site), encoding="utf-8")
    try:
        return run_scope(python, root)
    finally:
        path.write_text(original, encoding="utf-8")


def audit(python: str, root: pathlib.Path, jobs: int = 1) -> dict[str, object]:
    """Probe every audited function and report the ones tests never execute."""
    gaps: list[str] = []
    injection_errors: list[str] = []
    unstable: list[str] = []
    total = 0

    for path in audited_files(root):
        source = path.read_text(encoding="utf-8")
        sites = function_sites(source)
        total += len(sites)

        def classify(site: FunctionSite) -> tuple[FunctionSite, int, int]:
            first = probe(python, root, path, site)
            if first == -1:
                return site, first, first
            if first != 0:
                return site, first, first
            return site, first, probe(python, root, path, site)

        if jobs > 1:
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                verdicts = list(pool.map(classify, sites))
        else:
            verdicts = [classify(site) for site in sites]

        for site, first, second in verdicts:
            label = f"{path.name}::{site.name}"
            if first == -1:
                injection_errors.append(label)
            elif first == 0 and second != 0:
                unstable.append(label)
            elif first == 0 and second == 0:
                gaps.append(label)
        print(f"audited {path.name}", file=sys.stderr, flush=True)

    return {
        "total": total,
        "injection_errors": injection_errors,
        "unstable": unstable,
        "gaps": gaps,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="project interpreter running pytest")
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)

    if args.jobs < 1:
        parser.error("--jobs must be at least 1")
    root = args.root.resolve()
    report = audit(args.python, root, jobs=args.jobs)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    gaps = report["gaps"]
    assert isinstance(gaps, list)
    print(
        "\t".join(
            [
                str(report["total"]),
                str(len(report["injection_errors"])),  # type: ignore[arg-type]
                str(len(gaps)),
                "|".join(gaps),
            ]
        )
    )
    clean = not gaps and not report["injection_errors"] and not report["unstable"]
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
