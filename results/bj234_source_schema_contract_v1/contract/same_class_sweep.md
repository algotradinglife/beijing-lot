# Same-class complete sweep evidence (EV R1 REJECT mandate)

EV R1 REJECT (REWORK_TYPE=method) required: "返工必须提交'同类问题完整排查'
声明与证据" across six categories.  This document records what was inspected
for each category, the call sites / paths examined, and where the evidence
lives.  The next EV round is expected to probe outside this declared scope;
items not listed here but still defective are incomplete sweeps by this
definition.

## 1. 指标语义 / identity (C1)

Inspected every identity/duplicate/null/long-cell statistics call site:

- `src/source_schema/profiler.py`:
  - `identity_stats()` — the ONLY duplicate/null metric producer; v1 used
    `COUNT(*) - COUNT(DISTINCT issue||'|'||match_idx)` which excluded NULL
    keys from DISTINCT (so NULL rows inflated the "duplicate" count) and
    missed `outcome_code` in long-form tables.  v2 computes per primitive key:
    total, null_key_rows, non_null_rows, distinct_non_null_keys,
    duplicate_excess (= non_null - distinct), duplicate_groups, verdict.
  - Added fail-closed guard: every primitive-key column must exist
    (`PRAGMA table_info` check); missing columns return an explicit error
    instead of silently treating the identifier as a string literal
    (SQLite double-quote fallback) — this caught the v1 `beidan_features`
    mis-key where `match_idx` does not exist (real key is `match_id`).
  - `IDENTITY_KEYS` frozen per table: beidan_xlsm matches/match_features
    `(issue, match_idx)`; outcome_features `(issue, match_idx, outcome_code)`
    (long-form); beidan_features matches `(match_id)`; others
    `(issue, match_idx)`.
- Consumers of identity metrics: `builder.build_package()` (DS02 evidence),
  `verify.check_identity_semantics()`, `contract/identity_crosswalk.md`,
  `tables/identity_checks.csv`.
- Independent recomputation (EV's own numbers, confirmed in this package):
  beidan_xlsm.matches 195,269 total / 2,560 NULL-key / 192,709 non-null
  distinct / duplicate_excess=0; match_features identical; outcome_features
  585,807 / 7,680 NULL / 578,127 distinct / excess=0.
- New finding (same class): beidan_features.matches real key is `match_id`
  (190,743 distinct of 190,746; 3 duplicated rows → real
  `DUPLICATE_DEFECT` with excess=3, named in identity_checks.csv, not
  hidden).
- Evidence: `tables/identity_checks.csv`, tests `test_identity_*`.

## 2. schema / alias / M×3 (C3)

Inspected every PK/UK/FK, nullable-key, full-triplet, validity-window and
multi-provider path in `src/source_schema/ddl.py`:

- PKs: team_alias (source_id, source_team_key, valid_from_utc);
  competition_alias (source_id, source_competition_key, valid_from_utc);
  fixture UNIQUE(issue_code, match_idx); fixture_alias (id PK + unique
  active per fixture/source); market_quote PK
  (observation_id, bookmaker_id, outcome_code) — v1's
  `ux_quote_one_per_outcome(observation_id, outcome_code)` that erased
  bookmaker_id is REMOVED; settlement PK (fixture_id, source_id).
- Nullable-key handling: probability_estimate UNIQUE uses a COALESCE
  expression index (`COALESCE(handicap_line, -999.0)`) so NULL euro cells
  collide correctly; market_observation natural-key unique uses the same
  COALESCE treatment.
- Triplet completeness: SQLite has no deferred cross-row CHECK — documented
  decision in `contract/design_notes.md`; enforced at the canonical append
  boundary (write path inserts all three outcome rows per bookmaker in one
  transaction) + `v_incomplete_triplets` view + `trg_quote_max_three`
  trigger.
- FK enforcement: `PRAGMA foreign_keys = ON` in DDL header; verifier probes
  orphan-quote rejection.
- Validity windows: team/competition/fixture alias no-overlap BEFORE
  INSERT/UPDATE triggers (SQLite lacks exclusion constraints).
- Temporal: canonical-UTC GLOB CHECK on every timestamp column;
  observed<=received, requested<=received same-row CHECKs;
  observation/decision/settlement before/after kickoff triggers.
- Boundary matrix: 12 SQLite probe tests in
  `tests/test_bj234_source_schema.py` (`test_ddl_*`) execute the committed
  DDL and assert real constraint behavior (multi-bookmaker legal, dup cells
  rejected, FK orphan rejected, alias overlap rejected, timestamp order
  rejected, observation-after-kickoff rejected, NULL-handicap euro cell
  collides, primitive-observation dup rejected).

## 3. 时序 / 泄漏 (C4)

Inspected every read path that touches source data:

- `src/source_schema/profiler.py` census:
  - `MEASURABLE_COLUMNS` allow-list per database/table — the census only
    scans columns whose values are identity keys, timestamps or observation
    prices.  Everything else (score/result_code/winning_sp/hit/fthg/ftag/
    settlement tables) is SEALED.
  - `SEALED_TABLES` — settlement/label tables get metadata only (existence,
    row count, schema), never value stats.
  - `assert_measurable()` raises `SealedColumnError` on any sealed read;
    notebook cell 4 proves the guard blocks 4 concrete sealed reads.
  - `COLUMN_SCAN_MAX_ROWS` bounds per-column scans on 51M/20M-row tables
    (REQ-DS06), so no accidental full-value aggregation on huge tables.
- `builder.build_package()` consumes only census output; no direct source
  reads.
- `verify.check_sealing()` proves published `columns.csv` contains no value
  stats for any sealed (database, table, column) triple.
- 2024+ outcome/settlement values are physically unreachable through the
  census API; mutation/interception evidence:
  `tables/sealed_columns.csv` (every sealed column named) +
  `tests/test_sealing_*`.

## 4. source lineage (C2)

Inspected every selected/non-selected source row in
`src/source_schema/sources.py`:

- Every row carries provider, endpoint, endpoint_evidence (repo file:line
  citation where one exists), acquisition_method, terms_status, timezone,
  clock_semantics, cadence, parser_version, admissible_use,
  first/last_usable_at_utc, coverage_grade, raw_sha256, notes.
- 500.com masquerade removed: `BEIDAN_LIVE_DB` provider is "internal live
  collector over 500.com data plane" with endpoints cited to
  `src/live_collector/scraper.py:40-41` and
  `scripts/scrape_500_bjdc.py:46-47`; `BJ_FIRST_PARTY_OFFICIAL` is UNUSABLE
  with NO_RECEIPT and an explicit "not acquired" note.
- STRICT_CAUSAL rows (BEIDAN_LIVE_DB, BEIDAN_500BJDC) bind a resolvable
  census raw_sha256; DDL CHECK enforces STRICT_CAUSAL ⇒ TIMESTAMPED_UTC.
- Branch handoffs: #235→BEIDAN_LIVE_DB, #236→ODDS_API_HISTORICAL,
  #237→INTERNAL_RESULTS_POWER, #238→BEIDAN_500BJDC (contract/
  downstream_handoff.md).
