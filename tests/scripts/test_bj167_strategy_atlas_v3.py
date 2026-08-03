import csv
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj167_gate_a_strategy_atlas_v3"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_manifest_and_gate_a_contract():
    manifest_path = PACKAGE / "SHA256SUMS.json"
    declared = json.loads(manifest_path.read_text())
    actual = {p.name: sha(p) for p in PACKAGE.iterdir() if p.is_file() and p.name != manifest_path.name}
    assert declared == actual
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_SELECTOR_ALLOCATION_ATLAS"
    assert card["allocation"]["seed_count"] == 100
    assert card["allocation"]["M_grid"] == list(range(16, 257, 16)) + [512, 1024, 1458, 2187]
    assert card["denominator"]["selector_census_rows"] == 171216
    assert card["denominator"]["selector_role_rows"] == 8840496


def test_selector_and_allocation_surfaces_are_complete():
    census = rows(PACKAGE / "selector_census.csv")
    assert len(census) == 171216
    assert len({r["selector_id"] for r in census}) == 492
    assert {r["family"] for r in census} == {"S1_GATE_TOPK", "S2_COMPLETE_ISSUE_LOWP"}
    grid = rows(PACKAGE / "allocation_grid.csv")
    assert len(grid) == 24966
    assert len({r["cell_id"] for r in grid}) == len(grid)
    assert {r["seed"] for r in grid if r["seed"] != "NA"} == {f"137{i:03d}" for i in range(1, 101)}


def test_gate_a_payloads_are_outcome_unexposed():
    identity_shards = sorted(PACKAGE.glob("selector_identities-*.csv.gz"))
    role_shards = sorted(PACKAGE.glob("selector_role_vectors-*.csv.gz"))
    assert identity_shards and role_shards
    with gzip.open(identity_shards[0], "rt", newline="", encoding="utf-8") as handle:
        identity_fields = next(csv.reader(handle))
    with gzip.open(role_shards[0], "rt", newline="", encoding="utf-8") as handle:
        role_fields = next(csv.reader(handle))
    forbidden = {"result_code", "winning_sp", "payout", "tax_yuan", "no_tax_roi", "settlement_status"}
    assert not forbidden.intersection(identity_fields)
    assert not forbidden.intersection(role_fields)
    assert "outcome_boundary" in identity_fields and "outcome_boundary" in role_fields
