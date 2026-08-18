"""BJ SP timeseries canonical schema (BJ-UNIFIED-BJ-SP-TIMESERIES-001).

Implements the frozen physical design from issue #234
(BJ-UNIFIED-DATA-SOURCE-SCHEMA-001): SQLite WAL append-only capture/control
tables, immutable partitioned Parquet research snapshots. No JSON-blob
probability vectors.

Clock semantics (non-interchangeable, per #234 REQ-DS03):
  - observed_at_utc   : source-supplied native observation time (may be NULL)
  - received_at_utc   : trusted receive time recorded by our own collector
  - decision_at_utc   : decision epoch (the "as-of" instant)
  - kickoff_at_utc    : fixture kickoff
Admissible-use classes: STRICT_CAUSAL | RETROSPECTIVE_PROXY |
SETTLEMENT_ONLY | UNUSABLE.
"""

# outcome domain exactly 3/1/0 (home / draw / away after native line)
OUTCOME_DOMAIN = ("3", "1", "0")

ADMISSIBLE_USE = ("STRICT_CAUSAL", "RETROSPECTIVE_PROXY", "SETTLEMENT_ONLY", "UNUSABLE")

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS source_registry (
    source_id          TEXT PRIMARY KEY,
    provider           TEXT NOT NULL,
    endpoint           TEXT,
    acquisition_method TEXT NOT NULL,
    terms_status       TEXT,
    timezone           TEXT,
    clock_semantics    TEXT NOT NULL,
    cadence_seconds    INTEGER,
    parser_version     TEXT,
    admissible_use     TEXT NOT NULL CHECK (admissible_use IN
        ('STRICT_CAUSAL','RETROSPECTIVE_PROXY','SETTLEMENT_ONLY','UNUSABLE')),
    first_usable_at_utc TEXT,
    last_usable_at_utc  TEXT
);

CREATE TABLE IF NOT EXISTS ingestion_batch (
    batch_id          TEXT PRIMARY KEY,
    source_id         TEXT NOT NULL REFERENCES source_registry(source_id),
    requested_at_utc  TEXT,
    received_at_utc   TEXT,
    raw_uri           TEXT,
    raw_sha256        TEXT,
    parser_version    TEXT,
    row_count         INTEGER,
    status            TEXT
);

CREATE TABLE IF NOT EXISTS fixture (
    fixture_id         TEXT PRIMARY KEY,
    issue_code         TEXT NOT NULL,
    match_idx          INTEGER NOT NULL,
    source_match_key   TEXT,
    competition        TEXT,
    home               TEXT,
    away               TEXT,
    kickoff_at_utc     TEXT,
    native_handicap_line REAL,
    identity_status    TEXT,
    UNIQUE(issue_code, match_idx)
);

CREATE TABLE IF NOT EXISTS market_observation (
    observation_id     TEXT PRIMARY KEY,
    fixture_id         TEXT NOT NULL REFERENCES fixture(fixture_id),
    source_id          TEXT NOT NULL REFERENCES source_registry(source_id),
    market_type        TEXT NOT NULL,
    handicap_line      REAL,
    observed_at_utc    TEXT,
    received_at_utc    TEXT NOT NULL,
    snapshot_kind      TEXT,
    batch_id           TEXT REFERENCES ingestion_batch(batch_id),
    sale_status        TEXT,
    UNIQUE(fixture_id, source_id, observed_at_utc, received_at_utc)
);
CREATE INDEX IF NOT EXISTS idx_obs_fixture ON market_observation(fixture_id);
CREATE INDEX IF NOT EXISTS idx_obs_asof ON market_observation(fixture_id, received_at_utc);

CREATE TABLE IF NOT EXISTS market_quote (
    quote_id           TEXT PRIMARY KEY,
    observation_id     TEXT NOT NULL REFERENCES market_observation(observation_id),
    outcome_code       TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    decimal_odds       REAL,
    quote_status       TEXT,
    UNIQUE(observation_id, outcome_code)
);
CREATE INDEX IF NOT EXISTS idx_quote_obs ON market_quote(observation_id);

CREATE TABLE IF NOT EXISTS decision_epoch (
    decision_epoch_id  TEXT PRIMARY KEY,
    issue_code         TEXT NOT NULL,
    fixture_id         TEXT,
    decision_at_utc    TEXT NOT NULL,
    rule_id            TEXT NOT NULL,
    roster_version     TEXT
);

