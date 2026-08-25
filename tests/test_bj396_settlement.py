"""Adversarial tests for the #396 source-bound settlement package."""
from __future__ import annotations
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
