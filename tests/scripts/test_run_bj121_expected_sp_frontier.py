"""Outcome-unexposed integrity tests for #121 Gate A."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_bj121_expected_sp_frontier.py"
PACKAGE = ROOT / "results" / "bj121_gate_a_preoutcome_v2"


def load():
    spec = importlib.util.spec_from_file_location("bj121_frontier", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gate_a_binds_outcome_unexposed_sources() -> None:
    module = load()
    provenance = module.gate_a_provenance()
    assert provenance["atlas_manifest"] == module.EXPECTED["atlas"]
    assert provenance["pool_manifest"] == module.EXPECTED["pools"]


def test_complete_grid_keeps_all_pool_denominators() -> None:
    with (PACKAGE / "portfolio_frontier.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 9 * 10 * 2659
    assert {row["variant_id"] for row in rows} == set(load().VARIANTS)
    assert {row["arm"] for row in rows} == set(load().ARMS)
    assert any(row["arm"] == "DAN_N4" and row["disposition"] == "AVAILABLE" for row in rows)
    assert all(row["reason"] for row in rows)


def test_gate_a_package_is_manifest_bound_and_outcome_free() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    actual = {item.name: hashlib.sha256(item.read_bytes()).hexdigest()
              for item in PACKAGE.iterdir() if item.is_file() and item.name != "SHA256SUMS.json"}
    assert manifest == actual
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["outcome_boundary"].startswith("No result")
    assert "canonical_outcome_join" not in (PACKAGE / "runner.py").read_text()
