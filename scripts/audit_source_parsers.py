#!/usr/bin/env python3
"""Audit which page parsers have real page bytes behind their tests.

A parser proven only against inline HTML is proven against the author's idea of the page, and
this repository has already lost data to that gap: an Okooo parser read the site's GB2312 pages
as UTF-8 and quietly produced unreadable team names for as long as it existed, while its
synthetic fixtures stayed green. The question this answers is mechanical: for every module that
parses external markup, do its tests read bytes that came from the source?

Prints JSON so a delivery document can quote it and a check can diff it.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_PARSER_MARKERS = re.compile(r"BeautifulSoup|def parse_(page|archive|issue_page|history_page|html)")
# Strong evidence of committed source bytes: reading a file under tests/fixtures, or a
# compressed sample. Mentioning ".html" in a string is not evidence and used to pass here.
_SOURCE_BYTES = re.compile(r"fixtures?/[\w./-]+|read_bytes\(\)|\.gz['\"]")
# An inline sample, whatever it is named or whatever codec it is encoded with.
_INLINE = re.compile(r"(?m)^\s*[A-Za-z_]*(HTML|PAGE|BODY|MARKUP|PAGES?|SAMPLES?)\s*=")


def parser_modules(root: Path) -> list[Path]:
    """Return every module under src/ and scripts/ that parses external markup."""
    found = []
    for area in ("src", "scripts"):
        for path in (root / area).rglob("*.py"):
            if path.name.startswith("__") or path.name == Path(__file__).name:
                continue  # this auditor mentions BeautifulSoup in its own marker pattern
            if _PARSER_MARKERS.search(path.read_text(encoding="utf-8", errors="replace")):
                found.append(path)
    return sorted(found)


def related_tests(parser: Path, tests: dict[Path, str]) -> list[Path]:
    """Return the tests that import or name this parser, matched through their imports."""
    stem = parser.stem
    module = ".".join(parser.with_suffix("").parts)
    matched = []
    for path, text in tests.items():
        if module in text or re.search(rf"\b{re.escape(stem)}\b", text):
            matched.append(path)
    return sorted(matched)


def evidence_nature(blobs: str) -> str:
    """Classify the page bytes a set of tests relies on.

    The only claim this makes is whether committed bytes that came from the source are read.
    Inline samples are reported when a test defines one by assignment; a module that builds
    markup inline without naming it is reported as having no committed source bytes rather than
    guessed at, and the delivery document says which rows were confirmed by hand.
    """
    committed = bool(_SOURCE_BYTES.search(blobs))
    inline = bool(_INLINE.search(blobs))
    if committed and inline:
        return "committed bytes and inline samples"
    if committed:
        return "committed source bytes"
    if inline:
        return "no committed bytes; inline samples only"
    return "no committed bytes, no named sample"


def audit(root: Path) -> dict:
    """Return one row per parser: its tests, and the nature of their page bytes."""
    tests = {path: path.read_text(encoding="utf-8", errors="replace")
             for path in sorted((root / "tests").rglob("test_*.py"))}
    rows = []
    for parser in parser_modules(root):
        related = related_tests(parser, tests)
        blobs = "".join(tests[path] for path in related)
        rows.append({"parser": str(parser.relative_to(root)),
                     "tests": [str(path.relative_to(root)) for path in related],
                     "page_bytes": evidence_nature(blobs) if related else "untested"})
    return {
        "schema": "source_parser_audit_v1",
        "root": str(root),
        "parsers": rows,
        "real_page_fixtures": sorted(
            str(path.relative_to(root))
            for path in (root / "tests" / "fixtures").rglob("*")
            if path.is_file() and path.suffix in {".gz", ".html", ".htm"}),
        # A parser with no committed source bytes: the class of gap that hid the Okooo bug.
        "without_source_bytes": [row["parser"] for row in rows
                                 if row["page_bytes"].startswith("no committed")
                                 or row["page_bytes"] == "untested"],
    }


def main(argv=None):
    """Print the audit as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    report = audit(args.root)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