CREATE TABLE IF NOT EXISTS as_of_selection (
    selection_id       TEXT PRIMARY KEY,
    decision_epoch_id  TEXT NOT NULL REFERENCES decision_epoch(decision_epoch_id),
    fixture_id         TEXT NOT NULL,
    observation_id     TEXT NOT NULL REFERENCES market_observation(observation_id),
    observed_at_utc    TEXT NOT NULL,
    received_at_utc    TEXT NOT NULL,
    staleness_seconds  INTEGER NOT NULL,
    complete           INTEGER NOT NULL CHECK (complete IN (0,1)),
    UNIQUE(decision_epoch_id, fixture_id)
);

CREATE TABLE IF NOT EXISTS probability_estimate (
    estimate_id        TEXT PRIMARY KEY,
    fixture_id         TEXT NOT NULL,
    decision_epoch_id  TEXT,
    estimator_id       TEXT NOT NULL,
    market_type        TEXT,
    handicap_line      REAL,
    outcome_code       TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    probability        REAL NOT NULL CHECK (probability > 0.0),
    observed_at_utc    TEXT,
    provenance_hash    TEXT
);
CREATE INDEX IF NOT EXISTS idx_prob_fixture ON probability_estimate(fixture_id);

CREATE TABLE IF NOT EXISTS settlement (
    fixture_id         TEXT PRIMARY KEY,
    issue_code         TEXT,
    result_code        TEXT,
    winning_sp         REAL,
    settled_at_utc     TEXT,
    source_id          TEXT
);

CREATE TABLE IF NOT EXISTS exclusion_ledger (
    exclusion_id       TEXT PRIMARY KEY,
    fixture_id         TEXT,
    source_id          TEXT,
    issue_code         TEXT,
    season_year        INTEGER,
    native_handicap_line REAL,
    reason_code        TEXT NOT NULL,
    detail             TEXT,
    raw_count          INTEGER,
    batch_id           TEXT
);

