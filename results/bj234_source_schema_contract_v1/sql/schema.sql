-- BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v2 (candidate mode, EV R1 rework)
-- Versioned physical schema frozen by Issue #234 (Engineer, M1, parent #232).
-- SQLite in WAL mode; one-writer append-only capture/control tables.
-- All timestamps are timezone-aware UTC text (ISO-8601 with Z).
-- outcome_code domain is exactly '3' / '1' / '0' after explicit mapping.
-- The Beijing 0.65 payout coefficient is absent from every table here; it
-- exists only in downstream ticket settlement metadata.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- source_registry: every source carries one admissible-use class, clock
-- semantics, coverage grade and raw-content hash receipt (REQ-DS01/DS07).
-- raw_sha256 MUST be a resolvable receipt for STRICT_CAUSAL sources; empty
-- is rejected (v2: evidence, not prose).
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
    raw_sha256           TEXT NOT NULL CHECK (raw_sha256 != ''),
    notes                TEXT NOT NULL DEFAULT '',
    -- STRICT_CAUSAL requires a trusted UTC clock (logical implication)
    CHECK (admissible_use != 'STRICT_CAUSAL' OR clock_semantics = 'TIMESTAMPED_UTC')
);

-- ---------------------------------------------------------------------------
-- ingestion_batch: raw content receipt per fetch (raw_uri + raw_sha256).
-- requested_at_utc <= received_at_utc is a same-row CHECK (REQ-DS03).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_batch (
    batch_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id          TEXT NOT NULL REFERENCES source_registry(source_id),
    requested_at_utc   TEXT NOT NULL CHECK (requested_at_utc GLOB '????-??-??T??:??:??Z'),
    received_at_utc    TEXT NOT NULL CHECK (received_at_utc GLOB '????-??-??T??:??:??Z'),
    raw_uri            TEXT NOT NULL,
    raw_sha256         TEXT NOT NULL CHECK (raw_sha256 != ''),
    parser_version     TEXT NOT NULL,
    row_count          INTEGER NOT NULL CHECK (row_count >= 0),
    status             TEXT NOT NULL CHECK (status IN ('OK','PARTIAL','FAILED')),
    CHECK (requested_at_utc <= received_at_utc)
);

-- ---------------------------------------------------------------------------
-- team / team_alias : canonical team identity + source-key aliases with
-- non-overlapping validity windows (REQ-DS02).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team (
    team_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS team_alias (
    source_id       TEXT NOT NULL REFERENCES source_registry(source_id),
    source_team_key TEXT NOT NULL,
    team_id         INTEGER NOT NULL REFERENCES team(team_id),
    valid_from_utc  TEXT NOT NULL CHECK (valid_from_utc GLOB '????-??-??T??:??:??Z'),
    valid_to_utc    TEXT CHECK (valid_to_utc IS NULL OR (valid_to_utc GLOB '????-??-??T??:??:??Z')),
    PRIMARY KEY (source_id, source_team_key, valid_from_utc),
    CHECK (valid_to_utc IS NULL OR valid_from_utc < valid_to_utc)
);

-- no-overlap guarantee for team_alias validity windows (REQ-DS02 alias rules)
CREATE TRIGGER IF NOT EXISTS trg_team_alias_no_overlap
BEFORE INSERT ON team_alias
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM team_alias AS existing
    WHERE existing.source_id = NEW.source_id
      AND existing.source_team_key = NEW.source_team_key
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;

CREATE TRIGGER IF NOT EXISTS trg_team_alias_no_overlap_update
BEFORE UPDATE OF valid_from_utc, valid_to_utc ON team_alias
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM team_alias AS existing
    WHERE existing.rowid != NEW.rowid
      AND existing.source_id = NEW.source_id
      AND existing.source_team_key = NEW.source_team_key
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;


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
    valid_from_utc          TEXT NOT NULL CHECK (valid_from_utc GLOB '????-??-??T??:??:??Z'),
    valid_to_utc            TEXT CHECK (valid_to_utc IS NULL OR (valid_to_utc GLOB '????-??-??T??:??:??Z')),
    PRIMARY KEY (source_id, source_competition_key, valid_from_utc),
    CHECK (valid_to_utc IS NULL OR valid_from_utc < valid_to_utc)
);

-- no-overlap guarantee for competition_alias validity windows (REQ-DS02 alias rules)
CREATE TRIGGER IF NOT EXISTS trg_competition_alias_no_overlap
BEFORE INSERT ON competition_alias
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM competition_alias AS existing
    WHERE existing.source_id = NEW.source_id
      AND existing.source_competition_key = NEW.source_competition_key
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;

CREATE TRIGGER IF NOT EXISTS trg_competition_alias_no_overlap_update
BEFORE UPDATE OF valid_from_utc, valid_to_utc ON competition_alias
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM competition_alias AS existing
    WHERE existing.rowid != NEW.rowid
      AND existing.source_id = NEW.source_id
      AND existing.source_competition_key = NEW.source_competition_key
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;


