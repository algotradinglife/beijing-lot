"""Adversarial regression tests for BJ-UNIFIED-SOURCE-CENSUS-001 R2."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from source_census import census  # noqa: E402


def _remanifest(package: Path) -> None:
    """Attack model: adversary controls both artifact bytes and checksum list."""
    census.rewrite_checksums(package)


def test_data_root_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BEIJING_LOT_DATA_ROOT", raising=False)
    with pytest.raises(census.DataRootError):
        census.resolve_data_root()


def test_strict_forward_requires_both_complete_clocks() -> None:
    assert census.strict_forward_role(source_clock_complete=True, capture_clock_complete=True, mutable=False) == "STRICT_FORWARD_CANDIDATE"
    assert census.strict_forward_role(source_clock_complete=False, capture_clock_complete=True, mutable=True) == "RAW_ONLY"
    assert census.strict_forward_role(source_clock_complete=True, capture_clock_complete=False, mutable=True) == "RAW_ONLY"


def test_required_periods_expose_gap_and_null_anomaly_strata() -> None:
    periods = census.profiling_periods()
    assert "GAP_2025_01_TO_03" in periods
    assert "NULL_OR_UNPARSEABLE_DATE" in periods
    assert "EARLIER_YEAR" in periods


def test_native_intersection_is_exact_not_candidate_mapping() -> None:
    assert census.native_key_intersection([("25001", 1)], [("x", 1)]) == 0
    assert census.canonical_causal_intersection() == "NOT_YET_EVALUATED"


def test_lineage_deduplicates_same_root() -> None:
    rows = census.lineage_decisions([
        {"source_id": "raw", "lineage_root": "raw", "role": "HISTORICAL_PROXY"},
        {"source_id": "derived", "lineage_root": "raw", "role": "EXCLUDE"},
    ])
    assert rows[0]["independent_evidence"] is True
    assert rows[1]["independent_evidence"] is False


def test_clean_fixture_verifies(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    assert census.verify_package(package)["verified"] is True


@pytest.mark.parametrize(
    ("relative", "old", "new", "expected"),
    [
        ("tables/source_role_matrix.csv", "HISTORICAL_PROXY", "RAW_ONLY", "role recomputation mismatch"),
        ("tables/intersection_levels.csv", "NATIVE_KEY_INTERSECTION", "FORGED_INTERSECTION", "semantic hash mismatch: tables/intersection_levels.csv"),
        ("tables/field_profile.csv", "fixture", "forged", "semantic hash mismatch: tables/field_profile.csv"),
        ("tables/coverage_by_period.csv", "fixture", "forged", "semantic hash mismatch: tables/coverage_by_period.csv"),
        ("tables/m_per_issue_distribution.csv", "fixture", "forged", "semantic hash mismatch: tables/m_per_issue_distribution.csv"),
        ("tables/outcome_triplet_profile.csv", "fixture", "forged", "semantic hash mismatch: tables/outcome_triplet_profile.csv"),
    ],
)
def test_remanifested_decision_artifact_tamper_fails(tmp_path: Path, relative: str, old: str, new: str, expected: str) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    path = attacked / relative
    path.write_text(path.read_text(encoding="utf-8").replace(old, new, 1), encoding="utf-8")
    _remanifest(attacked)
    verdict = census.verify_package(attacked)
    assert verdict["verified"] is False
    assert expected in verdict["problems"]


def test_remanifested_source_trace_tamper_fails(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    path = attacked / "tables/source_inventory.csv"
    path.write_text(path.read_text(encoding="utf-8").replace("fixture", "forged", 1), encoding="utf-8")
    _remanifest(attacked)
    verdict = census.verify_package(attacked)
    assert verdict["verified"] is False
    assert "semantic hash mismatch: tables/source_inventory.csv" in verdict["problems"]


def test_remanifested_manifest_issue_tamper_fails(tmp_path: Path) -> None:
    package = census.build_fixture_package(tmp_path / "package")
    attacked = tmp_path / "attacked"
    shutil.copytree(package, attacked)
    path = attacked / "MANIFEST.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["issue"] = 999
    path.write_text(json.dumps(data), encoding="utf-8")
    _remanifest(attacked)
    verdict = census.verify_package(attacked)
    assert verdict["verified"] is False
    assert "manifest issue mismatch" in verdict["problems"]
