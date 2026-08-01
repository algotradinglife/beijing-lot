"""Integrity checks for #119's frozen sensitivity grid and settlement."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run_bj119_candidate_sensitivity.py"
GATE_A = ROOT / "results" / "bj119_gate_a_preoutcome_v1r1"
GATE_B = ROOT / "results" / "bj119_gate_b_outcome_settlement_v1r3"


def load():
    spec = importlib.util.spec_from_file_location("bj119_sensitivity", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def package_manifest(package: Path) -> None:
    expected = json.loads((package / "SHA256SUMS.json").read_text())
    actual = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in package.iterdir()
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    assert expected == actual


def test_gate_a_binds_only_accepted_upstream_controls() -> None:
    module = load()
    provenance = module.validate_gate_a()
    assert provenance["a106"] == module.MAN["a106"]
    assert provenance["b106"] == module.MAN["b106"]
    assert provenance["m101"] == module.MAN["m101"]


def test_frozen_grid_has_full_denominator_and_strict_zero_control() -> None:
    with (GATE_A / "portfolio_frontier.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2_659 * 8 * 7
    strict = [row for row in rows if row["variant_id"] == "STRICT_106_PROMOTED"]
    assert len(strict) == 2_659 * 7
    assert {row["disposition"] for row in strict} == {"NO_BET"}
    assert any(
        row["variant_id"] == "RELAX_Q110_P20" and row["arm"] == "SINGLE_N4"
        and row["disposition"] == "AVAILABLE"
        for row in rows
    )


def test_committed_packages_are_complete_and_gate_b_pins_gate_a() -> None:
    module = load()
    package_manifest(GATE_A)
    package_manifest(GATE_B)
    card = json.loads((GATE_B / "settlement_card.json").read_text())
    assert card["gate_a_manifest"] == module.EXPECTED_GATE_A_MANIFEST
    assert card["outcome_manifest"] == module.MAN["out"]
    with (GATE_B / "variant_roi_comparison.csv").open(newline="") as handle:
        comparison = list(csv.DictReader(handle))
    assert len(comparison) == 56
    assert all("ex_best_payout_roi" in row for row in comparison)
    assert all(
        int(row["frontiers"])
        == int(row["eligible_periods"])
        + int(row["gate_a_no_bet"])
        + int(row["outcome_unavailable"])
        == 2_659
        for row in comparison
    )
    assert all(
        int(row["non_settled"])
        == int(row["gate_a_no_bet"]) + int(row["outcome_unavailable"])
        for row in comparison
    )
    assert any(row["roi"] and float(row["roi"]) > 0 for row in comparison)


def test_settlement_has_every_required_robustness_scope() -> None:
    with (GATE_B / "robustness_summary.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1_232
    assert {row["scope"] for row in rows} == {"ALL", "YEAR", "FOLD", "LOYO"}
    assert all(row["max_drawdown_yuan"] != "" for row in rows)
    assert all(
        int(row["frontiers"])
        == int(row["eligible_periods"])
        + int(row["gate_a_no_bet"])
        + int(row["outcome_unavailable"])
        for row in rows
    )
    assert all(
        int(row["non_settled"])
        == int(row["gate_a_no_bet"]) + int(row["outcome_unavailable"])
        for row in rows
    )
    assert all(int(row["frontiers"]) == 2_659 for row in rows if row["scope"] == "ALL")


def test_chronology_uses_frozen_kickoff_not_numeric_issue_id() -> None:
    module = load()
    earlier_long_issue_id = {
        "year": "2019",
        "first_kickoff_ts": "2019-01-01 03:00:00",
        "segment_index": "1",
        "pool_id": "190101-OOS_2019-S01",
        "issue": "190101",
    }
    later_short_issue_id = {
        "year": "2020",
        "first_kickoff_ts": "2020-01-01 03:00:00",
        "segment_index": "1",
        "pool_id": "20001-OOS_2020-S01",
        "issue": "20001",
    }
    assert int(earlier_long_issue_id["issue"]) > int(later_short_issue_id["issue"])
    assert module.chronology_key(earlier_long_issue_id) < module.chronology_key(later_short_issue_id)
