"""Focused integrity and matched-accounting tests for #127 Gate B."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/settle_bj127_global_prune_gate_b.py"
PACKAGE = ROOT / "results/bj127_gate_b_outcome_settlement_v1"


def module():
    spec = importlib.util.spec_from_file_location("bj127_gate_b", SCRIPT)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def rows():
    with gzip.open(PACKAGE / "portfolio_settlement.csv.gz", "rt", newline="") as handle:
        yield from csv.DictReader(handle)


def test_manifest_full_denominator_and_decision() -> None:
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    assert declared == actual
    assert Counter(row["settlement_status"] for row in rows()) == {
        "NO_BET_GATE_A": 23_931, "SETTLED": 173_508, "UNAVAILABLE_CANONICAL_OUTCOME": 6_922,
    }
    assert json.loads((PACKAGE / "decision.json").read_text()) == {
        "decision": "NO_PROMOTION", "positive_all_rows": 0, "promotion_authorized": False,
        "rule": "Positive historical ROI requires strict independent EV; a negative or non-promotable finding receives light review.",
        "strict_independent_ev_required": False,
    }


def test_same_seven_pair_geometry_and_omitted_code_accounting() -> None:
    pairs: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows():
        if row["settlement_status"] == "SETTLED":
            pairs[(row["variant_id"], row["portfolio_id"])].append(row)
    assert len(pairs) == 86_754
    for pair in pairs.values():
        assert {row["arm"] for row in pair} == {"MATCHED_FULL_N7", "PRUNE_ONE_GLOBAL_N7"}
        full = next(row for row in pair if row["arm"] == "MATCHED_FULL_N7")
        prune = next(row for row in pair if row["arm"] == "PRUNE_ONE_GLOBAL_N7")
        assert full["selected_match_ids"] == prune["selected_match_ids"]
        assert (full["deleted_match_id"], full["deleted_code"]) == (prune["deleted_match_id"], prune["deleted_code"])
        assert (int(full["formula_k"]), Decimal(full["stake_yuan"])) == (2187, Decimal(4374))
        assert (int(prune["formula_k"]), Decimal(prune["stake_yuan"])) == (1458, Decimal(2916))
        assert full["coverage_hit"] == "YES"
        assert (prune["coverage_hit"] == "NO") == (prune["omitted_code_occurred"] == "YES")


def test_factor_once_issue_tax_and_source_binding() -> None:
    mod = module()
    assert mod.EXPECTED_FREEZE_MANIFEST == "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da"
    assert mod.EXPECTED_OUTCOME_PAYLOAD == "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
    buckets: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    settled = []
    for row in rows():
        if row["settlement_status"] != "SETTLED":
            assert Decimal(row["stake_yuan"]) == 0
            continue
        settled.append(row)
        buckets[(row["issue"], row["variant_id"], row["arm"])] += Decimal(row["gross_pre_tax_yuan"])
        if row["coverage_hit"] == "YES":
            displayed_gross = (Decimal(2) * Decimal("0.65") * Decimal(row["final_winning_sp_product"])).quantize(Decimal("0.000001"))
            assert abs(Decimal(row["gross_pre_tax_yuan"]) - displayed_gross) <= Decimal("0.000001")
        else:
            assert Decimal(row["gross_pre_tax_yuan"]) == 0
    for row in settled:
        expected_tax = Decimal(row["gross_pre_tax_yuan"]) * Decimal("0.20") if buckets[(row["issue"], row["variant_id"], row["arm"])] >= Decimal(10000) else Decimal(0)
        assert Decimal(row["tax_yuan"]) == expected_tax.quantize(Decimal("0.000001"))


def test_all_threshold_rows_are_nonpositive_and_robustness_is_present() -> None:
    with (PACKAGE / "arm_comparison.csv").open(newline="") as handle:
        all_rows = list(csv.DictReader(handle))
    assert len(all_rows) == 27
    prune = [row for row in all_rows if row["arm"] == "PRUNE_ONE_GLOBAL_N7"]
    assert len(prune) == 9 and all(Decimal(row["tax_adjusted_roi"]) < 0 for row in prune)
    best = max(prune, key=lambda row: Decimal(row["tax_adjusted_roi"]))
    assert (best["variant_id"], best["tax_adjusted_roi"]) == ("ESP300_GM305_LOWP20", "-0.199110206343")
    with (PACKAGE / "robustness_summary.csv").open(newline="") as handle:
        robust = list(csv.DictReader(handle))
    assert {row["scope"] for row in robust} == {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}
    assert len(list(PACKAGE.glob("matched_pair_deltas.csv"))) == 1
