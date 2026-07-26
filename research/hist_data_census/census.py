"""Read-only schema, provenance and admissible-use census after G0 inventory.

This module is intentionally conservative.  It does not fit a model, compute a
prediction, evaluate a ticket, or calculate any return-oriented metric.  It
turns a previously frozen inventory into public structural evidence while
keeping source payloads, private URLs and local paths out of the output.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zipfile import BadZipFile, ZipFile

from src.research_freeze_protocol import ResearchFreezeError, create_freeze_package, verify_freeze_package

from .audit import (
    ABSOLUTE_PATH_RE,
    AUDIT_ID,
    AUDIT_SCHEMA,
    INVENTORY_COLUMNS,
    RuntimeInput,
    CensusError,
    _full_git_commit,
    _read_csv,
    _write_csv,
    assert_public_redaction,
    build_source_inventory,
    canonical_bytes,
    canonical_json,
    inventory_identity,
    sha256_bytes,
    sha256_file,
    verify_inventory_package,
)


CENSUS_EXPERIMENT_ID = AUDIT_ID
CENSUS_SCHEMA = "hist_data_census_v1"
FULL_GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ISSUE_RE = re.compile(r"^(?:\d{5,8})$")
YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
SQL_IDENTIFIER_RE = re.compile(r"^[^\x00]+$")

SCHEMA_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "column_name", "ordinal", "declared_type",
    "nullable", "primary_key_position", "field_role", "terminal_value", "pre_match_feature_eligible",
    "admissible_use", "timestamp_grade", "evidence_basis",
)
COVERAGE_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "market", "period_basis", "period_value",
    "row_count", "distinct_match_count", "distinct_issue_count", "date_or_issue_field", "coverage_status", "coverage_note",
)
MARKET_SCHEMA_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "market", "outcome_field", "outcome_value",
    "row_count", "distinct_match_count", "schema_status", "schema_note",
)
TIMESTAMP_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "field_name", "clock_kind", "storage_semantics",
    "timestamp_grade", "strict_asof_eligible", "non_null_rows", "period_start", "period_end", "provenance_note",
)
MAPPING_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "mapping_field", "row_count", "non_null_rows",
    "distinct_non_null", "duplicate_rows", "cross_source_join_authorized", "quality_status", "quality_note",
)
FEATURE_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "field_name", "field_role", "availability",
    "admissible_use", "pre_match_feature_eligible", "terminal_guard", "timestamp_grade", "feature_note",
)
SETTLEMENT_COLUMNS = (
    "logical_asset_id", "logical_source_id", "source_kind", "table_name", "row_count", "outcome_fields", "winning_price_field",
    "special_state_field", "coverage_status", "admissible_use", "settlement_note",
)
ADMISSIBLE_COLUMNS = (
    "scope_level", "logical_asset_id", "logical_source_id", "table_name", "field_name", "market", "admissible_use",
    "strict_conditions", "provenance_grade", "classification_reason",
)
INTEGRATION_COLUMNS = (
    "scope_level", "logical_asset_id", "logical_source_id", "table_name", "field_name", "market", "integration_decision",
    "destination_layer", "lineage_fields", "required_transforms", "deduplication_key", "timestamp_grade", "limitations",
)
READINESS_COLUMNS = (
    "play_id", "market", "label_ready", "feature_ready", "price_ready", "chronological_split_ready",
    "coarse_baseline_constructible", "roi_ready", "sample_scope", "coverage_period", "blocking_fields_or_provenance",
    "recommended_next_issue", "audit_boundary",
)
BUNDLE_COLUMNS = (
    "logical_asset_id", "logical_source_id", "bundle_family", "issue", "market", "bundle_file_count", "manifest_present",
    "sha256sums_present", "checksum_status", "checksum_entries", "verified_files", "capture_clock_present",
    "source_clock_present", "strict_candidate_rows", "terminal_rows", "incomplete_rows", "manifest_key_sha256", "bundle_note",
)
WORKBOOK_COLUMNS = (
    "logical_asset_id", "logical_source_id", "filename", "package_status", "package_entry_count", "worksheet_entry_count",
    "has_vba_project", "has_external_links", "has_connections", "macro_executed", "workbook_note",
)
VIEW_COLUMNS = (
    "view_name", "input_provenance_requirement", "terminal_value_rule", "allowed_asset_classes", "row_level_guard", "status",
)

REQUIRED_CENSUS_ARTIFACTS = (
    "source_inventory.csv",
    "schema_dictionary.csv",
    "coverage_by_period.csv",
    "market_outcome_schemas.csv",
    "timestamp_provenance.csv",
    "mapping_quality.csv",
    "feature_availability.csv",
    "settlement_coverage.csv",
    "admissible_use_matrix.csv",
    "integration_decisions.csv",
    "model_readiness_matrix.csv",
    "bundle_integrity.csv",
    "workbook_structure.csv",
    "research_view_design.csv",
    "audit_report.json",
    "census_config.json",
    "reproducibility_receipt.json",
)

TARGET_MARKETS = {
    "p34": {"play_id": "34", "market": "handicap_310", "expected_outcomes": 3},
    "p40": {"play_id": "40", "market": "total_goals", "expected_outcomes": 8},
    "p41": {"play_id": "41", "market": "upper_lower_odd_even", "expected_outcomes": 4},
    "p42": {"play_id": "42", "market": "correct_score", "expected_outcomes": 25},
    "p51": {"play_id": "51", "market": "half_full", "expected_outcomes": 9},
}

# These tables are explicitly profiled.  Large modelling tables remain in the
# schema dictionary, but their unindexed row-wide aggregation is deliberately
# not mistaken for a prerequisite to this data-eligibility audit.
PROFILE_TABLES = frozenset({
    "matches", "settlements", "historical_matches", "live_market_sp_snapshots", "live_sp_snapshots",
    "market_sp_capture_batches", "multimarket_settlement_truth", "exotic_odds", "issue_list",
    "official_500_settlements", "official_3sp_settlements",
})
MAPPING_FIELD_TOKENS = ("match_id", "issue", "match_idx", "provider_match_id", "league", "home", "away", "team_id", "handicap")
TERMINAL_TOKENS = (
    "final", "fthg", "ftag", "score", "result", "winning_sp", "settle", "payout", "profit", "hit", "outcome_code",
)
PRICE_TOKENS = ("odds", "price", "_sp", "sp_", "euro", "kelly")
TIME_TOKENS = ("kickoff", "snapshot", "fetched", "created", "updated", "settled", "timestamp", "_ts", "ts_")
PREMATCH_TOKENS = ("rank", "form", "handicap", "initial", "10h", "1h", "league", "home", "away", "team", "line")
SAFE_STATUS_VALUES = frozenset({"complete", "partial", "partial_blocked", "failed", "success", "pending", "unknown"})
SAFE_MANIFEST_NUMBERS = (
    "match_rows", "outcome_rows", "complete_forward_open_rows", "terminal_rows", "complete_vector_rows", "open_rows",
    "price_rows", "snapshot_rows", "complete_snapshot_rows", "complete_pregame_rows", "selected_outcome_rows", "history_rows",
    "failed_or_missing_pages", "incomplete_match_indices", "rejected_pages", "failure_rows",
)


@dataclass(frozen=True)
class SourceReference:
    row: Mapping[str, str]
    path: Path | None

    @property
    def asset_id(self) -> str:
        return str(self.row["logical_asset_id"])

    @property
    def source_id(self) -> str:
        return str(self.row["logical_source_id"])

    @property
    def kind(self) -> str:
        return str(self.row["asset_kind"])


def _quote_identifier(value: str) -> str:
    if not SQL_IDENTIFIER_RE.fullmatch(value):
        raise CensusError("database schema contains an unsafe identifier")
    return '"' + value.replace('"', '""') + '"'


def _cell(value: Any) -> str | int | float:
    """Return a CSV-safe public scalar without serializing arbitrary objects."""

    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return ""
        return value
    rendered = str(value)
    if rendered[:1] in {"=", "+", "-", "@"}:
        return "'" + rendered
    return rendered


def _rows_sorted(rows: Iterable[Mapping[str, Any]], columns: Sequence[str]) -> list[dict[str, Any]]:
    normalized = [{column: _cell(row.get(column, "")) for column in columns} for row in rows]
    return sorted(normalized, key=lambda row: tuple(str(row[column]) for column in columns))


def _asset_base(reference: SourceReference) -> dict[str, str]:
    return {
        "logical_asset_id": reference.asset_id,
        "logical_source_id": reference.source_id,
        "source_kind": reference.kind,
    }


def _is_terminal_table(table_name: str) -> bool:
    lowered = table_name.casefold()
    return any(token in lowered for token in ("settle", "result", "review", "pnl", "profit"))


def _is_price_table(table_name: str) -> bool:
    lowered = table_name.casefold()
    return any(token in lowered for token in ("snapshot", "odds", "market", "sp_"))


def _field_role(table_name: str, field_name: str) -> str:
    table = table_name.casefold()
    field = field_name.casefold()
    if _is_terminal_table(table) and field not in {"issue", "match_id", "match_idx", "market_key"}:
        return "settlement_or_terminal"
    if field in {"fthg", "ftag", "score", "halftime_score", "result_code", "result_label", "total_goals", "half_full", "hit"}:
        return "outcome_label"
    if "winning_sp" in field or "payout" in field or "profit" in field:
        return "settlement_price"
    if field in {"outcome", "outcome_code", "outcome_label"} and _is_price_table(table):
        return "market_outcome_key"
    if any(token in field for token in PRICE_TOKENS):
        return "price_or_probability"
    if any(token in field for token in TIME_TOKENS):
        return "clock_or_event_time"
    if any(token in field for token in ("match_id", "issue", "match_idx", "provider", "league", "home", "away", "team_id")):
        return "mapping_or_context"
    if any(token in field for token in PREMATCH_TOKENS):
        return "pre_match_context_proxy"
    return "unclassified_schema_field"


def _field_assessment(reference: SourceReference, table_name: str, field_name: str) -> dict[str, str]:
    role = _field_role(table_name, field_name)
    table = table_name.casefold()
    field = field_name.casefold()
    terminal = role in {"outcome_label", "settlement_or_terminal", "settlement_price"}
    if terminal:
        admissible = "settlement_only" if role == "settlement_price" else "label_only"
        decision = "SETTLEMENT_ONLY"
        destination = "settlement_truth_v1"
        eligible = "false"
        grade = "TERMINAL_OR_POST_EVENT"
        note = "terminal or result-derived value is excluded from every pre-match feature view"
    elif reference.asset_id.endswith("derived-beidan-xlsm-beidan-xlsm-sqlite") and table == "exotic_odds" and field == "odds":
        admissible = "historical_proxy;descriptive_only"
        decision = "INTEGRATE_PROXY"
        destination = "historical_exploratory_v1"
        eligible = "false"
        grade = "UNVERIFIED_TIME_BY_MARKET"
        note = "market-specific override is required: SCORE-PRICE-HIST-AUDIT-001 prohibits the correct-score subset; other rows remain proxy-only until time binding is proved"
    elif role == "price_or_probability":
        admissible = "historical_proxy;descriptive_only"
        decision = "INTEGRATE_PROXY"
        destination = "historical_exploratory_v1"
        eligible = "false"
        grade = "PRICE_TIME_DEPENDS_ON_ROW_PROVENANCE"
        note = "price-like field is not strict as-of evidence without a row-level capture/cutoff binding"
    elif role == "pre_match_context_proxy":
        admissible = "historical_proxy;descriptive_only"
        decision = "INTEGRATE_PROXY"
        destination = "historical_exploratory_v1"
        eligible = "true"
        grade = "HISTORICAL_PROXY"
        note = "context field may support disclosed exploratory construction, not strict replay"
    elif role == "mapping_or_context":
        admissible = "descriptive_only"
        decision = "INTEGRATE_PROXY"
        destination = "historical_exploratory_v1"
        eligible = "false"
        grade = "MAPPING_OR_EVENT_CONTEXT"
        note = "mapping/event context requires source-specific join validation before cross-source use"
    elif role == "clock_or_event_time":
        admissible = "descriptive_only"
        decision = "KEEP_RAW_ONLY"
        destination = "raw_provenance"
        eligible = "false"
        grade = _timestamp_grade(table_name, field_name)
        note = "clock semantics are documented separately; a clock name alone does not bind a price observation"
    else:
        admissible = "descriptive_only"
        decision = "KEEP_RAW_ONLY"
        destination = "raw_provenance"
        eligible = "false"
        grade = "UNCLASSIFIED"
        note = "schema presence alone is insufficient to promote this field to a model input"
    return {
        "field_role": role,
        "terminal_value": "true" if terminal else "false",
        "pre_match_feature_eligible": eligible,
        "admissible_use": admissible,
        "integration_decision": decision,
        "destination_layer": destination,
        "timestamp_grade": grade,
        "note": note,
    }


def _timestamp_grade(table_name: str, field_name: str) -> str:
    table = table_name.casefold()
    field = field_name.casefold()
    if "fetched" in field or "snapshot" in field or "created" in field:
        return "CAPTURE_CLOCK_PRESENT_MUTABILITY_REQUIRES_SOURCE_CHECK"
    if "source_updated" in field or "last_update" in field or "updated" in field:
        return "SOURCE_UPDATE_CLOCK_AMBIGUOUS"
    if "kickoff" in field:
        return "EVENT_CLOCK_NOT_PRICE_OBSERVATION"
    if "10h" in field or "1h" in field:
        return "NAMED_SNAPSHOT_PROXY_UNVERIFIED_BINDING"
    if "settled" in field:
        return "POST_EVENT_SETTLEMENT_CLOCK"
    if "snapshot" in table:
        return "TABLE_NAME_IMPLES_SNAPSHOT_NOT_SUFFICIENT"
    return "TIME_SEMANTICS_UNVERIFIED"


def _market_from_value(value: Any) -> str:
    text = str(value).strip().casefold()
    aliases = {
        "34": "p34", "handicap": "p34", "handicap_310": "p34", "handicap-310": "p34",
        "40": "p40", "goals": "p40", "total_goals": "p40", "total-goals": "p40",
        "41": "p41", "upper_lower_odd_even": "p41", "upper-lower-odd-even": "p41",
        "42": "p42", "score": "p42", "correct_score": "p42", "correct-score": "p42",
        "51": "p51", "half_full": "p51", "half-full": "p51",
    }
    return aliases.get(text, "OTHER_OR_UNMAPPED")


def _market_label(value: str) -> str:
    return TARGET_MARKETS.get(value, {"market": value})["market"]


def _safe_issue(value: Any) -> str:
    rendered = str(value).strip()
    return rendered if ISSUE_RE.fullmatch(rendered) else "UNKNOWN"


def _safe_year(value: Any) -> str:
    rendered = str(value).strip()[:4]
    return rendered if YEAR_RE.fullmatch(rendered) else "UNKNOWN_OR_NON_ISO"


def _connect_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA trusted_schema = OFF")
    connection.execute("BEGIN")
    return connection


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[sqlite3.Row]:
    return list(connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})"))


def _table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        if str(row["name"]) != "sqlite_sequence"
    ]


def _choose_column(columns: Sequence[str], candidates: Sequence[str]) -> str | None:
    lowered = {name.casefold(): name for name in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for candidate in candidates:
        for name in columns:
            if candidate in name.casefold():
                return name
    return None


def _table_count(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) AS count FROM {_quote_identifier(table_name)}").fetchone()["count"])


def _basic_table_coverage(
    connection: sqlite3.Connection,
    reference: SourceReference,
    table_name: str,
    columns: Sequence[str],
) -> list[dict[str, Any]]:
    base = _asset_base(reference)
    if table_name not in PROFILE_TABLES:
        return [{
            **base,
            "table_name": table_name,
            "market": "ALL",
            "period_basis": "NOT_PROFILED",
            "period_value": "NOT_PROFILED",
            "row_count": "",
            "distinct_match_count": "",
            "distinct_issue_count": "",
            "date_or_issue_field": "",
            "coverage_status": "SCHEMA_ONLY_DETERMINISTIC_SCOPE_BOUNDARY",
            "coverage_note": "large or derived table retained in schema evidence; no unindexed full-table aggregation was required for eligibility classification",
        }]
    try:
        row_count = _table_count(connection, table_name)
    except sqlite3.Error:
        return [{
            **base,
            "table_name": table_name,
            "market": "ALL",
            "period_basis": "ERROR",
            "period_value": "ERROR",
            "row_count": "",
            "distinct_match_count": "",
            "distinct_issue_count": "",
            "date_or_issue_field": "",
            "coverage_status": "READ_ONLY_QUERY_FAILED",
            "coverage_note": "read-only aggregate failed; source remains inventoried with a deterministic audit limitation",
        }]
    match_column = _choose_column(columns, ("match_id", "provider_match_id"))
    issue_column = _choose_column(columns, ("issue",))
    distinct_match = ""
    distinct_issue = ""
    if match_column:
        distinct_match = int(connection.execute(
            f"SELECT COUNT(DISTINCT {_quote_identifier(match_column)}) AS count FROM {_quote_identifier(table_name)} "
            f"WHERE {_quote_identifier(match_column)} IS NOT NULL"
        ).fetchone()["count"])
    if issue_column:
        distinct_issue = int(connection.execute(
            f"SELECT COUNT(DISTINCT {_quote_identifier(issue_column)}) AS count FROM {_quote_identifier(table_name)} "
            f"WHERE {_quote_identifier(issue_column)} IS NOT NULL"
        ).fetchone()["count"])
    rows: list[dict[str, Any]] = [{
        **base,
        "table_name": table_name,
        "market": "ALL",
        "period_basis": "ALL_ROWS",
        "period_value": "ALL",
        "row_count": row_count,
        "distinct_match_count": distinct_match,
        "distinct_issue_count": distinct_issue,
        "date_or_issue_field": "",
        "coverage_status": "PROFILED",
        "coverage_note": "exact read-only aggregate; no source rows are published",
    }]
    if issue_column:
        counts: Counter[str] = Counter()
        for item in connection.execute(
            f"SELECT {_quote_identifier(issue_column)} AS value, COUNT(*) AS count "
            f"FROM {_quote_identifier(table_name)} GROUP BY {_quote_identifier(issue_column)}"
        ):
            counts[_safe_issue(item["value"])] += int(item["count"])
        for issue, count in sorted(counts.items()):
            rows.append({
                **base,
                "table_name": table_name,
                "market": "ALL",
                "period_basis": "ISSUE",
                "period_value": issue,
                "row_count": count,
                "distinct_match_count": "",
                "distinct_issue_count": 1 if issue != "UNKNOWN" else "",
                "date_or_issue_field": issue_column,
                "coverage_status": "PROFILED",
                "coverage_note": "issue value normalized without publishing other source fields",
            })
    date_column = _choose_column(columns, ("kickoff_ts", "kickoff", "match_date", "date"))
    if date_column:
        counts = Counter()
        for item in connection.execute(
            f"SELECT SUBSTR(CAST({_quote_identifier(date_column)} AS TEXT), 1, 4) AS value, COUNT(*) AS count "
            f"FROM {_quote_identifier(table_name)} GROUP BY SUBSTR(CAST({_quote_identifier(date_column)} AS TEXT), 1, 4)"
        ):
            counts[_safe_year(item["value"])] += int(item["count"])
        for year, count in sorted(counts.items()):
            rows.append({
                **base,
                "table_name": table_name,
                "market": "ALL",
                "period_basis": "CALENDAR_YEAR",
                "period_value": year,
                "row_count": count,
                "distinct_match_count": "",
                "distinct_issue_count": "",
                "date_or_issue_field": date_column,
                "coverage_status": "PROFILED" if year != "UNKNOWN_OR_NON_ISO" else "DATE_SEMANTICS_UNRESOLVED",
                "coverage_note": "calendar year is reported only for ISO-like event-time values; non-ISO values are not coerced",
            })
    return rows


def _market_schema_rows(
    connection: sqlite3.Connection,
    reference: SourceReference,
    table_name: str,
    columns: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Counter[str]]]:
    """Return market/outcome counts without emitting raw price values."""

    base = _asset_base(reference)
    market_column = _choose_column(columns, ("playid", "market_key", "market"))
    outcome_column = _choose_column(columns, ("outcome_code", "outcome", "outcome_label", "result_code"))
    if not market_column or not outcome_column or table_name not in PROFILE_TABLES:
        return [], {}
    match_column = _choose_column(columns, ("match_id",))
    grouped: dict[tuple[str, str], list[Any]] = {}
    query_columns = [
        f"{_quote_identifier(market_column)} AS market_value",
        f"{_quote_identifier(outcome_column)} AS outcome_value",
        "COUNT(*) AS row_count",
    ]
    if match_column:
        query_columns.append(f"COUNT(DISTINCT {_quote_identifier(match_column)}) AS match_count")
    query = (
        "SELECT " + ", ".join(query_columns) + f" FROM {_quote_identifier(table_name)} "
        f"GROUP BY {_quote_identifier(market_column)}, {_quote_identifier(outcome_column)}"
    )
    contexts: dict[str, Counter[str]] = defaultdict(Counter)
    for item in connection.execute(query):
        market = _market_from_value(item["market_value"])
        # Outcome codes are part of the public market schema, not proprietary
        # payloads.  A length cap prevents arbitrary source blobs entering CSV.
        outcome = str(item["outcome_value"]).strip() if item["outcome_value"] is not None else "<NULL>"
        if len(outcome) > 80 or "\n" in outcome or "\r" in outcome:
            outcome = "UNSAFE_OR_OVERSIZED_OUTCOME_LABEL"
        prior = grouped.get((market, outcome), [0, 0 if match_column else ""])
        grouped[(market, outcome)] = [
            int(prior[0]) + int(item["row_count"]),
            int(prior[1]) + int(item["match_count"]) if match_column else "",
        ]
        contexts[market]["price_or_outcome_rows"] += int(item["row_count"])
        contexts[market]["outcome_labels"] += 1
    output = [
        {
            **base,
            "table_name": table_name,
            "market": _market_label(market),
            "outcome_field": outcome_column,
            "outcome_value": outcome,
            "row_count": values[0],
            "distinct_match_count": values[1],
            "schema_status": "OBSERVED_READ_ONLY",
            "schema_note": "outcome schema counts; price values are not emitted",
        }
        for (market, outcome), values in grouped.items()
    ]
    return output, contexts


def _market_period_rows(
    connection: sqlite3.Connection,
    reference: SourceReference,
    table_name: str,
    columns: Sequence[str],
    tables: Sequence[str],
) -> list[dict[str, Any]]:
    """Report period coverage by market without using cross-source inference."""

    if table_name not in PROFILE_TABLES:
        return []
    base = _asset_base(reference)
    market_column = _choose_column(columns, ("playid", "market_key", "market"))
    issue_column = _choose_column(columns, ("issue",))
    match_column = _choose_column(columns, ("match_id",))
    output: list[dict[str, Any]] = []
    if market_column and issue_column:
        columns_sql = [
            f"{_quote_identifier(market_column)} AS market_value",
            f"{_quote_identifier(issue_column)} AS issue_value",
            "COUNT(*) AS row_count",
        ]
        if match_column:
            columns_sql.append(f"COUNT(DISTINCT {_quote_identifier(match_column)}) AS match_count")
        query = (
            "SELECT " + ", ".join(columns_sql) + f" FROM {_quote_identifier(table_name)} "
            f"GROUP BY {_quote_identifier(market_column)}, {_quote_identifier(issue_column)}"
        )
        for item in connection.execute(query):
            market = _market_from_value(item["market_value"])
            output.append({
                **base,
                "table_name": table_name,
                "market": _market_label(market),
                "period_basis": "ISSUE",
                "period_value": _safe_issue(item["issue_value"]),
                "row_count": int(item["row_count"]),
                "distinct_match_count": int(item["match_count"]) if match_column else "",
                "distinct_issue_count": 1,
                "date_or_issue_field": issue_column,
                "coverage_status": "PROFILED",
                "coverage_note": "within-database market/issue aggregate; no price values are emitted",
            })
    elif table_name == "exotic_odds" and market_column and match_column and "matches" in tables:
        match_columns = [str(column["name"]) for column in _table_columns(connection, "matches")]
        joined_issue = _choose_column(match_columns, ("issue",))
        if joined_issue:
            query = (
                f"SELECT e.{_quote_identifier(market_column)} AS market_value, m.{_quote_identifier(joined_issue)} AS issue_value, "
                f"COUNT(*) AS row_count, COUNT(DISTINCT e.{_quote_identifier(match_column)}) AS match_count "
                f"FROM {_quote_identifier(table_name)} AS e LEFT JOIN {_quote_identifier('matches')} AS m "
                f"ON e.{_quote_identifier(match_column)} = m.{_quote_identifier(_choose_column(match_columns, ('match_id',)) or 'match_id')} "
                f"GROUP BY e.{_quote_identifier(market_column)}, m.{_quote_identifier(joined_issue)}"
            )
            for item in connection.execute(query):
                market = _market_from_value(item["market_value"])
                output.append({
                    **base,
                    "table_name": table_name,
                    "market": _market_label(market),
                    "period_basis": "ISSUE",
                    "period_value": _safe_issue(item["issue_value"]),
                    "row_count": int(item["row_count"]),
                    "distinct_match_count": int(item["match_count"]),
                    "distinct_issue_count": 1 if _safe_issue(item["issue_value"]) != "UNKNOWN" else "",
                    "date_or_issue_field": "matches.issue",
                    "coverage_status": "PROFILED_WITHIN_DATABASE_JOIN",
                    "coverage_note": "same-database match_id join is reported as a structural linkage, not proof of price-time binding",
                })
    return output


def _timestamp_rows(
    connection: sqlite3.Connection,
    reference: SourceReference,
    table_name: str,
    columns: Sequence[str],
    row_count: int | str,
) -> list[dict[str, Any]]:
    base = _asset_base(reference)
    output: list[dict[str, Any]] = []
    for field_name in columns:
        lowered = field_name.casefold()
        if not any(token in lowered for token in TIME_TOKENS):
            continue
        grade = _timestamp_grade(table_name, field_name)
        clock_kind = (
            "capture_clock" if any(token in lowered for token in ("fetched", "snapshot", "created"))
            else "source_update_clock" if "updated" in lowered or "last_update" in lowered
            else "event_clock" if "kickoff" in lowered
            else "settlement_clock" if "settled" in lowered
            else "named_snapshot_or_derived_clock"
        )
        non_null = ""
        period_start = ""
        period_end = ""
        if table_name in PROFILE_TABLES:
            try:
                values = connection.execute(
                    f"SELECT COUNT({_quote_identifier(field_name)}) AS present, "
                    f"MIN(SUBSTR(CAST({_quote_identifier(field_name)} AS TEXT), 1, 4)) AS first_value, "
                    f"MAX(SUBSTR(CAST({_quote_identifier(field_name)} AS TEXT), 1, 4)) AS last_value "
                    f"FROM {_quote_identifier(table_name)}"
                ).fetchone()
                non_null = int(values["present"])
                period_start = _safe_year(values["first_value"])
                period_end = _safe_year(values["last_value"])
            except sqlite3.Error:
                pass
        output.append({
            **base,
            "table_name": table_name,
            "field_name": field_name,
            "clock_kind": clock_kind,
            "storage_semantics": "table_field; overwrite_or_append_not_inferred_from_name",
            "timestamp_grade": grade,
            "strict_asof_eligible": "false",
            "non_null_rows": non_null,
            "period_start": period_start,
            "period_end": period_end,
            "provenance_note": "clock field is reported structurally; strict eligibility needs source-observation and cutoff proof",
        })
    return output


def _mapping_rows(
    connection: sqlite3.Connection,
    reference: SourceReference,
    table_name: str,
    columns: Sequence[str],
    row_count: int | str,
) -> list[dict[str, Any]]:
    if table_name not in PROFILE_TABLES:
        return []
    base = _asset_base(reference)
    output: list[dict[str, Any]] = []
    for field_name in columns:
        lowered = field_name.casefold()
        if not any(token in lowered for token in MAPPING_FIELD_TOKENS):
            continue
        try:
            stat = connection.execute(
                f"SELECT COUNT(*) AS total, COUNT({_quote_identifier(field_name)}) AS present, "
                f"COUNT(DISTINCT {_quote_identifier(field_name)}) AS distinct_count "
                f"FROM {_quote_identifier(table_name)}"
            ).fetchone()
            total = int(stat["total"])
            present = int(stat["present"])
            distinct = int(stat["distinct_count"])
        except sqlite3.Error:
            continue
        output.append({
            **base,
            "table_name": table_name,
            "mapping_field": field_name,
            "row_count": total,
            "non_null_rows": present,
            "distinct_non_null": distinct,
            "duplicate_rows": max(present - distinct, 0),
            "cross_source_join_authorized": "false",
            "quality_status": "WITHIN_SOURCE_PROFILED_ONLY",
            "quality_note": "null/duplicate profile is within-source only; no identity is inferred by adjacency or name similarity",
        })
    return output


def _settlement_rows(
    connection: sqlite3.Connection,
    reference: SourceReference,
    table_name: str,
    columns: Sequence[str],
    row_count: int | str,
) -> list[dict[str, Any]]:
    terminal_fields = [name for name in columns if _field_role(table_name, name) in {"outcome_label", "settlement_or_terminal"}]
    winning = next((name for name in columns if "winning_sp" in name.casefold()), "")
    special = next((name for name in columns if "special" in name.casefold() or "status" in name.casefold()), "")
    if not terminal_fields and not winning:
        return []
    count = row_count
    if count == "" and table_name in PROFILE_TABLES:
        count = _table_count(connection, table_name)
    return [{
        **_asset_base(reference),
        "table_name": table_name,
        "row_count": count,
        "outcome_fields": ";".join(terminal_fields),
        "winning_price_field": winning,
        "special_state_field": special,
        "coverage_status": "PROFILED" if count != "" else "SCHEMA_PRESENT_COUNT_NOT_PROFILED",
        "admissible_use": "label_only;settlement_only" if winning else "label_only",
        "settlement_note": "terminal values are isolated to settlement_truth_v1 and never become pre-match features or price inputs",
    }]


def _audit_sqlite(reference: SourceReference) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Counter[str]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    contexts: dict[str, Counter[str]] = defaultdict(Counter)
    if reference.path is None:
        return output, contexts
    try:
        with _connect_read_only(reference.path) as connection:
            tables = _table_names(connection)
            for table_name in tables:
                raw_columns = _table_columns(connection, table_name)
                columns = [str(column["name"]) for column in raw_columns]
                table_assessments: list[dict[str, str]] = []
                for column in raw_columns:
                    field_name = str(column["name"])
                    assessment = _field_assessment(reference, table_name, field_name)
                    table_assessments.append(assessment)
                    output["schema_dictionary.csv"].append({
                        **_asset_base(reference),
                        "table_name": table_name,
                        "column_name": field_name,
                        "ordinal": int(column["cid"]),
                        "declared_type": str(column["type"] or ""),
                        "nullable": "false" if int(column["notnull"] or 0) else "true",
                        "primary_key_position": int(column["pk"] or 0),
                        "field_role": assessment["field_role"],
                        "terminal_value": assessment["terminal_value"],
                        "pre_match_feature_eligible": assessment["pre_match_feature_eligible"],
                        "admissible_use": assessment["admissible_use"],
                        "timestamp_grade": assessment["timestamp_grade"],
                        "evidence_basis": "sqlite_pragma_table_info_read_only",
                    })
                    output["feature_availability.csv"].append({
                        **_asset_base(reference),
                        "table_name": table_name,
                        "field_name": field_name,
                        "field_role": assessment["field_role"],
                        "availability": "SCHEMA_PRESENT",
                        "admissible_use": assessment["admissible_use"],
                        "pre_match_feature_eligible": assessment["pre_match_feature_eligible"],
                        "terminal_guard": assessment["terminal_value"],
                        "timestamp_grade": assessment["timestamp_grade"],
                        "feature_note": assessment["note"],
                    })
                    output["admissible_use_matrix.csv"].append({
                        "scope_level": "field",
                        **_asset_base(reference),
                        "table_name": table_name,
                        "field_name": field_name,
                        "market": "ALL",
                        "admissible_use": assessment["admissible_use"],
                        "strict_conditions": "none; no strict promotion from schema alone",
                        "provenance_grade": assessment["timestamp_grade"],
                        "classification_reason": assessment["note"],
                    })
                    output["integration_decisions.csv"].append({
                        "scope_level": "field",
                        **_asset_base(reference),
                        "table_name": table_name,
                        "field_name": field_name,
                        "market": "ALL",
                        "integration_decision": assessment["integration_decision"],
                        "destination_layer": assessment["destination_layer"],
                        "lineage_fields": "logical_asset_id;table_name;field_name",
                        "required_transforms": "retain raw source identifier; no terminal-to-feature projection",
                        "deduplication_key": "source-specific key not inferred in census",
                        "timestamp_grade": assessment["timestamp_grade"],
                        "limitations": assessment["note"],
                    })
                coverage = _basic_table_coverage(connection, reference, table_name, columns)
                output["coverage_by_period.csv"].extend(coverage)
                output["coverage_by_period.csv"].extend(
                    _market_period_rows(connection, reference, table_name, columns, tables)
                )
                all_count = next((row["row_count"] for row in coverage if row["period_basis"] == "ALL_ROWS"), "")
                output["timestamp_provenance.csv"].extend(_timestamp_rows(connection, reference, table_name, columns, all_count))
                output["mapping_quality.csv"].extend(_mapping_rows(connection, reference, table_name, columns, all_count))
                output["settlement_coverage.csv"].extend(_settlement_rows(connection, reference, table_name, columns, all_count))
                market_rows, market_context = _market_schema_rows(connection, reference, table_name, columns)
                output["market_outcome_schemas.csv"].extend(market_rows)
                for market, counts in market_context.items():
                    contexts[market].update(counts)
                    if table_name == "live_market_sp_snapshots" and market in TARGET_MARKETS:
                        classification_column = _choose_column(columns, ("capture_classification",))
                        if classification_column:
                            for entry in connection.execute(
                                f"SELECT {_quote_identifier(classification_column)} AS value, COUNT(*) AS count "
                                f"FROM {_quote_identifier(table_name)} WHERE {_quote_identifier(_choose_column(columns, ('playid',)) or 'playid')} "
                                f"= ? GROUP BY {_quote_identifier(classification_column)}",
                                (int(TARGET_MARKETS[market]["play_id"]),),
                            ):
                                label = str(entry["value"] or "UNKNOWN")
                                if label == "forward_complete_open":
                                    contexts[market]["strict_forward_rows"] += int(entry["count"])
                                elif "terminal" in label or "post_cutoff" in label:
                                    contexts[market]["terminal_or_postcutoff_rows"] += int(entry["count"])
                                else:
                                    contexts[market]["non_strict_rows"] += int(entry["count"])
    except (sqlite3.Error, OSError):
        # The inventory still preserves source existence; output one deterministic
        # failure row rather than hiding an unreadable or empty database.
        output["coverage_by_period.csv"].append({
            **_asset_base(reference),
            "table_name": "",
            "market": "ALL",
            "period_basis": "DATABASE_OPEN",
            "period_value": "UNAVAILABLE",
            "row_count": "",
            "distinct_match_count": "",
            "distinct_issue_count": "",
            "date_or_issue_field": "",
            "coverage_status": "READ_ONLY_DATABASE_UNAVAILABLE",
            "coverage_note": "database could not be opened read-only; no silent substitution was made",
        })
    return output, contexts


def _csv_headers_and_count(path: Path) -> tuple[list[str], int]:
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        try:
            headers = next(reader)
        except StopIteration:
            return [], 0
        return headers, sum(1 for _ in reader)


def _audit_tabular(reference: SourceReference) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if reference.path is None:
        return output
    locator = str(reference.row["repository_locator"]).casefold()
    if any(token in locator for token in ("pnl", "backtest", "profile", "auto_reports")):
        output["admissible_use_matrix.csv"].append({
            "scope_level": "asset",
            **_asset_base(reference),
            "table_name": "",
            "field_name": "",
            "market": "ALL",
            "admissible_use": "prohibited",
            "strict_conditions": "none",
            "provenance_grade": "DERIVED_PERFORMANCE_OR_RUNTIME_ARTIFACT",
            "classification_reason": "derived performance/runtime artifact is not a source input for this audit",
        })
        output["integration_decisions.csv"].append({
            "scope_level": "asset",
            **_asset_base(reference),
            "table_name": "",
            "field_name": "",
            "market": "ALL",
            "integration_decision": "PROHIBITED",
            "destination_layer": "none",
            "lineage_fields": "logical_asset_id",
            "required_transforms": "none",
            "deduplication_key": "none",
            "timestamp_grade": "DERIVED_PERFORMANCE_OR_RUNTIME_ARTIFACT",
            "limitations": "not opened; no performance/return artifact can become a model input",
        })
        return output
    if reference.path.suffix.casefold() != ".csv":
        return output
    try:
        headers, row_count = _csv_headers_and_count(reference.path)
    except OSError:
        headers, row_count = [], 0
    table_name = "csv_export"
    for ordinal, field_name in enumerate(headers):
        assessment = _field_assessment(reference, table_name, field_name)
        output["schema_dictionary.csv"].append({
            **_asset_base(reference),
            "table_name": table_name,
            "column_name": field_name[:160],
            "ordinal": ordinal,
            "declared_type": "CSV_UNTYPED",
            "nullable": "UNKNOWN",
            "primary_key_position": 0,
            "field_role": assessment["field_role"],
            "terminal_value": assessment["terminal_value"],
            "pre_match_feature_eligible": assessment["pre_match_feature_eligible"],
            "admissible_use": assessment["admissible_use"],
            "timestamp_grade": assessment["timestamp_grade"],
            "evidence_basis": "csv_header_read_only_no_values_published",
        })
        output["feature_availability.csv"].append({
            **_asset_base(reference),
            "table_name": table_name,
            "field_name": field_name[:160],
            "field_role": assessment["field_role"],
            "availability": "HEADER_PRESENT",
            "admissible_use": assessment["admissible_use"],
            "pre_match_feature_eligible": assessment["pre_match_feature_eligible"],
            "terminal_guard": assessment["terminal_value"],
            "timestamp_grade": assessment["timestamp_grade"],
            "feature_note": assessment["note"],
        })
        output["admissible_use_matrix.csv"].append({
            "scope_level": "field",
            **_asset_base(reference),
            "table_name": table_name,
            "field_name": field_name[:160],
            "market": "ALL",
            "admissible_use": assessment["admissible_use"],
            "strict_conditions": "CSV header and row count do not establish as-of observation time",
            "provenance_grade": assessment["timestamp_grade"],
            "classification_reason": assessment["note"],
        })
        output["integration_decisions.csv"].append({
            "scope_level": "field",
            **_asset_base(reference),
            "table_name": table_name,
            "field_name": field_name[:160],
            "market": "ALL",
            "integration_decision": assessment["integration_decision"],
            "destination_layer": assessment["destination_layer"],
            "lineage_fields": "logical_asset_id;csv_header",
            "required_transforms": "typed parse, source-time validation and terminal guard before any future integration",
            "deduplication_key": "not inferred from CSV header",
            "timestamp_grade": assessment["timestamp_grade"],
            "limitations": assessment["note"],
        })
    output["coverage_by_period.csv"].append({
        **_asset_base(reference),
        "table_name": table_name,
        "market": "ALL",
        "period_basis": "ALL_ROWS",
        "period_value": "ALL",
        "row_count": row_count,
        "distinct_match_count": "",
        "distinct_issue_count": "",
        "date_or_issue_field": "",
        "coverage_status": "HEADER_AND_ROW_COUNT_PROFILED",
        "coverage_note": "CSV values are not published; time semantics require a source-specific contract",
    })
    return output


def _audit_workbook(reference: SourceReference) -> list[dict[str, Any]]:
    if reference.path is None:
        return []
    try:
        with ZipFile(reference.path) as archive:
            names = archive.namelist()
    except (OSError, BadZipFile):
        return [{
            **_asset_base(reference),
            "filename": str(reference.row["filename"]),
            "package_status": "UNREADABLE_AS_SAFE_ZIP_METADATA",
            "package_entry_count": "",
            "worksheet_entry_count": "",
            "has_vba_project": "UNKNOWN",
            "has_external_links": "UNKNOWN",
            "has_connections": "UNKNOWN",
            "macro_executed": "false",
            "workbook_note": "workbook is retained raw-only; no macro or cell payload was executed/published",
        }]
    return [{
        **_asset_base(reference),
        "filename": str(reference.row["filename"]),
        "package_status": "SAFE_PACKAGE_METADATA_READ",
        "package_entry_count": len(names),
        "worksheet_entry_count": sum(name.startswith("xl/worksheets/") for name in names),
        "has_vba_project": "true" if any(name.casefold().endswith("vbaproject.bin") for name in names) else "false",
        "has_external_links": "true" if any(name.startswith("xl/externalLinks/") for name in names) else "false",
        "has_connections": "true" if "xl/connections.xml" in names else "false",
        "macro_executed": "false",
        "workbook_note": "safe ZIP structure only; workbook cell/formula/macro contents are not published or executed",
    }]


def _bundle_family(reference: SourceReference) -> str:
    parts = Path(str(reference.row["repository_locator"])).parts
    if "data_collection" in parts:
        index = parts.index("data_collection")
        return parts[index + 1] if len(parts) > index + 1 else "UNKNOWN"
    if "research" in parts:
        index = parts.index("research")
        return parts[index + 1] if len(parts) > index + 1 else "UNKNOWN"
    if "freeze" in parts:
        index = parts.index("freeze")
        return parts[index + 1] if len(parts) > index + 1 else "UNKNOWN"
    return "UNKNOWN"


def _bundle_issue(reference: SourceReference) -> str:
    for part in Path(str(reference.row["repository_locator"])).parts:
        if ISSUE_RE.fullmatch(part):
            return part
    return "UNKNOWN"


def _verify_sha256sums(bundle: Path) -> tuple[str, int, int]:
    sums = bundle / "SHA256SUMS"
    if not sums.is_file() or sums.is_symlink():
        return "MISSING", 0, 0
    entries: dict[str, str] = {}
    try:
        for line in sums.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, separator, name = line.partition("  ")
            relative = Path(name)
            if (
                separator != "  " or len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest)
                or not name or relative.is_absolute() or ".." in relative.parts or name in entries
            ):
                return "INVALID_FORMAT", len(entries), 0
            entries[name] = digest
    except OSError:
        return "UNREADABLE", 0, 0
    actual: set[str] = set()
    for candidate in bundle.rglob("*"):
        if candidate.is_dir():
            continue
        if candidate.is_symlink() or not candidate.is_file():
            return "NON_REGULAR_FILE", len(entries), 0
        relative_name = candidate.relative_to(bundle).as_posix()
        if relative_name != "SHA256SUMS":
            actual.add(relative_name)
    if set(entries) != actual:
        return "INEXACT_COVERAGE", len(entries), 0
    verified = 0
    for name, digest in entries.items():
        target = bundle / name
        if not target.is_file() or target.is_symlink() or sha256_file(target) != digest:
            return "MISMATCH", len(entries), verified
        verified += 1
    return "PASS", len(entries), verified


def _safe_manifest_stat(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    return int(value) if isinstance(value, int) and value >= 0 else 0


def _audit_bundle(reference: SourceReference) -> tuple[dict[str, Any], Counter[str]]:
    if reference.path is None:
        raise CensusError("bundle inventory row lacks a safe source locator")
    bundle = reference.path
    family = _bundle_family(reference)
    issue = _bundle_issue(reference)
    manifest_path = bundle / "manifest.json"
    manifest: Mapping[str, Any] = {}
    manifest_present = manifest_path.is_file() and not manifest_path.is_symlink()
    if manifest_present:
        try:
            decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = decoded if isinstance(decoded, Mapping) else {}
        except (OSError, json.JSONDecodeError):
            manifest = {}
    checksum_status, entries, verified = _verify_sha256sums(bundle)
    raw_market = manifest.get("playid", manifest.get("market_key", manifest.get("market", "")))
    market = _market_from_value(raw_market)
    if market == "OTHER_OR_UNMAPPED":
        # Family names are public logical provenance and are safer than a raw
        # arbitrary manifest string.
        market = "p42" if "correct_score" in family else "p40" if "multimarket" in family else market
    counter: Counter[str] = Counter()
    for key in SAFE_MANIFEST_NUMBERS:
        counter[key] += _safe_manifest_stat(manifest, key)
    status = manifest.get("status")
    normalized_status = str(status).casefold() if isinstance(status, str) and str(status).casefold() in SAFE_STATUS_VALUES else "UNKNOWN"
    key_hash = sha256_bytes(canonical_bytes(sorted(str(key) for key in manifest))) if manifest else ""
    capture_clock_present = any(key in manifest for key in ("fetched_at_utc", "created_at_utc", "capture_batch_id"))
    source_clock_present = any(key in manifest for key in ("source_updated_at_hkt", "source_updatetime"))
    strict_rows = counter["complete_forward_open_rows"]
    counter["strict_forward_rows"] += strict_rows
    incomplete = (
        counter["incomplete_match_indices"] + counter["failed_or_missing_pages"] + counter["failed_pages"]
        + counter["rejected_pages"] + counter["failure_rows"]
    )
    row = {
        "logical_asset_id": reference.asset_id,
        "logical_source_id": reference.source_id,
        "bundle_family": family,
        "issue": _safe_issue(manifest.get("issue", issue)),
        "market": _market_label(market),
        "bundle_file_count": reference.row.get("bundle_file_count", ""),
        "manifest_present": "true" if manifest_present else "false",
        "sha256sums_present": "true" if (bundle / "SHA256SUMS").is_file() else "false",
        "checksum_status": checksum_status,
        "checksum_entries": entries,
        "verified_files": verified,
        "capture_clock_present": "true" if capture_clock_present else "false",
        "source_clock_present": "true" if source_clock_present else "false",
        "strict_candidate_rows": strict_rows,
        "terminal_rows": counter["terminal_rows"],
        "incomplete_rows": incomplete,
        "manifest_key_sha256": key_hash,
        "bundle_note": f"manifest status class={normalized_status}; raw URLs/payloads/timestamps are not published",
    }
    if market in TARGET_MARKETS:
        counter["bundle_count"] += 1
        counter["checksum_pass_bundles"] += int(checksum_status == "PASS")
    return row, counter


def _asset_classification(reference: SourceReference) -> tuple[str, str, str, str, str]:
    """Return allowed use, integration decision, destination, grade and reason."""

    availability = str(reference.row["availability"])
    locator = str(reference.row["repository_locator"]).casefold()
    if availability == "MISSING":
        return "prohibited", "PROHIBITED", "none", "MISSING", "configured source root absent"
    if availability == "EXCLUDED_SENSITIVE":
        return "prohibited", "PROHIBITED", "none", "SENSITIVE_EXCLUDED", "credential/runtime configuration is intentionally not a research source"
    if any(token in locator for token in ("pnl", "backtest", "profile", "auto_reports")):
        return "prohibited", "PROHIBITED", "none", "DERIVED_PERFORMANCE_OR_RUNTIME", "derived performance/runtime artifact remains outside research input"
    if reference.kind == "immutable_bundle":
        return "descriptive_only", "KEEP_RAW_ONLY", "raw_provenance", "BUNDLE_PENDING_INTEGRITY", "bundle must pass checksum and row-level provenance checks before subset integration"
    if reference.kind in {"vendor_workbook", "workbook", "runtime_source"}:
        return "descriptive_only", "KEEP_RAW_ONLY", "raw_provenance", "RAW_WORKBOOK", "workbook remains raw-only absent a field-level conversion/provenance contract"
    if reference.kind == "sqlite_database":
        return "descriptive_only", "KEEP_RAW_ONLY", "raw_provenance", "TABLE_LEVEL_AUDIT_REQUIRED", "database asset classification is resolved table-by-table"
    if reference.kind == "tabular_export":
        return "historical_proxy;descriptive_only", "INTEGRATE_PROXY", "historical_exploratory_v1", "CSV_TIME_UNVERIFIED", "tabular export may be proxy/descriptive until source time is verified"
    return "descriptive_only", "KEEP_RAW_ONLY", "raw_provenance", "AUXILIARY", "auxiliary artifact has no input eligibility by filename alone"


def _asset_matrix_rows(reference: SourceReference) -> tuple[dict[str, Any], dict[str, Any]]:
    allowed, decision, destination, grade, reason = _asset_classification(reference)
    admissible = {
        "scope_level": "asset",
        **_asset_base(reference),
        "table_name": "",
        "field_name": "",
        "market": "ALL",
        "admissible_use": allowed,
        "strict_conditions": "explicit row-level source/cutoff proof required; no source is promoted by inventory alone",
        "provenance_grade": grade,
        "classification_reason": reason,
    }
    integration = {
        "scope_level": "asset",
        **_asset_base(reference),
        "table_name": "",
        "field_name": "",
        "market": "ALL",
        "integration_decision": decision,
        "destination_layer": destination,
        "lineage_fields": "logical_asset_id;source sha256",
        "required_transforms": "future Engineer-owned integration only; preserve raw lineage and terminal guards",
        "deduplication_key": "not inferred at asset inventory level",
        "timestamp_grade": grade,
        "limitations": reason,
    }
    return admissible, integration


def _p42_override(reference: SourceReference) -> tuple[dict[str, Any], dict[str, Any]]:
    base = _asset_base(reference)
    reason = (
        "SCORE-PRICE-HIST-AUDIT-001 accepted result: 26-way historical score vector is populated, but provider identity, Beijing p42 identity and row-level time binding are unresolved; replay is prohibited"
    )
    return (
        {
            "scope_level": "field_market",
            **base,
            "table_name": "exotic_odds",
            "field_name": "odds",
            "market": "correct_score",
            "admissible_use": "prohibited",
            "strict_conditions": "none; a separately scoped positive provider/market/time provenance audit is required",
            "provenance_grade": "UNVERIFIED_MARKET_AND_TIME",
            "classification_reason": reason,
        },
        {
            "scope_level": "field_market",
            **base,
            "table_name": "exotic_odds",
            "field_name": "odds",
            "market": "correct_score",
            "integration_decision": "PROHIBITED",
            "destination_layer": "none",
            "lineage_fields": "match_id;market;outcome;source asset sha256",
            "required_transforms": "none; retain raw evidence only",
            "deduplication_key": "match_id;market;outcome",
            "timestamp_grade": "UNVERIFIED_MARKET_AND_TIME",
            "limitations": reason,
        },
    )


def _view_rows() -> list[dict[str, str]]:
    return [
        {
            "view_name": "strict_asof_v1",
            "input_provenance_requirement": "immutable or append-only row with source/capture clock, pre-cutoff relation, sale/open eligibility and exact checksum lineage",
            "terminal_value_rule": "exclude outcome, final, winning and settlement fields",
            "allowed_asset_classes": "only individually verified strict rows; no historical proxy substitution",
            "row_level_guard": "capture_time < declared_cutoff AND sale_state=open AND integrity=PASS",
            "status": "DESIGNED_NOT_PRODUCTIONIZED",
        },
        {
            "view_name": "historical_exploratory_v1",
            "input_provenance_requirement": "source hash plus disclosed proxy/time-grade lineage",
            "terminal_value_rule": "exclude every terminal/final/winning/settlement field from feature projection",
            "allowed_asset_classes": "historical_proxy and descriptive-only fields only; preserve source row-by-row",
            "row_level_guard": "provenance_class in (historical_proxy, descriptive_only) AND terminal_guard=false",
            "status": "DESIGNED_NOT_PRODUCTIONIZED",
        },
        {
            "view_name": "settlement_truth_v1",
            "input_provenance_requirement": "terminal result/settlement source with special-state flags retained",
            "terminal_value_rule": "terminal fields allowed only here and never joined into either pre-match view",
            "allowed_asset_classes": "label_only and settlement_only",
            "row_level_guard": "settlement_status is explicitly retained; no pre-match feature export",
            "status": "DESIGNED_NOT_PRODUCTIONIZED",
        },
    ]


def _target_contract_schema_rows() -> list[dict[str, Any]]:
    """Make target-play schema requirements explicit even where data is absent."""

    return [
        {
            "logical_asset_id": f"audit_contract:{key}",
            "logical_source_id": AUDIT_ID,
            "source_kind": "target_market_contract",
            "table_name": "",
            "market": definition["market"],
            "outcome_field": "target_contract",
            "outcome_value": f"EXPECTED_OUTCOME_COUNT={definition['expected_outcomes']}",
            "row_count": "",
            "distinct_match_count": "",
            "schema_status": "DECLARED_TARGET_CONTRACT",
            "schema_note": "target market contract, not an observed source schema or eligibility promotion",
        }
        for key, definition in TARGET_MARKETS.items()
    ]


def _readiness_rows(context: Mapping[str, Counter[str]]) -> list[dict[str, Any]]:
    """Freeze data readiness, not a performance or profitability conclusion."""

    def strict_count(market: str) -> int:
        return int(context.get(market, Counter()).get("strict_forward_rows", 0))

    rows: list[dict[str, Any]] = []
    for key, definition in TARGET_MARKETS.items():
        strict = strict_count(key)
        if key == "p34":
            values = ("true", "historical_proxy", "conditional_forward_only", "historical_proxy", "true", "false",
                      "broad historical settlement/context plus bounded forward 3-way snapshots", "historical plus forward issues present",
                      "historical SP time semantics and per-match cutoff/sale proof are incomplete", "HIST-DATA-INTEGRATION-001")
        elif key == "p40":
            values = ("true", "historical_proxy", "conditional_strict_forward" if strict else "false", "conditional_strict_forward" if strict else "historical_proxy", "true", "false",
                      f"immutable p40 forward-complete-open rows={strict}; broader historical labels/context", "forward capture issues plus historical proxy context",
                      "strict use remains row-level and does not include terminal/backfill rows", "HIST-DATA-INTEGRATION-001")
        elif key == "p41":
            values = ("true", "historical_proxy", "false", "historical_proxy", "true", "false",
                      "settlement-derived labels/context; p41 capture rows are unclassified", "historical proxy context; no qualified p41 price panel",
                      "no strict p41 price/cutoff provenance subset", "FORWARD-P41-STRICT-CAPTURE-001")
        elif key == "p42":
            values = ("true", "historical_proxy", "conditional_strict_forward" if strict else "false", "conditional_strict_forward" if strict else "historical_proxy", "true", "false",
                      f"immutable p42 forward-complete-open rows={strict}; historical 26-way price vector excluded", "forward capture issues plus historical score labels/context",
                      "historical score price is PROHIBITED by SCORE-PRICE-HIST-AUDIT-001; 26-way historical vector is not mechanically current 25-way p42", "P42-PROVENANCE-AND-INTEGRATION-001")
        else:
            values = ("true", "historical_proxy", "false", "historical_proxy", "true", "false",
                      "settlement-derived labels/context; p51 capture rows are unclassified", "historical proxy context; no qualified p51 price panel",
                      "no strict p51 price/cutoff provenance subset", "FORWARD-P51-STRICT-CAPTURE-001")
        rows.append({
            "play_id": definition["play_id"],
            "market": definition["market"],
            "label_ready": values[0],
            "feature_ready": values[1],
            "price_ready": values[2],
            "chronological_split_ready": values[3],
            "coarse_baseline_constructible": values[4],
            "roi_ready": values[5],
            "sample_scope": values[6],
            "coverage_period": values[7],
            "blocking_fields_or_provenance": values[8],
            "recommended_next_issue": values[9],
            "audit_boundary": "data feasibility only; no model fit, selection, prediction, EV, ROI, ticket or strategy conclusion",
        })
    return rows


def _inventory_reference(package: Path) -> dict[str, str]:
    manifest_path = package / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusError("inventory package manifest is unreadable") from exc
    commit = str(manifest.get("git_commit", ""))
    _full_git_commit(commit)
    return {
        "inventory_freeze_id": str(manifest.get("freeze_id", "")),
        "inventory_manifest_sha256": sha256_file(manifest_path),
        "inventory_sha256s_sha256": sha256_file(package / "SHA256SUMS"),
        "inventory_git_commit": commit,
    }


def _references(
    rows: Sequence[Mapping[str, str]],
    *,
    repository_root: Path,
    runtime_inputs: Sequence[RuntimeInput],
) -> list[SourceReference]:
    runtime = {item.logical_id: item.path for item in runtime_inputs}
    output: list[SourceReference] = []
    for row in rows:
        availability = str(row["availability"])
        locator = str(row["repository_locator"])
        path: Path | None = None
        if availability.startswith("PRESENT"):
            if locator.startswith("runtime:"):
                path = runtime.get(locator.split(":", 1)[1])
                if path is None:
                    raise CensusError("runtime input required by frozen inventory was not supplied")
            else:
                candidate = (repository_root / locator).resolve()
                try:
                    candidate.relative_to(repository_root)
                except ValueError as exc:
                    raise CensusError("frozen repository locator escapes source root") from exc
                path = candidate
        output.append(SourceReference(row=row, path=path))
    return output


def _drifted_asset_ids(
    expected_rows: Sequence[Mapping[str, str]],
    observed_rows: Sequence[Mapping[str, Any]],
) -> set[str]:
    """Return frozen assets whose public identity changed after G0.

    Newly discovered assets are intentionally not folded into a frozen census;
    they belong to a later inventory release.  A changed frozen asset is kept
    in the public inventory but is not inspected further in this run.
    """

    fields = ("availability", "bytes", "sha256", "bundle_file_count")
    expected = {str(row["logical_asset_id"]): row for row in expected_rows}
    observed = {str(row["logical_asset_id"]): row for row in observed_rows}
    return {
        asset_id
        for asset_id, before in expected.items()
        if asset_id not in observed
        or any(str(before.get(field, "")) != str(observed[asset_id].get(field, "")) for field in fields)
    }


def _source_drift_rows(reference: SourceReference, *, phase: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    base = _asset_base(reference)
    reason = f"frozen source identity changed {phase}; no schema, coverage, outcome or price evidence from this asset is used"
    coverage = {
        **base,
        "table_name": "",
        "market": "ALL",
        "period_basis": "SOURCE_IDENTITY",
        "period_value": "DRIFTED_AFTER_G0",
        "row_count": "",
        "distinct_match_count": "",
        "distinct_issue_count": "",
        "date_or_issue_field": "",
        "coverage_status": "SOURCE_DRIFT_FAIL_CLOSED",
        "coverage_note": reason,
    }
    admissible = {
        "scope_level": "asset",
        **base,
        "table_name": "",
        "field_name": "",
        "market": "ALL",
        "admissible_use": "prohibited",
        "strict_conditions": "none until a new frozen inventory/snapshot is verified",
        "provenance_grade": "SOURCE_DRIFT_AFTER_G0",
        "classification_reason": reason,
    }
    integration = {
        "scope_level": "asset",
        **base,
        "table_name": "",
        "field_name": "",
        "market": "ALL",
        "integration_decision": "PROHIBITED",
        "destination_layer": "none",
        "lineage_fields": "logical_asset_id;frozen source sha256",
        "required_transforms": "new inventory freeze or immutable local snapshot before any future read",
        "deduplication_key": "none",
        "timestamp_grade": "SOURCE_DRIFT_AFTER_G0",
        "limitations": reason,
    }
    return coverage, admissible, integration


def audit_frozen_inventory(
    *,
    inventory_package: Path,
    repository_root: Path,
    runtime_inputs: Sequence[RuntimeInput],
    git_commit: str,
) -> dict[str, Any]:
    """Audit G1+ only after exact frozen G0 identity verification."""

    _full_git_commit(git_commit)
    source_root = repository_root.expanduser().resolve()
    package = inventory_package.expanduser().resolve()
    verify_inventory_package(
        package,
        repository_root=source_root,
        runtime_inputs=runtime_inputs,
        verify_current_sources=False,
    )
    inventory_rows = _read_csv(package / "inputs" / "source_inventory.csv")
    expected_inventory_identity = inventory_identity(inventory_rows)
    references = _references(inventory_rows, repository_root=source_root, runtime_inputs=runtime_inputs)
    observed_start = build_source_inventory(repository_root=source_root, runtime_inputs=runtime_inputs)
    drifted_before = _drifted_asset_ids(inventory_rows, observed_start)
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    output["source_inventory.csv"] = [dict(row) for row in inventory_rows]
    market_context: dict[str, Counter[str]] = defaultdict(Counter)

    for reference in references:
        if reference.asset_id in drifted_before:
            coverage, admissible, integration = _source_drift_rows(reference, phase="before audit")
            output["coverage_by_period.csv"].append(coverage)
            output["admissible_use_matrix.csv"].append(admissible)
            output["integration_decisions.csv"].append(integration)
            continue
        admissible, integration = _asset_matrix_rows(reference)
        output["admissible_use_matrix.csv"].append(admissible)
        output["integration_decisions.csv"].append(integration)
        if reference.kind == "sqlite_database" and reference.path is not None:
            partial, contexts = _audit_sqlite(reference)
            for name, rows in partial.items():
                output[name].extend(rows)
            for market, counts in contexts.items():
                market_context[market].update(counts)
        elif reference.kind == "tabular_export" and reference.path is not None:
            partial = _audit_tabular(reference)
            for name, rows in partial.items():
                output[name].extend(rows)
        elif reference.kind in {"vendor_workbook", "workbook", "runtime_source"} and reference.path is not None:
            if reference.path.suffix.casefold() in {".xlsm", ".xlsx"}:
                output["workbook_structure.csv"].extend(_audit_workbook(reference))
        elif reference.kind == "immutable_bundle" and reference.path is not None:
            row, counts = _audit_bundle(reference)
            output["bundle_integrity.csv"].append(row)
            market = next((key for key, item in TARGET_MARKETS.items() if item["market"] == row["market"]), "")
            if market:
                market_context[market].update(counts)
                if row["checksum_status"] == "PASS" and row["capture_clock_present"] == "true" and int(row["strict_candidate_rows"] or 0) > 0:
                    output["admissible_use_matrix.csv"].append({
                        "scope_level": "bundle_subset",
                        **_asset_base(reference),
                        "table_name": "",
                        "field_name": "",
                        "market": row["market"],
                        "admissible_use": "strict_replay",
                        "strict_conditions": "checksum=PASS; complete_forward_open_rows>0; source/capture clock retained; row-level sale/cutoff verification still required",
                        "provenance_grade": "IMMUTABLE_FORWARD_CAPTURE_CONDITIONAL",
                        "classification_reason": "only the declared forward-complete-open subset is eligible; terminal/backfill rows remain excluded",
                    })
                    output["integration_decisions.csv"].append({
                        "scope_level": "bundle_subset",
                        **_asset_base(reference),
                        "table_name": "",
                        "field_name": "",
                        "market": row["market"],
                        "integration_decision": "INTEGRATE_STRICT",
                        "destination_layer": "strict_asof_v1",
                        "lineage_fields": "bundle logical ID; SHA256SUMS identity; issue; playid; capture batch",
                        "required_transforms": "filter forward_complete_open; retain capture/source clocks and sale state; block terminal/backfill rows",
                        "deduplication_key": "issue;match_id;market;outcome;capture_batch",
                        "timestamp_grade": "IMMUTABLE_FORWARD_CAPTURE_CONDITIONAL",
                        "limitations": "not a blanket family-level promotion; row-level cutoff and sale eligibility remain mandatory",
                    })

    # The #37 finding is a fixed external dependency and must override any
    # generic field-name heuristic in this broader audit.
    for reference in references:
        if reference.asset_id not in drifted_before and reference.asset_id.endswith("derived-beidan-xlsm-beidan-xlsm-sqlite"):
            admissible, integration = _p42_override(reference)
            output["admissible_use_matrix.csv"].append(admissible)
            output["integration_decisions.csv"].append(integration)
            output["market_outcome_schemas.csv"].append({
                **_asset_base(reference),
                "table_name": "exotic_odds",
                "market": "correct_score",
                "outcome_field": "outcome",
                "outcome_value": "HISTORICAL_26_WAY_NOT_MECHANICALLY_CURRENT_P42_25_WAY",
                "row_count": "",
                "distinct_match_count": "",
                "schema_status": "SCORE_PRICE_HIST_AUDIT_001_ACCEPTED_OVERRIDE",
                "schema_note": "presence does not establish provider, Beijing p42 market identity, or row-level observation time; no replay/proxy price use is authorized",
            })
            break

    output["research_view_design.csv"].extend(_view_rows())
    output["market_outcome_schemas.csv"].extend(_target_contract_schema_rows())
    output["model_readiness_matrix.csv"].extend(_readiness_rows(market_context))

    # A second identity check removes all structural evidence for any source
    # that changed during the read.  That preserves a useful audit of stable
    # assets without silently mixing an active live database into it.
    observed_end = build_source_inventory(repository_root=source_root, runtime_inputs=runtime_inputs)
    drifted_after = _drifted_asset_ids(inventory_rows, observed_end)
    drifted_assets = drifted_before | drifted_after
    frozen_asset_ids = {str(row["logical_asset_id"]) for row in inventory_rows}
    newly_discovered_after_g0 = sorted(
        str(row["logical_asset_id"])
        for row in observed_end
        if str(row["logical_asset_id"]) not in frozen_asset_ids
    )
    if drifted_assets:
        for name, rows in output.items():
            if name == "source_inventory.csv":
                continue
            output[name] = [
                row for row in rows
                if str(row.get("logical_asset_id", "")) not in drifted_assets
            ]
        references_by_id = {reference.asset_id: reference for reference in references}
        for asset_id in sorted(drifted_assets):
            coverage, admissible, integration = _source_drift_rows(
                references_by_id[asset_id],
                phase="before audit" if asset_id in drifted_before else "during audit",
            )
            output["coverage_by_period.csv"].append(coverage)
            output["admissible_use_matrix.csv"].append(admissible)
            output["integration_decisions.csv"].append(integration)

    inventory_ref = _inventory_reference(package)
    audit_report = {
        "schema_version": CENSUS_SCHEMA,
        "audit_id": AUDIT_ID,
        "git_commit": _full_git_commit(git_commit),
        "phase": "G1_PLUS_READ_ONLY_CENSUS",
        "source_inventory_sha256": expected_inventory_identity,
        **inventory_ref,
        "source_count": len(inventory_rows),
        "bundle_count": len(output["bundle_integrity.csv"]),
        "database_assets_profiled": sum(reference.kind == "sqlite_database" for reference in references),
        "scope_boundary": "Data archaeology and admissible-use classification only; no model fitting, prediction, calibration, backtest, EV, q, ROI, ticket, stake, selection or strategy conclusion.",
        "score_price_hist_dependency": "incorporated_without_reinterpretation: historical correct-score price replay remains prohibited",
        "source_identity_verified_before_and_after": not drifted_assets,
        "mixed_source_evidence_blocked": True,
        "source_drifted_asset_count": len(drifted_assets),
        "source_drifted_logical_asset_ids": sorted(drifted_assets),
        "new_unfrozen_asset_count": len(newly_discovered_after_g0),
        "new_unfrozen_logical_asset_ids": newly_discovered_after_g0,
        "stable_asset_count": len(inventory_rows) - len(drifted_assets),
    }
    config = {
        "schema_version": CENSUS_SCHEMA,
        "audit_id": AUDIT_ID,
        "read_only": True,
        "inventory_freeze_required": True,
        "workbook_macros_executed": False,
        "source_payloads_published": False,
        "source_paths_published": False,
        "model_or_backtest_enabled": False,
        "roi_authorized": False,
        "strict_view_productionized": False,
        "inventory_source_identity_sha256": expected_inventory_identity,
        **inventory_ref,
    }
    receipt = {
        "schema_version": CENSUS_SCHEMA,
        "audit_id": AUDIT_ID,
        "git_commit": _full_git_commit(git_commit),
        "command_template": (
            "python scripts/run_hist_data_census.py audit --inventory-package <verified-g0-package> "
            "--source-root <main-repository-root> --runtime-input <logical_id>=<runtime-source> "
            "--output-dir <new-census-output> --freeze-dir <new-census-freeze> --frozen-at-utc <explicit-UTC>"
        ),
        "source_inventory_sha256": expected_inventory_identity,
        **inventory_ref,
        "source_identity_verified_before_and_after": not drifted_assets,
        "source_drifted_asset_count": len(drifted_assets),
        "source_drifted_logical_asset_ids": sorted(drifted_assets),
        "new_unfrozen_asset_count": len(newly_discovered_after_g0),
        "new_unfrozen_logical_asset_ids": newly_discovered_after_g0,
        "mixed_source_evidence_blocked": True,
        "public_redaction_verified": True,
        "no_model_or_return_analysis": True,
    }
    result: dict[str, Any] = {name: output[name] for name in REQUIRED_CENSUS_ARTIFACTS if name.endswith(".csv")}
    result["audit_report.json"] = audit_report
    result["census_config.json"] = config
    result["reproducibility_receipt.json"] = receipt
    for name, rows in result.items():
        if name.endswith(".csv"):
            assert_public_redaction(rows, private_paths=[item.path for item in runtime_inputs])
        else:
            assert_public_redaction(rows, private_paths=[item.path for item in runtime_inputs])
    return result


ARTIFACT_COLUMNS: Mapping[str, Sequence[str]] = {
    "source_inventory.csv": INVENTORY_COLUMNS,
    "schema_dictionary.csv": SCHEMA_COLUMNS,
    "coverage_by_period.csv": COVERAGE_COLUMNS,
    "market_outcome_schemas.csv": MARKET_SCHEMA_COLUMNS,
    "timestamp_provenance.csv": TIMESTAMP_COLUMNS,
    "mapping_quality.csv": MAPPING_COLUMNS,
    "feature_availability.csv": FEATURE_COLUMNS,
    "settlement_coverage.csv": SETTLEMENT_COLUMNS,
    "admissible_use_matrix.csv": ADMISSIBLE_COLUMNS,
    "integration_decisions.csv": INTEGRATION_COLUMNS,
    "model_readiness_matrix.csv": READINESS_COLUMNS,
    "bundle_integrity.csv": BUNDLE_COLUMNS,
    "workbook_structure.csv": WORKBOOK_COLUMNS,
    "research_view_design.csv": VIEW_COLUMNS,
}


def write_census_artifacts(output_dir: Path, artifacts: Mapping[str, Any]) -> dict[str, Path]:
    """Write deterministic public evidence files from an in-memory audit."""

    if set(artifacts) != set(REQUIRED_CENSUS_ARTIFACTS):
        raise CensusError("census artifact set does not match the immutable package contract")
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for name in REQUIRED_CENSUS_ARTIFACTS:
        path = output_dir / name
        paths[name] = path
        if name.endswith(".csv"):
            columns = ARTIFACT_COLUMNS[name]
            _write_csv(path, _rows_sorted(artifacts[name], columns), columns)
        else:
            path.write_text(canonical_json(artifacts[name]), encoding="utf-8")
    return paths


def _census_package_decisions(paths: Mapping[str, Path]) -> list[Path]:
    return [
        paths["admissible_use_matrix.csv"],
        paths["integration_decisions.csv"],
        paths["model_readiness_matrix.csv"],
    ]


def create_census_package(
    artifact_paths: Mapping[str, Path],
    *,
    output_dir: Path,
    git_commit: str,
    frozen_at_utc: str,
) -> dict[str, Any]:
    """Package complete public census evidence with exact full-commit binding."""

    _full_git_commit(git_commit)
    if set(artifact_paths) != set(REQUIRED_CENSUS_ARTIFACTS) or any(not path.is_file() for path in artifact_paths.values()):
        raise CensusError("census package requires every required public artifact")
    try:
        return create_freeze_package(
            output_dir,
            experiment_id=CENSUS_EXPERIMENT_ID,
            research_question="Which historical Beijing-lot assets may support strict replay, historical proxy, labels, settlement, or no research input?",
            model_version="hist-data-census-v1",
            input_files=[
                artifact_paths[name]
                for name in (
                    "source_inventory.csv", "schema_dictionary.csv", "coverage_by_period.csv", "market_outcome_schemas.csv",
                    "timestamp_provenance.csv", "mapping_quality.csv", "feature_availability.csv", "settlement_coverage.csv",
                    "bundle_integrity.csv", "workbook_structure.csv", "research_view_design.csv", "audit_report.json",
                )
            ],
            decision_files=_census_package_decisions(artifact_paths),
            config_file=artifact_paths["census_config.json"],
            metadata_files=[artifact_paths["reproducibility_receipt.json"]],
            git_commit=git_commit,
            frozen_at_utc=frozen_at_utc,
        )
    except ResearchFreezeError as exc:
        raise CensusError(str(exc)) from exc


def verify_census_package(
    package_dir: Path,
    *,
    inventory_package: Path | None = None,
    repository_root: Path | None = None,
    runtime_inputs: Sequence[RuntimeInput] = (),
) -> dict[str, Any]:
    """Verify hashes, redaction, full commit binding and optional source replay."""

    package = package_dir.expanduser().resolve()
    try:
        generic = verify_freeze_package(package)
    except ResearchFreezeError as exc:
        raise CensusError(str(exc)) from exc
    if generic.get("experiment_id") != CENSUS_EXPERIMENT_ID:
        raise CensusError("not a HIST-DATA-CENSUS-001 census package")
    try:
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CensusError("census package manifest is invalid") from exc
    commit = str(manifest.get("git_commit", ""))
    _full_git_commit(commit)
    input_paths = {Path(item["path"]).name: package / item["path"] for item in manifest["dataset_snapshot"]["files"]}
    decision_paths = {Path(item["path"]).name: package / item["path"] for item in manifest["frozen_decisions"]}
    config = package / manifest["config"]["path"]
    metadata = {Path(item["path"]).name: package / item["path"] for item in manifest["metadata_files"]}
    expected = set(REQUIRED_CENSUS_ARTIFACTS)
    observed = set(input_paths) | set(decision_paths) | {config.name} | set(metadata)
    if observed != expected:
        raise CensusError("census package artifact membership is incomplete or unexpected")
    public_rows: dict[str, Any] = {}
    for name in REQUIRED_CENSUS_ARTIFACTS:
        path = input_paths.get(name) or decision_paths.get(name) or (config if config.name == name else metadata.get(name))
        if path is None:
            raise CensusError("census package artifact cannot be resolved")
        if name.endswith(".csv"):
            with path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != tuple(ARTIFACT_COLUMNS[name]):
                    raise CensusError("census CSV schema does not match its contract")
                public_rows[name] = [dict(row) for row in reader]
        else:
            try:
                public_rows[name] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CensusError("census package JSON artifact is invalid") from exc
        assert_public_redaction(public_rows[name])
    report = public_rows["audit_report.json"]
    receipt = public_rows["reproducibility_receipt.json"]
    config_payload = public_rows["census_config.json"]
    if report.get("git_commit") != commit or receipt.get("git_commit") != commit:
        raise CensusError("census report/receipt do not bind the package's full git commit")
    if report.get("audit_id") != AUDIT_ID or config_payload.get("audit_id") != AUDIT_ID:
        raise CensusError("census package audit identity mismatch")
    if inventory_package is not None:
        inventory = inventory_package.expanduser().resolve()
        inventory_check = verify_inventory_package(
            inventory,
            repository_root=repository_root,
            runtime_inputs=runtime_inputs,
            verify_current_sources=False,
        )
        inventory_ref = _inventory_reference(inventory)
        if report.get("source_inventory_sha256") != inventory_check["source_inventory_sha256"]:
            raise CensusError("census package does not bind the supplied frozen G0 inventory")
        if report.get("inventory_freeze_id") != inventory_ref["inventory_freeze_id"]:
            raise CensusError("census package inventory freeze reference mismatch")
    current_frozen_source_identity = "NOT_REQUESTED"
    if repository_root is not None:
        frozen_rows = _read_csv(inventory / "inputs" / "source_inventory.csv") if inventory_package is not None else []
        observed = build_source_inventory(repository_root=repository_root, runtime_inputs=runtime_inputs)
        currently_drifted = _drifted_asset_ids(frozen_rows, observed) if frozen_rows else set()
        audited_drifted = set(str(item) for item in report.get("source_drifted_logical_asset_ids", []))
        stable_audited = not (currently_drifted - audited_drifted)
        current_frozen_source_identity = "STABLE_FOR_AUDITED_ASSETS" if stable_audited else "CURRENT_AUDITED_ASSET_DRIFT"
    return {
        "status": "valid",
        "audit_id": AUDIT_ID,
        "git_commit": commit,
        "source_inventory_sha256": report.get("source_inventory_sha256"),
        "artifact_count": len(REQUIRED_CENSUS_ARTIFACTS),
        "inventory_bound": inventory_package is not None,
        "current_frozen_source_identity": current_frozen_source_identity,
        "sha256s_sha256": generic["sha256s_sha256"],
        "manifest_sha256": generic["manifest_sha256"],
    }
