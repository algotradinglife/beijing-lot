"""Integrity and endpoint checks for #131's canonical soft-cover Gate B."""
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
SCRIPT = ROOT / "scripts" / "settle_bj131_soft_cover_n7_gate_b.py"
PACKAGE = ROOT / "results" / "bj131_gate_b_outcome_settlement_v2"
BASELINE = ROOT / "results" / "bj127_gate_b_outcome_settlement_v1"


def module():
    spec = importlib.util.spec_from_file_location("bj131_gate_b", SCRIPT)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def rows():
    with gzip.open(PACKAGE / "portfolio_settlement.csv.gz", "rt", newline="") as handle:
        yield from csv.DictReader(handle)


def aggregate(path: Path, new: bool) -> dict[tuple[str, str], tuple[Decimal, Decimal, Decimal, int]]:
    totals: dict[tuple[str, str], list[Decimal | int]] = {}
    with gzip.open(path / "portfolio_settlement.csv.gz", "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if new:
                if row["seed_role"] != "PRIMARY" or row["sleeve_label"] not in {"S00_HARD_PRUNE", "S100_FULL"}:
                    continue
                arm = {"S00_HARD_PRUNE": "PRUNE_ONE_GLOBAL_N7", "S100_FULL": "MATCHED_FULL_N7"}[row["sleeve_label"]]
            else:
                arm = row["arm"]
            if row["settlement_status"] != "SETTLED":
                continue
            key = row["variant_id"], arm
            item = totals.setdefault(key, [Decimal(0), Decimal(0), Decimal(0), 0])
            item[0] += Decimal(row["stake_yuan"])
            item[1] += Decimal(row["gross_pre_tax_yuan"])
            item[2] += Decimal(row["tax_adjusted_net_yuan"])
            item[3] += 1
    return {key: (item[0], item[1], item[2], item[3]) for key, item in totals.items()}


def test_manifest_complete_denominator_and_decision() -> None:
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    assert declared == actual
    assert Counter(row["settlement_status"] for row in rows()) == {
        "SETTLED": 1_821_834,
        "UNAVAILABLE_CANONICAL_OUTCOME": 72_681,
        "NO_BET_GATE_A": 502_551,
    }
    assert json.loads((PACKAGE / "decision.json").read_text())["decision"] == "NO_PROMOTION"


def test_each_frozen_seed_sleeve_has_full_support_and_geometry() -> None:
    counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in rows():
        counts[(row["seed_role"], row["sleeve_label"])][row["settlement_status"]] += 1
        if row["settlement_status"] == "SETTLED":
            assert int(row["formula_k"]) == 1458 + int(row["sleeve_tickets"])
            assert Decimal(row["stake_yuan"]) == Decimal(2) * int(row["formula_k"])
            if row["omitted_code_occurred"] == "NO":
                assert row["coverage_hit"] == "YES"
            if row["sleeve_label"] == "S00_HARD_PRUNE":
                assert (row["coverage_hit"] == "NO") == (row["omitted_code_occurred"] == "YES")
            if row["sleeve_label"] == "S100_FULL":
                assert row["coverage_hit"] == "YES"
    assert len(counts) == 21
    assert all(counter == {"SETTLED": 86_754, "UNAVAILABLE_CANONICAL_OUTCOME": 3_461,
                            "NO_BET_GATE_A": 23_931} for counter in counts.values())


def test_primary_endpoints_exactly_reproduce_accepted_bj127_full_and_hard_prune() -> None:
    assert aggregate(PACKAGE, True) == aggregate(BASELINE, False)


def test_complete_curve_is_nonpositive_and_contains_portfolio_layer_deltas() -> None:
    with (PACKAGE / "sleeve_summary.csv").open(newline="") as handle:
        summary = list(csv.DictReader(handle))
    with (PACKAGE / "sleeve_response_curve.csv").open(newline="") as handle:
        curve = list(csv.DictReader(handle))
    all_curve = [row for row in curve if row["scope"] == "ALL"]
    assert len(summary) == len(all_curve) == 9 * 3 * 7
    assert len(curve) > len(all_curve)  # year/fold/LOYO support accompanies the ALL response curve.
    assert all(Decimal(row["no_tax_roi"]) < 0 and Decimal(row["tax_adjusted_roi"]) < 0 for row in summary)
    strict = [row for row in summary if row["variant_id"] == "ESP300_GM305_LOWP20" and row["seed_role"] == "PRIMARY"]
    assert {row["sleeve_label"] for row in strict} == {"S00_HARD_PRUNE", "S05_SOFT_COVER", "S10_SOFT_COVER", "S20_SOFT_COVER", "S33_SOFT_COVER", "S50_SOFT_COVER", "S100_FULL"}
    assert next(row for row in strict if row["sleeve_label"] == "S00_HARD_PRUNE")["tax_adjusted_roi"] == "-0.199110206343"
    assert next(row for row in strict if row["sleeve_label"] == "S100_FULL")["tax_adjusted_roi"] == "-0.217545069710"
    assert all(row["tax_adjusted_roi_delta_vs_full"] and row["tax_adjusted_roi_delta_vs_hard_prune"] for row in all_curve)
    assert sum(1 for _ in gzip.open(PACKAGE / "matched_sleeve_deltas.csv.gz", "rt", newline="")) == 1_821_835


def test_source_bindings_and_portable_content_are_fixed() -> None:
    mod = module()
    assert mod.EXPECTED_FREEZE_MANIFEST == "79d722a7919afb03916d0be57dd72c51c5ef2174fbf6b27cea2042ed6a65e53c"
    assert mod.EXPECTED_OUTCOME_PAYLOAD == "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
    content = json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text())
    assert set(content["gzip_payloads"]) == {"portfolio_settlement.csv.gz", "matched_sleeve_deltas.csv.gz"}
    assert hashlib.sha256((PACKAGE / "CONTENT_IDENTITY.json").read_bytes()).hexdigest() == (
        "fc5d99234328f0ae8ced6b3624e69a2aedc6e196cb151b699f281beb392deacb"
    )
