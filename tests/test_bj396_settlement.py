"""Adversarial tests for the #396 source-bound settlement package."""
from __future__ import annotations
import csv
import json
import os
from pathlib import Path
import shutil
import pandas as pd
import pytest
from src.backfill.parser import MatchRow
from src.bj396_settlement import pipeline

ISSUES = ("25011",)


def _row(issue: str) -> MatchRow:
    return MatchRow(issue=issue, match_idx=1, league="L", kickoff_ts="2025-01-01 01:00:00", home="H", away="A", handicap_line=-1, fthg=2, ftag=1, result_code="1", winning_sp=3.2, avg_eu_home=2.0, avg_eu_draw=3.0, avg_eu_away=4.0)


def _raw(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(pipeline, "TARGET_ISSUES", ISSUES)
    monkeypatch.setattr(pipeline, "_check_target_issues", lambda issues: list(ISSUES))
    raw = tmp_path / "raw"
    pages = raw / "pages"; pages.mkdir(parents=True)
    page = pages / "25011.html"; page.write_bytes(b"fixture")
    digest = pipeline._sha256(page)
    pd.DataFrame([{"issue":"25011","source_url":"https://example/25011","requested_at_utc":"2026-01-01T00:00:00+00:00","received_at_utc":"2026-01-01T00:00:01+00:00","acquisition_result":"SUCCESS","http_status":"200","payload_bytes":"7","payload_sha256":digest,"error_class":"","error_detail":""}]).to_csv(raw / "acquisition_receipts.csv",index=False)
    monkeypatch.setattr(pipeline, "parse_issue_html", lambda html, issue: [_row(issue)])
    return raw


def _package(tmp_path: Path, monkeypatch) -> Path:
    raw = _raw(tmp_path, monkeypatch)
    package = tmp_path / "package"
    pipeline.build_package(raw, package, issues=ISSUES)
    assert pipeline.verify_package(package)["status"] == "PASS"
    return package


def test_build_and_verify(tmp_path, monkeypatch):
    _package(tmp_path, monkeypatch)


@pytest.mark.parametrize("target", ["canonical_settlements.parquet", "raw/pages/25011.html", "raw/acquisition_receipts.csv", "issue_ledger.csv"])
def test_tamper_fails_closed(tmp_path, monkeypatch, target):
    package = _package(tmp_path, monkeypatch)
    path = package / target
    if path.suffix == ".parquet":
        frame = pd.read_parquet(path); frame.loc[0, "winning_sp"] = 9.9; frame.to_parquet(path, index=False)
    else:
        path.write_bytes(path.read_bytes() + b"TAMPER")
    with pytest.raises(pipeline.SettlementError):
        pipeline.verify_package(package)


def test_semantic_settlement_mutation_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    package = _package(tmp_path, monkeypatch)
    table = package / "canonical_settlements.parquet"
    frame = pd.read_parquet(table); frame.loc[0, "winning_sp"] = 9.9; frame.to_parquet(table, index=False)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="semantic replay"):
        pipeline.verify_package(package)


def test_result_identity_mutation_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    package = _package(tmp_path, monkeypatch)
    table = package / "canonical_settlements.parquet"
    frame = pd.read_parquet(table); frame.loc[0, "result_code"] = "3"; frame.to_parquet(table, index=False)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError):
        pipeline.verify_package(package)


def test_strategy_execution_authorization_tamper_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    package = _package(tmp_path, monkeypatch)
    decision_path = package / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["strategy_execution_authorized"] = True
    pipeline._write_json(decision_path, decision)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=decision["disposition"])
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="must not authorize"):
        pipeline.verify_package(package)


def test_issue_ledger_tamper_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    package = _package(tmp_path, monkeypatch)
    ledger_path = package / "issue_ledger.csv"
    ledger = pd.read_csv(ledger_path, dtype=str)
    ledger.loc[0, "included_fixture_count"] = "999999"
    ledger.to_csv(ledger_path, index=False)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="issue ledger"):
        pipeline.verify_package(package)


def test_frozen_nowscore_source_trace_tamper_fails():
    with pytest.raises(pipeline.SettlementError, match="frozen receipt"):
        pipeline._check_v2_nowscore_freeze("25012", b"forged Nowscore source trace")
    with pytest.raises(pipeline.SettlementError, match="frozen receipt"):
        pipeline._check_v2_nowscore_freeze("25011", b"unknown issue")


