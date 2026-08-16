"""Issue #234 — versioned SQL DDL for the canonical physical schema (v2).

v2 rework addresses the EV R1 defect class C3:

- ``fixture_alias`` exists so one canonical fixture can hold multiple
  provider match aliases (the old ``fixture.source_match_key`` alone could
  not; it is retained as the primary-capture key).
- ``market_quote`` PK is ``(observation_id, bookmaker_id, outcome_code)`` and
  there is **no** unique index that erases ``bookmaker_id`` (the v1
  ``ux_quote_one_per_outcome`` index is removed).  Multi-bookmaker European
  feeds are legal.
- ``probability_estimate`` uniqueness uses a COALESCE expression index so the
  nullable ``handicap_line`` (euro cell) cannot be duplicated under SQLite
  NULL-distinct semantics.
- Primitive ``market_observation`` rows have a natural-key UNIQUE index
  (fixture/source/market/line/observed/received/snapshot_kind); re-ingesting
  the same primitive observation is rejected.
- Mx3 triplet completeness is enforced at the canonical append boundary (the
  write path inserts all three outcome rows in one transaction) and verified
  by ``v_incomplete_triplets`` + the semantic verifier.  SQLite has no
  deferred cross-row CHECK; the decision is documented in design_notes.md.
- ``PRAGMA foreign_keys = ON`` is emitted and the verifier executes the DDL
  with FK enforcement to prove orphan quotes cannot be written.
- Timestamp CHECKs enforce canonical UTC shape, observed<=received,
  requested<=received; cross-table ordering (observed<=kickoff,
  decision<=kickoff, settled>=kickoff) is enforced by triggers.
- Alias validity windows (team/competition/fixture) are no-overlap enforced
  by BEFORE INSERT/UPDATE triggers (SQLite lacks exclusion constraints).

All timestamps are timezone-aware UTC text (ISO-8601 with Z).  outcome_code
domain is exactly '3'/'1'/'0' after explicit mapping.  The Beijing 0.65
payout coefficient is absent from every table here.
"""

from __future__ import annotations

import json

from . import contract

DDL_VERSION = contract.DDL_VERSION

DDL_HEADER = f"""-- {contract.CONTRACT_VERSION} / v2 ({contract.CONTRACT_MODE} mode, EV R1 rework)
-- Versioned physical schema frozen by Issue #234 (Engineer, M1, parent #232).
-- SQLite in WAL mode; one-writer append-only capture/control tables.
-- All timestamps are timezone-aware UTC text (ISO-8601 with Z).
-- outcome_code domain is exactly '3' / '1' / '0' after explicit mapping.
-- The Beijing 0.65 payout coefficient is absent from every table here; it
-- exists only in downstream ticket settlement metadata.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;
PRAGMA foreign_keys = ON;
"""

# SQL fragments reused by multiple constraints ---------------------------------
_UTC_TS = "GLOB '" + contract.UTC_TS_GLOB + "'"
_OUTCOME_CHECK = "outcome_code IN ('3','1','0')"
_MARKET_CHECK = "market_type IN ('euro_1x2','sp_1x2','asian_hcap')"
_SNAPSHOT_CHECK = "snapshot_kind IN (" + ",".join(
    f"'{k}'" for k in contract.SNAPSHOT_KINDS
) + ")"


def _ts_check(col: str) -> str:
    """CHECK fragment: column is a canonical UTC timestamp (ISO-8601 Z)."""
    return f"{col} {_UTC_TS}"


def _no_overlap_trigger(table: str, key_cols: tuple[str, str]) -> str:
    """BEFORE INSERT/UPDATE trigger: no overlapping validity windows.

    A window [valid_from, valid_to) overlaps an existing window when
    existing.valid_from < COALESCE(NEW.valid_to, '9999-12-31T23:59:59Z')
    AND COALESCE(existing.valid_to, '9999-12-31T23:59:59Z') > NEW.valid_from.
    NEW.valid_to == NULL means open-ended (still active).
    """
    key1, key2 = key_cols
    return f"""
-- no-overlap guarantee for {table} validity windows (REQ-DS02 alias rules)
CREATE TRIGGER IF NOT EXISTS trg_{table}_no_overlap
BEFORE INSERT ON {table}
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM {table} AS existing
    WHERE existing.{key1} = NEW.{key1}
      AND existing.{key2} = NEW.{key2}
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;

CREATE TRIGGER IF NOT EXISTS trg_{table}_no_overlap_update
BEFORE UPDATE OF valid_from_utc, valid_to_utc ON {table}
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM {table} AS existing
    WHERE existing.rowid != NEW.rowid
      AND existing.{key1} = NEW.{key1}
      AND existing.{key2} = NEW.{key2}
      AND existing.valid_from_utc < COALESCE(NEW.valid_to_utc, '9999-12-31T23:59:59Z')
      AND COALESCE(existing.valid_to_utc, '9999-12-31T23:59:59Z') > NEW.valid_from_utc
)
BEGIN
    SELECT RAISE(ABORT, 'overlapping alias validity window');
END;
"""


