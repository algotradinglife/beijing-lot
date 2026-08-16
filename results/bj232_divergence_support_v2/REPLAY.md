# Deterministic replay — package

Run from the repository root with the pinned existing environment.

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/build_bj232_divergence_support.py verify   --package package

PYTHONPATH=src $PY scripts/build_bj232_divergence_support.py build   --force

PYTHONPATH=src $PY scripts/execute_bj232_notebook.py
```

The build reads only the four accepted upstream frozen packages plus
allow-listed columns from #203 inference feature values.  No
settlement/result table is opened.  Deterministic loading is
fail-closed: every upstream package is SHA256-verified before use.