def test_nowscore_probe_classifies_only_direct_cancel_or_finished_no_native_sp():
    residuals = pd.DataFrame([
        {"issue": "25011", "match_idx": 1, "exclusion_reason": "UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE", "source_row_evidence": "1 L H 0 A -"},
        {"issue": "25011", "match_idx": 2, "exclusion_reason": "UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE", "source_row_evidence": "2 L H 0 A -"},
        {"issue": "25011", "match_idx": 3, "exclusion_reason": "UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE", "source_row_evidence": "3 L H 0 A -"},
    ])
    probes = pd.DataFrame([
        {"issue": "25011", "match_idx": 1, "identity_status": "EXACT_ISSUE_SLOT", "nowscore_status": "closed", "nowscore_status_text": "取消", "nowscore_score": "", "nowscore_result_code": "", "nowscore_sp_url": "https://example/sp/1"},
        {"issue": "25011", "match_idx": 2, "identity_status": "EXACT_ISSUE_SLOT", "nowscore_status": "finished", "nowscore_status_text": "完场", "nowscore_score": "2-1", "nowscore_result_code": "3", "nowscore_sp_url": "https://example/sp/2"},
        {"issue": "25011", "match_idx": 3, "identity_status": "MISSING_OR_AMBIGUOUS", "nowscore_status": "finished", "nowscore_status_text": "完场", "nowscore_score": "2-1", "nowscore_result_code": "3", "nowscore_sp_url": ""},
    ])
    actual = pipeline.classify_residuals_with_nowscore(residuals, probes)
    assert actual["exclusion_reason"].tolist() == [
        "POSTPONED_OR_CANCELLED",
        "NEVER_SETTLED_OFFICIAL_NO_SP",
        "UNRESOLVED_NATIVE_SETTLEMENT_GAP",
    ]
    assert actual.loc[1, "nowscore_result_code"] == "3"


def test_v2_residual_label_tamper_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    raw = _raw(tmp_path, monkeypatch)
    incomplete = MatchRow(issue="25011", match_idx=2, league="L", kickoff_ts="2025-01-01 01:00:00", home="H", away="A", handicap_line=0, fthg=None, ftag=None, result_code=None, winning_sp=None, avg_eu_home=2.0, avg_eu_draw=3.0, avg_eu_away=4.0)
    monkeypatch.setattr(pipeline, "parse_issue_html", lambda html, issue: [_row(issue), incomplete])
    monkeypatch.setattr(pipeline, "_raw_row_text", lambda *args: "fixture -")
    baseline = tmp_path / "baseline"
    pipeline.build_package(raw, baseline, issues=ISSUES)
    probe_root = tmp_path / "nowscore"; probe_root.mkdir(); (probe_root / "25011.html").write_text("snapshot", encoding="utf-8")
    probes = pd.DataFrame([{
        "issue": "25011", "match_idx": 2, "nowscore_issue_url": "https://example/issue", "nowscore_payload_sha256": "x" * 64, "nowscore_payload_bytes": 8,
        "identity_status": "EXACT_ISSUE_SLOT", "provider_match_id": "p", "nowscore_status": "finished", "nowscore_status_text": "完场", "nowscore_score": "1-0", "nowscore_result_code": "3", "nowscore_handicap_line": "0", "nowscore_home": "H", "nowscore_away": "A", "nowscore_sp_url": "https://example/sp", "nowscore_raw_row_hash": "r",
    }])
    monkeypatch.setattr(pipeline, "_nowscore_probe_ledger", lambda *_args: probes)
    package = tmp_path / "v2"
    pipeline.extend_package_amendment_v2(baseline, probe_root, package)
    assert pipeline.verify_package(package)["disposition"] == pipeline.DISPOSITION_READY
    path = package / "residual_disposition_v2.csv"
    frame = pd.read_csv(path, dtype=str); frame.loc[0, "exclusion_reason"] = "POSTPONED_OR_CANCELLED"; frame.to_csv(path, index=False)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    manifest["contract"] = pipeline.CONTRACT_AMENDMENT_V2
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="residual disposition"):
        pipeline.verify_package(package)


