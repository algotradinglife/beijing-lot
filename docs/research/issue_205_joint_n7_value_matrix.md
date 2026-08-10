# Issue #205 — unified M×3 value and fixed-N7 calibration

Status: retrospective proxy research; no betting or production authority.

## Inherited interface

The reusable ticket-learning interface is the long-form `J × 3` value matrix in `results/issue-205/value_matrix.parquet`, governed by `value_matrix_schema.json`. Its controlling #206 lane is explicitly `control_probability` from `MARKET_ONLY`, source grade `FROZEN_SAFE_BASELINE`, together with the frozen pre-event SP head and `MARKET_INDEPENDENCE`. Its expected gross, pre-tax net and displayed utility use `control_*` names.

The #204 `LOGISTIC_RESIDUAL` lane is retained only under `experimental_*` names with source grade `RETROSPECTIVE_PROXY_METHOD_CORRECTION`, `promoted=false`, and confirmation dependency `#210`. Experimental probability, uncertainty, residual, gross, net and displayed utility remain separate ablation features and are not accepted “true probability” or the controlling #206 interface.

## Joint N7 scorer

One deterministic first-seven eligible panel is frozen per issue and all `3^7 = 2,187` outcome identities are evaluated. The exact baseline is the product of the frozen #204 market probabilities with the frozen #204 pre-event SP-head rule. Unsupported or shifted issues copy this probability vector exactly; fewer than seven supported matches emit `NO_BET_LT7`.

Chronological evidence compares market independence, accepted-model independence, a bounded simple issue-regime correction, and a package-backed latent set correction. The controlling advancement decision uses joint log loss and is stored in `results/issue-205/decision.json`. The selected simple dependence arm was slightly worse than model independence on chronological CV (+0.0002085 joint log loss) and worse than market on locked Brier (+0.000176), although locked log loss and payout MAE improved. This is promising retrospective evidence, not a validated edge and not evidence that dependence has no value.

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
