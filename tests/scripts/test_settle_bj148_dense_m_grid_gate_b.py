"""Integrity checks for #148's one-shot dense M-grid Gate-B settlement."""
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
SCRIPT = ROOT / "scripts" / "settle_bj148_dense_m_grid_gate_b.py"
PACKAGE = ROOT / "results" / "bj148_gate_b_outcome_settlement_v1"
MANIFEST_SHA256 = "a60389f27f0373ea03300db5edf28aebb3a0e567e47e78ade860094413756467"


def module():
    spec = importlib.util.spec_from_file_location("bj148_gate_b", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def rows_gzip(name: str) -> list[dict[str, str]]:
    with gzip.open(PACKAGE / name, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def rows_csv(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_manifest_and_authorized_input_bindings_are_exact() -> None:
    runner = module()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert manifest == actual
    assert hashlib.sha256((PACKAGE / "SHA256SUMS.json").read_bytes()).hexdigest() == MANIFEST_SHA256
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["contract"] == runner.CONTRACT
    assert card["provenance"]["gate_a_manifest_sha256"] == runner.FREEZE_MANIFEST
    assert card["provenance"]["canonical_outcome_join_sha256"] == runner.OUTCOME_PAYLOAD
    assert card["outcome_completeness"] == {
        "frozen_complete_issue_rows": 348,
        "frozen_available_issue_rows": 343,
        "settled_complete_issue_rows": 187,
        "unavailable_canonical_outcome_issue_rows": 156,
        "source_no_bet_issue_rows": 5,
        "rule": "Complete issue settlement only; unavailable rows have zero executed stake and remain in every M/seed/arm denominator.",
    }
    assert "never `/tmp`" in (PACKAGE / "README.md").read_text(encoding="utf-8")


def test_full_frozen_surface_is_preserved_with_complete_issue_outcome_boundary() -> None:
    runner = module()
    rows = rows_gzip("issue_m_grid_settlement.csv.gz")
    assert len(rows) == 119_364
    assert Counter(row["settlement_status"] for row in rows) == {
        "SETTLED": 64_141,
        "UNAVAILABLE_CANONICAL_OUTCOME": 53_508,
        "NO_BET_GATE_A": 1_715,
    }
    assert Counter(row["sampling_role"] for row in rows) == {
        "PRIMARY_WR_NATURAL_BASELINE": 59_508,
        "SENSITIVITY_WOR_DISTINCT": 59_508,
        "FULL_ECONOMIC_CONTROL": 348,
    }
    assert {int(row["M"]) for row in rows} == set(range(16, 513, 16)) | set(range(576, 1025, 64)) | set(range(1088, 2113, 64)) | {runner.FULL_TICKETS}
    for row in rows:
        frozen = int(row["frozen_planned_draw_count"])
        selected = int(row["candidate_identity_count"])
        assert frozen == selected * int(row["M"])
        if row["settlement_status"] == "SETTLED":
            assert int(row["planned_draw_count"]) == frozen
            assert Decimal(row["planned_stake_yuan"]) == Decimal(frozen) * runner.UNIT_STAKE
        else:
            assert int(row["planned_draw_count"]) == 0
            assert Decimal(row["planned_stake_yuan"]) == 0
        if row["ticket_mechanism"] == "Q_INFORMED_WOR_DISTINCT" and row["settlement_status"] == "SETTLED":
            assert int(row["duplicate_ticket_draw_count"]) == 0
            assert int(row["unique_ticket_draw_count"]) == int(row["planned_draw_count"])
        if row["sampling_role"] == "FULL_ECONOMIC_CONTROL":
            assert row["M"] == str(runner.FULL_TICKETS)
            assert row["seed"] == "NA"


def test_tax_is_per_ticket_and_reconciles_without_aggregate_thresholding() -> None:
    runner = module()
    assert runner.ticket_tax(Decimal("9000")) + runner.ticket_tax(Decimal("9000")) == 0
    assert runner.ticket_tax(Decimal("10000")) == Decimal("2000.00")
    tickets = rows_gzip("winning_ticket_tax_ledger.csv.gz")
    assert tickets
    assert {row["tax_rule"] for row in tickets} == {"20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"}
    for row in tickets:
        per_ticket = Decimal(row["winning_ticket_gross_yuan"])
        expected = runner.ticket_tax(per_ticket).quantize(runner.MONEY_QUANTUM)
        assert Decimal(row["per_ticket_tax_yuan"]) == expected
        assert Decimal(row["tax_yuan"]) == expected * Decimal(row["winning_ticket_count"])
    reconciliation = rows_csv("ticket_tax_reconciliation.csv")
    assert len(reconciliation) == 343
    assert all(abs(Decimal(row["difference_yuan"])) <= runner.MONEY_QUANTUM for row in reconciliation)
    assert sum((Decimal(row["ticket_ledger_tax_yuan"]) for row in reconciliation), Decimal(0)) == sum((Decimal(row["issue_ledger_tax_yuan"]) for row in reconciliation), Decimal(0))


def test_surface_outputs_full_deltas_and_bootstrap_for_every_primary_wr_point() -> None:
    summaries = rows_csv("m_grid_surface_summary.csv")
    assert len(summaries) == 7_546
    assert Counter(row["scope"] for row in summaries) == {"ALL": 343, "YEAR": 2401, "FOLD": 2401, "LEAVE_ONE_YEAR_OUT": 2401}
    all_wr = [row for row in summaries if row["scope"] == "ALL" and row["sampling_role"] == "PRIMARY_WR_NATURAL_BASELINE"]
    assert len(all_wr) == 57 * 3
    assert {row["seed"] for row in all_wr} == {"133001", "133002", "133003"}
    assert all(int(row["settled_issue_count"]) == 187 for row in all_wr)
    deltas = rows_csv("full_control_deltas.csv")
    assert len(deltas) == 7_524
    assert all(row["baseline_role"] == "FULL_ECONOMIC_CONTROL" and row["baseline_M"] == "2187" for row in deltas)
    bootstrap = rows_csv("issue_bootstrap_full_deltas.csv")
    assert len(bootstrap) == 342
    assert {row["metric"] for row in bootstrap} == {"no_tax_roi_delta", "tax_adjusted_roi_delta"}
    assert {row["replicates"] for row in bootstrap} == {"1000"}
    assert all(row["sampling_role"] == "PRIMARY_WR_NATURAL_BASELINE" for row in bootstrap)


def test_decision_reports_no_stable_sweet_spot_and_never_promotes() -> None:
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "DESCRIPTIVE_SURFACE_ONLY"
    assert decision["promotion_authorized"] is False
    assert decision["recommendation"] == "NO_STABLE_SWEET_SPOT"
    assert decision["recommended_M_interval"] == []
