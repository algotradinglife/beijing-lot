# Replay

```bash
export BEIJING_LOT_DATA_ROOT=/absolute/path/to/data
python scripts/build_bj253_physical_schema.py
python scripts/build_bj253_physical_schema.py --verify-only
python scripts/execute_bj253_notebook.py
python -m pytest -q tests/test_bj253_physical_schema.py
```

The external SQLite/raw/Parquet package is intentionally not stored in Git.
