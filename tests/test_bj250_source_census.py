"""Regression and adversarial tests for BJ-UNIFIED-SOURCE-CENSUS-001."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_census import census  # noqa: E402


def test_data_root_is_required_and_never_falls_back_to_repo_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEIJING_LOT_DATA_ROOT", raising=False)
    with pytest.raises(census.DataRootError, match="BEIJING_LOT_DATA_ROOT"):
        census.resolve_data_root()


def test_source_role_needs_both_capture_and_source_clock() -> None:
    assert census.strict_forward_role(
        source_clock="2026-05-01T00:00:00Z",
        capture_clock="2026-05-01T00:00:01Z",
        mutable=False,
    ) == "STRICT_FORWARD_CANDIDATE"
    assert census.strict_forward_role(
        source_clock="",
        capture_clock="2026-05-01T00:00:01Z",
        mutable=False,
    ) == "RAW_ONLY"
    assert census.strict_forward_role(
        source_clock="2026-05-01T00:00:00Z",
        capture_clock="",
        mutable=False,
    ) == "RAW_ONLY"


def test_native_key_intersection_never_uses_candidate_mapping() -> None:
    left = [("25001", 1), ("25001", 2)]
    right = [("x", 1), ("x", 2)]
    assert census.native_key_intersection(left, right) == 0
    assert census.canonical_causal_intersection() == "NOT_YET_EVALUATED"


def test_required_profiling_periods_are_explicit_and_non_overlapping() -> None:
    assert census.profiling_periods() == (
        "EARLIER_THAN_2024",
        "CALENDAR_2024",
        "2025_04_TO_2026_04",
        "PROSPECTIVE_2026_05_ONWARD",
    )


def test_p34_scope_filters_the_multimarket_capture_table() -> None:
    assert census.p34_where_clause("bjdc_500_capture") == " WHERE market_key = 'handicap_3way'"
    assert census.p34_where_clause("beidan_xlsm") == ""


def test_role_decision_deduplicates_derivatives_from_raw_lineage() -> None:
    records = [
        {"source_id": "raw", "lineage_root": "raw", "role": "HISTORICAL_PROXY"},
        {"source_id": "derived", "lineage_root": "raw", "role": "HISTORICAL_PROXY"},
    ]
    result = census.lineage_decisions(records)
    assert result[0]["independent_evidence"] is True
    assert result[1]["independent_evidence"] is False
    assert result[1]["dedup_reason"] == "DERIVED_FROM_raw"


def test_remanifested_role_tamper_is_rejected(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    assert census.verify_package(package)["verified"] is True

    tampered = tmp_path / "tampered"
    shutil.copytree(package, tampered)
    registry = tampered / "tables" / "source_role_matrix.csv"
    text = registry.read_text(encoding="utf-8")
    registry.write_text(text.replace("HISTORICAL_PROXY", "STRICT_FORWARD_CANDIDATE", 1), encoding="utf-8")
    census.rewrite_checksums(tampered)

    verdict = census.verify_package(tampered)
    assert verdict["verified"] is False
    assert "role recomputation mismatch" in verdict["problems"]


def test_remanifested_source_trace_tamper_is_rejected(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    tampered = tmp_path / "tampered"
    shutil.copytree(package, tampered)
    source = tampered / "tables" / "source_inventory.csv"
    payload = source.read_text(encoding="utf-8")
    source.write_text(payload.replace("fixture-source", "forged-source"), encoding="utf-8")
    census.rewrite_checksums(tampered)
    verdict = census.verify_package(tampered)
    assert verdict["verified"] is False
    assert "source trace hash mismatch" in verdict["problems"]


def test_manifest_tamper_is_rejected_even_when_rehashed(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    tampered = tmp_path / "tampered"
    shutil.copytree(package, tampered)
    manifest = tampered / "MANIFEST.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["issue"] = 999
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    census.rewrite_checksums(tampered)
    verdict = census.verify_package(tampered)
    assert verdict["verified"] is False
    assert "manifest issue mismatch" in verdict["problems"]
