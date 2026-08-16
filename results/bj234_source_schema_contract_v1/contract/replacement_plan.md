# Migration-free replacement plan (REQ: no backward-compat tax)

The contract replaces ambiguous legacy schemas at the interface boundary —
no compatibility layers, no migrations.

1. **Canonical capture DB** (SQLite WAL, one-writer append-only):
   `source_registry`, `ingestion_batch`, `team(_alias)`,
   `competition(_alias)`, `fixture(_alias)`, `decision_epoch`,
   `market_observation`, `market_quote`, `probability_estimate`,
   `settlement`.  Old workbook/history DBs are **read-only census inputs**,
   never written through this interface.
2. **Research snapshots** (immutable partitioned Parquet): `inference`,
   `proxy`, `settlement` namespaces read by pandas/PyArrow.  Namespaces are
   disjoint; settlement truth is physically separate from inference inputs.
3. **Deleted from the accepted interface**: `beidan_xlsm.sqlite`
   label columns (`initial/10h/1h/final`) as observation timestamps,
   `beidan_history.db` settlement rows as inference observations,
   `beidan_features.db` open/close labels as exact clocks, and any
   `0.65` payout factor in source/quote/probability tables.
4. **Why not wrap in compat layers**: AGENTS.md principle 1 — obsolete
   semantics are removed outright; downstream branches consume the frozen
   contract directly.

Scale/concurrency justification (REQ-DS06): SQLite WAL is the right capture
engine at this volume (one writer, append-only; measured total rows from the
census).  Immutable Parquet serves the research read path without a new
service; JSON-blob probability vectors are rejected because they cannot be
scanned by pandas/PyArrow and duplicate the relational contract.
