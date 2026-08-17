from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj159_gate_b_outcome_settlement_v2"
EXPECTED_MANIFEST = "ad724693f7fbee8a120030cb4ace852a4cf69011bf98b39b41ae427bcfbd0917"
FREEZE_MANIFEST = "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def gz_rows(path: Path):
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_manifest_and_provenance():
    assert sha256(PACKAGE / "SHA256SUMS.json") == EXPECTED_MANIFEST
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {p.name: sha256(p) for p in PACKAGE.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"}
    assert declared == actual
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["provenance"]["gate_a_manifest_sha256"] == FREEZE_MANIFEST
    assert card["provenance"]["canonical_outcome_manifest_sha256"] == OUTCOME_MANIFEST
    assert card["saturation_rule"].startswith("nominal_M is a reporting label")
    assert card["output"]["saturated_nominal_rows"] == 5301
    assert card["decision"]["promotion_authorized"] is False


def test_complete_surface_counts_and_actual_stake():
    identity = list(gz_rows(PACKAGE / "identity_settlement.csv.gz"))
    issue = list(gz_rows(PACKAGE / "issue_settlement.csv.gz"))
    assert len(identity) == 63180
    assert len(issue) == 348 * 9 * 9
    assert len({row["identity_id"] for row in identity}) == 7020
    assert Counter(row["saturation_status"] for row in identity) == Counter({"PARTIAL_WOR": 57879, "FULL_SPACE_SATURATED": 5301})
    assert all(int(row["planned_draw_count"]) == int(row["effective_M"]) for row in identity)
    assert all(int(row["executed_draw_count"]) in {0, int(row["effective_M"])} for row in identity)
    all_rows = [row for row in rows(PACKAGE / "surface_summary.csv") if row["scope"] == "ALL"]
    assert len(all_rows) == 81
    assert {(int(row["n"]), int(row["nominal_M"])) for row in all_rows} == {(n, m) for n in range(2, 11) for m in (32, 64, 128)}


def test_saturated_cells_share_allocation_and_tax_is_per_ticket():
    identity = list(gz_rows(PACKAGE / "identity_settlement.csv.gz"))
    grouped: dict[tuple[str, str], dict[int, dict[str, str]]] = defaultdict(dict)
    for row in identity:
        if row["seed"] == "137001" and (int(row["n"]), int(row["nominal_M"])) in {(2, 32), (2, 64), (2, 128), (3, 32), (3, 64), (3, 128), (4, 128)}:
            grouped[(row["identity_id"], row["seed"])][int(row["nominal_M"])] = row
    assert len(grouped) == 38 + 335 + 648
    assert all(len({row["allocation_fingerprint"] for row in values.values()}) == 1 for values in grouped.values())
    assert all(len({row["effective_M"] for row in values.values()}) == 1 for values in grouped.values())
    ledger = list(gz_rows(PACKAGE / "winning_ticket_tax_ledger.csv.gz"))
    assert all("no pooling" in row["tax_rule"] for row in ledger)


def test_settlement_and_surface_are_not_promotion_claims():
    identity = list(gz_rows(PACKAGE / "identity_settlement.csv.gz"))
    assert Counter(row["settlement_status"] for row in identity) == Counter({"SETTLED": 56988, "UNAVAILABLE_CANONICAL_OUTCOME": 6192})
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV"
    assert decision["promotion_authorized"] is False
    report = (PACKAGE / "report.md").read_text(encoding="utf-8")
    assert "Complete ALL N×M×seed surface" in report
    assert report.count("| 10 | 128 |") >= 3
