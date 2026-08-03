from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj159_gate_b_outcome_settlement_v2r1"
SOURCE = ROOT / "results" / "bj159_gate_b_outcome_settlement_v2"
EXPECTED_MANIFEST = "546d2a0aa026ea8f8bdaccad0cb9b7079d3e690e8db83c09675d62f0eb6077ef"
EXPECTED_CONTENT = "a33c802d98b00172a2cd84d32b7085a4900508f3b9c420afb30ecea6168b92ea"
V2_MANIFEST = "ad724693f7fbee8a120030cb4ace852a4cf69011bf98b39b41ae427bcfbd0917"
V2_CONTENT = "42f8960c9754efb3033cb6da54f38b759da3cb64d7272f195845aeabb51b1b08"


def load_recovery():
    path = ROOT / "scripts" / "recover_bj159_gate_b_v2r1.py"
    spec = importlib.util.spec_from_file_location("bj159_recovery", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def issue_row(**overrides):
    row = {
        "issue": "x", "fold": "OOS", "year": "2020", "issue_instance": "x@OOS", "n": "2",
        "M": "32", "nominal_M": "32", "effective_M": "9", "seed": "137001", "saturation_status": "PARTIAL_WOR",
        "selection_status": "AVAILABLE", "planned_identity_count": "1", "settled_identity_count": "1",
        "unavailable_identity_count": "0", "planned_draw_count": "5", "executed_draw_count": "5",
        "planned_stake_yuan": "10.000000", "stake_yuan": "10.000000", "full_control_stake_yuan": "10.000000",
        "unique_ticket_count": "5", "duplicate_ticket_count": "0", "hit_identity_count": "0", "winning_ticket_count": "0",
        "coverage_hit": "NO", "gross_pre_tax_yuan": "0.000000", "taxable_winning_ticket_count": "0",
        "tax_yuan": "0.000000", "after_tax_gross_yuan": "0.000000", "pre_tax_net_yuan": "-10.000000",
        "tax_adjusted_net_yuan": "-10.000000", "gm_expected_sp_mean": "0.5", "expected_sp_product_q_mean": "1.0",
        "actual_winning_sp_product_mean": "", "first_kickoff_ts": "2020-01-01T00:00:00",
    }
    row.update(overrides)
    return row


def test_recovery_manifest_and_inode_independent_ledger_copies():
    assert sha256(PACKAGE / "SHA256SUMS.json") == EXPECTED_MANIFEST
    assert sha256(PACKAGE / "CONTENT_IDENTITY.json") == EXPECTED_CONTENT
    declared = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {p.name: sha256(p) for p in PACKAGE.iterdir() if p.is_file() and p.name != "SHA256SUMS.json"}
    assert declared == actual
    binding = json.loads((PACKAGE / "source_v2_binding.json").read_text(encoding="utf-8"))
    assert binding["source_manifest_sha256"] == V2_MANIFEST
    assert binding["source_content_identity_sha256"] == V2_CONTENT
    for name in ("identity_settlement.csv.gz", "issue_settlement.csv.gz", "winning_ticket_tax_ledger.csv.gz"):
        assert (PACKAGE / name).read_bytes() == (SOURCE / name).read_bytes()
        assert os.stat(PACKAGE / name).st_ino != os.stat(SOURCE / name).st_ino


def test_signed_issue_exclusion_uses_net_and_actual_stake():
    module = load_recovery()
    rows = [
        issue_row(issue_instance="gross-winner", year="2020", stake_yuan="10", gross_pre_tax_yuan="1000", pre_tax_net_yuan="-100", tax_adjusted_net_yuan="-120"),
        issue_row(issue_instance="less-negative", year="2021", stake_yuan="20", gross_pre_tax_yuan="10", pre_tax_net_yuan="-5", tax_adjusted_net_yuan="-8"),
    ]
    issue, contribution = module.largest_group(module.contribution_groups(rows, "issue_instance"))
    assert issue == "less-negative"
    assert contribution["stake"] == module.Decimal("20")
    assert contribution["pre"] == module.Decimal("-5")
    assert module.exclusion_roi(module.Decimal("-105"), module.Decimal("30"), contribution) == "-10.000000000000"
    assert module.exclusion_tax_roi(module.Decimal("-128"), module.Decimal("30"), contribution) == "-12.000000000000"


def test_summary_has_year_controls_drawdown_and_separate_support_streaks():
    module = load_recovery()
    rows = [
        issue_row(issue_instance="z-no-bet", selection_status="NO_BET_NO_IDENTITY", settled_identity_count="0", planned_identity_count="0", planned_draw_count="0", executed_draw_count="0", planned_stake_yuan="0", stake_yuan="0", full_control_stake_yuan="0", unique_ticket_count="0", year="2020", coverage_hit="NO", first_kickoff_ts="2020-01-01T00:00:00", pre_tax_net_yuan="0", tax_adjusted_net_yuan="0"),
        issue_row(issue_instance="a-miss", year="2020", first_kickoff_ts="2020-01-02T00:00:00", pre_tax_net_yuan="-10", tax_adjusted_net_yuan="-12"),
        issue_row(issue_instance="b-hit", year="2021", first_kickoff_ts="2021-01-01T00:00:00", coverage_hit="YES", hit_identity_count="1", winning_ticket_count="1", gross_pre_tax_yuan="15", after_tax_gross_yuan="15", pre_tax_net_yuan="5", tax_adjusted_net_yuan="3"),
        issue_row(issue_instance="c-miss", year="2021", first_kickoff_ts="2021-01-02T00:00:00", pre_tax_net_yuan="-10", tax_adjusted_net_yuan="-11"),
    ]
    summary = module.summary_rows(rows, "ALL", "ALL")
    assert summary["largest_issue"] == "b-hit"
    assert summary["largest_year"] == "2021"
    assert summary["ex_largest_issue_no_tax_roi"] == "-1.000000000000"
    assert summary["ex_largest_year_no_tax_roi"] == "-1.000000000000"
    assert summary["max_drawdown_no_tax_yuan"] == "15.000000"
    assert summary["max_drawdown_tax_adjusted_yuan"] == "20.000000"
    assert summary["longest_frozen_calendar_miss_streak"] == 2
    assert summary["longest_executed_miss_streak"] == 1


def test_research_wiki_and_external_report_bind_final_package_hashes():
    report = ROOT / "docs" / "research" / "bj159_selected_wor_cross_n_gate_b_v2r1_2026-08-03.md"
    wiki = ROOT / "docs" / "research-notes" / "Research-Wiki.md"
    assert report.is_file()
    assert wiki.is_file()
    text = report.read_text(encoding="utf-8") + wiki.read_text(encoding="utf-8")
    assert EXPECTED_MANIFEST in text
    assert EXPECTED_CONTENT in text
