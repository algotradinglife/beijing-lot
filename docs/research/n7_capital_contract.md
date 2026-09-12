# #425 execution contract — N7 prefix capital frontier

Live Issue #425 is authoritative. Claimed In Progress by current task on2026-09-13;
no blockedBy/blocking, no native parent/subissues, issueType unset. Body references
#202/#424/#427 are scientific context, not invented native graph edges.

Research only, already-exposed100issues. No target outcomes or actual SP in
allocation; freeze every plan before this run opens settlement. Explicit native
cutoff validation/shared temporal receipts remain. Main integration is separate.

Reuse R n7_sleeve_tables, n7_joint_validate/worlds, authoritative single-ticket
settlement, and existing equity/ROI summaries. The frozen24 candidate seven-match
sets remain the primary universe; no expanded candidate pool in the first grid.
Deduplicate unordered physical sets; retain ordered canonical state identities.

Budgets512/1024/2048/4096CNY; unit2CNY; ticket payout factor0.65 once. Three fixed
seeds42501/42502/42503. Initial equity100000CNY, cash retained and spending limited
by available capital; chronological accounting assumes prior returns available
before next issue funding. Availability remains diagnostic/unproven.

Domain prefix ranking is the existing deterministic (-p,-value,state_id) rule.
Full depth curves0..2187 and exact threshold inverse are authoritative. Solver
candidate depth grid is explicit and separate from full threshold resolution:
8/16/32/48/64/96/128/192/256/384/512/768/1024/1536/2048/2187, plus zero via unselected
sleeves and budget clipping of infeasible options. Equal-depth and common-coverage
controls have separate support spaces. No claimed optimum outside registered
candidate depth grid or finite24sets.

Preference proposals to be frozen before batch: maximize any-hit probability at
explicit expected ROI floors -20%/0%; maximize at-least-two-hit probability at
-20%; maximize exact expected net at modeled any-hit floors25%/50%. These are
research conventions, not fitted user utility or inherited #424 -35% rule. Report
conditional mean gains/losses, their probability, payoff ratio and support as
model diagnostics; no unsupported ratio receives infinity. Fixed conditional
mean payout assumption does not model settlement-SP uncertainty.

Controls: historical8x64PROB at1024; same-budget equal-depth shapes when feasible;
common cumulative thresholds10/15/20/25%; row-additive vs joint nonuniform space;
deterministic random matched support and budget; archived monolithic references
with candidate-access mismatch disclosed. True joint outcomes share fixtures.
Optimization and independent numerical-evaluation worlds are separately seeded.
No settlement-based parameter revision inside one frozen version.

Acceptance requires answer tables of budget/preference versus funded sleeve count,
complete depth/actual coverage, equal-weight mean sleeve coverage, weighted mean,
unique fixtures, money/cash, modeled hit/profit/loss and expected return, realized
per-issue ROI, drawdown/tails/segments/seeds and matched-spend comparisons. All2010
only: cross-year/ex-year diagnostics unavailable, not blockers. Enumerated tiny
oracles, function tests, independent accounting replay, fresh executable QMD,
Codex review and submitted PR. No automatic main merge/issue closure.

Implementation now includes exact depth contracts, prefix MILP, physical-ticket
packing with sorted fixture/outcome identity, monetary exposure, shared-world
metrics, and an R issue runner. Python reuses the #424 freeze/evaluate pipeline
with explicit R entry point/source inventory and a domain reporting callback.
No parallel receipt or settlement implementation was added.

The v1 configuration is config/n7_capital_425.json:68arms x3seeds x100issues,
including4budgets. Simulation256optimization/5000evaluation worlds; offset1000000;
40nodes,1% solver gap,15seconds per solve,8process workers. Time-limit incumbents
are best-found only and timing may change which incumbent is returned; frozen
ticket/scenario replay is the reproducibility contract, not bit-identical timed
optimizer reruns. Raw solver status/bounds/gap are retained. Numerical precision
of evaluation probabilities is finite-world Monte Carlo, not historical error.

A prediction-only pilot on100608 exposed infeasibility at ROI floors -20% and0%.
Both remain registered; unconstrained any-hit and at-least-two controls were added
before opening this run's settlement. Row-additive and seeded random objectives
use the same nonuniform space/budget and no ROI floor, matching the unconstrained
joint arm. Random objective does not mean uniform allocation sampling. Threshold
and equal-depth controls allow cash, so matched-spend evidence must be separate.
Pilot files under the personal review-artifact directory are operational checks,
not a completed historical study or evidence for choosing a profitable policy.

## Reporting and independent verification

`quarto/140_n7_capital_frontier.qmd` is the analysis entry point. Reusable R
summaries live in `r/n7_capital_report.R`; descriptive same-depth/threshold
comparisons and registered-policy frontiers live in `r/n7_capital_compare.R`.
These diagnostics do not prune candidates or feed a revised allocation.
The QMD includes budget versus group count/coverage/model return, funded equity
and drawdown, per-issue returns and ROI, matched actual spend, solver diagnostics,
and the difference between model and realized conditional payoff ratios.

`scripts/package_n7_capital.py` creates its portable input only after a complete
freeze and evaluation. It invokes the common source/implementation/receipt
checker and `src/n7_capital_check.py` to independently reconstruct all prefix
curves, physical tickets, shared-world diagnostics and actual settlement. This
second settlement calculation is an independent audit, not a competing storage
or production settlement API. The portable report includes all issue results
and allocation depths plus one full-curve example; the external frozen package
retains the complete physical-ticket and scenario evidence.

Function tests map to `tests/testthat/test-n7-capital-{depth,portfolio,issue,report,compare}.R`
and `tests/test_n7_{joint_study,joint_check,capital_study,capital_check,capital_archive}.py`.
Rendering and full-study replay remain separate acceptance checks.

## Batch failure and recovery evidence

The first complete attempt stopped after69issues when issue101012 exceeded its
3600-second subprocess limit. No complete freeze receipt or evaluation exists
for that attempt. The Python coordinator retained completed Future objects and
their large results; its resident memory reached approximately7.3GB while host
memory and swap were exhausted. Commit0aad09d0 releases each completed Future
after taking its result and preserves the original total for progress reporting.
A regression test observes release while the study is still running; it fails
with the old implementation and passes with the fix.

The replacement run uses the same research configuration and original source
bundles, in a new output directory with a new implementation binding. No partial
plans or results from the failed attempt are imported into the replacement.
The failed attempt is retained as diagnostic evidence under the external data
root's `audits/issue425-capital-v1`; the replacement is
`audits/issue425-capital-v2`, with its log in
`runtime/logs/issue425-capital-v2-freeze.log`. Neither directory is a production
release. Reports belong under the persistent root's `reports/` directory.

Remaining: full frozen batch, independent full-study replay/accounting, report
execution and interpretation, final checks, final Codex review, PI classification
and PR. The memory-fix review found no actionable defects but did not run the
tests successfully in its chosen interpreter; separate project-interpreter
tests passed. This narrow review does not replace final research acceptance.
