# Issue #206 immutable evidence package

Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py verify --output results/issue-206`.

Replay to a new directory: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py run --output <new-directory>`.

Clean notebook: `PYTHONPATH=src .venv/bin/python scripts/execute_bj206_notebook.py --kernel python3`.

The package includes an enforced input-exclusion ledger, exact source-cell traces, ticket hit/payout calibration, matched policy surfaces, plots, and the label-blind request ledger. It is a Stage-3 requested-ticket handoff only and has no final bankroll, betting, or production authority.
