# Downstream Branch Handoff (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)

Each downstream subissue consumes exactly one selected source and the canonical physical schema published here.  Nothing below is a reputation label — every selected source is the registry receipt with clock/admissible-use evidence in the feasibility matrix.

## Branch `beijing`

- **Consumes**: `beijing_official_interface`
- **Provider**: Beijing Sports Lottery official interface
- **Endpoint**: `official 500.com live/issue feed (prospective capture)`
- **Admissible use**: STRICT_CAUSAL
- **Clock semantics**: TIMESTAMPED_UTC
- **Coverage grade**: A
- **Acquisition**: prospective capture with raw payload + trusted fetch clock (cost: free (self-capture))
- **Rationale**: Primary prospective causal source: native handicap + instant SP with raw payload and trusted fetch clock; clock TIMESTAMPED_UTC.

## Branch `beijing`

- **Consumes**: `beidan_live_db`
- **Provider**: live collector (2026-05+)
- **Endpoint**: `data/beidan_live.db:snapshots`
- **Admissible use**: STRICT_CAUSAL
- **Clock semantics**: TIMESTAMPED_UTC
- **Coverage grade**: A
- **Acquisition**: prospective timestamped capture (cost: already owned)
- **Rationale**: Primary prospective causal source; snapshot_ts is TIMESTAMPED_UTC with 1.49M rows observed 2026-05+.

## Branch `european`

- **Consumes**: `odds_api_historical`
- **Provider**: The Odds API
- **Endpoint**: `api.the-odds-api.com (historical snapshots from 2020, paid)`
- **Admissible use**: STRICT_CAUSAL
- **Clock semantics**: TIMESTAMPED_UTC
- **Coverage grade**: B
- **Acquisition**: licensed API purchase (cost: paid (per-request plan))
- **Rationale**: Selected EU branch source: licensed timestamped European bookmaker feed; GRADE_B while coverage is evaluated.

## Branch `power`

- **Consumes**: `internal_results_public_football`
- **Provider**: internal match results + accepted public football data
- **Endpoint**: `results + football-data CSV (causal team/league power features)`
- **Admissible use**: STRICT_CAUSAL
- **Clock semantics**: TIMESTAMPED_UTC
- **Coverage grade**: B
- **Acquisition**: internal results + public CSV (cost: already owned)
- **Rationale**: Causal team/league power features with explicit competition coverage and identity mapping (REQ-DS08).

## Branch `integration`

- **Consumes**: `bj234_canonical_schema`
- **Provider**: this contract's physical schema
- **Endpoint**: `results/bj234_source_schema_contract_v1 (DDL + PyArrow schemas)`
- **Admissible use**: STRICT_CAUSAL
- **Clock semantics**: TIMESTAMPED_UTC
- **Coverage grade**: A
- **Acquisition**: design freeze (Issue #234) (cost: already owned)
- **Rationale**: The integration branch consumes the canonical physical schema itself: sql/schema.sql, schemas/parquet_schema.json, domain dictionary and identity crosswalk (REQ-DS08).

The integration branch consumes the canonical schema itself (`integration` -> `bj234_canonical_schema`): the versioned DDL in `sql/schema.sql`, the PyArrow schemas in `schemas/parquet_schema.json`, and the domain dictionary / identity crosswalk contracts under `contract/`.
