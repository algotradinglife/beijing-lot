#!/usr/bin/env python3
"""Losslessly package #137 Gate-B v2 after correcting its decision predicate.

The v1 numeric ledger was atomically produced before the decision predicate was
found to be too weak (it reacted to any ALL-scope positive row).  This runner
does not recalculate or alter any outcome number: it verifies v1 exactly,
repackages every large CSV as deterministic gzip, and applies the frozen
all-seed plus YEAR/FOLD/LOYO persistence predicate in a new immutable package.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
from pathlib import Path

from settle_bj137_sampling_gate_b import (
    CALIBRATION_FIELDS,
    CONTRACT,
    FREEZE_MANIFEST,
    LIFT_FIELDS,
    OUTCOME_MANIFEST,
    OUTCOME_PAYLOAD,
    ROOT,
    SOURCE_FIELDS,
    SUMMARY_FIELDS,
    decision_from_lifts,
    exact_bundle,
    sha,
    uncompressed,
)


INPUT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v1"
OUTPUT = ROOT / "results" / "bj137_gate_b_outcome_settlement_v2"
INPUT_MANIFEST = "be74e5162207f621f212a981f6732da6aeaf8ebc595e76cdfd1e72a8e9537cd8"
NUMERIC_FILES = (
    "issue_policy_settlement.csv.gz",
    "surface_summary.csv",
    "selector_lift.csv",
    "sampler_lift.csv",
    "interaction_surface.csv",
    "calibration_diagnostics.csv",
    "source_census.csv",
)


def deterministic_gzip_copy(source: Path, target: Path) -> None:
    with source.open("rb") as raw, target.open("wb") as destination:
        with gzip.GzipFile(filename="", mode="wb", fileobj=destination, mtime=0) as zipped:
            shutil.copyfileobj(raw, zipped, length=1 << 20)


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"v1 schema drift: {path.name}")
        return list(reader)


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    exact_bundle(INPUT, INPUT_MANIFEST)
    for name in NUMERIC_FILES:
        if not (INPUT / name).is_file():
            raise RuntimeError(f"v1 numeric payload missing: {name}")
    summaries = read_csv(INPUT / "surface_summary.csv", SUMMARY_FIELDS)
    selector = read_csv(INPUT / "selector_lift.csv", LIFT_FIELDS)
    sampler = read_csv(INPUT / "sampler_lift.csv", LIFT_FIELDS)
    interaction = read_csv(INPUT / "interaction_surface.csv", LIFT_FIELDS)
    decision = decision_from_lifts(selector, sampler)
    if decision["decision"] != "NO_PROMOTION" or decision["all_seed_and_chronological_positive_sampler_candidates"] != 0:
        raise RuntimeError("v2 decision correction requires no promotable candidate")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj137_gateb_v2_", dir=output.parent))
    try:
        shutil.copy2(INPUT / "issue_policy_settlement.csv.gz", stage / "issue_policy_settlement.csv.gz")
        for name in ("surface_summary", "selector_lift", "sampler_lift", "interaction_surface"):
            deterministic_gzip_copy(INPUT / f"{name}.csv", stage / f"{name}.csv.gz")
        for name in ("calibration_diagnostics.csv", "source_census.csv"):
            shutil.copy2(INPUT / name, stage / name)
        lineage = {
            "source_numeric_bundle": str(INPUT.relative_to(ROOT)),
            "source_manifest_sha256": INPUT_MANIFEST,
            "source_content_identity_sha256": sha(INPUT / "CONTENT_IDENTITY.json"),
            "numeric_payloads": {name: sha(INPUT / name) for name in NUMERIC_FILES},
            "correction": "v1’s all-positive-row decision predicate was superseded. v2 changes no numeric ledger value; it uses deterministic gzip for large CSVs and the frozen all-seed plus YEAR/FOLD/LOYO persistence rule.",
        }
        (stage / "NUMERIC_LINEAGE.json").write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        card = {
            "issue": 137,
            "contract": CONTRACT,
            "runner_version": "bj137-gate-b-v2-decision-correction",
            "stage": "GATE_B_COMPLETE_ISSUE_OUTCOME_SETTLEMENT",
            "provenance": {
                "gate_a_manifest_sha256": FREEZE_MANIFEST,
                "outcome_manifest_sha256": OUTCOME_MANIFEST,
                "outcome_payload_sha256": OUTCOME_PAYLOAD,
                "v1_numeric_manifest_sha256": INPUT_MANIFEST,
            },
            "input_boundary": "Only accepted Gate-A v2 and canonical final-SP settlement truth generated the numeric v1 ledger. This v2 package losslessly repacks that ledger and corrects only the terminal-decision predicate; Gate-A v3/post-acceptance material is not read.",
            "settlement": "Each selected ticket pays ¥2×0.65×product(canonical final winning SP) per hit. Tax is assessed per realised winning ticket: 20% only where that individual ticket gross is at least ¥10,000. Tickets, identities and issue-policy arms are never aggregated merely to cross the tax threshold; duplicated WR hits are separately assessed tickets.",
            "promotion_rule": decision["rule"],
            "decision": decision,
            "scope": "historical paper research only; no purchase, production, or promotion authority.",
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(ROOT / "scripts" / "settle_bj137_sampling_gate_b.py", stage / "settlement_runner.py")
        shutil.copy2(Path(__file__), stage / "decision_correction_runner.py")
        (stage / "README.md").write_text("# #137 Gate B v2 — probability-weighted N7 sampling\n\nLossless repack of the canonical v1 numeric ledger with a corrected all-seed and chronological persistence decision predicate. Historical paper research only.\n", encoding="utf-8")
        gzip_payloads = ("issue_policy_settlement.csv.gz", "surface_summary.csv.gz", "selector_lift.csv.gz", "sampler_lift.csv.gz", "interaction_surface.csv.gz")
        content = {
            "contract_version": "bj137-gate-b-portable-content-v2",
            "gzip_payloads": {name: {"canonical_decompressed_sha256": uncompressed(stage / name)[0], "canonical_decompressed_bytes": uncompressed(stage / name)[1]} for name in gzip_payloads},
            "non_compressed_controls": {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_payloads},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha(output / "SHA256SUMS.json"), "content_identity_sha256": sha(output / "CONTENT_IDENTITY.json"), "summary_rows": len(summaries), "decision": decision}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
