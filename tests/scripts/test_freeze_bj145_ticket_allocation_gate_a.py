from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj145_gate_a_preoutcome_v4"
MANIFEST = "608ce7e8b07c46c5670b956e3459d9cccc0cb88e785aed804ba6ea55c227784a"


def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def gzip_rows(path: Path):
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_manifest_is_self_consistent_and_bound():
    manifest_path = PACKAGE / "SHA256SUMS.json"
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == MANIFEST
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in PACKAGE.iterdir()
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    assert declared == actual


def test_gate_a_contract_and_denominators():
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_TICKET_ALLOCATION_FREEZE"
    assert card["gate_b_requirements"]["authorization"].startswith("NOT_RUN")
    assert card["denominator"] == {
        "allocation_plan_rows": 1_006_416,
        "cohort_rows": 696,
        "identity_rows": 3_540,
        "m_points": 20,
        "primary_available": 339,
        "primary_no_bet": 9,
        "role_rows": 24_780,
        "secondary_available": 273,
        "secondary_no_bet": 75,
        "seed_count": 3,
        "weight_sources": 6,
    }
    assert card["weights"] == ["MODEL_P_CAL", "MARKET_WF_CAL", "BLEND_A25", "BLEND_A50", "BLEND_A75", "Q_WEIGHT"]
    assert card["caps"] == [1, 2, 4, 8]
    assert card["m_grid"] == list(range(16, 257, 16)) + [512, 1024, 1458, 2187]
    assert card["mechanisms"] == [
        "WR_DUPLICATE_STAKE", "WOR_DISTINCT", "RESIDUAL_SYSTEMATIC", "CAPPED_REPEAT",
        "DETERMINISTIC_TOP_MASS", "FULL_ENUMERATED",
    ]


def test_selection_and_role_geometry():
    cohort = rows(PACKAGE / "selection_cohort.csv")
    assert len(cohort) == 696
    assert Counter((r["arm_id"], r["selection_status"]) for r in cohort) == Counter({
        ("PRIMARY_NO_GATE_K4", "AVAILABLE"): 339,
        ("PRIMARY_NO_GATE_K4", "NO_BET_K_UNSATISFIED"): 9,
        ("SECONDARY_ESP300_GM290_K8", "AVAILABLE"): 273,
        ("SECONDARY_ESP300_GM290_K8", "NO_BET_K_UNSATISFIED"): 75,
    })
    identities = gzip_rows(PACKAGE / "identity_catalog.csv.gz")
    role_rows = gzip_rows(PACKAGE / "role_vectors.csv.gz")
    assert len(identities) == 3540
    assert len(role_rows) == 24780
    ids = {(r["arm_id"], r["issue_instance"], r["portfolio_id"]) for r in identities}
    assert len(ids) == len(identities)
    role_counts = Counter((r["arm_id"], r["issue_instance"], r["portfolio_id"]) for r in role_rows)
    assert set(role_counts.values()) == {7}
    assert set(role_counts) == ids
    for row in identities:
        assert row["selected_n"] == "7"
        assert row["outcome_boundary"].startswith("No outcome")


def test_complete_plan_surface_and_per_ticket_accounting():
    plans = gzip_rows(PACKAGE / "allocation_plan.csv.gz")
    assert len(plans) == 1_006_416
    assert len({r["plan_id"] for r in plans}) == len(plans)
    assert Counter(r["mechanism"] for r in plans) == {
        "CAPPED_REPEAT": 334_080,
        "DETERMINISTIC_TOP_MASS": 83_520,
        "FULL_ENUMERATED": 4_176,
        "RESIDUAL_SYSTEMATIC": 83_520,
        "WOR_DISTINCT": 250_560,
        "WR_DUPLICATE_STAKE": 250_560,
    }
    for row in plans:
        count, m = int(row["selected_identity_count"]), int(row["M"])
        expected = count * m * 2 if row["selection_status"] == "AVAILABLE" else 0
        assert int(row["planned_draw_count"]) == (count * m if row["selection_status"] == "AVAILABLE" else 0)
        assert int(row["planned_stake_yuan"]) == expected
        assert row["outcome_boundary"].startswith("No outcome")
    mechanisms = rows(PACKAGE / "mechanism_contract.csv")
    assert len(mechanisms) == 6
    assert all("no" in row["tax_unit_rule"] and "pooling" in row["tax_unit_rule"] for row in mechanisms)
    assert all(row["expected_unique_formula"] for row in mechanisms)
    assert all(row["realized_unique_rule"] for row in mechanisms)


def test_no_target_outcome_fields_in_frozen_payload_headers():
    forbidden = {"result", "score", "final_sp", "winning_sp", "payout", "settlement", "roi", "tax"}
    for path in (PACKAGE / "identity_catalog.csv.gz", PACKAGE / "role_vectors.csv.gz", PACKAGE / "allocation_plan.csv.gz"):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            fields = next(csv.reader(handle))
        fields = [field for field in fields if field not in {"tax_unit_rule", "outcome_boundary"}]
        assert not any(any(token in field.lower() for token in forbidden) for field in fields)
