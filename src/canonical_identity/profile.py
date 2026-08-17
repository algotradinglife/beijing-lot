"""Read-only source profiling and stratified #251 identity evidence."""

from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3
from pathlib import Path

import pandas as pd

from . import mapping


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    sqlite_path: Path
    table: str
    key_column: str
    issue_column: str
    match_idx_column: str
    competition_column: str
    home_column: str
    away_column: str
    kickoff_column: str
    causal_grade: str


@dataclass
class ProfileResult:
    mapping: mapping.MappingResult
    coverage: pd.DataFrame
    read_columns: dict[str, tuple[str, ...]]


def _identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        raise ValueError(f"unsafe SQLite identifier: {value!r}")
    return f'"{value}"'


def _records(specification: SourceSpec) -> tuple[list[mapping.IdentityRecord], tuple[str, ...]]:
    if not specification.sqlite_path.is_file():
        raise FileNotFoundError(specification.sqlite_path)
    fields = (
        specification.key_column,
        specification.issue_column,
        specification.match_idx_column,
        specification.competition_column,
        specification.home_column,
        specification.away_column,
        specification.kickoff_column,
    )
    if len(set(fields)) != len(fields):
        raise ValueError("identity source columns must be distinct")
    connection = sqlite3.connect(f"file:{specification.sqlite_path}?mode=ro", uri=True)
    try:
        available = {row[1] for row in connection.execute(f"PRAGMA table_info({_identifier(specification.table)})")}
        missing = set(fields) - available
        if missing:
            raise ValueError(f"{specification.source_id} missing identity columns: {sorted(missing)}")
        query = "SELECT " + ", ".join(_identifier(field) for field in fields) + f" FROM {_identifier(specification.table)}"
        frame = pd.read_sql_query(query, connection)
    finally:
        connection.close()
    result = [
        mapping.IdentityRecord(
            source_id=specification.source_id,
            source_key=str(row[specification.key_column]),
            issue_code=None if pd.isna(row[specification.issue_column]) else str(row[specification.issue_column]),
            match_idx=None if pd.isna(row[specification.match_idx_column]) else int(row[specification.match_idx_column]),
            competition_alias=None if pd.isna(row[specification.competition_column]) else str(row[specification.competition_column]),
            home_alias=None if pd.isna(row[specification.home_column]) else str(row[specification.home_column]),
            away_alias=None if pd.isna(row[specification.away_column]) else str(row[specification.away_column]),
            kickoff_at_utc=None if pd.isna(row[specification.kickoff_column]) else str(row[specification.kickoff_column]),
            causal_grade=specification.causal_grade,
        )
        for _, row in frame.iterrows()
    ]
    return result, fields


def coverage_table(result: mapping.MappingResult) -> pd.DataFrame:
    """Stratify exact, ambiguous, and quarantined identity outcomes by evidence axes."""
    traces = result.traces.copy()
    if traces.empty:
        return pd.DataFrame(columns=["source_id", "year", "competition_id", "causal_grade", "rows", "valid_fixture_rows", "ambiguous_rows", "unmatched_rows"])
    timestamps = pd.to_datetime(traces["kickoff_at_utc"], utc=True, errors="coerce")
    traces["year"] = timestamps.dt.year.astype("Int64").astype(str).replace("<NA>", "UNKNOWN")
    grouped = traces.groupby(["source_id", "year", "competition_id", "causal_grade"], dropna=False)
    rows = grouped.agg(
        rows=("source_key", "size"),
        valid_fixture_rows=("fixture_id", "size"),
        ambiguous_rows=("identity_status", lambda values: int((values == "AMBIGUOUS").sum())),
    ).reset_index()
    quarantined = result.ledger.loc[result.ledger["disposition"].eq("QUARANTINED")]
    rows["unmatched_rows"] = 0
    # A quarantined row has no trustworthy event/competition stratum.  Emit it
    # once in an explicit unknown bucket rather than repeating it in every
    # coverage group for that source (which would inflate denominators).
    source_grades = traces.groupby("source_id", dropna=False)["causal_grade"].first().to_dict()
    missing_rows: list[dict[str, object]] = []
    for source_id, count in quarantined.groupby("source_id", dropna=False).size().items():
        missing_rows.append(
            {
                "source_id": source_id,
                "year": "UNKNOWN",
                "competition_id": "competition:unidentified",
                "causal_grade": source_grades.get(source_id, "UNKNOWN"),
                "rows": 0,
                "valid_fixture_rows": 0,
                "ambiguous_rows": 0,
                "unmatched_rows": int(count),
            }
        )
    if missing_rows:
        rows = pd.concat([rows, pd.DataFrame(missing_rows)], ignore_index=True)
    return rows.sort_values(["source_id", "year", "competition_id"], kind="stable").reset_index(drop=True)


