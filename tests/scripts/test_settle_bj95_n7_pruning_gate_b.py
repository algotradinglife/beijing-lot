"""Focused accounting tests for #95's one-shot Gate-B settlement."""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("bj95_gate_b", ROOT / "scripts" / "settle_bj95_n7_pruning_gate_b.py")
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def frontier(**overrides: str) -> dict[str, str]:
    row = {
        "arm": "CAL_MIN_P", "depth": "1", "disposition": "AVAILABLE", "formula_k": "1458",
        "selected_sequence_count": "1458", "stake_yuan": "2916", "actual_removals": "1",
        "removed_positions": "2", "removed_codes": "0", "calibrated_mass": "0.8",
    }
    row.update(overrides)
    return row


def deletion(position: str = "2", code: str = "0") -> dict[str, str]:
    return {"removal_rank": "1", "position": position, "removed_code": code}


def test_available_geometry_hits_only_when_the_frozen_removed_code_is_not_truth() -> None:
    hit, selected, stake, mass, disposition = MOD.hit_and_geometry(frontier(), {1: "3", 2: "1", 3: "0", 4: "3", 5: "1", 6: "0", 7: "3"}, [deletion()])
    assert (hit, selected, stake, mass, disposition) == ("YES", 1458, Decimal("2916"), Decimal("0.8"), "AVAILABLE")
    hit, *_ = MOD.hit_and_geometry(frontier(), {1: "3", 2: "0", 3: "0", 4: "3", 5: "1", 6: "0", 7: "3"}, [deletion()])
    assert hit == "NO"


def test_full_control_and_unavailable_depth_preserve_frozen_k_and_zero_no_bet_stake() -> None:
    control = frontier(arm=MOD.CONTROL, depth="0", formula_k="2187", selected_sequence_count="2187", stake_yuan="4374", actual_removals="0", removed_positions="", removed_codes="", calibrated_mass="1")
    assert MOD.hit_and_geometry(control, {position: "3" for position in range(1, 8)}, [])[0:3] == ("YES", 2187, Decimal("4374"))
    unavailable = frontier(arm="MODEL_MARKET_AGREE", depth="4", disposition="UNAVAILABLE_BY_RULE", formula_k="432", selected_sequence_count="0", stake_yuan="0", actual_removals="0", removed_positions="", removed_codes="")
    assert MOD.hit_and_geometry(unavailable, {position: "3" for position in range(1, 8)}, [])[0:4] == ("NO_BET", 0, Decimal("0"), Decimal("0"))


def test_settlement_factor_is_once_and_final_price_is_uncapped() -> None:
    final_product = Decimal("10")
    assert MOD.STAKE_PER_SEQUENCE * MOD.FACTOR * final_product == Decimal("13.00")
    assert MOD.FACTOR == Decimal("0.65")


def test_nomination_is_fail_closed_without_all_scope_stability() -> None:
    overview = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "0.1", "ex_best_group_roi": "0.1", "ex_best_issue_roi": "0.1"}]
    annual = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "-0.1"}]
    loyo = [{"arm": "CAL_MIN_P", "depth": 1, "roi": "0.1"}]
    assert MOD.nomination(overview, annual, loyo)["decision"] == "NO_PROMOTION"


def test_gate_b_binds_accepted_immutable_sources() -> None:
    assert MOD.EXPECTED_GATE_A_MANIFEST == "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
    assert MOD.EXPECTED_OUTCOME_SOURCE_MANIFEST == "07957d4e21076bc9799f16e3b582e36854a16858436f07adf306260a474c271f"
    assert MOD.EXPECTED_CANONICAL_DB_SHA256 == "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"


def test_bj91_comparison_treats_zero_k_as_a_no_bet() -> None:
    recovery_spec = importlib.util.spec_from_file_location(
        "bj95_gate_b_recovery", ROOT / "scripts" / "summarize_bj95_gate_b_v1_recovery.py"
    )
    assert recovery_spec and recovery_spec.loader
    recovery = importlib.util.module_from_spec(recovery_spec)
    recovery_spec.loader.exec_module(recovery)
    assert recovery.normalise_bj91_status("0") == "NO_BET"
    assert recovery.normalise_bj91_status("2187") == "SETTLED"


def test_break_even_diagnostic_is_derived_from_realised_hit_gross_only() -> None:
    recovery_spec = importlib.util.spec_from_file_location(
        "bj95_gate_b_recovery", ROOT / "scripts" / "summarize_bj95_gate_b_v1_recovery.py"
    )
    assert recovery_spec and recovery_spec.loader
    recovery = importlib.util.module_from_spec(recovery_spec)
    recovery_spec.loader.exec_module(recovery)
    summary = [{"arm": "A", "depth": 1, "scope": "ALL"}]
    rows = [
        {"arm": "A", "depth": "1", "year": "2020", "quarter": "2020-Q1", "settlement_status": "SETTLED", "hit": "YES", "gross_yuan": "20", "stake_yuan": "10"},
        {"arm": "A", "depth": "1", "year": "2020", "quarter": "2020-Q1", "settlement_status": "SETTLED", "hit": "NO", "gross_yuan": "0", "stake_yuan": "10"},
    ]
    recovery.add_break_even_fields(summary, rows)
    assert summary[0]["break_even_hits_at_observed_mean_hit_gross"] == "1.000000000000"
    assert summary[0]["break_even_coverage_rate_at_observed_mean_hit_gross"] == "0.500000000000"
