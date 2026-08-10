# Issue #205 immutable evidence package

Clean environment: `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements.txt`. The exact scientific package versions are frozen in `requirements.txt` and its SHA-256 is bound in `provenance.json`.

Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj205_joint_n7.py verify --output results/issue-205`

Replay to a new output directory: `PYTHONPATH=src .venv/bin/python scripts/run_bj205_joint_n7.py run --output <new-directory>`

Clean-run notebook: `PYTHONPATH=src .venv/bin/python scripts/execute_bj205_notebook.py --kernel python3` (the installed ipykernel exposes the portable `python3` kernelspec; persistence uses same-directory temporary-file plus atomic replace).

#206 may consume only the schema-declared safe-control lane (`control_*`, `MARKET_ONLY`, `FROZEN_SAFE_BASELINE`) with `MARKET_INDEPENDENCE`. Every `experimental_*` probability/residual/utility channel is `RETROSPECTIVE_PROXY_METHOD_CORRECTION`, `promoted=false`, and ablation-only pending #210 confirmation.

The package includes the value schema/matrix, exact inference trace, exhaustive locked ticket ledger, chronological metrics, reliability and regime diagnostics, plots, decision report, parameters, provenance and SHA-256 manifest.
