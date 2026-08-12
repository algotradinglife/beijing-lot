from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj159_gate_a_preoutcome_v2r1"
EXPECTED_MANIFEST = "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325"
EXPECTED_IDS = {2: 38, 3: 335, 4: 648, 5: 844, 6: 937, 7: 1005, 8: 1042, 9: 1077, 10: 1094}


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


def test_manifest_and_gate_a_boundary():
    assert sha256(PACKAGE / "SHA256SUMS.json") == EXPECTED_MANIFEST
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {p.name: sha256(p) for p in PACKAGE.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"}
    assert declared == actual
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_SELECTED_BASELINE_CROSS_N_FREEZE"
    assert card["selection"]["analysis_unit"].startswith("complete lottery issue_instance")
    assert card["selection"]["n7_bridge_audit"]["bridge_status"] == "LEGACY_SEGMENT_BASELINE_NOT_EQUAL_COMPLETE_ISSUE_SELECTION"
    assert card["sampling"]["allocator"] == "Q_INFORMED_WOR_DISTINCT"
    assert "No result" in card["outcome_boundary"]


def test_complete_issue_identity_counts_and_provenance():
    identities = list(gz_rows(PACKAGE / "identity_catalog.csv.gz"))
    assert len(identities) == sum(EXPECTED_IDS.values())
    assert Counter(int(row["n"]) for row in identities) == Counter(EXPECTED_IDS)
    assert len({row["identity_id"] for row in identities}) == len(identities)
    assert all(row["selection_scope"] == "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOLS_PROVENANCE_ONLY" for row in identities)
    assert all(row["candidate_count_in_issue"] for row in identities)
    assert any("|" in row["source_pool_ids"] for row in identities if int(row["n"]) == 7)
    pools = list(rows(PACKAGE / "pool_census.csv"))
    assert len(pools) == 2659
    assert len({row["issue"] for row in pools}) == 344
    participation = list(rows(PACKAGE / "issue_participation.csv"))
    assert len(participation) == 348 * 9
    assert {int(row["n"]) for row in participation} == set(range(2, 11))
    assert all(row["complete_issue_unit"] == "TRUE" for row in participation)


def test_role_cardinality_q_mass_and_bridge():
    identities = list(gz_rows(PACKAGE / "identity_catalog.csv.gz"))
    roles = list(gz_rows(PACKAGE / "role_vectors.csv.gz"))
    by_id = Counter(row["identity_id"] for row in roles)
    assert set(by_id.values()) == set(range(2, 11))
    assert set(by_id) == {row["identity_id"] for row in identities}
    for row in roles:
        q = [float(row[f"q_weight{code}"]) for code in ("3", "1", "0")]
        assert all(0 < value < 1 for value in q)
        assert abs(sum(q) - 1.0) < 2e-12
        assert row["selection_scope"] == "COMPLETE_ISSUE_ANALYSIS_UNIT_NATIVE_POOLS_PROVENANCE_ONLY"
    audit = json.loads((PACKAGE / "n7_reference_audit.json").read_text(encoding="utf-8"))
    assert audit["legacy_segment_baseline_identity_count"] == 371
    assert audit["corrected_complete_issue_identity_count"] == 1005
    assert audit["exact_intersection_count"] == 6
    assert audit["legacy_only_count"] == 365
    assert audit["corrected_only_count"] == 999


def test_sampling_grid_saturation_and_no_settlement_fields():
    plans = list(rows(PACKAGE / "sampling_plan.csv"))
    assert len(plans) == 9 * 3 * 3
    assert {int(row["n"]) for row in plans} == set(range(2, 11))
    assert {int(row["nominal_M"]) for row in plans} == {32, 64, 128}
    assert {row["seed"] for row in plans} == {"137001", "137002", "137003"}
    assert {row["allocator"] for row in plans} == {"Q_INFORMED_WOR_DISTINCT"}
    saturated = {(int(row["n"]), int(row["nominal_M"])) for row in plans if row["saturation_status"] == "FULL_SPACE_SATURATED"}
    assert saturated == {(2, 32), (2, 64), (2, 128), (3, 32), (3, 64), (3, 128), (4, 128)}
    for row in plans:
        n, nominal = int(row["n"]), int(row["nominal_M"])
        assert int(row["ticket_space_k"]) == 3 ** n
        assert int(row["effective_M"]) == min(nominal, 3 ** n)
        assert abs(float(row["coverage_fraction"]) - int(row["effective_M"]) / (3 ** n)) < 1e-12
    for path in PACKAGE.iterdir():
        if not path.is_file() or path.name in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}:
            continue
        data = path.read_bytes()
        assert b"result_code" not in data
        assert b"winning_sp" not in data
        assert b"gross_pre_tax" not in data
        assert b"tax_yuan" not in data
