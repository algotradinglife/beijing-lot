"""Integrity checks for #151's fixed-candidate outcome-unexposed Gate A."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj151_candidate_reproduction_gate_a.py"
PACKAGE = ROOT / "results" / "bj151_gate_a_preoutcome_v1"
MANIFEST_SHA256 = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"


def module():
    spec = importlib.util.spec_from_file_location("bj151_gate_a", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def read_csv(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_fixed_candidate_is_exactly_137_no_gate_k4_and_keeps_no_bets() -> None:
    cohort = read_csv("candidate_cohort.csv")
    with gzip.open(PACKAGE / "candidate_identities.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identities = list(csv.DictReader(handle))
    with gzip.open(PACKAGE / "candidate_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        roles = list(csv.DictReader(handle))
    assert len(cohort) == 348
    assert Counter(row["selection_status"] for row in cohort) == {"AVAILABLE": 339, "NO_BET_SOURCE_K4_INSUFFICIENT_IDENTITIES": 9}
    assert len(identities) == 1356
    assert len(roles) == 9492
    assert {row["gate_id"] for row in identities} == {"NO_GATE"}
    counts = Counter((row["issue"], row["fold"], row["year"]) for row in identities)
    for row in cohort:
        key = row["issue"], row["fold"], row["year"]
        assert int(row["selected_identity_count"]) == counts[key]
        if row["selection_status"] == "AVAILABLE":
            assert row["top_k_id"] == "K4"
            assert counts[key] == 4
        else:
            assert counts[key] == 0


def test_dense_grid_and_sampling_arms_are_frozen() -> None:
    runner = module()
    grid = read_csv("dense_m_grid.csv")
    plan = read_csv("sampling_plan.csv")
    assert tuple(int(row["M"]) for row in grid) == runner.M_GRID
    assert len(grid) == 58 and grid[-1]["M"] == "2187"
    assert len(plan) == 119364
    assert Counter(row["sampling_role"] for row in plan) == {"PRIMARY_WR_NATURAL_BASELINE": 59508, "SENSITIVITY_WOR_FIXED_CANDIDATE": 59508, "FULL_ECONOMIC_CONTROL": 348}
    for row in plan:
        assert row["gate_id"] == "NO_GATE" and row["top_k_id"] == "K4"
        if row["sampling_role"] == "FULL_ECONOMIC_CONTROL":
            assert row["M"] == "2187" and row["seed"] == "NA"
        else:
            assert row["seed"] in runner.SEEDS and row["M"] != "2187"
            assert int(row["planned_stake_yuan"]) == int(row["planned_draw_count"]) * 2


def test_manifest_source_bindings_and_outcome_boundary() -> None:
    runner = module()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    assert manifest == actual
    assert hashlib.sha256((PACKAGE / "SHA256SUMS.json").read_bytes()).hexdigest() == MANIFEST_SHA256
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["contract"] == runner.CONTRACT
    assert card["fixed_candidate"] == {"gate_id": "NO_GATE", "historical_reference_M": 64, "historical_reference_seeds": ["137001", "137002", "137003"], "identity_rule": "exact #137 Gate-A v2 selected_portfolio_ids; no outcome-directed selection, parameter scan, or candidate-pool expansion", "probability_vector": "Q_WEIGHT", "sampler_id": "Q_INFORMED_WOR_DISTINCT", "top_k_id": "K4"}
    assert card["sources"]["bj137_gate_a_v2"]["manifest_sha256"] == runner.SOURCE_137_MANIFEST
    assert card["sources"]["bj148_gate_a_v1"]["manifest_sha256"] == runner.SOURCE_148_GATE_A_MANIFEST
    assert "No test outcome" in card["outcome_boundary"]
    assert "never in `/tmp`" in (PACKAGE / "README.md").read_text(encoding="utf-8")