- Evidence: `tables/source_registry.csv`, `tables/feasibility_matrix.csv`,
  tests `test_registry_*` (incl. `test_registry_no_500_masquerade`,
  `test_registry_strict_causal_requires_receipt`).

## 5. 验证盲区 / tamper (E2)

Inspected every decision-facing payload and the verifier:

- `verify.verify_package()` rebuilds semantics from committed payloads:
  byte manifest, MANIFEST consistency, DDL execution in SQLite + real
  schema-object probes (fixture_alias, quote PK w/ bookmaker, no
  bookmaker-erasing index, COALESCE unique, triggers, view), registry
  semantics, namespace disjointness (semantic columns only), sealing,
  identity NULL-awareness.
- Remanifest attack suite (12 attacks, all must FAIL): all-sources-UNUSABLE,
  single-source registry, empty raw hashes, forged selected sources, forged
  manifest hashes, deleted quote unique index, injected 0.65, mixed
  namespace columns, removed observed column, duplicate-verdict regression,
  forged manifest version, byte tamper, registry label/future info,
  settlement namespace merge.
- Tests run entirely on `tmp_path` copies (`pkg_copy` fixture); no test
  writes the committed package (E1).

## 6. 复审抽查 (EV will probe outside this scope)

Known same-class areas NOT covered by a specific test but reviewed in code:

- `ingestion_batch` cadence/status domain is CHECK-constrained but no
  per-source cadence conformance test exists (source rows may declare 60s
  while batches arrive slower — measurement, not contract violation).
- `fixture.sale_cutoff_at_utc` is nullable with a UTC CHECK but no trigger
  ties it to decision_epoch (decision<=cutoff is a policy, not schema).
- `probability_estimate.uncertainty` is constrained to >=0 but not to
  [0,1] — uncertainty semantics (std vs interval) are documented in the
  domain dictionary, not enforced numerically.
- `market_quote.decimal_odds > 1.0` CHECK uses float comparison; odds
  exactly 1.0 (certain outcome) are rejected by design (BJ SP domain).
- `source_registry.raw_sha256` is CHECKed non-empty but the verifier does
  not re-hash live DBs at verify time (census-time receipt is bound);
  a drift between census and verify is possible if sources change after
  build — replay reruns the census.
