# Issue #205 — unified M×3 value and fixed-N7 calibration

Status: retrospective proxy research; no betting or production authority.

## Inherited interface

The reusable ticket-learning interface is the long-form `J × 3` value matrix in `results/issue-205/value_matrix.parquet`, governed by `value_matrix_schema.json`. Probability, predicted final SP, probability/SP uncertainty, model-market residual, expected gross and expected pre-tax net are separate channels. The displayed scalar is only the documented projection `0.65 × p × predicted_SP - 1`.

## Joint N7 scorer

One deterministic first-seven eligible panel is frozen per issue and all `3^7 = 2,187` outcome identities are evaluated. The exact baseline is the product of the frozen #204 market probabilities with the frozen #204 pre-event SP-head rule. Unsupported or shifted issues copy this probability vector exactly; fewer than seven supported matches emit `NO_BET_LT7`.

Chronological evidence compares market independence, accepted-model independence, a bounded simple issue-regime correction, and a package-backed latent set correction. The controlling advancement decision uses joint log loss and is stored in `results/issue-205/decision.json`.

## Evidence links

- Executed notebook: `notebooks/research/issue-205/bj205_joint_n7_value_matrix.ipynb`
- Reusable implementation: `src/unified_value/joint_n7.py`
- Replay CLI: `scripts/run_bj205_joint_n7.py`
- Tests: `tests/test_bj205_joint_n7.py`
- Decision report and PI handoff: `results/issue-205/DECISION_REPORT.md`
- Metrics/reliability/diagnostics: `results/issue-205/metrics.csv`, `ticket_reliability.csv`, `cell_reliability.csv`, `regime_diagnostics.csv`

## Replay

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python -r requirements.txt
PYTHONPATH=src .venv/bin/python scripts/run_bj205_joint_n7.py verify --output results/issue-205
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj205_joint_n7.py
```
