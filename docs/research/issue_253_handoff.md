# Issue #253 handoff

## Tracked implementation

- `src/physical_schema/contract.py`: SQLite DDL and PyArrow schemas.
- `src/physical_schema/builder.py`: deterministic real-data slice, external
  package build, model-facing reader and semantic verifier.
- `scripts/build_bj253_physical_schema.py`: build/verify CLI.
- `notebooks/research/issue-253/bj253_physical_schema.ipynb`: executed build and
  profiling notebook.
- `tests/test_bj253_physical_schema.py`: row-grain, namespace, missingness,
  leakage-separation and path-portability tests.

## Replay

```bash
export BEIJING_LOT_DATA_ROOT=/absolute/path/to/data
python scripts/build_bj253_physical_schema.py
python scripts/build_bj253_physical_schema.py --verify-only
python scripts/execute_bj253_notebook.py
python -m pytest -q tests/test_bj253_physical_schema.py
```

The external package is always
`$BEIJING_LOT_DATA_ROOT/derived/bj253_physical_schema_v1`.  Do not commit its
SQLite, raw-slice or Parquet files.

## Downstream permissions

Allowed: issue-local M×3 joins, explicit proxy/strict namespace filtering,
nullable canonical entity fields, explicit missingness, and separate label
loading during evaluation.

Forbidden: fuzzy/cross-label entity joins, treating live URL-expect buckets as
canonical issue truth, pooling proxy and strict rows without a declared cohort,
or exposing the label store through the inference reader.
