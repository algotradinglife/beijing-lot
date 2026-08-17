"""Issue #234 — versioned SQL DDL for the canonical physical schema.

The canonical physical design (REQ-DS04/DS05/DS06):

- **SQLite in WAL mode** for one-writer append-only capture/control tables;
- **immutable partitioned Parquet** for research snapshots read by
  pandas/PyArrow;
- physically separate namespaces: ``inference`` (probability_estimate
  projection), ``proxy`` (RETROSPECTIVE_PROXY projections) and
  ``settlement`` (settlement truth) — REQ-DS05;
- ``outcome_code`` domain exactly ``3/1/0`` after explicit mapping; the
  Beijing ``0.65`` payout coefficient is absent from all source, quote and
  probability tables (REQ-DS03/DS04).

This module emits the versioned DDL text and the pandas/PyArrow schema
contract, both frozen with the package.
"""

from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# SQLite capture/control DDL (versioned, WAL, one-writer append-only)
# ---------------------------------------------------------------------------
DDL_VERSION = "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001-ddl-v1"

DDL_HEADER = """-- BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (candidate mode)
-- Versioned physical schema frozen by Issue #234 (Engineer, M1, parent #232).
-- SQLite in WAL mode; one-writer append-only capture/control tables.
-- All timestamps are timezone-aware UTC text (ISO-8601 with Z).
-- outcome_code domain is exactly '3' / '1' / '0' after explicit mapping.
-- The Beijing 0.65 payout coefficient is absent from every table here; it
-- exists only in downstream ticket settlement metadata.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
"""

