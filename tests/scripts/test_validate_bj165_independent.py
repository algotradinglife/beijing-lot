"""Durability and contract checks for the #165 independent package."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results/bj165_independent_validation_v1"
MANIFEST = "bf8a90f0ab55e5366093295a396388ea24569a22da147e47e6812a522750eebc"
CONTENT = "d190596a96750a59a98a33f5bf0d990ceebb14d2ce4fc21ca489522136ec5a00"


def test_package_manifest_and_content_identity() -> None:
    manifest_path = PACKAGE / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {name: hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() for name in manifest}
    assert manifest == actual
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == MANIFEST
    assert hashlib.sha256((PACKAGE / "CONTENT_IDENTITY.json").read_bytes()).hexdigest() == CONTENT


def test_zero_discrepancy_and_forward_wait_boundary() -> None:
    card = json.loads((PACKAGE / "validation_card.json").read_text(encoding="utf-8"))
    assert card["stage1_decision"] == "PASS_ZERO_MATERIAL_DISCREPANCIES"
    assert card["stage2_decision"] == "WAITING_FOR_FORWARD_DATA"
    assert card["material_discrepancies"] == 0
    assert card["allocation_checks"] == {"failures": 0, "rows": 63180}
    assert card["surface_rows_checked"] == 1782
    assert card["identity_discrepancies"] == 0
    assert card["matched_n7_discrepancies"] == 0
    assert card["overlap_discrepancies"] == 0
    assert card["bootstrap_discrepancies"] == 0
    availability = json.loads((PACKAGE / "forward_availability.json").read_text(encoding="utf-8"))
    assert availability["status"] == "WAITING_FOR_FORWARD_DATA"
    assert availability["new_issue_count"] == 0
    assert availability["same_window_reuse"] is False


def test_full_surface_and_focus_rows() -> None:
    with (PACKAGE / "recomputed_surface_summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1782
    all_rows = [row for row in rows if row["scope"] == "ALL"]
    assert len(all_rows) == 81
    focus = [row for row in all_rows if row["M"] == "64" and row["n"] in {"7", "8", "9", "10"}]
    assert len(focus) == 12
    n9 = [row for row in focus if row["n"] == "9"]
    assert {row["seed"] for row in n9} == {"137001", "137002", "137003"}


def test_stage2_protocol_is_unchanged_primary_and_controls() -> None:
    protocol = json.loads((PACKAGE / "stage2_protocol.json").read_text(encoding="utf-8"))
    assert protocol["primary"] == {"M": 64, "allocator": "Q_INFORMED_WOR", "n": 9, "seeds": ["137001", "137002", "137003"]}
    assert [control["n"] for control in protocol["controls"]] == [7, 8, 10]
    assert all(control["M"] == 64 and control["allocator"] == "Q_INFORMED_WOR" for control in protocol["controls"])
