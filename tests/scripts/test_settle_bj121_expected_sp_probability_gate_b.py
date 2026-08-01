"""Focused contract and accounting tests for #121 Gate B."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results/bj121_gate_b_outcome_settlement_v1"
SPEC = importlib.util.spec_from_file_location(
    "bj121_gate_b", ROOT / "scripts/settle_bj121_expected_sp_probability_gate_b.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def available_frontier(**changes: str) -> dict[str, str]:
    row = {
        "disposition": "AVAILABLE", "selected_n": "4", "formula_k": "12",
        "stake_yuan": "24", "role_codes": "1:DOUBLE:31;2:SINGLE:3;3:FULL:310;4:DOUBLE:10",
    }
    row.update(changes)
    return row


def canonical() -> dict[str, dict[str, str]]:
    return {
        "1": {"result_code": "3", "winning_sp": "2", "winning_sp_source": "official"},
        "2": {"result_code": "3", "winning_sp": "3", "winning_sp_source": "official"},
        "3": {"result_code": "1", "winning_sp": "4", "winning_sp_source": "official"},
        "4": {"result_code": "0", "winning_sp": "5", "winning_sp_source": "official"},
    }


def metric_row(kickoff: str, pool: str, net: str, hit: str) -> dict[str, str]:
    return {
        "first_kickoff_ts": kickoff, "pool_id": pool, "disposition": "AVAILABLE",
        "settlement_status": "SETTLED", "selected_n": "4", "formula_k": "1",
        "stake_yuan": "2", "gross_pre_tax_yuan": "0", "tax_yuan": "0",
        "after_tax_gross_yuan": "0", "tax_adjusted_net_yuan": net,
        "coverage_hit": hit, "excluded_outcome_hits": "0", "issue": pool,
    }


def test_factor_is_applied_once_and_frozen_ticket_geometry_is_preserved() -> None:
    result = MOD.settlement_geometry(available_frontier(), canonical())
    assert result["status"] == "SETTLED"
    assert result["hit"] == "YES"
    assert result["gross"] == Decimal("2") * Decimal("0.65") * Decimal(2 * 3 * 4 * 5)


def test_excluded_truth_misses_and_missing_truth_is_unavailable() -> None:
    truth = canonical()
    truth["1"] = {**truth["1"], "result_code": "0"}
    miss = MOD.settlement_geometry(available_frontier(), truth)
    assert miss["hit"] == "NO" and miss["gross"] == 0 and miss["excluded"] == 1
    del truth["4"]
    unavailable = MOD.settlement_geometry(available_frontier(), truth)
    assert unavailable["status"] == "UNAVAILABLE_CANONICAL_OUTCOME"
    assert unavailable["gap"] == 1


def test_no_bet_is_not_an_outcome_gap_and_tax_is_issue_policy_level() -> None:
    no_bet = MOD.settlement_geometry(
        available_frontier(disposition="NO_BET", selected_n="0", formula_k="0", stake_yuan="0", role_codes=""),
        canonical(),
    )
    assert no_bet["status"] == "NO_BET_GATE_A"
    assert MOD.allocated_tax(Decimal("9999"), Decimal("9999")) == 0
    assert MOD.allocated_tax(Decimal("4000"), Decimal("10000")) == Decimal("800")


def test_drawdown_and_streak_are_reordered_by_kickoff_not_file_order() -> None:
    metric = MOD.Metric("ESP300_GM305_LOWP30", "MIXED_N4", "ALL", "ALL")
    metric.add(metric_row("2022-01-02", "b", "-4", "NO"))
    metric.add(metric_row("2022-01-01", "a", "10", "YES"))
    metric.add(metric_row("2022-01-03", "c", "-8", "NO"))
    output = metric.output()
    assert output["max_drawdown_yuan"] == "12.000000"
    assert output["longest_losing_streak"] == 2


def test_committed_package_is_complete_manifest_bound_and_all_nonempty_arms_are_negative() -> None:
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert declared == actual
    counts: dict[str, int] = {}
    with gzip.open(PACKAGE / "portfolio_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        rows = 0
        for row in csv.DictReader(handle):
            counts[row["settlement_status"]] = counts.get(row["settlement_status"], 0) + 1
            rows += 1
    assert rows == 311_103
    assert counts == {
        "NO_BET_GATE_A": 86_994,
        "SETTLED": 207_765,
        "UNAVAILABLE_CANONICAL_OUTCOME": 16_344,
    }
    with (PACKAGE / "arm_comparison.csv").open(newline="", encoding="utf-8") as handle:
        comparison = list(csv.DictReader(handle))
    assert len(comparison) == 117
    assert all(not row["tax_adjusted_roi"] or Decimal(row["tax_adjusted_roi"]) < 0 for row in comparison)
    assert json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))["decision"] == "NO_PROMOTION"
