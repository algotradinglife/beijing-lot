#!/usr/bin/env python3
"""Compare static HTML against post-JavaScript rendered DOM for settlement quarantine.

Issue #480 deliverable helper. For every quarantined Nowscore page, decide whether the
slot the parser reported missing is absent from the *rendered* page (source-side
omission) or merely absent from the static markup (which would make it a parser defect).

Read-only: reads a staged-page manifest and previously dumped DOMs, writes one JSON
report. No network access and no store writes.

Inputs are explicit; no path is derived from the current working directory:

  --manifest  JSON list of staged pages, each carrying `file` (the staged page path,
              resolved here by basename against --pages), `issue`, `typeid`, `sha256`
              and the receipt's `embedded_only` / `visible_only` slot lists
  --pages     directory holding the staged static pages referenced by the manifest
  --rendered  directory holding `<page stem>.dom.html` post-JavaScript DOM dumps
  --output    JSON report path

Classification per page:
  source_omission  the slot is missing from static *and* rendered markup
  parser_defect    the slot is missing from static markup but present once rendered
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROW_ID_RE = re.compile(r'id="row_([0-9]+)"')
EMBEDDED_RE = re.compile(r"M\[(\d+)\]\[0\]\s*=\s*['\"]?(\d+)['\"]?\s*;")


def slots(text: str) -> set[int]:
    """Slots of fixture rows present in the given markup."""
    return {int(n) for n in ROW_ID_RE.findall(text)}


def embedded(text: str) -> dict[int, int]:
    """Slot -> provider id pairs declared by the page's embedded roster script."""
    return {int(i): int(v) for i, v in EMBEDDED_RE.findall(text)}


def analyse_page(entry: dict, pages: Path, rendered: Path) -> dict:
    """Classify one staged page against its rendered DOM dump."""
    stem = Path(entry["file"]).stem
    dom_path = rendered / f"{stem}.dom.html"
    static_path = pages / Path(entry["file"]).name
    if not static_path.exists():
        raise SystemExit(f"staged page missing for issue {entry['issue']}: {static_path}")
    static = static_path.read_text(errors="replace")
    if not dom_path.exists():
        return {**entry, "status": "dom_missing"}
    dom = dom_path.read_text(errors="replace")

    static_slots, dom_slots = slots(static), slots(dom)
    roster = embedded(dom) or embedded(static)

    missing_rendered = sorted(set(roster) - dom_slots)
    missing_static = sorted(set(roster) - static_slots)

    return {
        "issue": entry["issue"],
        "typeid": entry["typeid"],
        "sha256": entry["sha256"],
        "status": "ok",
        "static_rows": len(static_slots),
        "rendered_rows": len(dom_slots),
        "static_equals_rendered": static_slots == dom_slots,
        "embedded_roster": len(roster),
        "missing_in_static": missing_static,
        "missing_in_rendered": missing_rendered,
        "source_omission": missing_rendered == missing_static and len(missing_rendered) > 0,
        "parser_defect": len(missing_rendered) < len(missing_static),
        "receipt_embedded_only": [x[0] for x in entry["embedded_only"]],
        "receipt_visible_only": [x[0] for x in entry["visible_only"]],
    }


def summarise(pages: list[dict]) -> dict:
    """Aggregate per-page classifications into the report summary."""
    ok = [r for r in pages if r["status"] == "ok"]
    per_issue: dict[str, set[int]] = {}
    for row in ok:
        per_issue.setdefault(row["issue"], set()).update(row["missing_in_rendered"])
    return {
        "schema": "bj480_rendered_dom_check_v1",
        "pages": len(pages),
        "pages_ok": len(ok),
        "pages_dom_missing": len(pages) - len(ok),
        "static_equals_rendered_all": all(r["static_equals_rendered"] for r in ok),
        "parser_defect_any": any(r["parser_defect"] for r in ok),
        "source_omission_all": all(r["source_omission"] for r in ok),
        "receipt_matches_rendered": all(
            sorted(r["missing_in_rendered"]) == sorted(r["receipt_embedded_only"]) for r in ok
        ),
        "issues": sorted({r["issue"] for r in ok}),
        "per_issue_missing": {k: sorted(v) for k, v in sorted(per_issue.items())},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="staged-page manifest JSON")
    parser.add_argument("--pages", type=Path, required=True,
                        help="directory of staged static pages")
    parser.add_argument("--rendered", type=Path, required=True,
                        help="directory of post-JavaScript DOM dumps")
    parser.add_argument("--output", type=Path, required=True, help="JSON report path")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    pages = [analyse_page(entry, args.pages, args.rendered) for entry in manifest]
    report = {"summary": summarise(pages), "pages": pages}
    args.output.write_text(json.dumps(report, indent=1), encoding="utf-8")

    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
