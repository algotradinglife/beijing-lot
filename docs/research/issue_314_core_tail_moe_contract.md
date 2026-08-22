# Issue #314 — CORE/TAIL Soft-MoE, Explicit Coverage and Dynamic Exposure

Contract: `BJ-UNIFIED-CORE-TAIL-MOE-001/v1`

Mode: exploration. PI owns implementation and scientific review directly.
Post-merge EV is asynchronous and advisory.

## Strategic purpose

#312 rejected a small action-conditioned MLP followed by hard argmax. It did not
reject learning from the M×3 tensor: mean action ranking retained weak information,
while hard top-action selection amplified estimation error and long-tail winner's
curse. This successor tests a different decision layer:

1. maintain several interpretable ticket experts;
2. allocate continuously across them with a soft mixture-of-experts gate;
3. make single/double outcome coverage and capital exposure explicit decisions;
4. use 2023 and 2024 issue-level attribution to discover why near-winning tickets
   failed and which defects can be corrected before the event.

The accepted baseline ladder is never replaced by narrative judgment. Every result
reports absolute CNY100,000 capital and matched lift versus the strongest frozen
control on identical issue support.

## Inheritance and prior constraints

- #312 contributes the exact-support action interface and the negative hard-argmax
  result. Its learned policy is not an accepted Edge.
- Fixed N7/K512/WOR remains a same-exposure safety control, not a claim that N=7 or
  K=512 is optimal.
- #285 found that adverse-divergence wrong-leg localization was about four percentage
  points better than random at equal issue weight, but blanket protection remained
  negative after its added stake. Therefore protection must be selective and no
  protection remains a matched action.
- #167/#170 showed selector and allocator improvements do not automatically add.
  Stage interactions must be estimated explicitly.
- Beijing 0.65 is applied once to each complete winning N-fold ticket. It is never a
  per-leg or per-cell discount.

## Independent unit and chronology

- Independent unit: Beijing issue.
- Matches, M×3 cells, tickets, sampled subsets, experts and nuisance seeds are nested
  observations; they never increase the issue-level sample size.
- 2019–2021: training and expanding-OOF expert/gate fitting.
- 2022: model/factor screening, calibration and risk-constraint tuning.
- 2023: model-unseen validation plus issue-by-issue attribution. Human exposure is
  acknowledged; 2023 cannot be relabeled as untouched.
- Freeze the complete final expert library, gate, coverage rule, exposure rule,
  fallback, seed schedule and 2024 common-support receipt after 2023 diagnostics.
- 2024: one-shot terminal historical holdout. It is model-unseen, not necessarily
  human-unseen. No 2024 result may retune the frozen policy.
- 2025+ remains outside this Issue.
- Persist `source_temporal_role` and `experiment_role` as separate fields. A role
  inherited from a source contract may never stand in for this experiment's role;
  the overloaded legacy name `temporal_role` is not part of the #314 interface.

## Model inputs

Use only decision-epoch information accepted by the causal tensor contracts:

- mapped average-European-odds probability for each M×3 cell;
- Beijing handicap-line probability prior;
- their signed and absolute divergence as separate channels;
- accepted model probability/value and uncertainty channels;
- line, probability, SP/value, entropy and cross-match distribution summaries;
- upstream selection and coverage decisions when fitting a downstream component.

Do not compress all disagreement into one scalar. Keep European-market-versus-line,
future team-strength-versus-line and other sources as separate expert channels. Team
strength is included only if a causally aligned accepted input exists before freeze;
its absence cannot be silently imputed from outcomes.

## Expert library

The first library is deliberately small and interpretable.

### CORE experts

CORE receives most capital and targets break-even or modest positive compounding:

- strongest exact-support fixed N7/WOR control;
- value-ranked WR and WOR experts;
- market-probability calibrated expert;
- conservative selective-protection expert inherited from the #285/#286 interface;
- simple equal-weight CORE mixture.

CORE selection uses shrunken expected net return/log-capital growth with constraints on
ex-largest P&L, drawdown, losing streaks and rolling windows. Maximizing hit rate alone
is forbidden.

