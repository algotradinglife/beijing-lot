"""Integrity tests for #121's one-shot canonical Gate-B settlement."""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj121_gate_b_outcome_settlement_v1"
FREEZE = ROOT / "results" / "bj121_gate_a_preoutcome_v3"
FACTOR = Decimal("0.65")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def settlements():
    with gzip.open(PACKAGE / "portfolio_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_manifest_is_complete_and_binds_accepted_inputs() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in PACKAGE.iterdir()
              if item.is_file() and item.name != "SHA256SUMS.json"}
    assert manifest == actual
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["provenance"]["gate_a_manifest_sha256"] == sha256(FREEZE / "SHA256SUMS.json")
    assert card["provenance"]["canonical_outcome_payload_sha256"] == manifest["canonical_outcome_join.csv"]
    assert card["terminal_disposition"] == "NO_PROMOTION"


def test_complete_denominator_statuses_and_time_slices() -> None:
    rows = list(settlements())
    assert len(rows) == 311_103
    assert Counter(row["settlement_status"] for row in rows) == {
        "NO_BET_GATE_A": 86_994,
        "SETTLED": 207_765,
        "UNAVAILABLE_CANONICAL_OUTCOME": 16_344,
    }
    assert set(Counter((row["variant_id"], row["arm"]) for row in rows).values()) == {2659}
    for name in ("frontier_summary.csv", "annual_summary.csv", "fold_summary.csv", "leave_one_year_out_summary.csv"):
        with (PACKAGE / name).open(newline="", encoding="utf-8") as handle:
            count = sum(1 for _ in csv.DictReader(handle))
        assert count == (117 if name == "frontier_summary.csv" else 819)


def test_once_only_factor_and_issue_level_tax_accounting() -> None:
    buckets: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    rows = list(settlements())
    for row in rows:
        gross = Decimal(row["gross_pre_tax_yuan"])
        product = Decimal(row["final_winning_sp_product"])
        if row["coverage_hit"] == "YES":
            assert gross == (Decimal(2) * FACTOR * product).quantize(Decimal("0.000001"))
        else:
            assert gross == 0
        if row["settlement_status"] == "SETTLED":
            buckets[(row["issue"], row["variant_id"], row["arm"])] += gross
    for row in rows:
        gross = Decimal(row["gross_pre_tax_yuan"])
        expected_tax = gross * Decimal("0.20") if buckets[(row["issue"], row["variant_id"], row["arm"])] >= Decimal("10000") else Decimal(0)
        assert Decimal(row["tax_yuan"]) == expected_tax.quantize(Decimal("0.000001"))
        assert Decimal(row["tax_adjusted_net_yuan"]) == (
            gross - expected_tax - Decimal(row["stake_yuan"])
        ).quantize(Decimal("0.000001"))


def test_no_positive_promotable_row_exists() -> None:
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["terminal_disposition"] == "NO_PROMOTION"
    assert decision["positive_candidate_count"] == 0
    with (PACKAGE / "frontier_summary.csv").open(newline="", encoding="utf-8") as handle:
        active = [row for row in csv.DictReader(handle) if row["stake_yuan"] != "0.000000"]
    assert len(active) == 108
    assert max(Decimal(row["tax_adjusted_roi"]) for row in active) < 0
