"""Integrity checks for #151's fixed-candidate dense-M Gate-B replay."""
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
SCRIPT = ROOT / "scripts" / "settle_bj151_candidate_reproduction_gate_b.py"
PACKAGE = ROOT / "results" / "bj151_gate_b_outcome_settlement_v1"
MANIFEST_SHA256 = "7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2"


def module():
    spec = importlib.util.spec_from_file_location("bj151_gate_b", SCRIPT)
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


def test_manifest_and_authorized_bindings_are_exact() -> None:
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
    assert card["provenance"]["bj148_broader_settlement_manifest_sha256"] == runner.BROADER_MANIFEST
    assert not (PACKAGE / "issue_settlement_index.sqlite").exists()
    assert card["outcome_completeness"] == {
        "frozen_complete_issue_rows": 348,
        "frozen_available_issue_rows": 339,
        "settled_complete_issue_rows": 254,
        "unavailable_canonical_outcome_issue_rows": 85,
        "source_no_bet_issue_rows": 9,
        "rule": "Complete issue settlement only; unavailable rows have zero executed stake and remain in every M/seed/arm denominator.",
    }


def test_surface_preserves_all_frozen_candidate_rows() -> None:
    runner = module()
    shared = runner.engine()
    rows = rows_gzip("issue_m_grid_settlement.csv.gz")
    assert len(rows) == 119_364
    assert Counter(row["settlement_status"] for row in rows) == {
        "SETTLED": 87_122,
        "UNAVAILABLE_CANONICAL_OUTCOME": 29_155,
        "NO_BET_GATE_A": 3_087,
    }
    assert Counter(row["sampling_role"] for row in rows) == {
        "PRIMARY_WR_NATURAL_BASELINE": 59_508,
        "SENSITIVITY_WOR_FIXED_CANDIDATE": 59_508,
        "FULL_ECONOMIC_CONTROL": 348,
    }
    assert {int(row["M"]) for row in rows} == set(range(16, 513, 16)) | set(range(576, 1025, 64)) | set(range(1088, 2113, 64)) | {shared.FULL_TICKETS}
    for row in rows:
        frozen = int(row["frozen_planned_draw_count"])
        selected = int(row["candidate_identity_count"])
        assert frozen == selected * int(row["M"])
        if row["settlement_status"] == "SETTLED":
            assert Decimal(row["planned_stake_yuan"]) == Decimal(frozen) * shared.UNIT_STAKE
        else:
            assert int(row["planned_draw_count"]) == 0
            assert Decimal(row["planned_stake_yuan"]) == 0
        if row["ticket_mechanism"] == "Q_INFORMED_WOR_DISTINCT" and row["settlement_status"] == "SETTLED":
            assert int(row["duplicate_ticket_draw_count"]) == 0


def test_m64_wor_exactly_reproduces_the_accepted_137_candidate() -> None:
    rows = rows_csv("m_grid_surface_summary.csv")
    reference = {
        row["seed"]: Decimal(row["no_tax_roi"])
        for row in rows
        if row["scope"] == "ALL"
        and row["sampling_role"] == "SENSITIVITY_WOR_FIXED_CANDIDATE"
        and row["M"] == "64"
    }
    assert reference == {
        "137001": Decimal("0.163755668115"),
        "137002": Decimal("0.117735771069"),
        "137003": Decimal("0.026680342104"),
    }


def test_tax_bootstrap_and_broader_comparator_are_complete() -> None:
    shared = module().engine()
    assert shared.ticket_tax(Decimal("9000")) + shared.ticket_tax(Decimal("9000")) == 0
    assert shared.ticket_tax(Decimal("10000")) == Decimal("2000.00")
    tickets = rows_gzip("winning_ticket_tax_ledger.csv.gz")
    assert tickets
    assert {row["tax_rule"] for row in tickets} == {"20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"}
    reconciliation = rows_csv("ticket_tax_reconciliation.csv")
    assert len(reconciliation) == 343
    assert all(abs(Decimal(row["difference_yuan"])) <= shared.MONEY_QUANTUM for row in reconciliation)
    assert len(rows_csv("full_control_deltas.csv")) == 7_524
    bootstrap = rows_csv("issue_bootstrap_full_deltas.csv")
    assert len(bootstrap) == 342
    assert {row["replicates"] for row in bootstrap} == {"1000"}
    comparison = rows_csv("candidate_vs_broader_pool_m_curve.csv")
    assert len(comparison) == 115
    m64 = {row["sampling_role"]: row for row in comparison if row["M"] == "64"}
    assert m64["PRIMARY_WR_NATURAL_BASELINE"]["broader_seed_count"] == "3"
    assert m64["SENSITIVITY_WOR_FIXED_CANDIDATE"]["broader_sampling_role"] == "SENSITIVITY_WOR_DISTINCT"
    assert m64["SENSITIVITY_WOR_FIXED_CANDIDATE"]["broader_seed_count"] == "3"


def test_decision_is_reproduction_only_and_never_promotes() -> None:
    decision = json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))
    assert decision["decision"] == "FIXED_CANDIDATE_REPRODUCTION_ONLY"
    assert decision["promotion_authorized"] is False
    assert decision["historical_reference"] == "#137 NO_GATE/K4/Q_INFORMED_WOR_DISTINCT/M64"
