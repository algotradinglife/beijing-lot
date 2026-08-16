-- BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (frozen 2026-08-16)
-- Canonical source registry, identity and temporal store schema.
-- Rendered deterministically from src/source_schema/contract.py.
-- SQLite WAL mode; one-writer append-only capture/control tables;
-- research snapshots are immutable partitioned Parquet (see PyArrow schemas).
-- All timestamps are timezone-aware UTC (ISO-8601 with Z).
-- outcome_code domain is exactly ('3','1','0') after explicit mapping.
-- The Beijing 0.65 coefficient is ABSENT from all source/quote/probability
-- tables; it exists only in downstream ticket settlement metadata.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- namespace: capture
CREATE TABLE IF NOT EXISTS source_registry (
  source_id TEXT NOT NULL PRIMARY KEY,
  provider TEXT NOT NULL,
  endpoint TEXT,
  acquisition_method TEXT NOT NULL,
  terms_status TEXT NOT NULL,
  timezone TEXT NOT NULL,
  clock_semantics TEXT NOT NULL,
  cadence_seconds INTEGER,
  parser_version TEXT NOT NULL,
  admissible_use TEXT NOT NULL,
  first_usable_at_utc TEXT,
  last_usable_at_utc TEXT,
  raw_content_sha256 TEXT,
  coverage_grade TEXT NOT NULL,
  notes TEXT,
  CHECK (admissible_use IN ('STRICT_CAUSAL','RETROSPECTIVE_PROXY','SETTLEMENT_ONLY','UNUSABLE')),
  CHECK (clock_semantics IN ('NATIVE_PROVEN','TRUSTED_FETCH','LABELED_RELATIVE','FILE_MTIME','ABSENT'))
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS ingestion_batch (
  batch_id TEXT NOT NULL PRIMARY KEY,
  source_id TEXT NOT NULL,
  requested_at_utc TEXT NOT NULL,
  received_at_utc TEXT NOT NULL,
  raw_uri TEXT,
  raw_sha256 TEXT NOT NULL,
  parser_version TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES source_registry(source_id),
  CHECK (status IN ('RECEIVED','PARSED','FAILED','REJECTED'))
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS bookmaker (
  bookmaker_id TEXT NOT NULL PRIMARY KEY,
  canonical_name TEXT NOT NULL,
  source_id TEXT NOT NULL,
  FOREIGN KEY (source_id) REFERENCES source_registry(source_id)
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS team (
  team_id TEXT NOT NULL PRIMARY KEY,
  canonical_name TEXT NOT NULL
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS team_alias (
  alias_id TEXT NOT NULL PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_team_key TEXT NOT NULL,
  team_id TEXT NOT NULL,
  valid_from_utc TEXT NOT NULL,
  valid_to_utc TEXT,
  UNIQUE (source_id, source_team_key, valid_from_utc),
  FOREIGN KEY (source_id) REFERENCES source_registry(source_id),
  FOREIGN KEY (team_id) REFERENCES team(team_id)
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS competition (
  competition_id TEXT NOT NULL PRIMARY KEY,
  canonical_name TEXT NOT NULL
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS competition_alias (
  alias_id TEXT NOT NULL PRIMARY KEY,
  source_id TEXT NOT NULL,
  source_competition_key TEXT NOT NULL,
  competition_id TEXT NOT NULL,
  valid_from_utc TEXT NOT NULL,
  valid_to_utc TEXT,
  UNIQUE (source_id, source_competition_key, valid_from_utc),
  FOREIGN KEY (source_id) REFERENCES source_registry(source_id),
  FOREIGN KEY (competition_id) REFERENCES competition(competition_id)
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS fixture (
  fixture_id TEXT NOT NULL PRIMARY KEY,
  issue_code TEXT NOT NULL,
  match_idx INTEGER NOT NULL,
  source_match_key TEXT,
  competition_id TEXT,
  home_team_id TEXT,
  away_team_id TEXT,
  kickoff_at_utc TEXT NOT NULL,
  native_handicap_line REAL,
  sale_cutoff_at_utc TEXT,
  identity_status TEXT NOT NULL,
  UNIQUE (issue_code, match_idx),
  FOREIGN KEY (competition_id) REFERENCES competition(competition_id),
  FOREIGN KEY (home_team_id) REFERENCES team(team_id),
  FOREIGN KEY (away_team_id) REFERENCES team(team_id),
  CHECK (match_idx >= 1),
  CHECK (identity_status IN ('CANONICAL','ALIAS_RESOLVED','UNRESOLVED'))
);

-- namespace: capture
CREATE TABLE IF NOT EXISTS decision_epoch (
  decision_epoch_id TEXT NOT NULL PRIMARY KEY,
  issue_code TEXT NOT NULL,
  decision_at_utc TEXT NOT NULL,
  rule_id TEXT NOT NULL,
  roster_version TEXT
);

-- namespace: inference
CREATE TABLE IF NOT EXISTS market_observation (
  observation_id TEXT NOT NULL PRIMARY KEY,
  fixture_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  market_type TEXT NOT NULL,
  handicap_line REAL,
  observed_at_utc TEXT NOT NULL,
  received_at_utc TEXT NOT NULL,
  snapshot_kind TEXT NOT NULL,
  batch_id TEXT,
  FOREIGN KEY (fixture_id) REFERENCES fixture(fixture_id),
  FOREIGN KEY (source_id) REFERENCES source_registry(source_id),
  FOREIGN KEY (batch_id) REFERENCES ingestion_batch(batch_id),
  CHECK (snapshot_kind IN ('RAW_CAPTURE','RECOVERED_ARCHIVE','PROXY_LABEL','SETTLEMENT_CROSSCHECK'))
);

-- namespace: inference
CREATE TABLE IF NOT EXISTS market_quote (
  quote_id TEXT NOT NULL PRIMARY KEY,
  observation_id TEXT NOT NULL,
  bookmaker_id TEXT,
  outcome_code TEXT NOT NULL,
  decimal_odds REAL NOT NULL,
  quote_status TEXT NOT NULL,
  UNIQUE (observation_id, outcome_code),
  FOREIGN KEY (observation_id) REFERENCES market_observation(observation_id),
  FOREIGN KEY (bookmaker_id) REFERENCES bookmaker(bookmaker_id),
  CHECK (outcome_code IN ('3','1','0')),
  CHECK (decimal_odds > 1.0),
  CHECK (quote_status IN ('VALID','SUSPENDED','INVALID'))
);

-- namespace: inference
CREATE TABLE IF NOT EXISTS probability_estimate (
  estimate_id TEXT NOT NULL PRIMARY KEY,
  fixture_id TEXT NOT NULL,
  decision_epoch_id TEXT NOT NULL,
  estimator_id TEXT NOT NULL,
  target_market TEXT NOT NULL,
  handicap_line REAL,
  outcome_code TEXT NOT NULL,
  probability REAL NOT NULL,
  uncertainty REAL,
  observed_at_utc TEXT NOT NULL,
  calibration_version TEXT NOT NULL,
  provenance_hash TEXT NOT NULL,
  UNIQUE (fixture_id, decision_epoch_id, estimator_id, target_market, handicap_line, outcome_code),
  FOREIGN KEY (fixture_id) REFERENCES fixture(fixture_id),
  FOREIGN KEY (decision_epoch_id) REFERENCES decision_epoch(decision_epoch_id),
  CHECK (outcome_code IN ('3','1','0')),
  CHECK (probability >= 0.0 AND probability <= 1.0),
  CHECK (uncertainty IS NULL OR uncertainty >= 0.0)
);

-- namespace: settlement
CREATE TABLE IF NOT EXISTS settlement (
  settlement_id TEXT NOT NULL PRIMARY KEY,
  fixture_id TEXT NOT NULL,
  result_code TEXT NOT NULL,
  winning_sp REAL,
  settled_at_utc TEXT NOT NULL,
  source_id TEXT NOT NULL,
  UNIQUE (fixture_id, source_id),
  FOREIGN KEY (fixture_id) REFERENCES fixture(fixture_id),
  FOREIGN KEY (source_id) REFERENCES source_registry(source_id),
  CHECK (result_code IN ('3','1','0'))
);
