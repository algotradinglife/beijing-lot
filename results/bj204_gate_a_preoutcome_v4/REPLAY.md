# Deterministic Gate-A v4 replay

Run from the repository root with the pinned existing environment.  The
history source is read-only and queried with the documented eight-column
pre-event allow-list; no official-SP or result field is selected.

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py verify \
  --package results/bj204_gate_a_preoutcome_v4

PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py freeze \
  --source results/bj203_causal_tensor_v2 \
  --history-source data/beidan_history.db \
  --full-3sp-identity-source data/raw/beidan_full_3sp.csv \
  --pclose-source data/beidan_features.db --output <new-empty-directory>

PYTHONPATH=src $PY scripts/execute_bj204_notebook.py
```

The package and notebook never import `unified_tensor.settlement_labels` and
never read target values, target timestamps, results, or winning SP.