def test_v2_issue_ledger_keeps_admissibly_partial_issues_downstream_eligible():
    settlements = pd.DataFrame([
        {"issue": "25011", "match_idx": 1, "kickoff_ts": "2025-01-01 01:00:00", "settlement_availability_ts": "2026-01-01T00:00:00+00:00"},
        {"issue": "25012", "match_idx": 1, "kickoff_ts": "2025-01-02 01:00:00", "settlement_availability_ts": "2026-01-02T00:00:00+00:00"},
    ])
    exclusions = pd.DataFrame([
        {"issue": "25011", "match_idx": 2, "exclusion_reason": "POSTPONED_OR_CANCELLED"},
    ])
    ledger = pipeline._v2_issue_ledger(settlements, exclusions, ["25011", "25012"])
    assert ledger["issue"].tolist() == ["25011", "25012"]
    assert ledger["downstream_eligible"].tolist() == [True, True]
    assert ledger["inclusion_status"].tolist() == [
        "INCLUDED_WITH_ADMISSIBLE_FIXTURE_EXCLUSIONS",
        "INCLUDED",
    ]
    assert ledger.loc[0, "reason"] == "SEE_RESIDUAL_DISPOSITION_V2"


def test_v2_source_probe_receipts_fail_closed_on_semantic_rewrite():
    receipts = pipeline._v2_source_probe_receipts()
    assert set(receipts["source_id"]) == {
        "500_kaijiang",
        "beidan_live_settlements",
        "beidan_xlsm_bj268",
        "official_500_settlements",
        "nowscore_issue_provider",
    }
    assert receipts["exact_23_key_hit_count"].astype(int).tolist() == [23, 0, 7, 0, 23]
    attacked = receipts.copy()
    attacked.loc[0, "admissible_use"] = "FABRICATED_PAYOUT_SOURCE"
    with pytest.raises(pipeline.SettlementError, match="source-probe receipt"):
        pipeline._validate_v2_source_probe_receipts(attacked)


def test_v2_500_receipt_anchor_rejects_rewritten_raw_receipt(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    receipt = raw / "acquisition_receipts.csv"
    receipt.write_text("rewritten source receipt\n", encoding="utf-8")
    with pytest.raises(pipeline.SettlementError, match="frozen 500 acquisition receipt"):
        pipeline._validate_v2_500_receipt_anchor(pipeline._v2_source_probe_receipts(), raw)


def test_v2_xlsm_hits_are_identity_only():
    ledger = pipeline._validate_v2_xlsm_identity_probe_ledger(
        pipeline._v2_xlsm_identity_probe_ledger()
    )
    assert len(ledger) == 7
    assert ledger["native_winning_sp_admissible"].astype(str).str.lower().eq("false").all()


@pytest.mark.filterwarnings("ignore:Parsing dates involving a day of month without a year specified:DeprecationWarning")
def test_v2_500_receipt_rewrite_with_manifest_rewrite_fails_closed(tmp_path):
    package = tmp_path / "package"
    source = Path(__file__).resolve().parents[1] / "results/bj396_2025_settlement_backfill_v2"
    shutil.copytree(source, package)
    receipt_path = package / "raw/acquisition_receipts.csv"
    with receipt_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = list(rows[0])
    rows[0]["requested_at_utc"] = "1999-01-01T00:00:00+00:00"
    with receipt_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    manifest["contract"] = pipeline.CONTRACT_AMENDMENT_V2
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="frozen 500 acquisition receipt"):
        pipeline.verify_package(package)


def test_v2_source_probe_receipt_tamper_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    raw = _raw(tmp_path, monkeypatch)
    incomplete = MatchRow(issue="25011", match_idx=2, league="L", kickoff_ts="2025-01-01 01:00:00", home="H", away="A", handicap_line=0, fthg=None, ftag=None, result_code=None, winning_sp=None, avg_eu_home=2.0, avg_eu_draw=3.0, avg_eu_away=4.0)
    monkeypatch.setattr(pipeline, "parse_issue_html", lambda html, issue: [_row(issue), incomplete])
    monkeypatch.setattr(pipeline, "_raw_row_text", lambda *args: "fixture -")
    baseline = tmp_path / "baseline"; pipeline.build_package(raw, baseline, issues=ISSUES)
    probe_root = tmp_path / "nowscore"; probe_root.mkdir(); (probe_root / "25011.html").write_text("snapshot", encoding="utf-8")
    probes = pd.DataFrame([{
        "issue": "25011", "match_idx": 2, "nowscore_issue_url": "https://example/issue", "nowscore_captured_at_utc": "2026-01-01T00:00:00+00:00", "nowscore_payload_sha256": "x" * 64, "nowscore_payload_bytes": 8,
        "identity_status": "EXACT_ISSUE_SLOT", "provider_match_id": "p", "nowscore_status": "finished", "nowscore_status_text": "完场", "nowscore_score": "1-0", "nowscore_result_code": "3", "nowscore_handicap_line": "0", "nowscore_home": "H", "nowscore_away": "A", "nowscore_sp_url": "https://example/sp", "nowscore_raw_row_hash": "r",
    }])
    monkeypatch.setattr(pipeline, "_nowscore_probe_ledger", lambda *_args: probes)
    package = tmp_path / "v2"; pipeline.extend_package_amendment_v2(baseline, probe_root, package)
    path = package / "source_probe_receipts_v2.csv"
    frame = pd.read_csv(path, dtype=str); frame.loc[0, "exact_23_key_hit_count"] = "999"; frame.to_csv(path, index=False)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    manifest["contract"] = pipeline.CONTRACT_AMENDMENT_V2
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="source-probe receipt"):
        pipeline.verify_package(package)


