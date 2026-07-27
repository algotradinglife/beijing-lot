"""Exact-HEAD verification for the active v3.3.3 promotion baseline."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "promotion"
PROJECTION = FIXTURE_DIR / "active_v333_26078_shadow_selection_projection.csv"
RECEIPT = FIXTURE_DIR / "active_v333_26078_shadow_selection_projection.receipt.json"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def test_active_v333_promotion_fixture_is_self_contained_and_reproducible() -> None:
    """Reconstruct all promotion digests without a runtime-only source path."""

    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    claimed_receipt_sha = receipt.pop("sha256")
    assert receipt["schema_version"] == "active_v333_shadow_selection_projection_receipt_v1"
    assert claimed_receipt_sha == _sha256(receipt)

    projection = receipt["projection"]
    assert projection["path"] == PROJECTION.relative_to(ROOT).as_posix()
    assert projection["file_sha256"] == hashlib.sha256(PROJECTION.read_bytes()).hexdigest()
    assert projection["column"] == "shadow_selection_codes"

    with PROJECTION.open(newline="", encoding="utf-8") as stream:
        rows = [
            {
                "match_idx": int(row["match_idx"]),
                "selection_codes": row["shadow_selection_codes"].split("+"),
            }
            for row in csv.DictReader(stream)
        ]
    assert [row["match_idx"] for row in rows] == list(range(1, 174))
    assert len(rows) == projection["row_count"] == 173
    assert _sha256(rows) == projection["canonical_map_sha256"]
    assert _sha256(
        {
            "schema_version": projection["semantic_ticket_input_schema_version"],
            "issue": receipt["issue"],
            "rows": rows,
        }
    ) == projection["semantic_ticket_input_sha256"]

    source = receipt["source"]
    assert source["receipt_schema_version"] == "structured_decision_input_receipt_v1"
    assert source["csv_sha256"] == "4adf064b950901e70906c0db000d41f28c7cfd6b183e8e7d334436ebc82d6a4f"
    assert source["receipt_file_sha256"] == "2bf4c49fc0410f03d2922142321f6c7b93e7ab2e6429edfe83fa573ab58c411c"
