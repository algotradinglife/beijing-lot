# Issue #206 decision report — fixed-N7 ticket generation

## Decision

`LEARNED_POLICY_REJECTED_BASELINE_UNRESOLVED`. The validation-selected challenger was `LEARNED_MLP` at K=8; the best local matched comparator was `MARKET_WR` at K=8. The selection-adjusted paired validation realized-lift lower bound was -2.403563. The deterministic gate therefore emitted `ACCEPTED_TICKET_BASELINE_UNRESOLVED_NO_BET`.

The #205 accepted object is a `MARKET_INDEPENDENCE` probability scorer on a fixed first-seven exhaustive calibration roster, not a comparable Stage-3 ticket policy. The row formerly mislabeled `BEST_FULL` is now honestly named `TOP_K_EXPECTED`; it is not FULL coverage. Because no accepted ticket baseline is bound on matched Stage-3 support, the locked fallback-mixed path is `NO_BET` (zero requested tickets/stake). For diagnosis only, the local CV-2023 comparator recorded realized pre-tax net -1.000000, raw independence×SP expected pre-tax net 78.369429, and coverage 0.000000 at ¥880 turnover. Raw expected utility is diagnostic and is not a safety gate.

The issue-specific gate fits scikit-learn `StandardScaler` on CV-2021 issue-level safe-feature medians and freezes the CV-2022 99.00% maximum-absolute-z threshold at 7.549834. It evaluates feasibility and OOD before every locked handoff; 0 locked issues exceed the threshold. `issue_gate.csv` reports learned-only, pure-control and fallback-mixed paths separately, including deterministic safe-control and `NO_BET` reasons.

## Constraint and evidence interpretation

- Every ticket has exactly seven distinct match ids and one 3/1/0 outcome per match. There is no global seven-match roster.
- The three fixed nuisance seeds generate a bounded full-issue candidate pool; seed choice is never outcome-ranked.
- Exact duplicate ticket identity is separately measured from match overlap. Controlling WOR policies request distinct identities; repeat stake remains an explicit, traceable action rather than accidental duplication.
- Only #205 `MARKET_ONLY` / `FROZEN_SAFE_BASELINE` control probability and frozen pre-event SP enter the controlling policy. Experimental residuals appear only in `EXPERIMENTAL_MLP_ABLATION`.
- 651 source matches with all three safe-control probabilities missing are explicitly recorded in `input_exclusions.csv`; partial/non-finite, non-positive, non-normalized, incomplete-M×3, and post-exclusion M<7 inputs fail closed.
- Training uses CV-2021, policy/K selection uses CV-2022, final historical evaluation uses CV-2023. LOCKED_TEST 2025/2026 labels remain embargoed; its Stage-3 handoff is label-blind.
- The semantic verifier regenerates every candidate from the frozen #205 matrix, binding identity, source probability/SP/uncertainty/provenance, feature arithmetic and label boundary before recomputing OOD, issue routes, request selection, fallback evidence and matched-stake surfaces.

## Failure regimes and risks

Sparse seven-leg hits make realized utility high variance; this is why the selection-adjusted lower-confidence-bound gate fails closed. Bounded generation does not enumerate C(M,7)×3^7, and may miss useful identities. Independence, frozen predicted-SP error, issue-level concentration, OOD-threshold sensitivity, and retrospective-only evidence remain material. Stage 3 emits `NO_BET` for unresolved accepted-baseline binding, policy infeasibility, or OOD safety; Stage 4 retains final capital-sizing authority.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact fixed-N7 identities over issue-specific subsets | `candidate_ledger.parquet`, tests, `decision_trace.json` | PASS |
| K/WR-WOR/repeat/overlap outputs and fallback reasons | `policy_surface.csv`, `issue_metrics.csv`, `decision.json` | PASS |
| Ticket hit and payout calibration | `ticket_calibration.csv` on CV-2022/CV-2023 only | PASS |
| Absolute plus matched lift on equal ticket/stake budgets | `policy_surface.csv`, this report | PASS |
| Baseline, simple, learned, stochastic and experimental ablations | `policy_surface.csv`, `model_parameters.json` | PASS |
| Per-issue OOD/feasibility route to learned, control or NO_BET | `issue_gate.csv`, OOD adversarial test | PASS |
| Deterministic safe floor | `LEARNED_POLICY_REJECTED_BASELINE_UNRESOLVED` and per-issue `NO_BET` | PASS — fail closed; baseline unresolved |
| Notebook/code/artifact three-layer replay | executed notebook, reusable module/tests, manifest package | PASS |

Decision input: reject learned-policy advancement in this bounded candidate universe and emit per-issue `NO_BET` until PI binds a comparable accepted ticket baseline; do not promote `MARKET_WR` merely because it won the local surface. Known risks: sparse payouts, bounded candidate recall, market-independence assumption, predicted-SP error, OOD-threshold sensitivity, selection multiplicity, and no post-2023 label access. Explicit review request: independently verify no shared roster, exact N7 uniqueness, label embargo, package-backed logistic-before-MLP ordering, full candidate regeneration/source binding, per-issue OOD/feasibility/NO_BET routing, remanifested semantic tamper rejection, matched stake arithmetic, notebook clean-run, and manifest-identical replay. No bankroll sizing, betting, merge, or issue closure is authorized.
