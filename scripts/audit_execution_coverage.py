#!/usr/bin/env python3
"""Audit which runtime functions are never executed by the test suite.

Naming a function in a test proves nothing: the text ``main`` appears in almost
every test file, so a name search certifies coverage it does not have.  This
tool measures *execution* instead.  For every function in the audited set it
injects an unconditional ``raise AssertionError`` as the first statement and
re-runs the acceptance command; if the suite still passes, no test ever reached
that function.

Probe failures are only accepted as evidence when they are attributable to the
probe.  An unrelated flaky test can fail a run for reasons that have nothing to
do with the injected exception, so a single failure is not proof of execution.
Every function is therefore probed twice:

* pass, pass -> the function is never executed (a gap);
* pass, fail -> inconclusive; reported as unstable and the audit fails;
* fail, pass -> inconclusive; reported as unstable and the audit fails;
* fail, fail -> the injected exception was reached; the function is covered.

Any inconclusive or unusable result makes the audit fail.  Coverage is only
ever concluded from a doubled, consistent observation.

The audited set is deliberately closed: ``src/titan_clean/`` plus the five
collection entry scripts.  This auditor is not part of its own set.

Probes run strictly one at a time.  Parallel probes would mutate the same file
concurrently, letting one worker read another's injected source as its
"original" and write it back over the real file, which corrupts the checkout and
invalidates the result.

Usage::

    python scripts/audit_execution_coverage.py --python .venv/bin/python \\
        --root .

Exit code 0 means the audited set has no execution-coverage gap and no
inconclusive probe; 1 means gaps, inconclusive probes, or unusable probes were
found.  The last stdout line is a machine-readable tab-separated summary::

    total <TAB> injection_errors <TAB> unstable <TAB> gaps <TAB> labels
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import subprocess
import sys
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
PROBE_MARKER = "__execution_coverage_probe__"

PASSED, FAILED, UNUSABLE = "passed", "failed", "unusable"


@dataclass(frozen=True)
class FunctionSite:
    """Where one function starts, and where its first statement starts."""

    name: str
    lineno: int
    body_lineno: int
    body_col: int


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


def run_scope(python: str, root: pathlib.Path) -> tuple[str, str]:
    """Run the acceptance command; return its outcome and the output tail."""
    completed = subprocess.run(
        [python, "-m", "pytest", *AUDIT_SCOPE, "-q", "-p", "no:cacheprovider"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    combined = completed.stdout + completed.stderr
    if "SyntaxError" in combined or "errors during collection" in combined:
        return UNUSABLE, combined
    return (PASSED if completed.returncode == 0 else FAILED), combined


def probe(python: str, root: pathlib.Path, path: pathlib.Path, site: FunctionSite) -> tuple[str, str]:
    """Run the acceptance command once with ``site`` disabled.

    The original bytes are always restored, including on failure.
    """
    original = path.read_text(encoding="utf-8")
    try:
        path.write_text(mutated_source(original, site), encoding="utf-8")
        return run_scope(python, root)
    finally:
        path.write_text(original, encoding="utf-8")


def classify(python: str, root: pathlib.Path, path: pathlib.Path, site: FunctionSite) -> tuple[str, str]:
    """Decide one function's verdict from two consistent probe observations.

    Returns ``(verdict, detail)`` where verdict is ``"gap"``, ``"covered"``,
    ``"unstable"`` or ``"unusable"``.  Only ``fail, fail`` counts as evidence
    that the injected exception was reached; every other combination is either
    a gap (two clean passes) or an inconclusive result that fails the audit.
    """
    first, first_output = probe(python, root, path, site)
    second, second_output = probe(python, root, path, site)

    if UNUSABLE in (first, second):
        return "unusable", _tail(first_output if first == UNUSABLE else second_output)
    if first == PASSED and second == PASSED:
        return "gap", ""
    if first == FAILED and second == FAILED:
        # The probe's own exception must appear, otherwise the two failures are
        # some unrelated flakiness rather than evidence of execution.
        if PROBE_MARKER in first_output and PROBE_MARKER in second_output:
            return "covered", ""
        return "unstable", _tail(first_output + second_output)
    return "unstable", _tail(first_output + second_output)


def _tail(text: str, limit: int = 400) -> str:
    stripped = [line for line in text.strip().split("\n") if line.strip()]
    return " / ".join(stripped[-3:])[:limit]


def audit(python: str, root: pathlib.Path) -> dict[str, object]:
    """Probe every audited function and report the ones tests never execute."""
    gaps: list[str] = []
    unstable: dict[str, str] = {}
    injection_errors: dict[str, str] = {}
    total = 0

    for path in audited_files(root):
        source = path.read_text(encoding="utf-8")
        sites = function_sites(source)
        total += len(sites)

        for site in sites:
            label = f"{path.name}::{site.name}"
            verdict, detail = classify(python, root, path, site)
            if verdict == "gap":
                gaps.append(label)
            elif verdict == "unstable":
                unstable[label] = detail
            elif verdict == "unusable":
                injection_errors[label] = detail
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
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    report = audit(args.python, root)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    gaps = report["gaps"]
    assert isinstance(gaps, list)
    print(
        "\t".join(
            [
                str(report["total"]),
                str(len(report["injection_errors"])),  # type: ignore[arg-type]
                str(len(report["unstable"])),  # type: ignore[arg-type]
                str(len(gaps)),
                "|".join(gaps),
            ]
        )
    )
    clean = not gaps and not report["injection_errors"] and not report["unstable"]
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
