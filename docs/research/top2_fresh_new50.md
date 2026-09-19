# Fresh Top2 grouping on the accepted new 50 issues

Question: does letting Top2 select its own seven-fixture groups improve the
fixed-JOINT-group result? Scope is 140902–150202, using the already accepted
`reports/joint-next50-replay-v2/receipt.json` and its bound source bundles.
No additional collection, cleaning, calibration or label-driven parameter search.

## Frozen experiment

- N=7, unit CNY2, period cap CNY1024, initial capital CNY100000.
- SP>=1.3 uses the existing `n7_sp_filter`: 1/raw-market-probability at the
  calibrated-market Top1 outcome, W/D/L tie order.
- Full Top2: 128 distinct outcome tickets per group, CNY256, at most four
  distinct fixture groups. Same fixture may occur in multiple groups.
- All available eligible fixtures are considered, independently of the old
  24 JOINT candidates. Candidate family is sorted cyclic windows of seven
  plus every one-fixture replacement of the highest-mass seven.
- PROB selects four highest group probabilities, then estimated gross.
- DIVERSE greedily selects the greatest incremental union probability, then
  estimated gross. Inclusion–exclusion is exact for this small portfolio under
  fixture independence; overlapping groups are not treated as independent.
- No minimum 25% group coverage gate in Top2. JOINT_P0 retains its original
  gate, group depth and unmodified ticket copies, not the later BASE policy.
- No seed, randomness, experts, replacements or score protection. No global
  optimum claim outside the explicitly bounded candidate family.

The existing full-state candidate generator enumerates all 2187 outcomes and
runs unrelated frontier optimization. Reusing it here would couple selection
to an old ticket frontier and waste computation. R's `combn`, `prod`, sorting,
and tidyverse supply the required primitives; the added helper is only the
small missing exact overlapping-event calculation.

## Implementation and evidence

Entry point `quarto/224_top2_fresh_groups.qmd`, explicit JSON config with
repository_root, input, receipt_sha256, output and python. Output must not exist.
R functions `r/top2_fresh_groups.R`:

- `top2_fresh_groups`: prediction-only candidate generation and sealed selection.
  Accepts fixture cutoffs and delegates validation to existing shared machinery.
- `top2_group_increment`: exact event arithmetic, no learning or routing.
- `top2_fresh_settle`: separate official-label settlement; seal, identity and
  completeness checks. One ticket-level .65, never an additional group factor.

`top2_fresh_summary` adds per-period counts, monetary totals and drawdown.

All four map to `tests/testthat/test-top2-fresh-groups.R`: exhaustive nine-leg
Bernoulli-world union check, one-group closed forms, multigroup selection,
cutoff failure, label rejection, duplicate/missing label failures, empty gated
pool, deterministic replay and seal tampering. Existing SP and equity functions
remain authoritative; tests for these dependencies are also run.

The report freezes all 50 plans before reading the audited label table, repeats
each selection, and binds original source bytes, R code, native Python transitive
implementation and fixture cutoffs. This is exposed fixture-relative historical
diagnosis, not prospective availability certification. No fitting occurs; the
legacy probability calibration remains inventoried input evidence.

Results, per-period ROI, group identities, model-versus-observed coverage and
CNY100000 equity/drawdown curves are in the rendered QMD and receipt-bound CSVs.

## Results and conclusion

| Strategy | Actual stake CNY | Hit issues / 50 | Profitable issues | Net CNY | ROI | Max drawdown CNY |
|---|---:|---:|---:|---:|---:|---:|
| Original JOINT P0 | 44,054 | 18 | 13 | -13,883.13 | -31.51% | 16,864.84 |
| Fresh Top2 probability | 51,200 | 9 | 3 | -35,527.05 | -69.39% | 38,770.49 |
| Fresh Top2 diversified | 51,200 | 24 | 13 | -1,490.22 | -2.91% | 10,980.87 |

Diversified Top2 improves net by CNY12,392.91 versus original JOINT and reduces
maximum drawdown by about 34.9%, while committing CNY7,146 more. It increases
hit periods, but not profitable periods. This supports testing fresh diversified
selection instead of mechanically keeping the JOINT sets; it does not establish
a profitable strategy.

Probability-first groups cover only 9.14 distinct fixtures per issue on average,
compared with 28 for diversified. All selected diversified groups happen to be
disjoint in this sample; disjointness was not a hard constraint. The model
predicts 15.71 hit issues for probability-first (actual 9), and 27.51 for
diversified (actual 24). Actual group hits are 22/200 versus 31/200.
Higher individual group probabilities did not offset concentration in this run.

The diversified result remains dependent on large payouts: excluding its best
period leaves net -10,455.39 CNY. Therefore near break-even cannot be interpreted
as stable positive expectation or an established replacement for JOINT.

Authoritative outputs: `reports/top2-fresh-new50-v3/`, rendered entry point at
`reports/top2-fresh-new50-html-v3/224_top2_fresh_groups.html`, both under the
configured persistent data root. v1 and v2 are explicitly rejected intermediate
runs. v2 had a profitable-issue summary masking error; row-level settlement and
monetary totals were unchanged. `top2_fresh_summary` now has a regression test
with positive periods but negative aggregate net.

Independent audit `scripts/check_top2_fresh_replay.py REPORT_DIR` reconstructs
Top2 order, exact group coverage increments and all 128 outcomes per group.
`tests/test_top2_fresh_replay.py` covers singleton JSON unboxing, no-bet and
hash-tampering rejection. Targeted R tests also cover existing SP gate and equity
functions. Full repository tests are not used as an acceptance claim: this shared
worktree contains substantial unrelated changes. No merge or issue closure.