### TAIL experts

TAIL may pay only once every one or two years, but it receives a minority sleeve:

- higher-N/high-payoff value expert;
- divergence-direction expert;
- low-overlap distinct-ticket expert;
- a small number of predeclared protection/tail constructions.

TAIL is evaluated on long-run contribution, payoff interval, maximum drag, ex-largest,
and correlation with CORE. One historical jackpot cannot authorize a large weight.

Start with CORE 85–95% and TAIL 5–15% as screening anchors. The final weights are
learned continuous outputs, not a globally fixed grid choice.

## Explicit action and coverage semantics

Each physical N-fold ticket still selects exactly one result for each selected match.
Coverage depth describes the support of the issue-level ticket bundle:

- `N ∈ {3, ..., 10}`;
- `coverage_depth[j] ∈ {1,2}` for selected match j;
- depth 1 means one supported result; depth 2 means a main result plus one explicitly
  selected protection result;
- depth 3/full three-result coverage is excluded from this cycle;
- `protected_leg_count = sum(coverage_depth[j] - 1)` is an explicit learned/action
  parameter;
- the model must identify the main result, optional protection result and reason;
- WR/WOR then samples physical tickets inside that frozen support. Sampling cannot
  silently substitute for the coverage-depth decision.

Compare every learned protection configuration against no protection and a same-budget
random protection control.

## Dynamic K and capital exposure

K=512 is a comparator, not an operational constant or maximum.

- Model log-ticket count and issue exposure as continuous/ordinal outputs conditioned
  on the current issue matrix and selected expert mixture.
- Do not impose an arbitrary single-issue stake cap. Natural constraints are the
  available bankroll, CNY2 ticket granularity, executable distinct-ticket support and
  deduplication.
- Separate a funded CORE base from non-negative incremental exposure. The primary
  model does not manufacture alpha by selecting CASH/NO_BET for difficult issues;
  cash is reported only as an external diagnostic.
- Publish the complete marginal-K curve until additional unique tickets have
  non-positive predicted marginal value or the natural funding/support boundary is
  reached.
- Increasing K counts only if incremental gross exceeds incremental stake and the
  issue-level capital/path constraints remain acceptable.

## Experimental design and learning

Do not run an unbounded Cartesian grid.

1. Use a reproducible space-filling/fractional design to screen interactions among N,
   selector, outcome direction, coverage depth, protected-leg count, WR/WOR, expert
   identity and log exposure.
2. Preserve fixed anchors and fully matched one-factor resets for N, K/exposure,
   generator, candidate pool/selector, outcome direction and coverage/protection.
   Each reset must hold issue, seed, budget and every other factor fixed. Descriptive
   outcome-exposed marginals are labeled post-hoc and cannot replace these resets.
3. Fit regularized linear/stacking and maintained tree models as simple controls.
4. Fit a neural gate only as a challenger. It receives weight only if chronological
   OOS evidence beats the simpler gate.
5. The MoE output is a soft expert-weight vector plus structural/exposure parameters;
   hard argmax over the full action cube is prohibited.
6. Use issue-grouped chronological folds and equal issue statistical weight.
7. Freeze a fallback to the strongest control whenever OOS risk-adjusted matched lift
   is not positive. This is a model constraint, not a post-result story.

## 2023–2024 issue-level near-miss attribution

For the frozen learned policy and matched controls, persist sufficient ticket identity
to analyze every issue chronologically. For each losing ticket report
`miss_distance = N - correct_leg_count` and focus on d=1 and d=2.

Assign failure through a staged attribution ledger:

1. the eventual match was not selected;
2. the match was selected but the realized outcome was outside the frozen depth-1/2
   support;
3. the realized outcome was in support but finite WR/WOR sampling did not generate the
   winning identity;
4. the winning identity was generated but received insufficient copies/capital;
5. the selector/value/SP threshold removed the relevant branch;
6. model direction error or cold-outcome underestimation.

