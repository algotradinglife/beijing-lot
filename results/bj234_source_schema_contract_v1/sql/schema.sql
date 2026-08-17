-- BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (candidate mode)
-- Versioned physical schema frozen by Issue #234 (Engineer, M1, parent #232).
-- SQLite in WAL mode; one-writer append-only capture/control tables.
-- All timestamps are timezone-aware UTC text (ISO-8601 with Z).
-- outcome_code domain is exactly '3' / '1' / '0' after explicit mapping.
-- The Beijing 0.65 payout coefficient is absent from every table here; it
-- exists only in downstream ticket settlement metadata.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;

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