-- ---------------------------------------------------------------------------
-- fixture: canonical identity unique within issue_code x match_idx (REQ-DS02).
-- source_match_key is the primary-capture key; additional provider aliases
-- live in fixture_alias (v2: multi-provider aliases are first-class).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixture (
    fixture_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_code            TEXT NOT NULL,
    match_idx             INTEGER NOT NULL,
    source_match_key      TEXT NOT NULL,
    competition_id        INTEGER NOT NULL REFERENCES competition(competition_id),
    home_team_id          INTEGER NOT NULL REFERENCES team(team_id),
    away_team_id          INTEGER NOT NULL REFERENCES team(team_id),
    kickoff_at_utc        TEXT NOT NULL CHECK (kickoff_at_utc GLOB '????-??-??T??:??:??Z'),
    native_handicap_line  REAL,
    sale_cutoff_at_utc    TEXT CHECK (sale_cutoff_at_utc IS NULL OR (sale_cutoff_at_utc GLOB '????-??-??T??:??:??Z')),
    identity_status       TEXT NOT NULL CHECK (identity_status IN (
        'CANONICAL','ALIAS','AMBIGUOUS','UNIDENTIFIED')),
    UNIQUE (issue_code, match_idx)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_fixture_issue_idx
    ON fixture(issue_code, match_idx);

-- ---------------------------------------------------------------------------
-- fixture_alias: one canonical fixture may be referenced by many providers
-- (v2 C3 fix).  source_match_key + source_id -> fixture_id.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fixture_alias (
    fixture_alias_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id        INTEGER NOT NULL REFERENCES fixture(fixture_id),
    source_id         TEXT NOT NULL REFERENCES source_registry(source_id),
    source_match_key  TEXT NOT NULL,
    valid_from_utc    TEXT NOT NULL CHECK (valid_from_utc GLOB '????-??-??T??:??:??Z'),
    valid_to_utc      TEXT CHECK (valid_to_utc IS NULL OR (valid_to_utc GLOB '????-??-??T??:??:??Z')),
    CHECK (valid_to_utc IS NULL OR valid_from_utc < valid_to_utc)
);

-- no-overlap guarantee for fixture_alias validity windows (REQ-DS02 alias rules)
CREATE TRIGGER IF NOT EXISTS trg_fixture_alias_no_overlap
BEFORE INSERT ON fixture_alias
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM fixture_alias AS existing
    WHERE existing.fixture_id = NEW.fixture_id
      AND existing.source_id = NEW.source_id
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;

CREATE TRIGGER IF NOT EXISTS trg_fixture_alias_no_overlap_update
BEFORE UPDATE OF valid_from_utc, valid_to_utc ON fixture_alias
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM fixture_alias AS existing
    WHERE existing.rowid != NEW.rowid
      AND existing.fixture_id = NEW.fixture_id
      AND existing.source_id = NEW.source_id
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;

-- plus a unique active alias per (fixture, source)
CREATE UNIQUE INDEX IF NOT EXISTS ux_fixture_alias_active
    ON fixture_alias(fixture_id, source_id) WHERE valid_to_utc IS NULL;

-- ---------------------------------------------------------------------------
-- decision_epoch: frozen per-issue decision time (REQ-DS03).  A trigger
-- guarantees decision_at_utc <= kickoff_at_utc of every fixture in the issue.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS decision_epoch (
    decision_epoch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    issue_code        TEXT NOT NULL UNIQUE,
    decision_at_utc   TEXT NOT NULL CHECK (decision_at_utc GLOB '????-??-??T??:??:??Z'),
    rule_id           TEXT NOT NULL,
    roster_version    TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- market_observation / market_quote : normalized Mx3 cells (REQ-DS04).
-- v2: natural-key UNIQUE on primitive observation; quote PK includes
-- bookmaker_id; timestamps canonical + ordered; no 0.65 anywhere.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS market_observation (
    observation_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    fixture_id       INTEGER NOT NULL REFERENCES fixture(fixture_id),
    source_id        TEXT NOT NULL REFERENCES source_registry(source_id),
    market_type      TEXT NOT NULL CHECK (market_type IN ('euro_1x2','sp_1x2','asian_hcap')),
    handicap_line    REAL,
    observed_at_utc  TEXT NOT NULL CHECK (observed_at_utc GLOB '????-??-??T??:??:??Z'),
    received_at_utc  TEXT NOT NULL CHECK (received_at_utc GLOB '????-??-??T??:??:??Z'),
    snapshot_kind    TEXT NOT NULL CHECK (snapshot_kind IN ('initial','10h','1h','final','live')),
    batch_id         INTEGER NOT NULL REFERENCES ingestion_batch(batch_id),
    CHECK (observed_at_utc <= received_at_utc)
);

-- primitive observation natural key: same fixture/source/market/line observed
-- and received at the same instants with the same snapshot label is one row
-- (v2: re-ingestion of the same primitive is rejected).
CREATE UNIQUE INDEX IF NOT EXISTS ux_observation_natural_key
    ON market_observation(
        fixture_id, source_id, market_type,
        COALESCE(handicap_line, -999.0),
        observed_at_utc, received_at_utc, snapshot_kind
    );

CREATE TABLE IF NOT EXISTS market_quote (
    observation_id INTEGER NOT NULL REFERENCES market_observation(observation_id),
    bookmaker_id   TEXT NOT NULL,
    outcome_code   TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    decimal_odds   REAL NOT NULL CHECK (decimal_odds > 1.0),
    quote_status   TEXT NOT NULL CHECK (quote_status IN ('LIVE','CLOSED','VOID')),
    PRIMARY KEY (observation_id, bookmaker_id, outcome_code)
);

-- at most three quotes per observation+bookmaker (defense in depth; the
-- append boundary enforces exactly-3 completeness, see design notes).
CREATE TRIGGER IF NOT EXISTS trg_quote_max_three
AFTER INSERT ON market_quote
FOR EACH ROW
WHEN (SELECT COUNT(*) FROM market_quote
      WHERE observation_id = NEW.observation_id
        AND bookmaker_id = NEW.bookmaker_id) > 3
BEGIN
    SELECT RAISE(ABORT, 'more than three quotes per Mx3 cell');
END;

-- completeness view: observations whose quote set is not exactly (3, 1, 0)
-- per bookmaker (semantic verifier runs this against any real database).
CREATE VIEW IF NOT EXISTS v_incomplete_triplets AS
SELECT q.observation_id, q.bookmaker_id,
       COUNT(*) AS quote_count,
       GROUP_CONCAT(q.outcome_code, ',') AS outcome_codes
FROM market_quote q
GROUP BY q.observation_id, q.bookmaker_id
HAVING COUNT(*) <> 3
   OR COUNT(DISTINCT q.outcome_code) <> 3;

-- ---------------------------------------------------------------------------
-- probability_estimate: long-form scalar triplets keyed by match/outcome.
-- v2: COALESCE expression index — nullable handicap_line (euro cell) cannot
-- be duplicated under SQLite NULL-distinct semantics.
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
    uncertainty         REAL CHECK (uncertainty IS NULL OR uncertainty >= 0.0),
    observed_at_utc     TEXT NOT NULL CHECK (observed_at_utc GLOB '????-??-??T??:??:??Z'),
    calibration_version TEXT NOT NULL,
    provenance_hash     TEXT NOT NULL
);

-- one probability per (fixture, estimator, target_market, outcome) per epoch;
-- COALESCE maps NULL handicap to -999 so euro cells collide correctly.
CREATE UNIQUE INDEX IF NOT EXISTS ux_probability_cell
    ON probability_estimate(
        fixture_id, decision_epoch_id, estimator_id, target_market,
        COALESCE(handicap_line, -999.0), outcome_code
    );

-- ---------------------------------------------------------------------------
-- settlement : physically separate namespace (REQ-DS05) — after-event truth,
-- never an inference-time observation.  settled_at_utc >= kickoff is
-- enforced by trigger; result_code domain is 3/1/0; no 0.65.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settlement (
    fixture_id      INTEGER NOT NULL REFERENCES fixture(fixture_id),
    result_code     TEXT NOT NULL CHECK (result_code IN ('3','1','0')),
    winning_sp      REAL,
    settled_at_utc  TEXT NOT NULL CHECK (settled_at_utc GLOB '????-??-??T??:??:??Z'),
    source_id       TEXT NOT NULL REFERENCES source_registry(source_id),
    PRIMARY KEY (fixture_id, source_id)
);

-- ---------------------------------------------------------------------------
-- Cross-table temporal triggers (REQ-DS03): observed/decision before kickoff,
-- settlement after kickoff.
-- ---------------------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS trg_observation_before_kickoff
BEFORE INSERT ON market_observation
FOR EACH ROW
WHEN (SELECT kickoff_at_utc FROM fixture WHERE fixture_id = NEW.fixture_id) < NEW.observed_at_utc
BEGIN
    SELECT RAISE(ABORT, 'observation after kickoff');
END;

CREATE TRIGGER IF NOT EXISTS trg_decision_before_kickoff
BEFORE INSERT ON decision_epoch
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM fixture
    WHERE issue_code = NEW.issue_code
      AND kickoff_at_utc < NEW.decision_at_utc
)
BEGIN
    SELECT RAISE(ABORT, 'decision epoch after kickoff');
END;

CREATE TRIGGER IF NOT EXISTS trg_settlement_after_kickoff
BEFORE INSERT ON settlement
FOR EACH ROW
WHEN (SELECT kickoff_at_utc FROM fixture WHERE fixture_id = NEW.fixture_id) > NEW.settled_at_utc
BEGIN
    SELECT RAISE(ABORT, 'settlement before kickoff');
END;
