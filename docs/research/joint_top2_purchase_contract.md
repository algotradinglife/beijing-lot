# Joint purchase efficiency: fixed-probability comparison

User authorization: retain joint portfolio selection and absorb Top2 purchase
ideas. This is retrospective research, not probability calibration or deployment.
Live graph checked: #459 is open, Project Review, no dependencies or children;
PR #462 is open on codex/recent295-diagnostics. This document changes neither.

## Frozen comparison

Use the verified expanded-study catalog and the common 484-issue calendar used
in the probability attribution. Preserve the original frozen joint probabilities
and raw-market q prices. Do not substitute HANDICAP or RAW for that primary
control. Reproduce original joint tickets/accounting before interpreting changes.
Hard Top2 is regenerated on this SAME probability surface as a purchase control;
the earlier HANDICAP Top2 curve is not the comparator.

Explicit constants: N=7, unit CNY2, issue budget ceiling CNY1,024, initial capital
CNY100,000, one ticket-level 0.65 factor, original SP admission threshold 1.3.
Cash is retained when constraints prevent spending. Actual settlement SP enters
only after all plans have been frozen. No score protection or expert training.

## Controlled directions

1. Purchase ordering: original joint ordering; hard Top2; a soft third-outcome
   penalty conditional on the original second-minus-third gap. Preserve original
   state probability and expected payout for all evaluation. A purchasing weight
   is not a recalibrated probability. Test large-gap preference separately from
   close-gap behavior; record displaced second-outcome tickets and new thirds.
2. Concentration: cap fixture participation and outcome-specific stake exposure.
   Exposure for fixture f and direction d is the money in purchased tickets
   requiring d at f. Conditional loss if outcome d occurs is the stake requiring
   other directions at f. Report both, including maxima. This is not a claim that
   all remaining tickets win or that all fixture risks are independent.
3. Allocation: reuse n7_core_allocate OPEN_FIRST versus COMPETE with a common
   legal depth grid. COMPETE already ranks marginal union probability per CNY;
   do not create a second allocator merely to rename this existing mechanism.
   Distinguish expanded depth-grid effects from allocation-order effects.

Start with one-factor comparisons, then combine only a small explicitly recorded
set of mechanisms. Historical parameter comparisons remain exposed diagnostics;
do not select retrospective winners and call their results out of sample.
Any history-based trust score or adaptive selection must use temporal_learning;
initial purchase constraints are explicit fixed parameters, not fitted reliability.

## Reuse and implementation boundaries

Reuse r/n7_probability_replay.R, r/n7_core_opportunity.R and shared scenario
generation/settlement. Existing third_outcome_ticket_plan supplies useful canonical
state validation, but assumes fixed funded groups and depth <=128; it cannot
silently represent full joint reallocation. Implement only the missing purchase
surface transformation and concentration checks, with corresponding tests.
Retain complete source, cutoff, implementation and parameter identities. Freeze
all target plans before settlement and independently replay selection/accounting.

## Acceptance

### Subsequent owner steering

The full 11-arm fixed-constraint run remains the reference and must not be
rewritten in flight. Add separate comparisons in which reuse grows only with
probability distinction: Top2 boundary p2-p3 controls fixture-use limits, while
direction-specific stake requires that direction to clearly outrank alternatives.
These fixed probability rules are not claims of empirically calibrated trust.

Also examine seven-fixture group composition (core/middle/opportunity) and curve
shape before joint allocation. A desirable concentrated head with a long tail is
not a flat distribution. Report Top16/32/64/128 mass and the ticket costs reaching
15/20/25% before setting explicit, disclosed shape bands. Similar curves must not
be interpreted as independence. Candidate roles and shape constraints must be
tested separately before combination; no forced opportunity leg in every group.
Any candidate-generation extension must retain a same-candidate control so its
effect can be separated from allocation. The original candidate universe may not
contain enough requested role combinations; report that support rather than
silently substituting a different role mix.

