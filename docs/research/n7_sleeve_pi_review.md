# #424 PI review: scoped historical research delivery

Review date: 2026-09-12. Reviewed implementation: `b125a0d1`, against
`2798b83a` (three research commits, 44 files). Live contract:
[#424](https://github.com/algotradinglife/beijing-lot/issues/424).

## PI disposition

**DONE_WITH_CONCERNS: accept the numerical and accounting evidence as exposed
historical diagnostics; submit a draft PR. Do not declare full issue acceptance,
merge readiness, causal admission or a deployable strategy.**

The live graph was read before review: Task, parent #202, no dependencies or
subissues, Project status PI Review, issue OPEN. This review leaves that state
unchanged. #419 remains blocked by #421; neither lifecycle is changed.
The unresolved contract items below remain acceptance work on #424, rather than
being silently dropped or redirected by this document.

The research branch contains 80 predecessor commits beyond main before #424.
The PR therefore uses a pinned predecessor branch at `2798b83a` as its base,
and a separate #424 head. This isolates the reviewed work without representing
the predecessor stack as reviewed or merged. Do not retarget or merge into main
until that stack and its dependencies have been reviewed and reconciled.

## Contract completion audit

| Requirement | PI assessment | Evidence / remaining limit |
|---|---|---|
| Exact 2,187 states, stable identity, normalized state mass | Met for diagnostic input | `src/n7_sleeve_states.py`; enumerator and numerical regression tests; independent replay |
| Exactly 64 unique states and eight distinct fixture sets | Met for primary experiment | `src/n7_sleeve_portfolio.py`; infeasible full portfolios are NO_BET; physical ticket checks |
| Common-universe monolithic controls and seven ablations | Met as bounded numerical comparison | Eleven primary arms; same expanded universe; frontier diagnostics and matched-funded comparisons; no global optimum claim |
| Joint portfolio optimization with return, overlap and path-risk constraints | **Partial** | Separate union, overlap-penalty and return-aware arms exist; path risk is evaluated afterward. This is not one solver enforcing all three constraints together |
| Shared-world union rather than independent sleeves | Met under fixture-independence probability model | Construction/evaluation streams separated; independent bitset replay; overlap and hit-count diagnostics |
| CNY1,024, CNY2 tickets, one ticket-level 0.65, funded capital | Met | Canonical settlement helper, independent payout arithmetic, R funded accounting, cash/stop regressions |
| R matrices, tidy audit tables and reusable depth curves | Met at R reporting/export boundary | `n7_sleeve_tables()`; full depths 1–2,187, canonical codes and explicit character IDs; 200 persisted depth/long exports |
| First implementation uses R-native vectorized numerical structures | **Changed, not fully met literally** | Numerical enumeration/optimization uses NumPy/SciPy and existing shared selectors; R reconstructs/checks matrices. Avoiding a duplicate engine is reasonable, but does not constitute approval to rewrite the issue's R-first requirement |
| Causal frozen probabilities, prior-only threshold selection and transfer freeze | **Not met for causal acceptance** | Inherited model and timestamps are diagnostic proxies; exposed 100 issues; predeclared sensitivity settings do not establish cutoff-derived development/transfer partitions |
| Hash-bound freeze, imported code and independent replay | Met for this diagnostic execution | Three freeze closures; all plans freeze before target audit is opened; source/plan/evaluation receipts; this does not certify upstream historical model fitting |
| Full risk outputs and tail tests | Met where estimable | Capital, ROI, drawdown, streaks, worst windows, concentration and ex-best issue. Only 2010 exists: ex-largest-year leaves no sample; out-of-year evidence unavailable |
| Cluster inference | Not claimed | No bootstrap significance or clean generalization claim; three seeds are sensitivity runs, not independent issues |
| QMD delivery, function tests and Codex review | Met for scoped diagnostic implementation | QMD 134–136, corresponding Python/R tests, native/archive renders and recorded independent reviews |

The 15% candidate screen and 25% cap are user-authorized follow-up experiments.
The cap deliberately changes sleeve depth and permits more than eight sleeves;
it is an additional arm, not evidence that variable depth satisfies the original
fixed 8×64 contract. Its 900 fixed64 controls retain their original bytes.

## Answers to the PI adversarial questions

1. **Real union coverage, not relabeling:** the union arm changes selected fixture
   sets and states. Shared-world modeled coverage is 61.76%, versus 37.29% for
   quality sleeves. Labeling alone cannot change union coverage.
2. **Distinctness has a quality cost:** mean maximum pair overlap falls from 6
   to 2.77 and fixture concentration falls, but quality ROI 27.79% exceeds union
   ROI 6.29%. More diverse holdings do not automatically improve economics.
3. **Threshold provenance remains limited:** bounded settings were declared for
   these exposed historical diagnostics. They were not selected in a verified
   prior-cutoff development window. No clean threshold-admission gate passes.
4. **Price proxy is weak for economic selection:** estimated payout is inverse
   raw-market probability, not executable official pre-event SP. Return-aware
   selection improves proxy expectations but realizes −33.72% ROI.
5. **Dependence materially matters:** treating quality sleeves as independent
   would give 85.92% any-hit, versus the correct shared-world 37.29%. The invalid
   calculation is only a counterfactual diagnostic.
6. **Tail tests qualify gains:** quality retains 15.21% ROI excluding its best
   issue; union retains 1.81%. Ex-largest-year cannot be established here.
7. **No overall win against the stronger controls:** monolithic probability has
   52.98% ROI / 28 hit issues; monolithic coverage has −7.12% / 62 hit issues;
   quality has 27.79% / 40; union has 6.29% / 57. No arm dominates both objectives.
8. **No stable frontier established:** expansion 24→240→960 and the 25% cap do
   not deliver monotonic realized gains. Further selection from these same
   outcomes would remain retrospective tuning.

All financial figures above are medians over three seeds on the same 100
issues, not additional samples. Different median columns need not correspond
to the same seed. Modeled coverage is an average under the supplied probability
model and fixture-independence assumption, not a proven real-world hit rate.
The appropriate conclusions are limited coverage/return trade-offs; there is
**no general SLEEVE_PORTFOLIO_SIGNAL**.

## Evidence and review boundary

Retained full-run evidence:

- Primary: 3,300 frozen portfolios independently replayed; full R suite, scoped
  Python tests, cutoff checks, native and archive QMD renders passed.
- Expansion: 96,000 candidates / 1,800 plans independently checked; full R
  suite, tests and both renders passed.
- Cap: 1,800 ledger rows independently checked (900 new plans plus 900 immutable
  controls); full R suite, 23 scoped/imported Python tests and renders passed.
- Native/archive accounting CSVs matched byte-for-byte: 7, 6 and 5 respectively.

Current PI verification rechecked the 39 acceptance-bound file hashes, all three
transitive implementation closures and the absence of working-tree/index edits
to the 44 reviewed files. The eight #424 Python test files were rerun: **19
tests passed**. All four #424 R test files were rerun: **53 assertions passed**
with no failures, warnings or skips. The cutoff governance check also passed. Earlier full-suite
and complete-study replays are retained evidence, not claimed as newly rerun.
The machine-readable PI receipt records exact identities and current checks.

The final independent [Codex PI review](n7_sleeve_codex_pi_review.md) found no new
critical correctness defects in the full scoped diff, independently passed 34
Python tests and 53 R assertions, and confirmed the outstanding contract gaps.
Its verdict is draft-ready historical evidence, not full #424 acceptance.
See [PI receipt](n7_sleeve_pi_receipt.json) for checked hashes and scope.

Transitive decision inventory: `enumerate_sleeve`, `select_sleeve_states`,
`build_sleeve_candidates`, `sleeve_portfolios`, `expand_top64`, `sample_top64`,
`sample_capped_sleeves`, and imported `rank_double_candidates`,
`select_probability_gate`, `incremental_coverage_plans`; inherited probability
calibration includes `draw_cells`, `fit_draw_foundation` and
`predict_draw_foundation` under diagnostic temporal context. Independent checkers
replay these contracts. Shared `src/temporal_learning` owns cutoffs, stable
hashes and implementation closure checks. R table/accounting functions describe
frozen outputs; `settle_single_tickets` consumes labels after the freeze.
No new fit, expert retraining, recency policy or cross-cutoff cache is admitted.

The archived CI lane proves portable accounting/report replay, not reconstruction
of absent native raw sources or prospective chronology. Remote PR CI must be
read separately; local passing logs do not assert that remote checks passed.

## Remaining acceptance decisions

1. Resolve the R-first implementation requirement explicitly in the live #424
   contract, or implement the required R-native numerical path without keeping
   duplicate business implementations. This review has not waived that clause.
2. Establish cutoff-safe probability/price and prior-development evidence before
   accepting causal or transfer claims. The current exposed package remains an
   inventoried diagnostic; freezing it now does not repair historical leakage.
3. Complete or explicitly revise the joint portfolio-constraint requirement:
   the separate controls and ex-post risk tables do not certify constrained
   union optimization under simultaneous return, overlap and path-risk limits.
4. Review the predecessor stack before any main-branch merge. The draft PR is
   intentionally scoped and does not approve its unmerged dependencies.

These are reasons to keep #424 open in PI Review and the PR draft. They do not
prevent publishing the reproducible diagnostic results for code review.
