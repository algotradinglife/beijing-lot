"""Focused no-outcome tests for #107's terminal all-NO_BET Gate-A freeze."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj107_gate_a", ROOT / "scripts" / "freeze_bj107_issue_value_gate_a.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def test_accepted_inputs_bind_terminal_no_signal_boundary() -> None:
    provenance = MOD.validate_upstream()
    assert provenance["input_manifests"]["bj106_gate_b"] == MOD.EXPECTED["bj106_gate_b"]


def test_every_pool_is_retained_and_explicit_no_bet() -> None:
    pools = MOD.read_exact_csv(MOD.SEGMENTATION / "issue_pool_census.csv", MOD.POOL_FIELDS)
    rows = MOD.make_denominator(pools)
    assert len(rows) == 2659
    assert len({row["issue"] for row in rows}) == 344
    assert {row["gate_disposition"] for row in rows} == {"ALL_NO_BET_UPSTREAM_NO_SIGNAL"}
    assert {row["accepted_value_pocket_count"] for row in rows} == {0}
    assert {row["selected_match_count"] for row in rows} == {0}


def test_committed_package_is_manifest_bound_and_outcome_free() -> None:
    package = ROOT / "results" / "bj107_gate_a_preoutcome_v1"
    manifest = json.loads((package / "SHA256SUMS.json").read_text())
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in package.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    assert manifest == actual
    with (package / "issue_pool_no_bet_denominator.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2659
    assert all(row["no_bet_reason"] == "UPSTREAM_106_NO_PROMOTED_VALUE_POCKETS" for row in rows)
    card = json.loads((package / "gate_a_card.json").read_text())
    assert card["gate_b"] == "NOT_REQUIRED: no staked policy exists when every candidate count is zero."