QMD presents all issues and fixed BEFORE/DRAWDOWN/AFTER strata, actual stake,
cash, net, ROI, hit/profit issues, drawdown amount/percentage, minimum equity,
fixture/outcome exposure, breadth/depth, rescued/lost periods, and removal of each
strategy's own best 1/3/5 periods with associated stake and return removed.
Compare equal-budget policies and disclose spending differences; lower drawdown
from holding cash alone is not evidence of superior selection. Use original
probabilities for model coverage, shared worlds for overlapping groups, and
separate-world checks for simulation noise. Send plots directly to the session.
Finish with adopt/reject/insufficient evidence conclusions, tested reusable R
functions, independent replay, Codex review, commit/push and PR evidence update.

## Full accepted-data replay entry

`quarto/200_joint_purchase_comparison.qmd` accepts explicit `catalog`, `config`,
`config_sha256`, `output`, `python`, `settle`, `labels`, and `labels_sha256`.
The configuration binds the catalog hash and issue list. `settle: false` freezes
all purchase plans without opening settlement; structure allocation and independent
replay follow before the settlement report. `limit` is only for smoke verification,
never for claiming full-scope completion. Missing identities fail rather than
selecting an implicit latest release. Fixed budget, seed, coverage, unit, SP floor
and payout settings are checked against this experiment's original constants.

The latest accepted union must report original, additional and complete eligible
issues separately. Market-publication counts are not betting eligibility counts.
Any explicit fixture exclusion carries issue, original slot, reason and verified
roster hash in the preparation receipt; both markets are removed together while
the original published/raw data remain unchanged. An exclusion must exist in the
input and cannot silently remove an entire issue from the requested scope.

The `140401/63` diagnostic exclusion records a noninteger original lottery
handicap (`-0.5`). The displayed abandoned status is supporting context, not a
replacement handicap or permission to rewrite source data. Full-data results
must retain this exclusion ledger alongside missing-market and settlement gaps.

## Independent replay entry points

The mathematical verifiers are retained in the repository rather than only in
local review artifacts. They are diagnostic checks, not purchase or fitting APIs;
they do not import the production purchase/settlement functions.

- `Rscript scripts/check_n7_purchase_replay.R PLAN_DIRECTORY RECEIPT_SHA256 OUTPUT_JSON`
  reconstructs all 2,187 canonical states, ranking, exposure and greedy allocation.
- `Rscript scripts/check_n7_purchase_gates.R MAIN_DIRECTORY STRUCTURE_DIRECTORY OUTPUT_JSON`
  independently reconstructs head mass, coverage cost, roles and admitted options.
- `Rscript scripts/check_n7_purchase_settlement.R REPORT_PARAMS_JSON OUTPUT_JSON`
  checks official ticket payouts and chronological accounting after labels open.
- `Rscript scripts/check_n7_purchase_cohorts.R REPORT_PARAMS_JSON OUTPUT_JSON`
  binds the report to the requested parent receipts, catalog and labels, then
  independently checks ALL/ORIGINAL/ADDITIONAL accounting against the frozen
  policy roster. Omitting an entire policy from both tables is rejected.

Use a fresh output path and the declared project R environment. The first two
checks must pass before opening new labels; the third runs after report rendering.
Bind verifier code hashes and resulting proof hashes in the acceptance record.
Run long checks from a hash-bound immutable script copy; do not edit an R script
while its process may still be reading it. The repository entry regression tests
exercise changed purchase lists, malformed identity, missing columns, inconsistent
net returns and mismatched parent receipts, alongside valid synthetic reports.
These checks do not establish historical source availability or authorize a
prospective learned policy. The settlement check covers the original stage
summaries; the cohort extension additionally requires ORIGINAL/ADDITIONAL/ALL
scope and accounting reconciliation. Its reusable implementation is
`r/n7_purchase_cohort_audit.R`, tested by
`tests/testthat/test-n7-purchase-cohort-audit.R`, including tampered summary fields,
missing policies/issues, invalid cash, wrong cohort membership and stale source
bindings. Each independent cohort starts at the declared initial capital, while
ALL remains a single uninterrupted account.

## First expanded snapshot and latest-release extension

