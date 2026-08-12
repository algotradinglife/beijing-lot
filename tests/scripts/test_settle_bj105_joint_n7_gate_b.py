"""Focused integrity/accounting tests for #105's one-shot Gate-B settlement."""
from __future__ import annotations

import importlib.util
import csv
import gzip
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj105_gate_b_outcome_settlement_v1r2"
SPEC = importlib.util.spec_from_file_location(
    "bj105_gate_b", ROOT / "scripts" / "settle_bj105_joint_n7_gate_b.py"
)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)


def frontier(**changes: str) -> dict[str, str]:
    value = {
        "disposition": "AVAILABLE", "formula_k": "648", "active_k": "648",
        "stake_yuan": "1296", "issue": "24001", "pool_id": "p", "threshold": "0.2",
        "gm_threshold": "2.9", "depth": "3", "arm": "FIXED_ARGMIN",
    }
    value.update(changes)
    return value


def roles() -> list[dict[str, str]]:
    result = []
    for rank in range(1, 8):
        result.append({"role_rank": str(rank), "match_id": str(rank), "role": "FULL",
                       "allowed_codes": "310", "omitted_codes": "", "p_min": "0.1"})
    result[0].update({"role": "DOUBLE", "allowed_codes": "31", "omitted_codes": "0"})
    result[1].update({"role": "DOUBLE", "allowed_codes": "30", "omitted_codes": "1"})
    result[2].update({"role": "DOUBLE", "allowed_codes": "10", "omitted_codes": "3"})
    return result


def outcomes() -> dict[str, dict[str, str]]:
    codes = {1: "3", 2: "3", 3: "1", 4: "3", 5: "3", 6: "3", 7: "3"}
    return {str(rank): {"result_code": codes[rank], "winning_sp": "2", "winning_sp_source": "canonical"}
            for rank in range(1, 8)}


def test_factor_once_and_frozen_k_geometry() -> None:
    result = MOD.settlement_geometry(frontier(), roles(), outcomes())
    assert result["status"] == "SETTLED"
    assert result["hit"] == "YES"
    assert result["gross"] == Decimal(2) * Decimal("0.65") * Decimal(2) ** 7
    assert result["stake"] == Decimal(1296)


def test_canonical_gap_is_fail_closed_not_a_no_bet_gate() -> None:
    source = outcomes(); del source["3"]
    result = MOD.settlement_geometry(frontier(), roles(), source)
    assert result["status"] == "UNAVAILABLE_CANONICAL_OUTCOME"
    assert result["gap_count"] == 1
    assert result["stake"] == 0


def test_gate_a_fail_gm_retains_roles_but_never_stakes() -> None:
    result = MOD.settlement_geometry(
        frontier(disposition="FAIL_GM_GATE", active_k="0", stake_yuan="0"), roles(), outcomes()
    )
    assert result["status"] == "NO_BET_GATE_A"
    assert result["gross"] == 0


def test_tax_aggregates_by_policy_issue_bucket() -> None:
    assert MOD.allocated_tax(Decimal("9999"), Decimal("9999")) == 0
    assert MOD.allocated_tax(Decimal("4000"), Decimal("10000")) == Decimal("800")
    assert MOD.allocated_tax(Decimal(0), Decimal("12000")) == 0


def test_exact_binomial_and_input_identities_are_bound() -> None:
    assert MOD.exact_binomial_two_sided(2, 10, 0.5) == 0.10937500000000006
    assert MOD.EXPECTED_GATE_A_MANIFEST == "e11b24c31a86582aa254a7af7b7cbdc535547f82c018042253baec196d069912"
    assert MOD.EXPECTED_OUTCOME_PAYLOAD == "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"


def test_committed_package_is_manifest_bound_and_keeps_full_denominator() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    assert manifest == actual
    with gzip.open(PACKAGE / "portfolio_settlement.csv.gz", "rt", newline="") as handle:
        counts: dict[str, int] = {}
        for row in csv.DictReader(handle):
            counts[row["settlement_status"]] = counts.get(row["settlement_status"], 0) + 1
    assert counts == {"NO_BET_GATE_A": 499069, "SETTLED": 12019, "UNAVAILABLE_CANONICAL_OUTCOME": 1008}
    assert (PACKAGE / "per_code_calibration.csv").is_file()
    assert (PACKAGE / "pool_failure_concentration.csv").is_file()
