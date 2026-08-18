"""Acceptance and adversarial tests for #251 identity-grain candidate v2."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

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
    competition: str | None = "Premier League",
    home: str | None = "Home FC",
    away: str | None = "Away FC",
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


def remanifest(root: Path) -> None:
    (root / "SHA256SUMS.json").write_text(
        json.dumps(package._checksums(root), sort_keys=True), encoding="utf-8"
    )


def alias_row(*, kind: str = "team", entity: str = "source:s:team:a") -> dict[str, object]:
    return {
        "alias_kind": kind,
        "source_id": "s",
        "source_alias": "A",
        "entity_id": entity,
        "valid_from_utc": "2025-01-01T00:00:00Z",
        "valid_to_utc": "2025-12-31T23:59:59Z",
        "validity_semantics": "OBSERVED_FIRST_LAST_NOT_AUTHORITATIVE",
        "provenance": "observed:test",
    }


def test_issue_slot_is_not_fixture_entity() -> None:
    assert mapping.issue_id("26061") == "bjissue:26061"
    assert mapping.issue_slot_id("26061", 1) == "bjslot:26061:001"
    result = mapping.map_records([record()])
    assert result.slots.loc[0, "issue_slot_id"] == "bjslot:26061:001"
    assert result.slots.loc[0, "fixture_entity_id"] == ""
    assert result.slots.loc[0, "fixture_entity_status"] == "UNRESOLVED_NO_STABLE_KEY"


def test_invalid_issue_slot_is_quarantined() -> None:
    result = mapping.map_records([record(issue_code=None, match_idx=None)])
    assert result.slots.empty
    assert result.ledger.loc[0, "disposition"] == "QUARANTINED"
    assert result.ledger.loc[0, "exception_class"] == "MISSING_ISSUE_SLOT"


def test_duplicate_source_slot_is_removed_from_automatic_outputs() -> None:
    result = mapping.map_records(
        [record(source_key="a"), record(source_key="b")]
    )
    assert result.traces.empty
    assert result.slots.empty
    assert set(result.ledger["exception_class"]) == {"DUPLICATE_SOURCE_SLOT"}
    assert set(result.ledger["disposition"]) == {"QUARANTINED"}


def test_exact_cross_source_labels_create_provenance_bounded_canonical_entities() -> None:
    result = mapping.map_records(
        [
            record(source_id="history", source_key="h-1"),
            record(source_id="live", source_key="l-1"),
        ]
    )
    assert len(result.slots) == 1
    assert set(result.traces["home_team_resolution_status"]) == {"EXACT_CROSS_SOURCE"}
    assert set(result.traces["canonical_home_team_id"]) == {"team:home fc"}


def test_conflicting_cross_source_entity_stays_null_and_is_ledgered() -> None:
    result = mapping.map_records(
        [
            record(source_id="history", source_key="h-1", home="Home FC"),
            record(source_id="live", source_key="l-1", home="Other FC"),
        ]
    )
    assert set(result.traces["home_team_resolution_status"]) == {"UNRESOLVED_CONFLICT"}
    assert set(result.traces["canonical_home_team_id"]) == {""}
    conflict = result.ledger.loc[
        result.ledger["exception_class"].eq("CROSS_SOURCE_ENTITY_ALIAS_CONFLICT")
    ]
    assert conflict["entity_kind"].tolist() == ["home_team"]


def test_missing_entity_never_collapses_to_shared_pseudo_identity() -> None:
    result = mapping.map_records([record(home=None, competition=None)])
    trace = result.traces.iloc[0]
    assert trace["source_home_team_entity_id"] == ""
    assert trace["canonical_home_team_id"] == ""
    assert trace["home_team_resolution_status"] == "UNIDENTIFIED"
    assert set(result.ledger["exception_class"]) == {"MISSING_ENTITY_LABEL"}


def test_fuzzy_candidate_is_never_accepted() -> None:
    ledger = mapping.reject_fuzzy_candidates(
        [
            mapping.FuzzyCandidate(
                source_id="external",
                source_key="x-1",
                candidate_issue_slot_id="bjslot:26061:001",
                confidence=0.99,
                reason="similar names",
            )
        ]
    )
    assert ledger.loc[0, "disposition"] == "MANUAL_REVIEW"


def test_identity_chain_has_exact_three_outcome_cells() -> None:
    result = mapping.map_records([record()])
    profile.validate_identity_tables(result)
    assert result.issues["issue_id"].tolist() == ["bjissue:26061"]
    assert result.plays["play_id"].tolist() == [
        "bjplay:26061:001:BJ_HANDICAP_3WAY"
    ]
    assert set(result.outcome_cells["outcome_code"]) == {"3", "1", "0"}
    assert len(result.outcome_cells) == 3


def test_null_or_invalid_outcome_grain_fails_closed() -> None:
    result = mapping.map_records([record()])
    null_cells = result.outcome_cells.copy()
    null_cells.loc[0, "issue_slot_id"] = None
    with pytest.raises(ValueError, match="non-null"):
        profile.validate_outcome_cells(null_cells)
    missing = result.outcome_cells.iloc[:2].copy()
    with pytest.raises(ValueError, match="missing or invalid"):
        profile.validate_outcome_cells(missing)


def test_alias_contract_is_kind_aware() -> None:
    team = alias_row(kind="team")
    competition = alias_row(kind="competition", entity="source:s:competition:a")
    table = pd.DataFrame([team, competition])
    aliases.validate_alias_intervals(table)
    resolution = aliases.resolve_alias(
        table, "team", "s", "A", "2025-06-01T00:00:00Z"
    )
    assert resolution.entity_id == "source:s:team:a"
    assert resolution.status == "SOURCE_LOCAL"


def test_alias_overlap_within_kind_is_rejected() -> None:
    first = alias_row()
    second = alias_row(entity="source:s:team:b")
    second["valid_from_utc"] = "2025-06-01T00:00:00Z"
    with pytest.raises(ValueError, match="overlapping"):
        aliases.validate_alias_intervals(pd.DataFrame([first, second]))


def test_coverage_separates_slot_and_entity_resolution() -> None:
    result = mapping.map_records(
        [
            record(source_id="history", source_key="h-1", home="Home FC"),
            record(source_id="live", source_key="l-1", home="Other FC"),
        ]
    )
    coverage = profile.coverage_table(result)
    assert coverage["exact_slot_rows"].sum() == 2
    assert coverage["conflicting_entity_fields"].sum() == 2
    assert coverage["unmatched_slot_rows"].sum() == 0


def test_sqlite_profile_uses_only_identity_columns(tmp_path: Path) -> None:
    database = tmp_path / "live.db"
    con = sqlite3.connect(database)
    con.execute(
        "CREATE TABLE matches (match_id TEXT, issue TEXT, match_idx INTEGER, league TEXT, kickoff_ts TEXT, home TEXT, away TEXT, result_code TEXT)"
    )
    con.executemany(
        "INSERT INTO matches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("m1", "26061", 1, "League", "2026-06-01T12:00:00Z", "Home", "Away", "3"),
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
    assert len(result.mapping.traces) == 1
    assert result.coverage["exact_slot_rows"].sum() == 1
    assert result.coverage["unmatched_slot_rows"].sum() == 1
    assert "result_code" not in result.read_columns["live"]


def test_package_semantically_rejects_remanifested_coverage_tamper(tmp_path: Path) -> None:
    result = mapping.map_records([record()])
    coverage = profile.coverage_table(result)
    observed_aliases = profile.derive_temporal_aliases(result.traces)
    built = package.build_package(tmp_path, result, coverage, observed_aliases)
    package.verify_package(built)
    path = built / "tables" / "coverage.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "exact_slot_rows"] = 999
    frame.to_csv(path, index=False)
    remanifest(built)
    with pytest.raises(AssertionError, match="coverage or alias"):
        package.verify_package(built)


def test_package_semantically_rejects_missing_entity_promotion(tmp_path: Path) -> None:
    result = mapping.map_records([record(home=None)])
    built = package.build_package(
        tmp_path,
        result,
        profile.coverage_table(result),
        profile.derive_temporal_aliases(result.traces),
    )
    trace_path = built / "tables" / "source_trace.csv"
    trace = pd.read_csv(trace_path, keep_default_na=False)
    trace.loc[0, "source_home_team_entity_id"] = "team:unidentified"
    trace.to_csv(trace_path, index=False)
    remanifest(built)
    with pytest.raises(AssertionError, match="missing entity"):
        package.verify_package(built)


def test_package_rejects_rehashed_outcome_column(tmp_path: Path) -> None:
    result = mapping.map_records([record()])
    built = package.build_package(
        tmp_path,
        result,
        profile.coverage_table(result),
        profile.derive_temporal_aliases(result.traces),
    )
    trace_path = built / "tables" / "source_trace.csv"
    trace = pd.read_csv(trace_path)
    trace["payout"] = 9999.0
    trace.to_csv(trace_path, index=False)
    remanifest(built)
    with pytest.raises(AssertionError, match="outcome-exposed"):
        package.verify_package(built)
