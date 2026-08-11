# Issue #206 decision report — fixed-N7 ticket generation

## Decision

`INHERIT_STRONGEST_FROZEN_CONTROL`. The validation-selected challenger was `LEARNED_MLP` at K=8; the strongest matched control was `MARKET_WR` at K=8. The paired validation realized-lift one-sided 95% lower bound was -0.914040. The deterministic gate therefore emitted `VALIDATION_UNCERTAINTY_OR_MATCHED_LIFT_FLOOR`.

The fallback-mixed CV-2023 path delivered absolute realized pre-tax net -1.000000, expected pre-tax net 78.369429, coverage 0.000000, and matched realized lift +0.000000 at exactly ¥880 turnover. No apparent improvement from fewer tickets or cash is accepted.

The issue-specific gate fits scikit-learn `StandardScaler` on CV-2021 issue-level safe-feature medians and freezes the CV-2022 99.00% maximum-absolute-z threshold at 7.549834. It evaluates feasibility and OOD before every locked handoff; 0 locked issues exceed the threshold. `issue_gate.csv` reports learned-only, pure-control and fallback-mixed paths separately, including deterministic safe-control and `NO_BET` reasons.

## Constraint and evidence interpretation

- Every ticket has exactly seven distinct match ids and one 3/1/0 outcome per match. There is no global seven-match roster.
- The three fixed nuisance seeds generate a bounded full-issue candidate pool; seed choice is never outcome-ranked.
- Exact duplicate ticket identity is separately measured from match overlap. Controlling WOR policies request distinct identities; repeat stake remains an explicit, traceable action rather than accidental duplication.
- Only #205 `MARKET_ONLY` / `FROZEN_SAFE_BASELINE` control probability and frozen pre-event SP enter the controlling policy. Experimental residuals appear only in `EXPERIMENTAL_MLP_ABLATION`.
- 651 source matches with all three safe-control probabilities missing are explicitly recorded in `input_exclusions.csv`; partial/non-finite, non-positive, non-normalized, incomplete-M×3, and post-exclusion M<7 inputs fail closed.
- Training uses CV-2021, policy/K selection uses CV-2022, final historical evaluation uses CV-2023. LOCKED_TEST 2025/2026 labels remain embargoed; its Stage-3 handoff is label-blind.
- The semantic verifier recomputes the OOD gate, issue routes, ticket selection, identity/list/source-trace agreement, 3/1/0 outcome domain, joint probability, SP product, expected utility, fallback evidence, and matched-stake surface after manifest validation.

## Failure regimes and risks

Sparse seven-leg hits make realized utility high variance; this is why the lower-confidence-bound gate fails closed. Bounded generation does not enumerate C(M,7)×3^7, and may miss useful identities. Independence, frozen predicted-SP error, issue-level concentration, OOD-threshold sensitivity, and retrospective-only evidence remain material. Stage 3 may emit `NO_BET` only for policy infeasibility/OOD safety; Stage 4 retains final capital-sizing authority.

## PI 对接块

| Acceptance criterion | Evidence | Result |
|---|---|---|
| Exact fixed-N7 identities over issue-specific subsets | `ticket_requests.parquet`, tests, `decision_trace.json` | PASS |
| K/WR-WOR/repeat/overlap outputs and fallback reasons | `policy_surface.csv`, `issue_metrics.csv`, `decision.json` | PASS |
| Ticket hit and payout calibration | `ticket_calibration.csv` on CV-2022/CV-2023 only | PASS |
| Absolute plus matched lift on equal ticket/stake budgets | `policy_surface.csv`, this report | PASS |
| Baseline, simple, learned, stochastic and experimental ablations | `policy_surface.csv`, `model_parameters.json` | PASS |
| Per-issue OOD/feasibility route to learned, control or NO_BET | `issue_gate.csv`, OOD adversarial test | PASS |
| Deterministic safe floor | `INHERIT_STRONGEST_FROZEN_CONTROL` and paired LCB | PASS — conservative inheritance |
| Notebook/code/artifact three-layer replay | executed notebook, reusable module/tests, manifest package | PASS |

Decision input: retain `MARKET_WR` with K=8 as the Stage-3 requested-ticket control; do not claim learned-policy advancement. Known risks: sparse payouts, bounded candidate recall, market-independence assumption, predicted-SP error, OOD-threshold sensitivity, and no post-2023 label access. Explicit review request: independently verify no shared roster, exact N7 uniqueness, label embargo, package-backed sampling/model/statistics, per-issue OOD/feasibility routing, remanifested semantic tamper rejection, matched stake arithmetic, notebook clean-run, and manifest-identical replay. No bankroll sizing, betting, merge, or issue closure is authorized.