DDL_TABLES = """
-- ---------------------------------------------------------------------------
-- source_registry: every source carries one admissible-use class, clock
-- semantics, coverage grade and raw-content hash receipt (REQ-DS01/DS07).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS source_registry (
    source_id            TEXT PRIMARY KEY,
    provider             TEXT NOT NULL,
    endpoint             TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    terms_status         TEXT NOT NULL,
    timezone             TEXT NOT NULL,
    clock_semantics      TEXT NOT NULL CHECK (clock_semantics IN (
        'TIMESTAMPED_UTC','TIMESTAMPED_LOCAL_NO_TZ','LABEL_RELATIVE',
        'SCHEDULE_ONLY','SETTLEMENT_AFTER_EVENT','NO_CLOCK')),
    cadence_seconds      TEXT NOT NULL,
    parser_version       TEXT NOT NULL,
    admissible_use       TEXT NOT NULL CHECK (admissible_use IN (
        'STRICT_CAUSAL','RETROSPECTIVE_PROXY','SETTLEMENT_ONLY','UNUSABLE')),
    first_usable_at_utc  TEXT NOT NULL,
    last_usable_at_utc   TEXT NOT NULL,
    coverage_grade       TEXT NOT NULL CHECK (coverage_grade IN ('A','B','C','D','F')),
    raw_sha256           TEXT NOT NULL DEFAULT '',
    notes                TEXT NOT NULL DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- ingestion_batch: raw content receipt per fetch (raw_uri + raw_sha256).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_batch (
    batch_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id          TEXT NOT NULL REFERENCES source_registry(source_id),
    requested_at_utc   TEXT NOT NULL,
    received_at_utc    TEXT NOT NULL,
    raw_uri            TEXT NOT NULL,
    raw_sha256         TEXT NOT NULL,
    parser_version     TEXT NOT NULL,
    row_count          INTEGER NOT NULL CHECK (row_count >= 0),
    status             TEXT NOT NULL CHECK (status IN ('OK','PARTIAL','FAILED'))
);

-- ---------------------------------------------------------------------------
-- team / team_alias : canonical team identity + source-key aliases.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team (
    team_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS team_alias (
    source_id       TEXT NOT NULL REFERENCES source_registry(source_id),
    source_team_key TEXT NOT NULL,
    team_id         INTEGER NOT NULL REFERENCES team(team_id),
    valid_from_utc  TEXT NOT NULL,
    valid_to_utc    TEXT,
    PRIMARY KEY (source_id, source_team_key, valid_from_utc)
);

-- one active alias window per (source, key)
CREATE UNIQUE INDEX IF NOT EXISTS ux_team_alias_active
    ON team_alias(source_id, source_team_key) WHERE valid_to_utc IS NULL;

-- ---------------------------------------------------------------------------
-- competition / competition_alias
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competition (
    competition_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS competition_alias (
    source_id               TEXT NOT NULL REFERENCES source_registry(source_id),
    source_competition_key  TEXT NOT NULL,
    competition_id          INTEGER NOT NULL REFERENCES competition(competition_id),
    valid_from_utc          TEXT NOT NULL,
    valid_to_utc            TEXT,
    PRIMARY KEY (source_id, source_competition_key, valid_from_utc)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_competition_alias_active
    ON competition_alias(source_id, source_competition_key) WHERE valid_to_utc IS NULL;

-- ---------------------------------------------------------------------------
-- fixture: canonical identity unique within issue_code x match_idx (REQ-DS02).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixture (
    fixture_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_code            TEXT NOT NULL,
    match_idx             INTEGER NOT NULL,
    source_match_key      TEXT NOT NULL,
    competition_id        INTEGER NOT NULL REFERENCES competition(competition_id),
    home_team_id          INTEGER NOT NULL REFERENCES team(team_id),
    away_team_id          INTEGER NOT NULL REFERENCES team(team_id),
    kickoff_at_utc        TEXT NOT NULL,
    native_handicap_line  REAL,
    sale_cutoff_at_utc    TEXT,
    identity_status       TEXT NOT NULL CHECK (identity_status IN (
        'CANONICAL','ALIAS','AMBIGUOUS','UNIDENTIFIED')),
    UNIQUE (issue_code, match_idx)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fixture_issue_idx
    ON fixture(issue_code, match_idx);

-- ---------------------------------------------------------------------------
-- decision_epoch: frozen per-issue decision time (REQ-DS03).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_epoch (
    decision_epoch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_code        TEXT NOT NULL UNIQUE,
    decision_at_utc   TEXT NOT NULL,
    rule_id           TEXT NOT NULL,
    roster_version    TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- market_observation / market_quote : normalized Mx3 cells (REQ-DS04).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_observation (
    observation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id       INTEGER NOT NULL REFERENCES fixture(fixture_id),
    source_id        TEXT NOT NULL REFERENCES source_registry(source_id),
    market_type      TEXT NOT NULL CHECK (market_type IN (
        'euro_1x2','sp_1x2','asian_hcap')),
    handicap_line    REAL,
    observed_at_utc  TEXT NOT NULL,
    received_at_utc  TEXT NOT NULL,
    snapshot_kind    TEXT NOT NULL CHECK (snapshot_kind IN (
        'initial','10h','1h','final')),
    batch_id         INTEGER NOT NULL REFERENCES ingestion_batch(batch_id)
);

CREATE INDEX IF NOT EXISTS ux_observation_fixture_market
    ON market_observation(fixture_id, market_type, observed_at_utc);

CREATE TABLE IF NOT EXISTS market_quote (
    observation_id INTEGER NOT NULL REFERENCES market_observation(observation_id),
    bookmaker_id   TEXT NOT NULL,
    outcome_code   TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    decimal_odds   REAL NOT NULL CHECK (decimal_odds > 1.0),
    quote_status   TEXT NOT NULL CHECK (quote_status IN ('LIVE','CLOSED','VOID')),
    PRIMARY KEY (observation_id, bookmaker_id, outcome_code)
);

-- one complete Mx3 triplet per observation: at most one quote per outcome
-- (REQ-DS04 rejects duplicate cells).
CREATE UNIQUE INDEX IF NOT EXISTS ux_quote_one_per_outcome
    ON market_quote(observation_id, outcome_code);

-- ---------------------------------------------------------------------------
-- probability_estimate: long-form scalar triplets keyed by match/outcome.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS probability_estimate (
    estimate_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id          INTEGER NOT NULL REFERENCES fixture(fixture_id),
    decision_epoch_id   INTEGER NOT NULL REFERENCES decision_epoch(decision_epoch_id),
    estimator_id        TEXT NOT NULL,
    target_market       TEXT NOT NULL CHECK (target_market IN ('euro_1x2','sp_1x2','asian_hcap')),
    handicap_line       REAL,
    outcome_code        TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    probability         REAL NOT NULL CHECK (probability >= 0.0 AND probability <= 1.0),
    uncertainty         REAL,
    observed_at_utc     TEXT NOT NULL,
    calibration_version TEXT NOT NULL,
    provenance_hash     TEXT NOT NULL
);

-- one probability per (fixture, estimator, target_market, outcome) per epoch
CREATE UNIQUE INDEX IF NOT EXISTS ux_probability_cell
    ON probability_estimate(
        fixture_id, decision_epoch_id, estimator_id, target_market, handicap_line, outcome_code
    );

-- ---------------------------------------------------------------------------
-- settlement : physically separate namespace (REQ-DS05) — after-event truth,
-- never an inference-time observation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settlement (
    fixture_id      INTEGER NOT NULL REFERENCES fixture(fixture_id),
    result_code     TEXT NOT NULL CHECK (result_code IN ('3','1','0')),
    winning_sp      REAL,
    settled_at_utc  TEXT NOT NULL,
    source_id       TEXT NOT NULL REFERENCES source_registry(source_id),
    PRIMARY KEY (fixture_id, source_id)
);
"""

