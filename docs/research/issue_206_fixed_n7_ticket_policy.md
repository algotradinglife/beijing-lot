# Issue #206 — fixed-N7 constrained ticket policy

Status: retrospective Stage-3 research; requested tickets only. No bankroll, betting, ROI, or production authority.

## Frozen interface and action space

The implementation consumes the complete #205 `J × 3` value matrix. The controlling path reads only `control_probability` (`MARKET_ONLY`, source grade `FROZEN_SAFE_BASELINE`) and the frozen pre-event predicted SP. A source match whose complete three-cell safe-control probability row is absent is explicitly recorded in `input_exclusions.csv`; 651 such matches are ledgered across the chronological package. Partial NaN/Inf rows, non-positive or non-normalized probabilities/SP, incomplete M×3 rows, and issues with fewer than seven safe matches fail closed before candidate construction. Every retained ticket contains exactly seven distinct matches and one 3/1/0 outcome for each selected match. Each ticket chooses its own subset from the eligible issue pool; no shared first-seven roster is inherited from #205.

Candidate generation is bounded and reproducible: deterministic top-mass/systematic identities plus NumPy package-backed market-weighted sampling without replacement under three frozen nuisance seeds. Exact identity, subset, outcomes, per-cell control probability/source grade, predicted SP, SP seed uncertainty, expected utility, overlap, repeats, and requested ¥2 stake remain traceable. The experimental #204 residual lane appears only in the explicitly named `EXPERIMENTAL_MLP_ABLATION` and cannot enter the safe control.

## Chronology and policy comparison

- CV-2021: train the package-backed scikit-learn MLP ranker.
- CV-2022: select K and compare controls/challengers at matched ticket and stake budgets.
- CV-2023: final historical evaluation.
- LOCKED_TEST (2025/2026): label-blind Stage-3 ticket requests only; outcome and official-final-SP labels are embargoed.

The frozen K grid is 8/16/32. The surface compares BEST_FULL, market-weighted WR and WOR, two temperature rules, overlap-capped and overlap-penalized controls, a safe-feature MLP, and the residual-feature experimental ablation. Absolute utility, expected utility, coverage, turnover, match overlap, ticket overlap, repeat share, and stake HHI are reported together with matched lift versus the selected safe control.

The per-issue safe gate uses scikit-learn `StandardScaler` on CV-2021 issue-level medians of the eight safe candidate features. It freezes the CV-2022 99th-percentile (higher method) maximum-absolute standardized-feature threshold at 7.549834, then evaluates each LOCKED_TEST issue independently. `issue_gate.csv` reports OOD score/threshold, feasibility, learned-only, pure-control and fallback-mixed paths. An OOD learned-only issue is `NO_BET_OOD`; fallback-mixed routing uses the strongest feasible frozen control, or `NO_BET` when no safe control is feasible. None of the 75 current locked issues exceeds the frozen OOD threshold.

## Decision

`INHERIT_STRONGEST_FROZEN_CONTROL`. CV-2022 selected MARKET_WR at K=8 as the strongest frozen matched control. LEARNED_MLP at the same K had positive point realized lift but expected utility was 68.685147 below control and the paired one-sided 95% realized-lift lower bound was -0.914040. The deterministic uncertainty/matched-floor gate therefore routes every locked request to MARKET_WR with reason `VALIDATION_UNCERTAINTY_OR_MATCHED_LIFT_FLOOR`; OOD and feasibility are still evaluated and retained per issue before handoff.

On CV-2023 the inherited path recorded absolute realized pre-tax net -1.000000, expected pre-tax net 78.369429, zero hit coverage, mean match overlap 0.196197, repeat share 0.154545, and matched realized lift 0.000000 at exactly the same K/stake budget. This is a conservative negative result, not a learned-policy advancement claim.

## Evidence links

- Executed notebook: `notebooks/research/issue-206/bj206_fixed_n7_ticket_policy.ipynb`
- Reusable implementation: `src/ticket_policy/fixed_n7.py`
- Replay CLI: `scripts/run_bj206_fixed_n7.py`
- Tests: `tests/test_bj206_fixed_n7.py`
- Immutable package: `results/issue-206/`
- Decision report: `results/issue-206/DECISION_REPORT.md`
- Policy and matched-lift surface: `results/issue-206/policy_surface.csv`
- Ticket hit/payout calibration: `results/issue-206/ticket_calibration.csv`
- Enforced source-match exclusion ledger: `results/issue-206/input_exclusions.csv`
- Per-issue OOD/feasibility and learned/control/NO_BET paths: `results/issue-206/issue_gate.csv`
- Stage-3 request ledger: `results/issue-206/ticket_requests.parquet`

The verifier does not treat a regenerable manifest as semantic proof. After hash validation it recomputes the chronology-frozen OOD gate, per-issue route, selected ticket identities (including explicit repeats), identity/list/source-trace agreement, 3/1/0 outcome domain, probability/SP/utility arithmetic, fallback evidence, and the matched-stake surface. Regression tests re-manifest invalid-outcome, trace-count, trace-identity, fallback and matched-budget tampering and require semantic rejection.

## Replay

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py verify --output results/issue-206
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj206_fixed_n7.py
PYTHONPATH=src .venv/bin/python scripts/execute_bj206_notebook.py --kernel python3
```