def test_v2_nowscore_source_trace_tamper_fails_even_if_manifest_rewritten(tmp_path, monkeypatch):
    raw = _raw(tmp_path, monkeypatch)
    incomplete = MatchRow(issue="25011", match_idx=2, league="L", kickoff_ts="2025-01-01 01:00:00", home="H", away="A", handicap_line=0, fthg=None, ftag=None, result_code=None, winning_sp=None, avg_eu_home=2.0, avg_eu_draw=3.0, avg_eu_away=4.0)
    monkeypatch.setattr(pipeline, "parse_issue_html", lambda html, issue: [_row(issue), incomplete])
    monkeypatch.setattr(pipeline, "_raw_row_text", lambda *args: "fixture -")
    baseline = tmp_path / "baseline"; pipeline.build_package(raw, baseline, issues=ISSUES)
    probe_root = tmp_path / "nowscore"; probe_root.mkdir(); (probe_root / "25011.html").write_text("snapshot", encoding="utf-8")
    probes = pd.DataFrame([{
        "issue": "25011", "match_idx": 2, "nowscore_issue_url": "https://example/issue", "nowscore_captured_at_utc": "2026-01-01T00:00:00+00:00", "nowscore_payload_sha256": "x" * 64, "nowscore_payload_bytes": 8,
        "identity_status": "EXACT_ISSUE_SLOT", "provider_match_id": "p", "nowscore_status": "finished", "nowscore_status_text": "完场", "nowscore_score": "1-0", "nowscore_result_code": "3", "nowscore_handicap_line": "0", "nowscore_home": "H", "nowscore_away": "A", "nowscore_sp_url": "https://example/sp", "nowscore_raw_row_hash": "r",
    }])
    monkeypatch.setattr(pipeline, "_nowscore_probe_ledger", lambda *_args: probes)
    package = tmp_path / "v2"; pipeline.extend_package_amendment_v2(baseline, probe_root, package)
    path = package / "nowscore_probe_ledger.csv"
    frame = pd.read_csv(path, dtype=str); frame.loc[0, "nowscore_payload_sha256"] = "f" * 64; frame.to_csv(path, index=False)
    manifest = pipeline._manifest(package, implementation_sha=pipeline._sha256(Path(pipeline.__file__)), disposition=pipeline.DISPOSITION_READY)
    manifest["contract"] = pipeline.CONTRACT_AMENDMENT_V2
    pipeline._write_json(package / "MANIFEST.json", manifest)
    with pytest.raises(pipeline.SettlementError, match="probe ledger"):
        pipeline.verify_package(package)


def test_v2_verifier_is_invariant_to_checkout_mtime(tmp_path):
    """Fresh Git checkouts assign new mtimes; source provenance must remain
    content/receipt-bound and must not require mutating tracked raw files."""
    source = (
        Path(__file__).resolve().parents[1]
        / "results/bj396_2025_settlement_backfill_v2"
    )
    package = tmp_path / "v2"
    shutil.copytree(source, package)
    for ordinal, page in enumerate(
        sorted((package / "raw/nowscore_issue_pages").glob("*.html"))
    ):
        timestamp = 1_700_000_000 + ordinal
        os.utime(page, (timestamp, timestamp))
    assert pipeline.verify_package(package)["status"] == "PASS"