DDL_TABLES = f"""
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
    requested_at_utc   TEXT NOT NULL CHECK ({_ts_check('requested_at_utc')}),
    received_at_utc    TEXT NOT NULL CHECK ({_ts_check('received_at_utc')}),
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
    valid_from_utc  TEXT NOT NULL CHECK ({_ts_check('valid_from_utc')}),
    valid_to_utc    TEXT CHECK (valid_to_utc IS NULL OR ({_ts_check('valid_to_utc')})),
    PRIMARY KEY (source_id, source_team_key, valid_from_utc),
    CHECK (valid_to_utc IS NULL OR valid_from_utc < valid_to_utc)
);
{_no_overlap_trigger("team_alias", ("source_id", "source_team_key"))}

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
    valid_from_utc          TEXT NOT NULL CHECK ({_ts_check('valid_from_utc')}),
    valid_to_utc            TEXT CHECK (valid_to_utc IS NULL OR ({_ts_check('valid_to_utc')})),
    PRIMARY KEY (source_id, source_competition_key, valid_from_utc),
    CHECK (valid_to_utc IS NULL OR valid_from_utc < valid_to_utc)
);
{_no_overlap_trigger("competition_alias", ("source_id", "source_competition_key"))}

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
    kickoff_at_utc        TEXT NOT NULL CHECK ({_ts_check('kickoff_at_utc')}),
    native_handicap_line  REAL,
    sale_cutoff_at_utc    TEXT CHECK (sale_cutoff_at_utc IS NULL OR ({_ts_check('sale_cutoff_at_utc')})),
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
    valid_from_utc    TEXT NOT NULL CHECK ({_ts_check('valid_from_utc')}),
    valid_to_utc      TEXT CHECK (valid_to_utc IS NULL OR ({_ts_check('valid_to_utc')})),
    CHECK (valid_to_utc IS NULL OR valid_from_utc < valid_to_utc)
);
{_no_overlap_trigger("fixture_alias", ("fixture_id", "source_id"))}
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
    decision_at_utc   TEXT NOT NULL CHECK ({_ts_check('decision_at_utc')}),
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
    market_type      TEXT NOT NULL CHECK ({_MARKET_CHECK}),
    handicap_line    REAL,
    observed_at_utc  TEXT NOT NULL CHECK ({_ts_check('observed_at_utc')}),
    received_at_utc  TEXT NOT NULL CHECK ({_ts_check('received_at_utc')}),
    snapshot_kind    TEXT NOT NULL CHECK ({_SNAPSHOT_CHECK}),
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
    outcome_code   TEXT NOT NULL CHECK ({_OUTCOME_CHECK}),
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

-- completeness view: observations whose quote set is not exactly {3,1,0}
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
    outcome_code        TEXT NOT NULL CHECK ({_OUTCOME_CHECK}),
    probability         REAL NOT NULL CHECK (probability >= 0.0 AND probability <= 1.0),
    uncertainty         REAL CHECK (uncertainty IS NULL OR uncertainty >= 0.0),
    observed_at_utc     TEXT NOT NULL CHECK ({_ts_check('observed_at_utc')}),
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
    settled_at_utc  TEXT NOT NULL CHECK ({_ts_check('settled_at_utc')}),
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
"""


def sql_ddl() -> str:
    """Return the full versioned DDL text (deterministic)."""
    return DDL_HEADER + DDL_TABLES


# ---------------------------------------------------------------------------
# pandas / PyArrow research snapshot schemas (immutable partitioned Parquet)
# ---------------------------------------------------------------------------
# Namespace -> column -> pyarrow type string.  The builder emits a JSON schema
# contract and a Parquet schema file for each research namespace.
# v2: semantic columns are disjoint across namespaces (E2: no mixing).
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


