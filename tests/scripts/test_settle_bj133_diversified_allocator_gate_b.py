"""Integrity checks for #133's one-shot diversified-allocation settlement."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "settle_bj133_diversified_allocator_gate_b.py"
PACKAGE = ROOT / "results" / "bj133_gate_b_outcome_settlement_v2"


def module():
    spec = importlib.util.spec_from_file_location("bj133_gate_b", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def settlement_rows():
    with gzip.open(PACKAGE / "issue_allocator_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_manifest_and_exact_authorized_input_binding() -> None:
    runner = module()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert manifest == actual
    assert hashlib.sha256((PACKAGE / "SHA256SUMS.json").read_bytes()).hexdigest() == "b0fc08d096b81c7345b2f21ed80199fbb2c81dbfb1599237a0ae3113a94af167"
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["contract"] == "BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001"
    assert card["provenance"]["gate_a_manifest_sha256"] == runner.FREEZE_MANIFEST
    assert card["provenance"]["gate_a_v2_wr_manifest_sha256"] == runner.WR_FREEZE_MANIFEST
    assert card["provenance"]["canonical_outcome_join_sha256"] == runner.OUTCOME_PAYLOAD
    assert "/tmp" not in card["sampling"]


def test_ticket_tax_is_per_ticket_and_never_policy_pooled() -> None:
    runner = module()
    assert runner.ticket_tax(Decimal("9000")) + runner.ticket_tax(Decimal("9000")) == Decimal(0)
    assert runner.ticket_tax(Decimal("10001")) == Decimal("2000.20")
    with gzip.open(PACKAGE / "winning_ticket_tax_ledger.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert {row["tax_rule"] for row in rows} == {"20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"}
    for row in rows:
        expected = runner.ticket_tax(Decimal(row["winning_ticket_gross_yuan"])).quantize(Decimal("0.000001"))
        assert Decimal(row["per_ticket_tax_yuan"]) == expected
        assert Decimal(row["tax_yuan"]) == expected * Decimal(row["winning_ticket_count"])
    wr = [row for row in rows if row["ticket_mechanism"] == "Q_INFORMED_WR_DUPLICATE_STAKE"]
    assert wr and any(int(row["winning_ticket_count"]) > 1 for row in wr)


def test_surface_preserves_all_frozen_rows_and_expands_only_seed_axis() -> None:
    rows = list(settlement_rows())
    assert len(rows) == 99_180
    counts = Counter(row["settlement_status"] for row in rows)
    assert counts["NO_BET_GATE_A"] > 0
    assert counts["SETTLED"] > 0
    assert counts["UNAVAILABLE_CANONICAL_OUTCOME"] > 0
    by_plan = Counter((row["config_id"], row["allocator_id"], row["ticket_mechanism"], row["issue_instance"]) for row in rows)
    assert set(by_plan.values()) == {1, 3}
    for row in rows:
        if row["ticket_mechanism"] == "EXACT_K4_FULL":
            assert row["seed"] == "NA"
        else:
            assert row["seed"] in {"133001", "133002", "133003"}
        assert int(row["planned_draw_count"]) == int(row["unique_ticket_draw_count"]) + int(row["duplicate_ticket_draw_count"])
        if row["ticket_mechanism"] == "Q_INFORMED_WOR_DISTINCT":
            assert int(row["duplicate_ticket_draw_count"]) == 0
        if row["settlement_status"] != "SETTLED":
            assert Decimal(row["planned_stake_yuan"]) == 0
    wr = [row for row in rows if row["ticket_mechanism"] == "Q_INFORMED_WR_DUPLICATE_STAKE" and row["settlement_status"] == "SETTLED"]
    assert wr and any(int(row["duplicate_ticket_draw_count"]) > 0 for row in wr)


def test_q_delete_effects_are_matched_and_full_is_capital_normalized_only() -> None:
    with gzip.open(PACKAGE / "matched_effects.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        effects = list(csv.DictReader(handle))
    all_rows = [row for row in effects if row["scope"] == "ALL"]
    primary = [row for row in all_rows if row["comparison_class"] == "PRIMARY_ACTIVE_OVERLAP_CAP"]
    assert len(primary) == 12
    assert {row["effect"] for row in primary} == {"ACTIVE_CAP_WR_MINUS_WR_BASELINE"}
    assert {row["allocator_id"] for row in primary} == {"Q_DELETE_EXPOSURE_CAP_1", "Q_DELETE_EXPOSURE_CAP_2"}
    assert {row["ticket_mechanism"] for row in primary} == {"Q_INFORMED_WR_DUPLICATE_STAKE"}
    assert {row["baseline_ticket_mechanism"] for row in primary} == {"Q_INFORMED_WR_DUPLICATE_STAKE"}
    assert {row["config_id"] for row in primary} == {"PRIMARY_NO_GATE_K4_M64", "PRIMARY_NO_GATE_K4_M128"}
    assert {"WOR_DISTINCT_MINUS_WR_BASELINE", "ACTIVE_CAP_WOR_MINUS_ACTIVE_CAP_WR"} <= {row["effect"] for row in all_rows}
    for row in primary:
        assert int(row["support_issue_count"]) > 0
        assert row["matched_support_rule"].startswith("complete issue/fold")


def test_tax_ledger_reconciles_and_decision_is_not_a_promotion() -> None:
    with (PACKAGE / "ticket_tax_reconciliation.csv").open(newline="", encoding="utf-8") as handle:
        reconciliation = list(csv.DictReader(handle))
    assert len(reconciliation) == 285
    assert all(abs(Decimal(row["difference_yuan"])) <= Decimal("0.000001") for row in reconciliation)
    assert sum(Decimal(row["ticket_ledger_tax_yuan"]) for row in reconciliation) == sum(Decimal(row["issue_ledger_tax_yuan"]) for row in reconciliation)
    with gzip.open(PACKAGE / "winning_ticket_tax_ledger.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        ticket_tax = sum((Decimal(row["tax_yuan"]) for row in csv.DictReader(handle)), Decimal(0))
    assert ticket_tax == sum(Decimal(row["ticket_ledger_tax_yuan"]) for row in reconciliation)
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision == {
        "decision": "NO_PROMOTION",
        "promotion_authorized": False,
        "primary_effect_comparisons": 12,
        "primary_metric_tests_for_bonferroni": 24,
        "strict_ev_candidates": [],
        "strict_independent_ev_required": False,
        "rule": decision["rule"],
    }
    assert "every frozen seed" in decision["rule"]


def test_bootstrap_and_multiple_comparison_diagnostics_cover_both_return_metrics() -> None:
    with (PACKAGE / "issue_bootstrap_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        bootstrap = list(csv.DictReader(handle))
    assert len(bootstrap) == 24
    assert {row["metric"] for row in bootstrap} == {"no_tax_roi_delta", "tax_adjusted_roi_delta"}
    assert {row["replicates"] for row in bootstrap} == {"1000"}
    with (PACKAGE / "multiple_comparison_diagnostics.csv").open(newline="", encoding="utf-8") as handle:
        diagnostics = list(csv.DictReader(handle))
    assert len(diagnostics) == 12
    assert all("tax_bootstrap_ci95_low" in row and "tax_bonferroni_two_sided_p" in row for row in diagnostics)
    assert all(float(row["fwer_alpha"]) == 0.05 for row in diagnostics)
