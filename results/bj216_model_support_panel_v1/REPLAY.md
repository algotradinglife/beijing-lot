# Deterministic replay

```bash
PY=/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python
PYTHONPATH=src $PY scripts/build_bj216_model_support_panel.py verify \
  --package results/bj216_model_support_panel_v1
PYTHONPATH=src $PY scripts/build_bj216_model_support_panel.py replay \
  --source-package results/bj216_model_support_panel_v1 --output <new-empty-directory>
PYTHONPATH=src $PY scripts/build_bj216_model_support_panel.py compare \
  --frozen results/bj216_model_support_panel_v1 --replay <new-empty-directory>
```

Replay reads only the frozen source namespace and never opens a runtime or
outcome/settlement database.
