#!/usr/bin/env python3
"""Audit which page parsers have real page bytes behind their tests.

A parser proven only against inline HTML is proven against the author's idea of the page, and
this repository has already lost data to that gap: an Okooo parser read the site's GB2312 pages
as UTF-8 and quietly produced unreadable team names for as long as it existed, while its
synthetic fixtures stayed green. The question this answers is mechanical: for every module that
parses external markup, do its tests read bytes that came from the source?

The scan reads the tracked files of a revision, never the working tree: a report generated from
whatever happens to be on disk cannot be reproduced from a clean checkout, and it silently mixes
in other people's in-flight work.

Prints JSON so a delivery document can quote it and a check can diff it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_PARSER_MARKERS = re.compile(r"BeautifulSoup|def parse_(page|archive|issue_page|history_page|html)")
# A fixture reference in the tests that name a parser: a path under tests/fixtures together with
# a read. Matching only a literal "fixtures/x.html" missed tests that join the parts
# (Path(...) / "fixtures" / "page.gz" with gzip.open), which is how the Okooo lesson was applied.
_FIXTURE_REF = re.compile(r"""(?x)
    ["']fixtures["']\s*/     # Path(...) / "fixtures" / ...
  | fixtures/                 # a literal relative path
  | tests/fixtures
""")
_READS_BYTES = re.compile(r"""read_bytes\(\)|read_text\(|gzip\.open\(|\bopen\([^)]*["']r""")

# An inline sample, whatever it is named or whatever codec it is encoded with.
_INLINE = re.compile(r"(?m)^\s*[A-Za-z_]*(HTML|PAGE|BODY|MARKUP|PAGES?|SAMPLES?)\s*=")


def revision_files(root: Path, revision: str) -> dict[str, str]:
    """Return {path: text} for every tracked Python file at the revision.

    Uses one `git cat-file --batch` so a full scan costs two processes rather than one per file.
    """
    # ls-tree lists the revision's tree; ls-files would list the index, which includes files
    # another agent has staged but not committed.
    listed = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "-z", "--name-only", revision,
                             "--", "src", "scripts", "tests"],
                            check=True, capture_output=True).stdout.decode("utf-8")
    names = [name for name in listed.split("\0") if name.endswith(".py")]
    if not names:
        raise SystemExit(f"no tracked Python files at {root}")
    query = "\n".join(f"{revision}:{name}" for name in names).encode("utf-8") + b"\n"
    out = subprocess.run(["git", "-C", str(root), "cat-file", "--batch"],
                         input=query, check=True, capture_output=True).stdout
    files, cursor = {}, 0
    for name in names:
        header_end = out.index(b"\n", cursor)
        header = out[cursor:header_end].split()  # "<sha> blob <size>"
        if len(header) != 3 or header[1] != b"blob":
            raise SystemExit(f"{name} is not a blob at {revision}: {header!r}")
        size = int(header[2])
        start = header_end + 1
        files[name] = out[start:start + size].decode("utf-8", errors="replace")
        cursor = start + size + 1
    return files


def parser_modules(root: Path, files: dict[str, str]) -> list[str]:
    """Return every tracked module under src/ and scripts/ that parses external markup."""
    found = []
    for name, text in files.items():
        if not name.startswith(("src/", "scripts/")):
            continue
        if Path(name).name.startswith("__") or Path(name).name == Path(__file__).name:
            continue  # this auditor mentions BeautifulSoup in its own marker pattern
        if _PARSER_MARKERS.search(text):
            found.append(name)
    return sorted(found)


def related_tests(parser: str, tests: dict[str, str]) -> list[str]:
    """Return the tests that import or name this parser, matched through their imports."""
    path = Path(parser)
    stem = path.stem
    module = ".".join(path.with_suffix("").parts)
    matched = [
        name for name, text in tests.items()
        if name.startswith("tests/")
        and (module in text or re.search(rf"\b{re.escape(stem)}\b", text))
    ]
    return sorted(matched)


def evidence_nature(blobs: str) -> str:
    """Report the static signal in the tests that name a parser, and nothing more.

    This deliberately stops short of a verdict. Tests are not reliably associated with a parser
    by filename or import -- tests/test_nowscore_settlement.py states it uses no 500 fixtures
    while other tests consume them -- so "no reference found" is a prompt to look, not proof
    that no page bytes are read. The delivery document carries the hand-checked list.
    """
    referenced = bool(_FIXTURE_REF.search(blobs)) and bool(_READS_BYTES.search(blobs))
    inline = bool(_INLINE.search(blobs))
    if referenced and inline:
        return "reads fixtures and defines inline samples"
    if referenced:
        return "reads fixtures"
    if inline:
        return "inline samples only"
    return "no fixture reference in the tests that name it"



# Curated disposition of the parsers that lack preserved page bytes. It lives here rather than only
# in prose so that an entry naming a file the repository does not track fails a test, instead of
# sitting in a gap list that nobody can act on -- which is exactly what happened to a script that
# existed only on one machine's disk.
GAP_REGISTER = {
    "src/nowscore_bjdc_sp_history.py": {
        "status": "resolved",
        "why": ("three pages fetched from the source's history endpoint; the parser agrees with "
                "them (234 vectors on a live issue's page) and refuses the two whose history the "
                "source purged"),
        "evidence": "tests/fixtures/nowscore_sp_history/, tests/scripts/test_nowscore_bjdc_sp_history_real_pages.py",
    },
    "src/correct_score_price_history.py": {
        "status": "blocked",
        "why": ("one input of two is missing, and the other source's collector cannot run on this "
                "host. Context input: already preserved (tests/fixtures/fundamentals_census/"
                "nowscore-*.gz are https://live.nowscore.com/analysis/{id}cn.html pages carrying the "
                "最后更新 marker the normalisation reads). Crown correct-score panel: absent -- "
                "feeding the preserved analysisJs data{id}.js in its place raises 'Crown "
                "correct-score table missing'. The Okooo history path "
                "(/soccer/match/{id}/{market}/change/{provider}/) needs an authenticated browser "
                "session: manage_correct_score_price_history.py drives Windows Chrome against the "
                "logged-in profile /mnt/c/Users/hhusl/AppData/Local/OkoooCollectorProfile, and this "
                "host is native Linux with no /mnt/c, no session and an overseas egress. Measured: "
                "curl_cffi's four browser fingerprints 0/5, headless Chrome and a Playwright browser "
                "both get the WAF page, and the human opening the URL from China lands on a login "
                "page -- while / and /livecenter/danchang/ return 200. No client change substitutes "
                "for the missing session."),
        "next": ("obtain the Crown correct-score panel (run the live refresh loop once and keep its "
                 "captures), and reach the Okooo history path from a China-side egress"),
        "reusable_inputs": ["tests/fixtures/fundamentals_census/nowscore-2910880.gz",
                            "tests/fixtures/fundamentals_census/nowscore-2910880.provenance.json"],
    },
    "scripts/replay_settlement_quarantine.py": {
        "status": "owned-elsewhere",
        "issue": 480,
        "why": "produced by #480's delivery, and within that issue's remaining scope",
    },
    "scripts/update_beidan_nowscore_sqlite.py": {
        "status": "deprecated-line",
        "why": ("the beidan_xlsm line is being retired; the script is still referenced by "
                "backfill_beidan_nowscore_lines.py and eu_proxy_backfill, so testing it is not "
                "obviously worth the work"),
    },
}


def audit(root: Path, revision: str = "HEAD") -> dict:
    """Return one row per parser: its tests, and the static fixture signal in them.

    Everything comes from the revision, so the report can be regenerated from a clean checkout
    and binds the identity of what it read.
    """
    files = revision_files(root, revision)
    tests = {name: text for name, text in files.items() if Path(name).name.startswith("test_")}
    rows = []
    for parser in parser_modules(root, files):
        related = related_tests(parser, tests)
        blobs = "".join(tests[name] for name in related)
        rows.append({"parser": parser, "tests": related,
                     "page_bytes": evidence_nature(blobs) if related else "untested"})
    report = {
        "schema": "source_parser_audit_v3",
        "revision": subprocess.run(["git", "-C", str(root), "rev-parse", revision],
                                   check=True, capture_output=True).stdout.decode().strip(),
        "scanned_files": len(files),
        "scanned_sha256": hashlib.sha256(
            "".join(f"{name}\0{files[name]}\0" for name in sorted(files)).encode("utf-8")).hexdigest(),
        "parsers": rows,
        "real_page_fixtures": fixture_inventory(root, revision),
        "gap_register": GAP_REGISTER,
        # No static fixture reference: a prompt to look, not a verdict (see evidence_nature).
        "without_fixture_reference": [row["parser"] for row in rows
                                      if row["page_bytes"].startswith("no fixture reference")
                                      or row["page_bytes"] == "untested"],
    }
    return report


def fixture_inventory(root: Path, revision: str) -> list[str]:
    """Tracked page samples under tests/fixtures: the bytes a parser can be proven against."""
    listed = subprocess.run(["git", "-C", str(root), "ls-tree", "-r", "--name-only", revision,
                             "--", "tests/fixtures"],
                            check=True, capture_output=True).stdout.decode("utf-8")
    # the revision listing is authoritative: asking the working tree here would both miss files
    # deleted since the revision and pick up files that do not exist in it
    return sorted(name for name in listed.splitlines()
                  if Path(name).suffix in {".gz", ".html", ".htm"})


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
