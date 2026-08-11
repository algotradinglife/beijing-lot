# Issue #206 — fixed-N7 constrained ticket policy

Status: retrospective Stage-3 research; requested tickets only. No bankroll, betting, ROI, or production authority.

## Frozen interface and action space

The implementation consumes the complete #205 `J × 3` value matrix. The controlling path reads only `control_probability` (`MARKET_ONLY`, source grade `FROZEN_SAFE_BASELINE`) and the frozen pre-event predicted SP. A source match whose complete three-cell safe-control probability row is absent is explicitly recorded in `input_exclusions.csv`; 651 such matches are ledgered across the chronological package. Partial NaN/Inf rows, non-positive or non-normalized probabilities/SP, incomplete M×3 rows, and issues with fewer than seven safe matches fail closed before candidate construction. Every retained ticket contains exactly seven distinct matches and one 3/1/0 outcome for each selected match. Each ticket chooses its own subset from the eligible issue pool; no shared first-seven roster is inherited from #205.

Candidate generation is bounded and reproducible: deterministic top-mass/systematic identities plus NumPy package-backed market-weighted sampling without replacement under three frozen nuisance seeds. Exact identity, subset, outcomes, per-cell control probability/source grade, predicted SP, SP seed uncertainty, expected utility, overlap, repeats, and requested ¥2 stake remain traceable. The experimental #204 residual lane appears only in the explicitly named `EXPERIMENTAL_MLP_ABLATION` and cannot enter the safe control.

## Chronology and policy comparison

- CV-2021: train the simple scikit-learn logistic baseline first, then the MLP rankers.
- CV-2022: select K and compare controls/challengers at matched ticket and stake budgets.
- CV-2023: final historical evaluation.
- LOCKED_TEST (2025/2026): label-blind Stage-3 ticket requests only; outcome and official-final-SP labels are embargoed.

The frozen K grid is 8/16/32. The surface compares the honestly named `TOP_K_EXPECTED` control (not FULL coverage), market-weighted WR and WOR, two temperature rules, overlap-capped and overlap-penalized controls, a package-backed logistic baseline, a safe-feature MLP, and the residual-feature experimental ablation. Absolute utility, diagnostic raw expected utility, coverage, turnover, match overlap, ticket overlap, repeat share, and stake HHI are reported together with matched lift versus the best local matched comparator.

The per-issue safe gate uses scikit-learn `StandardScaler` on CV-2021 issue-level medians of the eight safe candidate features. It freezes the CV-2022 99th-percentile (higher method) maximum-absolute standardized-feature threshold at 7.549834, then evaluates each LOCKED_TEST issue independently. `issue_gate.csv` reports OOD score/threshold, feasibility, learned-only, pure-local-control and fallback-mixed paths. An OOD learned-only issue is `NO_BET_OOD`; fallback-mixed routing emits `NO_BET` while accepted ticket-baseline binding remains unresolved. None of the 75 current locked issues exceeds the frozen OOD threshold.

## Decision

`LEARNED_POLICY_REJECTED_BASELINE_UNRESOLVED`. CV-2022 selected MARKET_WR at K=8 only as the best local matched comparator. LEARNED_MLP at the same K had positive point realized lift, but the Bonferroni-adjusted one-sided lower bound across all 30 policy/K rows was -2.403563. Raw independence×predicted-SP expected utility is severely miscalibrated and remains diagnostic only; it is not a safety gate.

The #205 accepted object is `MARKET_INDEPENDENCE`, a probability scorer calibrated on a fixed first-seven exhaustive roster—not a comparable Stage-3 ticket policy. Therefore no local policy is promoted merely for winning this bounded surface: all 75 locked issues emit machine-readable `NO_BET` with reason `ACCEPTED_TICKET_BASELINE_UNRESOLVED_NO_BET`, while learned-only and pure-local-control paths remain reported separately. This rejects the present MLP only within the bounded 55,042-candidate generator; it does not reject per-ticket subset learning generally.

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

The verifier does not treat a regenerable manifest as semantic proof. After hash validation it regenerates all 55,042 candidates from the frozen #205 matrix and compares every identity, list, source trace, probability, predicted SP, SP uncertainty, provenance, feature, arithmetic and label-boundary field. It then recomputes the chronology-frozen OOD gate, per-issue route, selected requests, fallback evidence, and matched-stake surface. Regression tests re-manifest invalid candidate outcomes, forged source uncertainty, missing candidates, request trace/fallback mutations and matched-budget tampering and require semantic rejection.

## Replay

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python -r requirements.txt
PYTHONPATH=src .venv/bin/python scripts/run_bj206_fixed_n7.py verify --output results/issue-206
PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_bj206_fixed_n7.py
PYTHONPATH=src .venv/bin/python scripts/execute_bj206_notebook.py --kernel python3
```
