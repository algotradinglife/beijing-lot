#!/usr/bin/env python3
"""Verify the clean-checkout Segment 1 incident bundle and missed conclusion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / "segment_1_source_bundle"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


entries = {}
for line in (BUNDLE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    digest, name = line.split("  ", 1)
    entries[name] = digest
    if file_hash(BUNDLE / name) != digest:
        raise SystemExit(f"FAIL: source byte mismatch: {name}")

manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
if manifest.get("schema_version") != "exact_n_segment_freeze_v1":
    raise SystemExit("FAIL: unexpected historical schema")
if {int(item["requested_n"]) for item in manifest["artifacts"] if "requested_n" in item} != {3, 4, 5, 6, 7}:
    raise SystemExit("FAIL: historical five-candidate inventory mismatch")
if any("requested_budget_yuan" in item for item in manifest["artifacts"]):
    raise SystemExit("FAIL: historical bundle unexpectedly claims an N×budget matrix")
if manifest.get("sha256") != "fc07fba06a0315abbd21339db17affb37042185d9c5eb38cefd59d2bb6a41974":
    raise SystemExit("FAIL: historical manifest payload identity mismatch")

receipt = {
    "status": "PASS",
    "conclusion": "MISSED_FREEZE_PRE_FREEZE_OUT_OF_CONTRACT",
    "source_files_verified": len(entries),
    "source_sha256s_sha256": file_hash(BUNDLE / "SHA256SUMS"),
    "manifest_file_sha256": file_hash(BUNDLE / "manifest.json"),
    "manifest_payload_sha256": manifest["sha256"],
    "decision_input_sha256": manifest["decision_input_sha256"],
    "reasons": [
        "historical_schema_v1_not_exact_n_budget_matrix_v2",
        "no_5x3_budget_grid",
        "no_effective_decision_binding",
        "no_append_only_segment_ledger",
        "correct_score_record_is_incident_evidence_not_a_contract_freeze",
    ],
}
print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
