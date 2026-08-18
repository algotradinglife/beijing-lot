# Issue #206 immutable evidence package

Verify: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py verify --output results/issue-206`.

Replay to a new directory: `PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py run --output <new-directory>`.

Clean notebook: `PYTHONPATH=src .venv/bin/python scripts/execute_bj206_notebook.py --kernel python3`.

The package includes an enforced input-exclusion ledger, per-issue OOD/feasibility paths, exact source-cell traces, ticket hit/payout calibration, matched policy surfaces, plots, and the label-blind request ledger. Its semantic verifier recomputes routes, selection, ticket traces and matched-budget evidence after checking the manifest. It is a Stage-3 requested-ticket/NO_BET handoff only and has no final bankroll, betting, or production authority.
