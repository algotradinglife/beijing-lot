"""Versioned SQLite and PyArrow contract for the prototype M×3 cube.

The contract deliberately stops at the smallest model-facing physical layer:
issue-local slot identity, explicit temporal namespaces, long outcome cells,
and a physically separate settlement store.  It does not pretend that the
available sources identify real-world fixtures, teams, or competitions.
"""

from __future__ import annotations

import json

import pyarrow as pa

CONTRACT_VERSION = "BJ-UNIFIED-PHYSICAL-SCHEMA-001-v1"
PACKAGE_SCHEMA = "bj253_physical_schema_v1"
OUTCOME_CODES = ("3", "1", "0")
NAMESPACES = ("historical_proxy", "strict_forward")

CONTROL_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

CREATE TABLE source_registry (
    source_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL CHECK (namespace IN ('historical_proxy','strict_forward')),
    causal_grade TEXT NOT NULL,
    time_semantics TEXT NOT NULL,
    source_role TEXT NOT NULL,
    source_receipt TEXT NOT NULL
);

CREATE TABLE issue_slot (
    issue_slot_id TEXT PRIMARY KEY,
    issue_code TEXT NOT NULL,
    match_idx INTEGER NOT NULL CHECK (match_idx > 0),
    provider_fixture_id TEXT,
    kickoff_at_utc TEXT NOT NULL,
    identity_status TEXT NOT NULL CHECK (identity_status IN (
        'ISSUE_LOCAL_SLOT','SOURCE_PROVIDER_KEY','UNKNOWN_ALIAS'
    )),
    UNIQUE (issue_code, match_idx)
);

CREATE TABLE play (
    play_id TEXT PRIMARY KEY,
    issue_slot_id TEXT NOT NULL REFERENCES issue_slot(issue_slot_id),
    play_code TEXT NOT NULL CHECK (play_code = 'BJ_HANDICAP_3WAY'),
    UNIQUE (issue_slot_id, play_code)
);

CREATE TABLE outcome_cell (
    outcome_cell_id TEXT PRIMARY KEY,
    play_id TEXT NOT NULL REFERENCES play(play_id),
    issue_slot_id TEXT NOT NULL REFERENCES issue_slot(issue_slot_id),
    outcome_code TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    UNIQUE (play_id, outcome_code)
);

CREATE TABLE observation (
    observation_id TEXT PRIMARY KEY,
    issue_slot_id TEXT NOT NULL REFERENCES issue_slot(issue_slot_id),
    source_id TEXT NOT NULL REFERENCES source_registry(source_id),
    namespace TEXT NOT NULL CHECK (namespace IN ('historical_proxy','strict_forward')),
    snapshot_horizon TEXT NOT NULL CHECK (snapshot_horizon IN ('initial','10h','1h','poll')),
    time_semantics TEXT NOT NULL,
    causal_grade TEXT NOT NULL,
    observed_at_utc TEXT,
    kickoff_at_utc TEXT NOT NULL,
    handicap_line REAL,
    source_event_key TEXT NOT NULL,
    CHECK (
        (namespace = 'historical_proxy' AND observed_at_utc IS NULL
         AND time_semantics = 'SOURCE_RELATIVE_LABEL')
        OR
        (namespace = 'strict_forward' AND observed_at_utc IS NOT NULL
         AND time_semantics = 'POLL_STARTED_AT_UTC')
    )
);

CREATE TABLE feature_cell (
    observation_id TEXT NOT NULL REFERENCES observation(observation_id),
    outcome_cell_id TEXT NOT NULL REFERENCES outcome_cell(outcome_cell_id),
    feature_name TEXT NOT NULL CHECK (feature_name IN ('eu_decimal_odds','bj_sp')),
    value REAL,
    availability_mask INTEGER NOT NULL CHECK (availability_mask IN (0,1)),
    missing_reason TEXT,
    provenance_hash TEXT NOT NULL,
    PRIMARY KEY (observation_id, outcome_cell_id, feature_name),
    CHECK (
        (availability_mask = 1 AND value IS NOT NULL AND missing_reason IS NULL)
        OR
        (availability_mask = 0 AND value IS NULL AND missing_reason IS NOT NULL)
    )
);

