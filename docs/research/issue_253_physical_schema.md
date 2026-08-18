# BJ-UNIFIED-PHYSICAL-SCHEMA-001

`BEIJING_LOT_DATA_ROOT` is mandatory and is the sole external-data interface.
`normalized/bj_unified_physical_schema_v1/` is generated beneath it, never in Git.

SQLite is the normalized control plane (`source_registry`, `capture_manifest`,
`issue_slot`, `m3_cell`, `settlement`). Parquet is the analytical immutable
projection (`m3_cells.parquet`). The canonical analytical grain is
`issue_code × match_idx × outcome_code(3/1/0) × source_id × snapshot_horizon`.

`issue_slot` is only `bjslot:<issue>:<index>`; real fixture/team/competition
identities stay null. Strict-forward and historical-proxy rows share the long
shape but have required distinct `source_namespace`, `causal_grade`, and
`time_semantics`; consumers must never pool them. Settlement has no FK or view
into the feature projection. Missing numeric values are null with an explicit
reason, never zero.

Representative replay:
`PYTHONPATH=src BEIJING_LOT_DATA_ROOT=/data/root python -c 'from unified_physical_schema import build_representative_slice; print(build_representative_slice())'`
