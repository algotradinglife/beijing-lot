from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj159_gate_a_preoutcome_v1"
EXPECTED_MANIFEST = "20ad6d3b8d5183a6fb6cadc92e80f5f6905c90318d7c195defc12ead68f60c2c"
EXPECTED_IDS = {2: 8, 3: 52, 4: 133, 5: 240, 6: 322, 7: 371, 8: 397, 9: 388, 10: 377}


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
    assert card["selection"]["variant"] == "ESP300_GM305_LOWP20"
    assert card["selection"]["n_grid"] == list(range(2, 11))
    assert card["sampling"]["allocator"] == "Q_INFORMED_WOR_DISTINCT"
    assert "No result" in card["outcome_boundary"]


def test_n_identity_counts_and_issue_denominator():
    identities = list(gz_rows(PACKAGE / "identity_catalog.csv.gz"))
    assert len(identities) == sum(EXPECTED_IDS.values())
    assert Counter(int(row["n"]) for row in identities) == Counter(EXPECTED_IDS)
    assert len({row["identity_id"] for row in identities}) == len(identities)
    pools = list(rows(PACKAGE / "pool_census.csv"))
    assert len(pools) == 2659
    assert len({row["issue"] for row in pools}) == 344
    participation = list(rows(PACKAGE / "issue_participation.csv"))
    assert len(participation) == 348 * 9
    assert {int(row["n"]) for row in participation} == set(range(2, 11))


def test_role_cardinality_q_mass_and_n7_equivalence():
    identities = list(gz_rows(PACKAGE / "identity_catalog.csv.gz"))
    roles = list(gz_rows(PACKAGE / "role_vectors.csv.gz"))
    by_id = Counter(row["identity_id"] for row in roles)
    assert set(by_id.values()) == set(range(2, 11))
    assert set(by_id) == {row["identity_id"] for row in identities}
    for row in roles:
        q = [float(row[f"q_weight{code}"]) for code in ("3", "1", "0")]
        assert all(0 < value < 1 for value in q)
        assert abs(sum(q) - 1.0) < 2e-12
    audit = json.loads((PACKAGE / "n7_reference_audit.json").read_text(encoding="utf-8"))
    assert audit["n7_identity_count"] == "371"
    assert audit["source_variant"] == "ESP300_GM305_LOWP20"


def test_sampling_grid_and_no_settlement_fields():
    plans = list(rows(PACKAGE / "sampling_plan.csv"))
    assert len(plans) == 9 * 3 * 3
    assert {int(row["n"]) for row in plans} == set(range(2, 11))
    assert {int(row["M"]) for row in plans} == {32, 64, 128}
    assert {row["seed"] for row in plans} == {"137001", "137002", "137003"}
    assert {row["allocator"] for row in plans} == {"Q_INFORMED_WOR_DISTINCT"}
    assert all(int(row["ticket_space_k"]) == 3 ** int(row["n"]) for row in plans)
    for path in PACKAGE.iterdir():
        if not path.is_file() or path.name in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}:
            continue
        data = path.read_bytes()
        assert b"result_code" not in data
        assert b"winning_sp" not in data
        assert b"gross_pre_tax" not in data
        assert b"tax_yuan" not in data
