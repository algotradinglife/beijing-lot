# Probability foundation versus purchasing implementation

This study diagnoses the difference between the frozen JOINT ledger and the
HANDICAP_PROB result. It does not select new calibration parameters.

## Frozen comparison

- Source: `audits/issue459-expanded-v1/settlement-inputs/catalog.json`, SHA256
  `3b502b7827a93354ff74e826829779391bb062a1b9b41d6cf3a11537d397ef00`.
- Reference results: `audits/issue459-expanded-v1/evaluation/results.csv`, SHA256
  `7ec5f907de61fc2f3571a3b0fbc333724c574058e3225058a077a011b43ba6ff`.
- Reference: JOINT, seed 42501, budget CNY1,024, minimum estimated SP 1.3.
- Seven fixtures, CNY2 per ticket, one ticket-level 0.65 payout factor,
  CNY100,000 initial capital; retained cash is not spending.
- Old foundation: the frozen source bundle probabilities, historical evidence
  only. Replaying them does not establish prospective historical availability.
- New foundation: the HANDICAP specification in
  `config/top2_outside_validation.json`, with the same 49-block calendar over
  all post-warmup issues, including the previously excluded drawdown window.
- No parameter, block boundary, seed or rule is selected from target returns.

## Four cells and equivalence gate

| Cell | Foundation | Purchasing implementation |
|---|---|---|
| A | Frozen source | `n7_probability_allocate` |
| B | HANDICAP | `n7_probability_allocate` |
| C | Frozen source | `n7_top2_options(PROB)` + `n7_top2_allocate` |
| D | HANDICAP | `n7_top2_options(PROB)` + `n7_top2_allocate` |

These are implementation comparisons until a substantive rule difference is
demonstrated. Both implementations appear to use probability-ranked prefixes,
25% group coverage, CNY256 group caps and the same joint-world allocator.
Do not manufacture a second experimental factor if A=C and B=D.

Compare canonical purchased state IDs, ordered fixture identities, group IDs,
depths, stakes, simulated worlds and actual settlement. Ignore only descriptive
rule labels and irrelevant vector names. Reproduce the legacy funded ledger
before drawing attribution conclusions. Compare all eligible options as well
as selected tickets; equal aggregate returns alone are insufficient.

## Scope and reporting

The old ledger has 494 usable issues: 315 before the drawdown, 94 in
111104–120419, and 85 after it. Issue 110915 is unavailable, not a losing bet.
The first ten issues are new-model warmup. Show the old full494 curve and
warmup separately; four-cell common-scope comparison has 484 issues (305/94/85).
Never concatenate the previous outside390 curve and a differently scheduled
drawdown experiment as if they were one frozen model run.

Report spending, net return, ROI, hit/profit issues, drawdown and minimum
capital. At ticket and issue levels distinguish retained, added and removed
winners. Keep the original drawdown window marked on chronological plots.
Explain implementation equivalence, calibration effects and candidate/coverage
changes separately. A descriptive replay is not an unseen-data evaluation.

## Acceptance still required

All494 reference reproduction; all484 four-cell replay; source/model/code
bindings; shared temporal-learning admission and independent replay; explicit
new/removed ticket accounting; R function tests; clean QMD execution and figure
inspection; Codex review; commit/push and linked PR update. The initial single
issue equivalence observation does not satisfy these requirements.

## Reusable diagnostic interfaces

- `r/n7_purchase_equivalence.R::n7_purchase_equivalence`: compares the frozen
  eligible options, purchased canonical states, fixture universe and worlds;
  tests: `tests/testthat/test-n7-purchase-equivalence.R`.
- `r/n7_replay_checks.R::n7_replay_checks`: validates exact issue coverage and
  typed, nonmissing replay verdicts; tests:
  `tests/testthat/test-n7-replay-checks.R`.
- `r/n7_winner_changes.R::n7_winner_changes`: reconciles retained, added and
  lost winning tickets and returns; tests:
  `tests/testthat/test-n7-winner-changes.R`.
- Existing `n7_quality_settlement` and `n7_baseline_comparison` remain the
  authoritative settlement and equity summarizers. The added
  `test-factorial-empty-settlement.R` verifies entirely unfunded arms.

The QMD180 entry produces the missing94 frozen plans. QMD181 validates replay
evidence, settles them and reports all four cells without new parameter fitting.
External independent reconstruction scripts remain acceptance evidence, not
alternative public implementations of the purchasing or learning contracts.

## Results

The complete old494 replay and outside390 new-probability replay reproduce the
same eligible pools, selected tickets, fixture universes and simulated worlds
across the two implementations. The separate same-calendar drawdown94 replay
also compares both implementations. The common484 accounting
shows old net CNY53,342.31 versus new net −CNY5,211.52. In the drawdown94, the new
foundation saves CNY11,518 in spending but loses CNY4,613.20 in gross returns;
its CNY6,904.80 net improvement is not a recovery in winning-ticket counts.
Keep the old JOINT as the historical research baseline. Neither result
establishes prospective profit. Final acceptance records bind the complete-pool
evidence, independent numerical replay, rendered report and Codex review.