def parquet_schema_contract() -> dict[str, object]:
    """Return the machine-readable PyArrow schema contract."""
    return {
        "ddl_version": DDL_VERSION,
        "namespaces": PARQUET_SCHEMAS,
        "partitioning": "immutable, partitioned by issue_code/year",
        "reader": "pandas / PyArrow",
        "namespace_rule": "semantic columns are disjoint across inference/"
                          "proxy/settlement namespaces (REQ-DS05)",
    }


# Join keys are shared across namespaces by design (REQ-DS02 identity);
# REQ-DS05 disjointness applies to SEMANTIC columns only.  Both the builder
# (REQ-DS05 evidence) and the semantic verifier (check_namespaces) must use
# this same definition so they can never drift apart (EV R1 E2 lesson).
NAMESPACE_JOIN_KEYS = {
    "fixture_id", "issue_code", "match_idx", "source_id",
    "handicap_line", "outcome_code",
}


def namespace_semantic_overlap() -> set[str]:
    """Semantic columns shared between any two namespaces (empty = REQ-DS05 OK)."""
    namespaces = PARQUET_SCHEMAS
    semantic = {
        name: set(cols.keys()) - NAMESPACE_JOIN_KEYS
        for name, cols in namespaces.items()
    }
    overlap: set[str] = set()
    pairs = [("inference", "settlement"), ("proxy", "settlement"),
             ("inference", "proxy")]
    for left, right in pairs:
        if left in semantic and right in semantic:
            overlap |= semantic[left] & semantic[right]
    return overlap


def namespaces_disjoint() -> bool:
    """REQ-DS05: no semantic column is shared across any two namespaces."""
    return (
        contract.INFERENCE_NAMESPACE in PARQUET_SCHEMAS
        and contract.PROXY_NAMESPACE in PARQUET_SCHEMAS
        and contract.SETTLEMENT_NAMESPACE in PARQUET_SCHEMAS
        and not namespace_semantic_overlap()
    )


def parquet_schema_json() -> str:
    return json.dumps(parquet_schema_contract(), indent=2, sort_keys=True) + "\n"


def domain_dictionary() -> str:
    """Render the domain dictionary document (markdown)."""
    lines = [
        f"# Domain Dictionary ({contract.CONTRACT_VERSION} / v2)",
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
        "- `live` — prospective timestamped capture from the live collector "
        "(beidan_live.db snapshots / 500_bjdc live_market_sp_snapshots).  "
        "Carries clock_semantics `TIMESTAMPED_UTC`; the exact "
        "`observed_at_utc` is the collector fetch clock and must be bound to "
        "the raw payload receipt.",
        "",
        "## admissible_use (REQ-DS01)",
        "",
        "| class | meaning |",
        "|---|---|",
        "| STRICT_CAUSAL | observed before decision epoch with trusted clock |",
        "| RETROSPECTIVE_PROXY | timestamp semantics insufficient; proxy only |",
        "| SETTLEMENT_ONLY | after-event truth; never inference input |",
        "| UNUSABLE | no clock / no identity / corrupt / not owned |",
        "",
        "v2 rule: a source with `admissible_use = STRICT_CAUSAL` must carry "
        "`clock_semantics = TIMESTAMPED_UTC` and a resolvable `raw_sha256` "
        "receipt; prose without a hash receipt is never STRICT_CAUSAL.",
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
        "## Mx3 triplet completeness (REQ-DS04)",
        "",
        "SQLite cannot express a deferred cross-row CHECK.  Triplet "
        "completeness is enforced at the canonical append boundary (the write "
        "path inserts all three `outcome_code` rows for a bookmaker in one "
        "transaction and rejects incomplete input) and is independently "
        "verifiable via the `v_incomplete_triplets` view.  A trigger rejects "
        "more than three quotes per cell.",
        "",
        "## Payout factor",
        "",
        "The Beijing `0.65` payout coefficient is absent from all source, quote "
        "and probability tables; it exists only in downstream ticket settlement "
        "metadata (frozen contract rule, checked by the verifier).",
        "",
        "## Alias validity windows (REQ-DS02)",
        "",
        "`valid_from_utc` inclusive, `valid_to_utc` exclusive; `NULL` "
        "`valid_to_utc` means still active.  Overlapping windows for the same "
        "(source, key) are rejected by triggers.",
        "",
    ]
    return "\n".join(lines)
