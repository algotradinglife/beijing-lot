# Issue #254 compact evidence

The bulk normalized SQLite/Parquet package is external and is not committed.
This directory contains its exact manifest, predecessor bindings, replay and
physical receipts, downstream readiness matrix, generated data dictionary and
REQ evidence.

```bash
export BEIJING_LOT_DATA_ROOT=/absolute/path/to/data
python scripts/build_bj254_schema_integration.py --data-root "$BEIJING_LOT_DATA_ROOT"
python scripts/build_bj254_schema_integration.py --data-root "$BEIJING_LOT_DATA_ROOT" --verify-only
python scripts/execute_bj254_notebook.py --data-root "$BEIJING_LOT_DATA_ROOT"
```

Expected external package:
`$BEIJING_LOT_DATA_ROOT/derived/bj254_schema_integration_v2`.
