"""Read-only integrity checks for the #145 Gate-B settlement package."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj145_gate_b_outcome_settlement_v1"
GATE_A = ROOT / "results" / "bj145_gate_a_preoutcome_v8"


def _runner():
    path = PACKAGE / "settlement_runner.py"
    spec = importlib.util.spec_from_file_location("bj145_package_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _csv_rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_manifest_is_complete_and_sqlite_is_not_published():
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in PACKAGE.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert declared == actual
    assert not list(PACKAGE.glob("*.sqlite"))
    assert not list(PACKAGE.glob("*.db"))


def test_surface_denominators_tax_and_decision():
    card = json.loads((PACKAGE / "settlement_card.json").read_text(encoding="utf-8"))
    assert card["surface"] == {
        "issue_rows": 1006416,
        "configuration_count": 2892,
        "summary_rows": 63624,
        "full_control_delta_rows": 63360,
        "bootstrap_rows": 5760,
        "holm_rows": 2880,
        "tax_reconciliation_rows": 2892,
    }
    assert json.loads((PACKAGE / "decision.json").read_text(encoding="utf-8"))["promotion_authorized"] is False
    assert "mechanism_surface_median.svg" in (PACKAGE / "settlement_card.json").read_text(encoding="utf-8")
    assert "descriptive surface" in (PACKAGE / "mechanism_surface_median.svg").read_text(encoding="utf-8")
    tax = _csv_rows(PACKAGE / "tax_reconciliation.csv")
    assert len(tax) == 2892
    assert {row["status"] for row in tax} == {"PASS"}
    assert len(_csv_rows(PACKAGE / "issue_bootstrap.csv")) == 5760
    assert len(_csv_rows(PACKAGE / "multiple_comparison.csv")) == 2880


def test_streamed_payload_row_denominators():
    with gzip.open(PACKAGE / "issue_allocation_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        rows = sum(1 for _ in handle) - 1
    assert rows == 1006416
    with gzip.open(PACKAGE / "winning_ticket_tax_ledger.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        ledger_rows = sum(1 for _ in handle) - 1
    assert ledger_rows == 626782
    with gzip.open(PACKAGE / "outcome_code_frequency.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        code_rows = sum(1 for _ in handle) - 1
    assert code_rows == 1472028


def test_native_allocator_matches_gate_a_reference_for_small_vectors():
    runner = _runner()
    engine, binding, _ = runner.load_engine()
    allocator = engine
    weights = allocator.golden_weights(runner.FULL_TICKETS)
    truth = 137
    signature = "bj145-test-signature"
    m_grid = (16, 32, 64)
    cases = (
        ("WR_DUPLICATE_STAKE", None, "137001", m_grid),
        ("WOR_DISTINCT", None, "137002", m_grid),
        ("RESIDUAL_SYSTEMATIC", None, "NA", m_grid),
        ("CAPPED_REPEAT", 2, "NA", m_grid),
        ("FULL_ENUMERATED", None, "NA", (runner.FULL_TICKETS,)),
    )
    assert binding["module_sha256"] == hashlib.sha256((GATE_A / "bj145_allocation_engine.py").read_bytes()).hexdigest()
    for mechanism, cap, seed, case_grid in cases:
        native = runner.profile_metrics(allocator, weights, truth, seed, signature, mechanism, cap, case_grid)
        for m in case_grid:
            counts = allocator.allocate(mechanism, weights, m, seed=seed, identity_signature=signature, cap=cap)
            expected = (sum(counts[truth] for _ in [0]), sum(value > 0 for value in counts), m - sum(value > 0 for value in counts), sum(value > 1 for value in counts))
            assert native[m] == expected