Report by issue/year/N/expert: gap-count distribution, error reason, selected and
realized probability rank, SP/value, divergence, coldness, coverage depth, K and
exposure. Include frozen counterfactuals for one additional protection result and
marginal K, with their real added stake. The 2024 attribution is explanatory only and
cannot change the 2024 policy.

## Controls and responses

Matched controls on identical issue calendars include:

1. exact accepted BEST_FULL/B0 baseline where executable identities exist;
2. fixed N7/K512/WOR;
3. best train-only static action;
4. equal-weight CORE mixture;
5. simple fixed CORE/TAIL split;
6. learned soft MoE;
7. no-protection and same-budget random-protection ablations;
8. fixed-exposure and learned-exposure ablation;
9. issue-state and action-identity shuffles;
10. cash/NO_BET as a diagnostic outside Edge attribution.

Primary evidence is the issue-by-issue CNY100,000 pre-tax capital path. Also report
turnover ROI, matched lift, positive issue rate, hit/tail frequencies, max drawdown,
time under water, recovery issues, longest losing/no-payout run, rolling 5/10/20 worst
windows, ex-largest issue/year, HHI/overlap, expert weights, K/exposure distributions,
and 2023-versus-2024 drift.

## Decision semantics

- `NO_LEARNABLE_INCREMENT`: no learned gate/coverage/exposure component beats the
  strongest matched control; retain the baseline and preserve attribution findings.
- `STRUCTURAL_SIGNAL`: one or more coverage/exposure/expert factors add stable matched
  lift but the full mixture does not pass terminal constraints.
- `MOE_SIGNAL`: the frozen 2024 soft mixture beats the strongest matched control in
  absolute ending capital and matched lift without worse ex-largest/path risk or a
  lower-exposure explanation.
- `CANDIDATE_SIGNAL`: additionally survives adjacent settings, issue bootstrap,
  year/ex-largest removal and funding/executability checks. Only this disposition may
  replace the candidate inherited by #210.

Negative results are information, not a reason to stop analysis. The terminal report
must identify which stage failed and the next evidence-bounded improvement direction.

## Executable requirements

- **REQ-314-01:** Freeze chronological roles, 2024 support and all target-outcome/SP
  read boundaries before terminal settlement.
- **REQ-314-02:** Deliver explicit depth-1/2 coverage, protected-leg count and main/
  protection outcome identities; reject depth 3.
- **REQ-314-03:** K/exposure is dynamic and has no arbitrary 512 or single-issue cap;
  all natural funding, uniqueness and marginal-value constraints reconcile.
- **REQ-314-04:** Deliver interpretable CORE/TAIL experts, simple gates and a neural
  challenger with soft weights; prohibit hard full-cube argmax.
- **REQ-314-05:** Every learned arm reports absolute capital and matched lift versus
  the strongest frozen baseline on identical support/exposure semantics. Deliver
  matched single-factor attribution for N, K/exposure, generator, candidate pool/
  selector, outcome direction and coverage/protection; uncovered factors cannot be
  interpreted as zero increment.
- **REQ-314-06:** 2023 validation and frozen 2024 terminal remain separate; 2024 never
  retunes the model. Persist separate `source_temporal_role` and `experiment_role`
  fields and enforce their cross-table consistency.
- **REQ-314-07:** Deliver complete 2023–2024 d=1/d=2 staged attribution and funded
  protection/marginal-K counterfactuals.
- **REQ-314-08:** Deliver package-first Python, focused tests, an executed Jupyter
  notebook, compact results/figures, manifest and a decision report. Bind external
  source snapshots by path-independent manifest and provide ticket-level replay
  primitives/receipt plus access instructions; large source databases remain outside
  Git.

## Resource and delivery boundary

Use existing numpy, pandas, scipy, scikit-learn and maintained project dependencies;
do not implement estimators from scratch. Stage the computation and cache immutable
surfaces in SQLite/Parquet. Target under six wall-clock hours per complete replay and
under 12 GB peak memory; if the space is larger, screen then refine instead of silently
truncating the scientific question.

Paper research only. No live betting, release, frontend or production authority.
