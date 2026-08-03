# #159 Gate B v2r1

Reporting-only recovery from the authenticated `bj159_gate_b_outcome_settlement_v2` ledgers. The recovery does not open canonical outcomes or alter settlement rows. `analysis_summary.json` contains the quantitative terminal synthesis; `report.md` links the full immutable row-level surfaces. Replay with `python3 recovery_runner.py --output <new-dir>`; staging uses the repository `.scratch` directory, never `/tmp`.
