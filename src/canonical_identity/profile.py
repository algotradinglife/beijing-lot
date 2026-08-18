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
    """Stratify slot coverage separately from entity-resolution coverage."""
    traces = result.traces.copy()
    if traces.empty:
        return pd.DataFrame(
            columns=[
                "source_id",
                "year",
                "source_competition_key",
                "causal_grade",
                "rows",
                "exact_slot_rows",
                "resolved_entity_fields",
                "source_local_entity_fields",
                "conflicting_entity_fields",
                "unidentified_entity_fields",
                "unmatched_slot_rows",
            ]
        )
    timestamps = pd.to_datetime(traces["kickoff_at_utc"], utc=True, errors="coerce")
    traces["year"] = timestamps.dt.year.astype("Int64").astype("string").fillna("UNKNOWN")
    axes = ["source_id", "year", "source_competition_key", "causal_grade"]
    grouped = traces.groupby(axes, dropna=False)
    rows = grouped.agg(rows=("source_key", "size"), exact_slot_rows=("issue_slot_id", "size")).reset_index()
    status_columns = (
        "competition_resolution_status",
        "home_team_resolution_status",
        "away_team_resolution_status",
    )
    for output, status in (
        ("resolved_entity_fields", "EXACT_CROSS_SOURCE"),
        ("source_local_entity_fields", "SOURCE_LOCAL_ONLY"),
        ("conflicting_entity_fields", "UNRESOLVED_CONFLICT"),
        ("unidentified_entity_fields", "UNIDENTIFIED"),
    ):
        values = traces.loc[:, axes].copy()
        values[output] = sum(traces[column].eq(status).astype(int) for column in status_columns)
        counts = values.groupby(axes, dropna=False)[output].sum().reset_index()
        rows = rows.merge(counts, on=axes, how="left", validate="one_to_one")
    quarantined = result.ledger.loc[result.ledger["disposition"].eq("QUARANTINED")]
    rows["unmatched_slot_rows"] = 0
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
                "source_competition_key": "UNKNOWN",
                "causal_grade": source_grades.get(source_id, "UNKNOWN"),
                "rows": 0,
                "exact_slot_rows": 0,
                "resolved_entity_fields": 0,
                "source_local_entity_fields": 0,
                "conflicting_entity_fields": 0,
                "unidentified_entity_fields": 0,
                "unmatched_slot_rows": int(count),
            }
        )
    if missing_rows:
        rows = pd.concat([rows, pd.DataFrame(missing_rows)], ignore_index=True)
    return rows.sort_values(["source_id", "year", "source_competition_key"], kind="stable").reset_index(drop=True)


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
    frames: list[pd.DataFrame] = []
    definitions = (
        ("competition", "source_competition_key", "source_competition_entity_id"),
        ("team", "source_home_team_key", "source_home_team_entity_id"),
        ("team", "source_away_team_key", "source_away_team_entity_id"),
    )
    for kind, source_column, entity_column in definitions:
        value = traces.loc[
            :, ["source_id", source_column, entity_column, "kickoff_at_utc"]
        ].rename(
            columns={
                source_column: "source_alias",
                entity_column: "entity_id",
                "kickoff_at_utc": "asof_utc",
            }
        )
        value.insert(0, "alias_kind", kind)
        present = (
            value["source_alias"].astype(str).str.strip().ne("")
            & value["entity_id"].astype(str).str.strip().ne("")
            & value["asof_utc"].astype(str).str.strip().ne("")
        )
        frames.append(value.loc[present])
    observed = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if observed.empty:
        return pd.DataFrame(
            columns=[
                "alias_kind",
                "source_id",
                "source_alias",
                "entity_id",
                "valid_from_utc",
                "valid_to_utc",
                "validity_semantics",
                "provenance",
            ]
        )
    observed["asof_utc"] = pd.to_datetime(observed["asof_utc"], utc=True, errors="coerce")
    observed = observed.dropna(subset=["asof_utc"])
    result = observed.groupby(
        ["alias_kind", "source_id", "source_alias", "entity_id"], dropna=False
    )["asof_utc"].agg(["min", "max"]).reset_index()
    result["valid_from_utc"] = result["min"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["valid_to_utc"] = result["max"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    result["validity_semantics"] = "OBSERVED_FIRST_LAST_NOT_AUTHORITATIVE"
    result["provenance"] = "observed_identity_trace:v2"
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


def validate_outcome_cells(cells: pd.DataFrame) -> None:
    """Validate non-null, deterministic issue-slot × play × 3/1/0 cells."""
    required = {
        "outcome_cell_id",
        "play_id",
        "issue_slot_id",
        "outcome_code",
    }
    missing = required - set(cells.columns)
    if missing:
        raise ValueError(f"cell table missing columns: {sorted(missing)}")
    values = cells.loc[:, sorted(required)].copy()
    if values.isna().any().any() or values.astype(str).apply(lambda column: column.str.strip().eq("")).any().any():
        raise ValueError("outcome cell identity grain must be non-null and nonblank")
    if cells.duplicated(["issue_slot_id", "outcome_code"]).any():
        raise ValueError("duplicate issue-slot outcome cell")
    codes = cells["outcome_code"].astype(str)
    if not codes.isin(mapping.OUTCOME_CODES).all():
        raise ValueError("missing or invalid three-outcome cells")
    group_size = cells.groupby("issue_slot_id", sort=False)["outcome_code"].transform("size")
    unique_codes = cells.groupby("issue_slot_id", sort=False)["outcome_code"].transform("nunique")
    if not (group_size.eq(3) & unique_codes.eq(3)).all():
        raise ValueError("missing or invalid three-outcome cells")
    expected_plays = cells["issue_slot_id"].astype(str).map(mapping.play_id)
    if not cells["play_id"].astype(str).eq(expected_plays).all():
        raise ValueError("invalid play identity")
    expected_cells = pd.Series(
        [
            mapping.outcome_cell_id(str(slot_id), str(code))
            for slot_id, code in zip(cells["issue_slot_id"], codes, strict=True)
        ],
        index=cells.index,
    )
    if not cells["outcome_cell_id"].astype(str).eq(expected_cells).all():
        raise ValueError("invalid outcome-cell identity")


def validate_identity_tables(result: mapping.MappingResult) -> None:
    """Validate the complete issue → slot → play → outcome identity chain."""
    table_keys = (
        (result.issues, "issue_id"),
        (result.slots, "issue_slot_id"),
        (result.plays, "play_id"),
        (result.outcome_cells, "outcome_cell_id"),
    )
    for frame, key in table_keys:
        if key not in frame.columns:
            raise ValueError(f"identity table missing key: {key}")
        if frame[key].isna().any() or frame[key].astype(str).str.strip().eq("").any():
            raise ValueError(f"identity key must be non-null: {key}")
        if frame[key].duplicated().any():
            raise ValueError(f"duplicate identity key: {key}")
    issue_ids = set(result.issues["issue_id"])
    if not set(result.slots["issue_id"]).issubset(issue_ids):
        raise ValueError("slot references unknown issue")
    slot_ids = set(result.slots["issue_slot_id"])
    if set(result.plays["issue_slot_id"]) != slot_ids:
        raise ValueError("play/slot coverage mismatch")
    if set(result.outcome_cells["issue_slot_id"]) != slot_ids:
        raise ValueError("outcome/slot coverage mismatch")
    validate_outcome_cells(result.outcome_cells)
