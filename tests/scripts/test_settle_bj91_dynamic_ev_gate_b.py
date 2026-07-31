"""Focused integrity and accounting tests for #91's Gate-B settlement."""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj91_gate_b", ROOT / "scripts" / "settle_bj91_dynamic_ev_gate_b.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def leg(match_id: str = "1") -> dict[str, str]:
    return {
        "match_id": match_id, "p3": "0.5", "p1": "0.3", "p0": "0.2",
        "point_sp_3": "7", "point_sp_1": "2", "point_sp_0": "3",
        "m2_sp_3": "4", "m2_sp_1": "2", "m2_sp_0": "3",
    }


def test_frozen_issue_quarter_uses_only_the_issue_identity() -> None:
    assert MOD.frozen_quarter("20011") == "2020-Q1"
    assert MOD.frozen_quarter("191201") == "2019-Q4"


def test_predicted_value_uses_sp5_but_actual_settlement_is_uncapped() -> None:
    probability, uncapped, effective = MOD.probabilities_and_prices([leg()], "3", "POINT_SP5", None)
    assert probability == Decimal("0.5")
    assert uncapped == Decimal("7")
    assert effective == Decimal("5")
    assert MOD.STAKE_PER_SEQUENCE * MOD.FACTOR * Decimal("7") == Decimal("9.10")


def test_aggregate_counts_unavailable_without_silently_dropping_it() -> None:
    rows = [
        {"settlement_status": "SETTLED", "k": 1, "stake_yuan": "2.000000", "gross_yuan": "2.600000", "net_yuan": "0.600000", "predicted_gross_yuan": "2.200000", "retained_mass": "0.5", "hit": "YES", "issue": "20011", "group_ordinal": 1, "n": 4, "group_id": "A"},
        {"settlement_status": "UNAVAILABLE", "k": 1, "stake_yuan": "", "gross_yuan": "", "net_yuan": "", "predicted_gross_yuan": "", "retained_mass": "0.5", "hit": "UNAVAILABLE", "issue": "20011", "group_ordinal": 2, "n": 4, "group_id": "B"},
    ]
    result = MOD.aggregate(rows, cohort="PRIMARY", n=4, arm="TEST", scope="ALL")
    assert result["group_arms_total"] == 2
    assert result["group_arms_unavailable"] == 1
    assert result["bet_groups"] == 1
    assert result["stake_yuan"] == "2.000000"


def test_gate_a_manifest_and_source_identity_are_locked_constants() -> None:
    assert len(MOD.EXPECTED_GATE_A_MANIFEST) == 64
    assert len(MOD.EXPECTED_SOURCE_SHA256) == 64
    assert MOD.ARM_SPECS["FULL_3_TO_N_ANALYTIC"][0] == "full_coverage_k"