# ---------------------------------------------------------------------------
# pandas / PyArrow research snapshot schemas (immutable partitioned Parquet)
# ---------------------------------------------------------------------------
# Namespace -> column -> pyarrow type string.  The builder emits a JSON schema
# contract and a Parquet schema file for each research namespace.
PARQUET_SCHEMAS: dict[str, dict[str, str]] = {
    "inference": {
        "fixture_id": "int64",
        "issue_code": "string",
        "match_idx": "int32",
        "estimator_id": "string",
        "target_market": "string",
        "handicap_line": "double",
        "outcome_code": "string",
        "probability": "double",
        "uncertainty": "double",
        "observed_at_utc": "timestamp[ns, tz=UTC]",
        "decision_epoch_id": "int64",
        "provenance_hash": "string",
    },
    "proxy": {
        "fixture_id": "int64",
        "issue_code": "string",
        "match_idx": "int32",
        "source_id": "string",
        "market_type": "string",
        "snapshot_kind": "string",
        "handicap_line": "double",
        "outcome_code": "string",
        "value": "double",
        "proxy_grade": "string",
    },
    "settlement": {
        "fixture_id": "int64",
        "issue_code": "string",
        "match_idx": "int32",
        "result_code": "string",
        "winning_sp": "double",
        "settled_at_utc": "timestamp[ns, tz=UTC]",
        "source_id": "string",
    },
}


def sql_ddl() -> str:
    """Return the full versioned DDL text."""
    return DDL_HEADER + DDL_TABLES


def parquet_schema_contract() -> dict[str, object]:
    """Return the machine-readable PyArrow schema contract."""
    return {
        "ddl_version": DDL_VERSION,
        "namespaces": PARQUET_SCHEMAS,
        "partitioning": "immutable, partitioned by issue_code/year",
        "reader": "pandas / PyArrow",
    }


def domain_dictionary() -> str:
    """Render the domain dictionary document (markdown)."""
    lines = [
        "# Domain Dictionary (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)",
        "",
        "## outcome_code",
        "",
        "Exactly `3` (home win), `1` (draw), `0` (away win) after explicit "
        "mapping.  Any legacy label (e.g. `3/1/0`, `主/和/客`, `W/D/L`) must be "
        "mapped by an explicit mapping table; unmapped values are rejected by "
        "the schema CHECK constraints (REQ-DS04).",
        "",
        "## market_type",
        "",
        "- `euro_1x2` — European 1X2 decimal odds",
        "- `sp_1x2` — Beijing SP 1X2",
        "- `asian_hcap` — Asian handicap (native line)",
        "",
        "## snapshot_kind",
        "",
        "- `initial`, `10h`, `1h`, `final` — workbook labels.  These are "
        "**labels**, not exact observation timestamps (REQ-DS03); a registry "
        "row using them carries clock_semantics `LABEL_RELATIVE` unless "
        "independently proven.",
        "",
        "## admissible_use (REQ-DS01)",
        "",
        "| class | meaning |",
        "|---|---|",
        "| STRICT_CAUSAL | observed before decision epoch with trusted clock |",
        "| RETROSPECTIVE_PROXY | timestamp semantics insufficient; proxy only |",
        "| SETTLEMENT_ONLY | after-event truth; never inference input |",
        "| UNUSABLE | no clock / no identity / corrupt |",
        "",
        "## clock_semantics (REQ-DS03)",
        "",
        "| value | meaning |",
        "|---|---|",
        "| TIMESTAMPED_UTC | parseable UTC timestamps |",
        "| TIMESTAMPED_LOCAL_NO_TZ | local naive timestamps |",
        "| LABEL_RELATIVE | initial/10h/1h/final labels |",
        "| SCHEDULE_ONLY | kickoff schedule, no observation clock |",
        "| SETTLEMENT_AFTER_EVENT | settlement time only |",
        "| NO_CLOCK | no usable time |",
        "",
        "## identity_status (REQ-DS02)",
        "",
        "CANONICAL / ALIAS / AMBIGUOUS / UNIDENTIFIED — see the identity "
        "crosswalk contract.",
        "",
        "## coverage_grade",
        "",
        "A = full coverage with trusted clock; B = broad coverage with clock "
        "caveats; C = partial coverage or unproven clock; D = narrow or "
        "settlement-only; F = unusable.",
        "",
        "## Payout factor",
        "",
        "The Beijing `0.65` payout coefficient is absent from all source, quote "
        "and probability tables; it exists only in downstream ticket settlement "
        "metadata (frozen contract rule, checked by the builder).",
        "",
    ]
    return "\n".join(lines)


def parquet_schema_json() -> str:
    return json.dumps(parquet_schema_contract(), indent=2, sort_keys=True) + "\n"
