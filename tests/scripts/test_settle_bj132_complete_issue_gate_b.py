"""Integrity checks for #132's primary complete-issue Gate-B settlement."""
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
SCRIPT = ROOT / "scripts/settle_bj132_complete_issue_gate_b.py"
PACKAGE = ROOT / "results/bj132_gate_b_complete_issue_outcome_settlement_v1"


def module():
    spec = importlib.util.spec_from_file_location("bj132_complete_issue_gate_b", SCRIPT)
    assert spec and spec.loader
    result = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def rows():
    with gzip.open(PACKAGE / "portfolio_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_manifest_denominator_and_primary_boundary() -> None:
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    assert declared == actual
    assert Counter(row["settlement_status"] for row in rows()) == {
        "NO_BET_GATE_A": 3_132,
        "SETTLED": 128_964,
        "UNAVAILABLE_CANONICAL_OUTCOME": 28_638,
    }
    assert json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))["decision"] == "NO_PROMOTION"
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_B_PRIMARY_COMPLETE_ISSUE_OUTCOME_SETTLEMENT"
    assert card["primary_unit"] == "complete (issue, fold) instance; no segment is used for selection, tax, participation, overlap, folds, or LOYO"
    assert "not read by this runner" in card["legacy_boundary"]


def test_matched_geometry_outcome_factor_and_issue_tax() -> None:
    mod = module()
    assert mod.FREEZE_MANIFEST == "6583503ee80fd2b40bb1c000917ff094afa0551b6a3f0af4b8d175a6432872f9"
    assert mod.OUTCOME_PAYLOAD == "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    buckets: dict[str, Decimal] = defaultdict(Decimal)
    all_rows = list(rows())
    for row in all_rows:
        if row["arm"] != "NO_BET_CONTROL":
            grouped[(row["variant_id"], row["portfolio_id"])].append(row)
        if row["settlement_status"] != "SETTLED":
            assert Decimal(row["stake_yuan"]) == 0
            continue
        buckets[row["tax_bucket_key"]] += Decimal(row["gross_pre_tax_yuan"])
        if row["coverage_hit"] == "YES":
            expected = (Decimal(2) * Decimal("0.65") * Decimal(row["final_winning_sp_product"])).quantize(Decimal("0.000001"))
            assert abs(Decimal(row["gross_pre_tax_yuan"]) - expected) <= Decimal("0.000001")
        else:
            assert Decimal(row["gross_pre_tax_yuan"]) == 0
    assert len(grouped) == 52_534
    for group in grouped.values():
        assert {row["arm"] for row in group} == {"MATCHED_FULL_N7", "P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"}
        assert len({row["selected_match_ids"] for row in group}) == 1
        assert {int(row["formula_k"]) for row in group if row["arm"] == "MATCHED_FULL_N7"} == {2187}
        assert {int(row["formula_k"]) for row in group if row["arm"] != "MATCHED_FULL_N7"} == {1458}
    for row in all_rows:
        if row["settlement_status"] != "SETTLED":
            continue
        expected_tax = Decimal(row["gross_pre_tax_yuan"]) * Decimal("0.20") if buckets[row["tax_bucket_key"]] >= Decimal(10_000) else Decimal(0)
        assert Decimal(row["tax_yuan"]) == expected_tax.quantize(Decimal("0.000001"))


def test_all_primary_arms_are_negative_and_robustness_is_complete() -> None:
    with (PACKAGE / "arm_summary.csv").open(newline="", encoding="utf-8") as handle:
        all_rows = list(csv.DictReader(handle))
    active = [row for row in all_rows if row["arm"] != "NO_BET_CONTROL"]
    assert len(active) == 27
    assert all(Decimal(row["tax_adjusted_roi"]) < 0 for row in active)
    with (PACKAGE / "robustness_summary.csv").open(newline="", encoding="utf-8") as handle:
        robust = list(csv.DictReader(handle))
    assert len(robust) == 702
    assert {row["scope"] for row in robust} == {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}
    with (PACKAGE / "issue_policy_accounting.csv").open(newline="", encoding="utf-8") as handle:
        accounting = list(csv.DictReader(handle))
    assert len(accounting) == 7_413
    assert all(row["tax_bucket_key"] == f"{row['issue_instance']}|{row['variant_id']}|{row['arm']}" for row in accounting)
    assert {row["loyo_unit"] for row in accounting} == {"entire issue instance held intact within its year/fold"}


def test_portable_content_and_primary_diagnostics_are_present() -> None:
    content = json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    assert content["contract_version"] == "bj132-complete-issue-gateb-portable-content-v1"
    assert set(content["gzip_payloads"]) == {
        "portfolio_settlement.csv.gz", "matched_full_deltas.csv.gz", "q_minus_p_disagreement_deltas.csv.gz",
    }
    assert content["gzip_payloads"]["portfolio_settlement.csv.gz"]["canonical_decompressed_bytes"] == 131_941_897
    for name, expected in (("matched_full_deltas.csv.gz", 85_976), ("q_minus_p_disagreement_deltas.csv.gz", 35_117)):
        with gzip.open(PACKAGE / name, "rt", newline="", encoding="utf-8") as handle:
            assert sum(1 for _ in csv.DictReader(handle)) == expected
