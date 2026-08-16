# Design notes (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v2)

## Physical design

- **Capture/control**: SQLite in WAL mode, one-writer append-only.  The
  capture layer is the single write path; immutable Parquet serves research.
- **Research**: immutable partitioned Parquet read by pandas/PyArrow.
  No JSON-blob probability vectors, no new service/database until measured
  concurrency requires it.
- **Namespaces**: `inference` / `proxy` / `settlement` are disjoint
  projections (REQ-DS05).  Settlement rows are never inference inputs.

## Scale measurements (v2 census, read-only)

Total rows across registered tables: **96,129,720**.
Raw source receipts bound: 7 database hashes in MANIFEST.

- `beidan_live.db` snapshots: ~1.5M rows, snapshot_ts canonical-Z (0 null).
- `beidan_xlsm.sqlite` market_snapshots: ~51.5M rows; labels only.
- `500_bjdc.sqlite`: 17GB live DB with raw payload receipts.

## Concurrency justification (REQ-DS06)

SQLite WAL handles one-writer append-only capture at this volume without a
new service.  A separate service/database is only justified when measured
contention exceeds WAL's practical envelope; the census provides the
measurement baseline for that future decision.

## Mx3 triplet completeness

SQLite cannot express a deferred cross-row CHECK.  Completeness is enforced
at the canonical append boundary (write path inserts all three outcome rows
for a bookmaker in one transaction and rejects incomplete input) and is
independently verifiable through the `v_incomplete_triplets` view; a trigger
rejects more than three quotes per cell.

## 0.65 boundary

The Beijing `0.65` payout coefficient is absent from all source, quote and
probability tables (checked by the verifier); it exists only in downstream
ticket settlement metadata.
