# Design notes: scale and concurrency (REQ-DS06)

The canonical physical design reuses the existing mature stack — no new service or database until measured concurrency requires it:

- **SQLite WAL mode, one-writer append-only** for capture/control tables (`source_registry`, `ingestion_batch`, `fixture`, `market_observation`, `market_quote`, `probability_estimate`, `settlement`).  SQLite handles single-writer/multi-reader concurrency with WAL; the capture pipeline is the only writer and appends immutable rows.
- **Immutable partitioned Parquet** for research snapshots read by pandas/PyArrow.  Research reads never block the capture writer and the snapshot is frozen per build.
- **Measured scale** (from the census):
  - `market_snapshots` legacy table: 51,551,016 rows / 24 bookmakers
  - `market_consensus` legacy table: 3,124,304 rows
  - `beidan_live.snapshots`: 1,495,895 timestamped rows (primary causal source)
  - `beidan_xlsm.sqlite` file: ~6.9 GB; `beidan_live.db`: ~262 MB

No JSON-blob probability vectors: probability triplets remain long-form scalars keyed by match/outcome in `probability_estimate` (one row per outcome).  This keeps the Mx3 contract checkable by schema constraints.