-- REQ-BJ09: historical proxy cells have a relative snapshot bucket rather
-- than fabricated observed/received wall-clock timestamps.
CREATE TABLE IF NOT EXISTS relative_horizon_panel (
    panel_id             TEXT PRIMARY KEY,
    fixture_id           TEXT NOT NULL REFERENCES fixture(fixture_id),
    issue_code           TEXT NOT NULL,
    match_idx            INTEGER NOT NULL,
    native_handicap_line REAL,
    snapshot_bucket      TEXT NOT NULL CHECK (snapshot_bucket IN
        ('initial','10h','1h','final')),
    outcome_code         TEXT NOT NULL CHECK (outcome_code IN ('3','1','0')),
    decimal_odds         REAL,
    availability         TEXT NOT NULL CHECK (availability IN ('present','missing')),
    consensus_n          INTEGER,
    market_type          TEXT NOT NULL,
    source_id            TEXT NOT NULL REFERENCES source_registry(source_id),
    batch_id             TEXT,
    provenance_hash      TEXT NOT NULL,
    UNIQUE(fixture_id, snapshot_bucket, outcome_code, source_id)
);
CREATE INDEX IF NOT EXISTS idx_panel_bucket ON relative_horizon_panel(snapshot_bucket);
CREATE INDEX IF NOT EXISTS idx_panel_issue ON relative_horizon_panel(issue_code);
"""

# Known first-party / internal sources with their clock semantics.
SOURCE_REGISTRY = [
    # --- STRICT_CAUSAL (prospective, trusted receive + native source clock) ---
    dict(source_id="beidan_live_500", provider="500.com BJDC bet page",
         endpoint="https://trade.500.com/bjdc/?expect={issue}",
         acquisition_method="first_party_live_poll", terms_status="public_html",
         timezone="Asia/Shanghai", clock_semantics="trusted_receive",
         cadence_seconds=300, parser_version="live_collector/v0.1.0",
         admissible_use="STRICT_CAUSAL",
         first_usable_at_utc="2026-05-02T00:57:44Z", last_usable_at_utc=None),
    dict(source_id="bjdc_500_xml_34", provider="500.com BJDC live SP XML (playid 34 handicap_3way)",
         endpoint="https://www.500.com/static/public/bjdc/xml/sp/just_{issue}_34.xml",
         acquisition_method="first_party_live_poll", terms_status="public_xml",
         timezone="Asia/Shanghai", clock_semantics="native_source_plus_trusted_receive",
         cadence_seconds=900, parser_version="scrape_500_bjdc/v0.1.0",
         admissible_use="STRICT_CAUSAL",
         first_usable_at_utc="2026-06-29T16:47:31Z", last_usable_at_utc=None),
    # --- RETROSPECTIVE_PROXY (label-based, no exact observation clock) ---
    dict(source_id="beidan_xlsm_archive", provider="internal Excel VBA archive (beidan_xlsm)",
         endpoint="data/derived/beidan_xlsm/beidan_xlsm.sqlite",
         acquisition_method="internal_archive", terms_status="internal",
         timezone="Asia/Shanghai", clock_semantics="label_proxy_initial_10h_1h_final",
         cadence_seconds=None, parser_version="bj232_inspect_xlsm/v1",
         admissible_use="RETROSPECTIVE_PROXY",
         first_usable_at_utc="2014-01-01T00:00:00Z", last_usable_at_utc="2025-12-31T23:59:59Z"),
    dict(source_id="nowscore_history", provider="cp.nowscore.com BJDC SP history",
         endpoint="https://cp.nowscore.com/sp/danchang/{issue}_{midx}_{typeid}.html",
         acquisition_method="third_party_timestamped_archive", terms_status="third_party_public",
         timezone="Asia/Shanghai", clock_semantics="native_source_change_time",
         cadence_seconds=None, parser_version="nowscore_bjdc_sp_history/v1",
         admissible_use="RETROSPECTIVE_PROXY",
         first_usable_at_utc=None, last_usable_at_utc=None),
    dict(source_id="okooo_prekick", provider="okooo BJDC prekick archive",
         endpoint="https://www.okooo.com/",
         acquisition_method="third_party_timestamped_archive", terms_status="third_party_public",
         timezone="Asia/Shanghai", clock_semantics="native_source_change_time",
         cadence_seconds=None, parser_version="okooo_prekick_sp/v1",
         admissible_use="RETROSPECTIVE_PROXY",
         first_usable_at_utc=None, last_usable_at_utc=None),
    # --- SETTLEMENT_ONLY ---
    dict(source_id="beidan_history", provider="beidan_history.db settlement rows",
         endpoint="data/beidan_history.db",
         acquisition_method="internal_archive", terms_status="internal",
         timezone="Asia/Shanghai", clock_semantics="settlement_time",
         cadence_seconds=None, parser_version="bj232_reprobe_hist5/v1",
         admissible_use="SETTLEMENT_ONLY",
         first_usable_at_utc="2024-01-01T00:00:00Z", last_usable_at_utc="2026-08-16T00:00:00Z"),
    dict(source_id="official_500_settlements", provider="500.com kaijiang settlements",
         endpoint="https://zx.500.com/zqdc/kaijiang.php?playid=1&expect={issue}",
         acquisition_method="first_party_settlement_poll", terms_status="public_html",
         timezone="Asia/Shanghai", clock_semantics="settlement_time",
         cadence_seconds=None, parser_version="live_collector/v0.1.0",
         admissible_use="SETTLEMENT_ONLY",
         first_usable_at_utc="2014-01-01T00:00:00Z", last_usable_at_utc=None),
    # --- UNUSABLE for inference (no clock at all) ---
    dict(source_id="beidan_features", provider="beidan_features.db EU probability features",
         endpoint="data/beidan_features.db",
         acquisition_method="internal_archive", terms_status="internal",
         timezone="Asia/Shanghai", clock_semantics="no_observation_clock",
         cadence_seconds=None, parser_version="bj232_reprobe/v1",
         admissible_use="UNUSABLE",
         first_usable_at_utc=None, last_usable_at_utc=None),
]

# Decision-epoch rules supported by the as-of replay.
# rule_id -> description of deterministic selection semantics.
DECISION_RULES = {
    "asof_latest_complete_pre_kickoff_v1": (
        "latest complete 3/1/0 triplet with observed/received time <= decision_at "
        "< kickoff_at; ties broken by (received_at, observation_id); bounded "
        "staleness window per rule parameter."
    ),
}