CREATE TABLE snapshot_manifest (
    snapshot_id TEXT PRIMARY KEY,
    issue_code TEXT NOT NULL,
    namespace TEXT NOT NULL CHECK (namespace IN ('historical_proxy','strict_forward')),
    snapshot_horizon TEXT NOT NULL,
    decision_at_utc TEXT,
    segment_id TEXT,
    rule_version TEXT NOT NULL
);
"""

LABELS_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;

CREATE TABLE settlement_label (
    issue_slot_id TEXT PRIMARY KEY,
    issue_code TEXT NOT NULL,
    match_idx INTEGER NOT NULL CHECK (match_idx > 0),
    result_code TEXT NOT NULL CHECK (result_code IN ('3','1','0')),
    winning_sp REAL,
    settled_at_utc TEXT NOT NULL,
    source_id TEXT NOT NULL,
    provenance_hash TEXT NOT NULL,
    UNIQUE (issue_code, match_idx)
);
"""


def feature_schema() -> pa.Schema:
    """Long analytical feature schema shared by both temporal namespaces."""
    return pa.schema(
        [
            pa.field("issue_slot_id", pa.string(), nullable=False),
            pa.field("issue_code", pa.string(), nullable=False),
            pa.field("match_idx", pa.int32(), nullable=False),
            pa.field("play_code", pa.string(), nullable=False),
            pa.field("outcome_code", pa.string(), nullable=False),
            pa.field("observation_id", pa.string(), nullable=False),
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("namespace", pa.string(), nullable=False),
            pa.field("snapshot_horizon", pa.string(), nullable=False),
            pa.field("time_semantics", pa.string(), nullable=False),
            pa.field("causal_grade", pa.string(), nullable=False),
            pa.field("observed_at_utc", pa.timestamp("ns", tz="UTC"), nullable=True),
            pa.field("kickoff_at_utc", pa.timestamp("ns", tz="UTC"), nullable=False),
            pa.field("handicap_line", pa.float64(), nullable=True),
            pa.field("feature_name", pa.string(), nullable=False),
            pa.field("value", pa.float64(), nullable=True),
            pa.field("availability_mask", pa.bool_(), nullable=False),
            pa.field("missing_reason", pa.string(), nullable=True),
            pa.field("provenance_hash", pa.string(), nullable=False),
        ]
    )


def label_schema() -> pa.Schema:
    """Physically separate post-event label schema."""
    return pa.schema(
        [
            pa.field("issue_slot_id", pa.string(), nullable=False),
            pa.field("issue_code", pa.string(), nullable=False),
            pa.field("match_idx", pa.int32(), nullable=False),
            pa.field("result_code", pa.string(), nullable=False),
            pa.field("winning_sp", pa.float64(), nullable=True),
            pa.field("settled_at_utc", pa.timestamp("ns", tz="UTC"), nullable=False),
            pa.field("source_id", pa.string(), nullable=False),
            pa.field("provenance_hash", pa.string(), nullable=False),
        ]
    )


def schema_payload() -> dict[str, object]:
    """Portable JSON representation committed with the delivery."""
    def fields(schema: pa.Schema) -> list[dict[str, object]]:
        return [
            {"name": field.name, "type": str(field.type), "nullable": field.nullable}
            for field in schema
        ]

    return {
        "contract_version": CONTRACT_VERSION,
        "row_grain": "issue_code × match_idx × outcome_code × observation × feature_name",
        "outcome_codes": list(OUTCOME_CODES),
        "namespaces": list(NAMESPACES),
        "feature_cells": fields(feature_schema()),
        "settlement_labels": fields(label_schema()),
        "label_separation": "separate SQLite database and separate Parquet namespace",
        "canonical_entity_policy": "nullable/unavailable; never inferred from labels",
    }


def schema_json() -> str:
    return json.dumps(schema_payload(), indent=2, sort_keys=True) + "\n"
