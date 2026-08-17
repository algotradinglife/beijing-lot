# Deterministic replay

```bash
PY=.venv/bin/python
PYTHONPATH=src $PY scripts/build_bj214_decision_epoch_tensor.py verify \
  --package results/bj214_decision_epoch_tensor_v1

PYTHONPATH=src $PY scripts/build_bj214_decision_epoch_tensor.py replay \
  --source-package results/bj214_decision_epoch_tensor_v1 \
  --output <new-empty-directory>

PYTHONPATH=src $PY scripts/build_bj214_decision_epoch_tensor.py compare \
  --frozen results/bj214_decision_epoch_tensor_v1 \
  --replay <new-empty-directory>

PYTHONPATH=src $PY scripts/execute_bj214_notebook.py
```

Replay reads only the locked source namespace embedded in the package. It never
opens runtime databases or any settlement/result table.
