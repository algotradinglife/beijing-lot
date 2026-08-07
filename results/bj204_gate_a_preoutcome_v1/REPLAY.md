# Deterministic Gate-A replay

Run from the repository root with the pinned existing environment:

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py verify \
  --package results/bj204_gate_a_preoutcome_v1
PYTHONPATH=src $PY scripts/execute_bj204_notebook.py

# Detached rebuild: use a new, empty directory.
PYTHONPATH=src $PY scripts/freeze_bj204_model_gate_a.py freeze \
  --source results/bj203_causal_tensor_v2 --output <new-empty-directory>
```

The Gate-A builder validates only #203's `inference/` namespace.  It never
imports `unified_tensor.settlement_labels` and never opens 2024 test labels.