The first expanded accepted-source snapshot requests 735 issues: the original 484 and 251
additional issues. The candidate catalog admits 734 (484 + 250); `110915` remains
`NO_USABLE_MARKET_PROBABILITIES`, not a losing or cash-only betting period.
The catalog SHA-256 is
`fa6929fcc3c6afc39b3168d2854e65b453a845635a4ad4644acd1dcabdfbb255`.
The combined-input receipt binds the accepted releases and every candidate bundle.
Do not interpret this as coverage of every issue ever published: it is the
complete eligible union of the accepted inputs identified by this receipt.

The subsequent registry recheck found the accepted `140412-140901` release:
`afb8b42bd933c2dae3f6adbafeaa3742aaa3f9a9d509e95fd349a8e072cc4da6`.
Its 50 additional issues expand the requested union to 785. The prior release's
645 issue-level published row sets are byte-equivalent after canonical encoding;
the new acceptance and Codex-review receipt hashes have been verified. Complete
delivery must include this extension; the 734-issue replay is an intermediate
snapshot, not final full-data acceptance. Betting eligibility for the new 50 is
determined by the same projection/candidate contracts, not presumed from cleaning
acceptance. Freeze this explicit release for the comparison rather than chasing
unbounded subsequent registry publications during computation.

`quarto/202_joint_purchase_report.qmd` additionally requires the explicit
`catalog` parameter and verifies it against the frozen main purchase receipt.
Its scope and unavailable-issue tables must reconcile to the complete requested
union, and all 21 policies must retain the same eligible issue calendar. Original
484-issue narrative is labeled separately until the full-union conclusion is
verified. Original/additional comparisons use independently initialized accounts;
the ALL curve uses one continuous account without replenishing capital.

The post-freeze label entry is `scripts/prepare_n7_purchase_labels.py CONFIG`.
It requires main and structure allocation replay plus group-gate replay, exact
receipt/catalog/bundle bindings, current implementation closure and purchase-file
hashes before opening outcomes. It preserves missing outcomes rather than
turning them into losses. `scripts/settle_n7_expanded_batches.R CONFIG` then uses
the authoritative R/SQLite settlement audit; report rendering follows only after
the full scope is resolved or unresolved cases are explicitly accounted for.

## Funding exhaustion discovered in the expanded replay

The first 734-issue report stopped on the existing unaffordable-plan guard.
Do not raise the CNY100,000 initial capital, drop the affected policies/issues,
or silently report debt-financed plans as executed wagers. Purchase plans and
probability inputs remain unchanged. Use `r/n7_purchase_accounting.R` to reuse
the authoritative `strategy_equity_curves()` funding ledger and report both:

- FUNDED: execute whole affordable plans; permanently hold remaining cash after
  the first unaffordable plan, without deposits, debt, partial plans or resumption.
- SHADOW: continue all frozen plans diagnostically; capital may be negative and
  is not a claim of performance achievable with the declared initial capital.

Every evaluation/cohort is tagged by accounting basis. ALL uses one continuous
account; each separately reported cohort/stage initializes independently. Report
the first unaffordable issue and stopped issue count. `cash_cny` denotes unused
nominal per-issue budget, not new cash credited to a depleted account.

`rows.csv` and `groups.csv` preserve planned outcomes. `funded_groups.csv` records
only executable groups. `curves.csv`, `summary.csv`, `cohort_summary.csv` and
`trimmed.csv` distinguish both bases; default equity/drawdown figures are funded,
with separately labeled shadow figures. Probability-shape plots describe funded
groups, while exposure diagnostics remain explicitly plan-level. Trimming the
largest gains removes their costs/returns from each existing ledger; it does not
refit a strategy or recompute funding stops after deleting those gains.

The accounting and cohort tests cover exhaustion followed by later shadow
profits, no-bet ROI, independent cohort starts, full-scope validation and unchanged
metrics on affordable histories. The physical settlement entry tests include 100
consecutive losing plans, exact stop at issue 98, negative shadow capital, and
rejection of falsely funded curves or a wrong stop issue. Independent replay must
validate both bases and funded-group execution before final acceptance.
