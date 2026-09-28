#!/usr/bin/env python3
"""Freeze the exact #493 probe revision submitted for review.

Writes an immutable record of the reviewed file hashes so a later change cannot
silently inherit the review's authority. The delivery QMD compares current files
against this record.

Usage:
  python scripts/freeze_n7_493_reviewed_revision.py --round 12
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REVIEWED_FILES = (
    "src/n7_493_probe.py",
    "src/n7_493_probe_analysis.py",
    "scripts/probe_n7_493_3in1_identity.py",
    "scripts/rebuild_n7_493_probe_ledger.py",
    "scripts/analyze_n7_493_3in1_probe.py",
    "tests/scripts/test_probe_n7_493_3in1_identity.py",
    "tests/scripts/test_n7_493_probe_analysis.py",
    "tests/scripts/test_n7_493_probe_entrypoints.py",
    "r/n7_493_probe_report.R",
    "tests/testthat/test-n7-493-probe-report.R",
    "quarto/493_n7_input_probe.qmd",
    # The Titan capability verification is new evidence this delivery rests on;
    # leaving it unfrozen would let the principal evidence change silently.
    "docs/research/n7_493_titan_source_verification.md",
    # The freeze script is itself part of the reviewed delivery, and the captured
    # artifact bytes are the evidence the delivery rests on: bind both.
    "scripts/freeze_n7_493_reviewed_revision.py",
    "results/data_collection/n7_493_3in1_probe_v1/SHA256SUMS",
    "results/data_collection/n7_493_3in1_probe_v1/manifest.json",
    "results/data_collection/n7_493_3in1_probe_v1/ledger_provenance.json",
    "results/data_collection/n7_493_3in1_probe_v1/diagnostics.csv",
    "results/data_collection/n7_493_3in1_probe_v1/requests.jsonl",
)

# Artifact bytes are validated against this bound manifest, not merely displayed.
ARTIFACT_MANIFEST = "results/data_collection/n7_493_3in1_probe_v1/SHA256SUMS"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "docs/reviews/issue-493-reviewed-revision.json")
    args = parser.parse_args(argv)

    files = {}
    for relative in REVIEWED_FILES:
        path = ROOT / relative
        if not path.exists():
            raise SystemExit(f"reviewed file missing: {relative}")
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()

    record = {
        "schema": "n7_493_reviewed_revision_v1",
        "issue": 493,
        "review_round": args.round,
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "review_command": ("codex exec -c sandbox_mode='\"danger-full-access\"' "
                           "--cd $PWD - < docs/reviews/issue-493-review-prompt-"
                           f"round{args.round}.txt"),
        "files": files,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
