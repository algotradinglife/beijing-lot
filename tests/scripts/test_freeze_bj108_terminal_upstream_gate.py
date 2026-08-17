"""Focused no-outcome tests for #108's all-not-run terminal evaluation."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj108_terminal", ROOT / "scripts" / "freeze_bj108_terminal_upstream_gate.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC); sys.modules[SPEC.name] = MOD; SPEC.loader.exec_module(MOD)


def test_terminal_inputs_bind_without_opening_settlement_payloads() -> None:
    provenance = MOD.validate_inputs()
    assert provenance["input_manifests"] == {"bj105": MOD.EXPECTED_105_MANIFEST, "bj107": MOD.EXPECTED_107_MANIFEST}


def test_all_no_bet_prerequisite_disables_optimizer_and_settlement() -> None:
    source = MOD.read_csv(MOD.BJ107 / "issue_pool_no_bet_denominator.csv", MOD.INPUT_FIELDS)
    rows = MOD.make_rows(source)
    assert len(rows) == 2659 and len({row["issue"] for row in rows}) == 344
    assert {row["dynamic_n_status"] for row in rows} == {"NOT_RUN_UPSTREAM_ALL_NO_BET"}
    assert {row["candidate_portfolio_count"] for row in rows} == {0}
    assert {row["stake_yuan"] for row in rows} == {"0.000000"}


def test_committed_package_is_manifest_bound_and_terminal() -> None:
    package = ROOT / "results" / "bj108_terminal_upstream_gate_v1"
    manifest = json.loads((package / "SHA256SUMS.json").read_text())
    actual = {item.name: hashlib.sha256(item.read_bytes()).hexdigest() for item in package.iterdir()
              if item.is_file() and item.name != "SHA256SUMS.json"}
    assert manifest == actual
    with (package / "issue_pool_not_run_denominator.csv").open(newline="") as handle: rows = list(csv.DictReader(handle))
    assert len(rows) == 2659
    decision = json.loads((package / "decision.json").read_text())
    assert decision == {"decision": "NO_PROMOTION", "reason": "#107 accepted periods=0; dynamic-N optimization and outcome settlement are not required.", "status": "NOT_RUN_UPSTREAM_ALL_NO_BET"}
