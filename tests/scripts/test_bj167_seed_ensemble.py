"""Durability checks for the #167 N7-only 100-seed packages."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE_A = ROOT / "results/bj167_gate_a_preoutcome_v1"
GATE_B = ROOT / "results/bj167_gate_b_outcome_settlement_v1r1"
GA_MANIFEST = "3e9cd84d8714ee52c979da26b174bb32e0c1d1cdb5e72bca9e34cc80deeaa519"
GA_CONTENT = "3fb79bf49f15484067b8934e96c1b7a4a831762929c5892b15679d38b87d443b"
GB_MANIFEST = "11e7019efa2eca044b012125bebcdcaaf4b25d843ac49d062ef62e9b409def34"
GB_CONTENT = "61d9a60e3b7c9ef49e6dca786936d69d377fbcabc678a4e1e6041f96796eec6b"


def manifest_check(path: Path, expected: str, content: str) -> None:
    manifest_path = path / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {name: hashlib.sha256((path / name).read_bytes()).hexdigest() for name in manifest}
    assert manifest == actual
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == expected
    assert hashlib.sha256((path / "CONTENT_IDENTITY.json").read_bytes()).hexdigest() == content


def test_gate_a_immutable_n7_seed_freeze() -> None:
    manifest_check(GATE_A, GA_MANIFEST, GA_CONTENT)
    card = json.loads((GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_N7_SEED_ENSEMBLE"
    assert card["n"] == 7
    assert card["identity_count"] == 1005
    assert card["role_count"] == 7035
    assert card["allocation_rows"] == 100500
    assert card["seed_panel"] == [f"137{i:03d}" for i in range(1, 101)]
    assert card["M_grid"] == [32, 64, 128]
    assert "No result" in card["outcome_boundary"]
    with gzip.open(GATE_A / "allocation_catalog.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100500
    assert len({(row["identity_id"], row["seed"]) for row in rows}) == 100500


def test_gate_b_settlement_and_ensemble_contract() -> None:
    manifest_check(GATE_B, GB_MANIFEST, GB_CONTENT)
    card = json.loads((GATE_B / "validation_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_B_OUTCOME_SETTLEMENT_N7_SEED_ENSEMBLE"
    assert card["n"] == 7
    assert card["seed_count"] == 100
    assert card["identity_settlement_rows"] == 301500
    assert card["issue_settlement_rows"] == 104400
    assert card["bootstrap_replicates"] == 2000
    with (GATE_B / "ensemble_summary.csv").open(newline="", encoding="utf-8") as handle:
        ensemble = list(csv.DictReader(handle))
    assert [row["M"] for row in ensemble] == ["32", "64", "128"]
    assert all(float(row["mean_roi"]) < 0 for row in ensemble)
    with (GATE_B / "seed_summary.csv").open(newline="", encoding="utf-8") as handle:
        seeds = list(csv.DictReader(handle))
    assert len(seeds) == 300
    assert {row["seed"] for row in seeds} == {f"137{i:03d}" for i in range(1, 101)}
    bootstrap = list(csv.DictReader((GATE_B / "issue_cluster_bootstrap.csv").open(newline="", encoding="utf-8")))
    assert len(bootstrap) == 3
    assert all(int(row["replicates"]) == 2000 for row in bootstrap)
    for filename in ("prefix_convergence.csv", "three_vs_hundred_seed_delta.csv", "variance_decomposition.csv", "truth_rank_distribution.csv", "seed_overlap_summary.csv", "seed_ensemble_roi.svg", "prefix_convergence.svg", "interpretation.md"):
        assert (GATE_B / filename).is_file()


def test_no_pooling_statement_is_durable() -> None:
    card = json.loads((GATE_B / "validation_card.json").read_text(encoding="utf-8"))
    assert "no pooling" in card["tax_rule"]
    assert "independent" in (GATE_B / "interpretation.md").read_text(encoding="utf-8")