def profile_sources(specifications: list[SourceSpec]) -> ProfileResult:
    records: list[mapping.IdentityRecord] = []
    read_columns: dict[str, tuple[str, ...]] = {}
    for specification in specifications:
        source_records, fields = _records(specification)
        records.extend(source_records)
        read_columns[specification.source_id] = fields
    result = mapping.map_records(records)
    return ProfileResult(mapping=result, coverage=coverage_table(result), read_columns=read_columns)


def derive_temporal_aliases(traces: pd.DataFrame) -> pd.DataFrame:
    """Derive bounded, source-provenanced alias intervals from identity traces.

    The result is evidence of observed validity, not an assertion that the
    final interval remains open.  Entity renames must be added through a
    reviewed/manual alias row with its own provenance.
    """
    rows: list[dict[str, str]] = []
    definitions = (
        ("competition", "source_competition_key", "competition_id"),
        ("team", "source_home_team_key", "home_team_id"),
        ("team", "source_away_team_key", "away_team_id"),
    )
    for kind, source_column, canonical_column in definitions:
        for _, row in traces.iterrows():
            source_alias = str(row[source_column]).strip()
            asof = str(row["kickoff_at_utc"]).strip()
            if not source_alias or not asof:
                continue
            rows.append(
                {
                    "alias_kind": kind,
                    "source_id": str(row["source_id"]),
                    "source_alias": source_alias,
                    "canonical_id": str(row[canonical_column]),
                    "asof_utc": asof,
                }
            )
    observed = pd.DataFrame(rows)
    if observed.empty:
        return pd.DataFrame(columns=["alias_kind", "source_id", "source_alias", "canonical_id", "valid_from_utc", "valid_to_utc", "provenance"])
    observed["asof_utc"] = pd.to_datetime(observed["asof_utc"], utc=True, errors="coerce")
    observed = observed.dropna(subset=["asof_utc"])
    result = observed.groupby(
        ["alias_kind", "source_id", "source_alias", "canonical_id"], dropna=False
    )["asof_utc"].agg(["min", "max"]).reset_index()
    result["valid_from_utc"] = result["min"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["valid_to_utc"] = result["max"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["provenance"] = "observed_identity_trace:v1"
    return result.drop(columns=["min", "max"]).sort_values(
        ["alias_kind", "source_id", "source_alias"], kind="stable"
    ).reset_index(drop=True)


def exceptional_case_policy() -> pd.DataFrame:
    """Explicit required dispositions; no status/outcome field is consumed."""
    return pd.DataFrame(
        [
            {"case_class": "RESCHEDULED", "disposition": "MANUAL_REVIEW", "rule": "retain issue slot but require provenance-bound schedule amendment"},
            {"case_class": "POSTPONED", "disposition": "MANUAL_REVIEW", "rule": "do not auto-map until a source declares a replacement fixture"},
            {"case_class": "ABANDONED", "disposition": "EXCLUDE_FROM_INFERENCE", "rule": "retain source trace; never create a settlement or feature inference shortcut"},
            {"case_class": "DUPLICATE", "disposition": "QUARANTINED", "rule": "multiple source rows for one source and exact slot block automatic acceptance"},
            {"case_class": "NEUTRAL_VENUE", "disposition": "CANONICAL_NO_TEAM_REWRITE", "rule": "venue does not alter home/away team identity; record venue only in a later fixture attribute"},
            {"case_class": "RENAMED_ENTITY", "disposition": "MANUAL_REVIEW", "rule": "only a provenance-bound temporal alias may connect renamed labels"},
        ]
    )


def validate_fixture_outcome_cells(cells: pd.DataFrame) -> None:
    """Validate the required issue×fixture and fixture×three-outcome grain."""
    required = {"issue_code", "match_idx", "outcome_code"}
    missing = required - set(cells.columns)
    if missing:
        raise ValueError(f"cell table missing columns: {sorted(missing)}")
    if cells.duplicated(["issue_code", "match_idx", "outcome_code"]).any():
        raise ValueError("duplicate fixture outcome cell")
    allowed = {"3", "1", "0"}
    for fixture, group in cells.groupby(["issue_code", "match_idx"], dropna=False):
        observed = set(group["outcome_code"].astype(str))
        if observed != allowed:
            raise ValueError(f"missing or invalid three-outcome cells for {fixture}: {sorted(observed)}")
