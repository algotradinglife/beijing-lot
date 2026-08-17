"""Acceptance and adversarial tests for #251 canonical identity candidate."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
import json

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from canonical_identity import aliases, mapping, package, profile  # noqa: E402


def record(
    *,
    source_id: str = "live",
    source_key: str = "m-1",
    issue_code: str | None = "26061",
    match_idx: int | None = 1,
    competition: str = "Premier League",
    home: str = "Home FC",
    away: str = "Away FC",
    kickoff_at_utc: str | None = "2026-06-01T12:00:00Z",
    causal_grade: str = "STRICT_CAUSAL",
) -> mapping.IdentityRecord:
    return mapping.IdentityRecord(
        source_id=source_id,
        source_key=source_key,
        issue_code=issue_code,
        match_idx=match_idx,
        competition_alias=competition,
        home_alias=home,
        away_alias=away,
        kickoff_at_utc=kickoff_at_utc,
        causal_grade=causal_grade,
    )


def test_fixture_identifier_is_stable_and_outcome_unexposed() -> None:
    assert mapping.canonical_fixture_id("26061", 1) == "bjfi:26061:001"
    assert mapping.canonical_fixture_id("26061", 1) == mapping.canonical_fixture_id("26061", 1)
    assert "result" not in mapping.canonical_fixture_id.__annotations__


def test_invalid_issue_slot_is_quarantined_not_silently_matched() -> None:
    result = mapping.map_records([record(issue_code=None, match_idx=None)])
    assert result.fixtures.empty
    assert result.ledger.loc[0, "disposition"] == "QUARANTINED"
    assert result.ledger.loc[0, "exception_class"] == "MISSING_CANONICAL_SLOT"


def test_exact_cross_source_slot_mapping_is_deterministic() -> None:
    result = mapping.map_records(
        [record(source_id="historical", source_key="h-7"), record(source_id="live", source_key="l-9")]
    )
    assert result.fixtures["fixture_id"].tolist() == ["bjfi:26061:001"]
    assert result.traces["fixture_id"].tolist() == ["bjfi:26061:001", "bjfi:26061:001"]
    assert result.ledger.empty


def test_conflicting_cross_source_alias_is_ledgered_without_losing_exact_fixture_slot() -> None:
    result = mapping.map_records(
        [record(source_id="historical", home="Home FC"), record(source_id="live", home="Other FC")]
    )
    assert "CROSS_SOURCE_ENTITY_ALIAS_CONFLICT" in result.ledger["exception_class"].tolist()
    assert set(result.traces["identity_status"]) == {"ALIAS"}


def test_fuzzy_candidate_is_never_accepted() -> None:
    candidate = mapping.FuzzyCandidate(
        source_id="external",
        source_key="x-1",
        candidate_fixture_id="bjfi:26061:001",
        confidence=0.99,
        reason="similar names",
    )
    ledger = mapping.reject_fuzzy_candidates([candidate])
    assert ledger.loc[0, "disposition"] == "MANUAL_REVIEW"
    assert ledger.loc[0, "identity_status"] == "UNIDENTIFIED"


def test_temporal_alias_resolver_requires_one_active_provenanced_alias() -> None:
    table = pd.DataFrame(
        [
            {
                "source_id": "s",
                "source_alias": "Old Name",
                "canonical_id": "team:alpha",
                "valid_from_utc": "2025-01-01T00:00:00Z",
                "valid_to_utc": "2025-12-31T23:59:59Z",
                "provenance": "manual:v1",
            }
        ]
    )
    assert aliases.resolve_alias(table, "s", "Old Name", "2025-06-01T00:00:00Z").canonical_id == "team:alpha"
    assert aliases.resolve_alias(table, "s", "Old Name", "2026-01-01T00:00:00Z").status == "UNIDENTIFIED"


def test_temporal_alias_overlap_is_rejected() -> None:
    table = pd.DataFrame(
        [
            {"source_id": "s", "source_alias": "A", "canonical_id": "team:a", "valid_from_utc": "2025-01-01T00:00:00Z", "valid_to_utc": None, "provenance": "p1"},
            {"source_id": "s", "source_alias": "A", "canonical_id": "team:b", "valid_from_utc": "2025-06-01T00:00:00Z", "valid_to_utc": None, "provenance": "p2"},
        ]
    )
    with pytest.raises(ValueError, match="overlapping"):
        aliases.validate_alias_intervals(table)


def test_fixture_and_three_outcome_cells_have_unique_grains() -> None:
    cells = pd.DataFrame(
        [
            {"issue_code": "26061", "match_idx": 1, "outcome_code": "3"},
            {"issue_code": "26061", "match_idx": 1, "outcome_code": "1"},
            {"issue_code": "26061", "match_idx": 1, "outcome_code": "0"},
        ]
    )
    profile.validate_fixture_outcome_cells(cells)
    with pytest.raises(ValueError, match="duplicate"):
        profile.validate_fixture_outcome_cells(pd.concat([cells, cells.iloc[[0]]], ignore_index=True))
    with pytest.raises(ValueError, match="missing"):
        profile.validate_fixture_outcome_cells(cells.iloc[:2])


def test_sqlite_profile_uses_only_identity_columns_and_reports_coverage(tmp_path: Path) -> None:
    database = tmp_path / "live.db"
    con = sqlite3.connect(database)
    con.execute(
        "CREATE TABLE matches (match_id TEXT, issue TEXT, match_idx INTEGER, league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, result_code TEXT)"
    )
    con.executemany(
        "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("m1", "26061", 1, "League", "2026-06-01T12:00:00Z", "Home", "Away", "3"),
            ("m3", "26061", 2, "Other League", "2026-06-03T12:00:00Z", "H3", "A3", "0"),
            ("m2", None, None, "League", "2026-06-02T12:00:00Z", "H2", "A2", "1"),
        ],
    )
    con.commit()
    con.close()
    specification = profile.SourceSpec(
        source_id="live",
        sqlite_path=database,
        table="matches",
        key_column="match_id",
        issue_column="issue",
        match_idx_column="match_idx",
        competition_column="league",
        home_column="home",
        away_column="away",
        kickoff_column="kickoff_ts",
        causal_grade="STRICT_CAUSAL",
    )
    result = profile.profile_sources([specification])
    # Only canonicalized rows enter the automatic source trace; non-canonical
    # input remains visible in the exception ledger rather than disappearing.
    assert len(result.mapping.traces) == 2
    assert len(result.mapping.ledger) == 1
    assert result.coverage["valid_fixture_rows"].sum() == 2
    assert result.coverage["unmatched_rows"].sum() == 1
    assert "result_code" not in result.read_columns["live"]


def test_package_verifier_detects_tampered_settlement_free_trace(tmp_path: Path) -> None:
    result = mapping.map_records([record()])
    built = package.build_package(tmp_path, result, pd.DataFrame(), pd.DataFrame())
    package.verify_package(built)
    trace_path = built / "tables" / "source_trace.csv"
    trace_path.write_text(trace_path.read_text(encoding="utf-8").replace("m-1", "forged"), encoding="utf-8")
    with pytest.raises(AssertionError, match="hash"):
        package.verify_package(built)


def test_trusted_anchor_rejects_rehashed_manifest_and_trace_forgery(tmp_path: Path) -> None:
    result = mapping.map_records([record()])
    built = package.build_package(tmp_path, result, pd.DataFrame(), pd.DataFrame())
    trusted_anchor = package.checksums_anchor(built)

    manifest_path = built / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["fixture_count"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    trace_path = built / "tables" / "source_trace.csv"
    trace_path.write_text(trace_path.read_text(encoding="utf-8").replace("m-1", "forged"), encoding="utf-8")
    (built / "SHA256SUMS.json").write_text(json.dumps(package._checksums(built), sort_keys=True), encoding="utf-8")

    with pytest.raises(AssertionError, match="trusted anchor"):
        package.verify_package(built, trusted_anchor=trusted_anchor)


def test_verifier_rejects_rehashed_payout_column_in_trace(tmp_path: Path) -> None:
    result = mapping.map_records([record()])
    built = package.build_package(tmp_path, result, pd.DataFrame(), pd.DataFrame())
    trace_path = built / "tables" / "source_trace.csv"
    trace = pd.read_csv(trace_path)
    trace["payout"] = 9999.0
    trace.to_csv(trace_path, index=False)
    (built / "SHA256SUMS.json").write_text(json.dumps(package._checksums(built), sort_keys=True), encoding="utf-8")
    with pytest.raises(AssertionError, match="outcome-exposed"):
        package.verify_package(built)
