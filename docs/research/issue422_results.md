# #422 implementation and current results

## Scope and status

Isolated branch: `codex/422-conditional-score-remap`, based on `e9ad29eb`.
No production expert version or raw data changed. No page download needed for this experiment.
The existing 48-issue archived packet supplies 2,561 unique fixtures. The earliest 19
issues lack the frozen prior-window support; the common evaluation cohort is
29 issues / 1,369 fixtures. All are previously exposed retrospective observations.

The independent Codex review command was rejected by automatic approval review:
it may transmit private uncommitted code to the configured external review service.
It has **not run**, and acceptance is **not complete**. No attempt to bypass the rejection.
The new CI workflow is configured but not remotely executed yet.

## Results (same fixture cohort)

| Method | Score log loss | Handicap log loss | Top2 |
|---|---:|---:|---:|
| Baseline | 2.97784 | 1.10371 | 72.53% |
| Global calibration | 2.97722 | 1.10319 | 72.39% |
| Market context only | 2.92391 | 1.07624 | 71.66% |
| Fundamental conditional | 2.92649 | 1.07473 | 73.34% |

The conditional model improves baseline probability metrics, but does not beat the
market-context control on exact-score log loss. Therefore this study cannot attribute
all improvement to incremental fundamentals. Handicap quality and Top2 favor the
conditional model slightly; these exposed diagnostics do not establish durable superiority.

| Method | Fixed groups ROI | Reselected groups ROI |
|---|---:|---:|
| Baseline | -35.62% | -35.62% |
| Global calibration | -39.27% | -35.22% |
| Market context only | -57.25% | -53.19% |
| Fundamental conditional | -44.98% | -43.46% |

Every comparison stakes CNY28,672 in total from 29 budgets of CNY1,024, with unused
cash preserved. Conditional fixed groups hit 12 winning combinations versus
baseline 11, yet pay less overall; counting wins alone misses the payout mix.
No score protection. Recommendation: retain baseline for the frozen N7 construction.
Do not interpret disagreement itself as an exploitable opportunity.

## Runtime function and learning inventory

- `read_score_archive`: immutable input identities, joins/grid contracts, proxy clocks;
  `diagnostic_label_clock` comes from shared temporal learning. No fitting or collection.
- `fit_remapper`: sole domain learning client. Shared `prepare_issue_learning_context` / `prepare_learning_context`
  controls availability, exact target exclusion, complete prior issues, partitions,
  weights/ESS, implementation closure, receipt/cache identity.
- Within that context only: SimpleImputer and StandardScaler fit statistics,
  OneHotEncoder fit vocabulary, SciPy convex penalized tilt coefficients, validation
  selection from the frozen penalty list. Calibration only measures the selected fit.
- `predict_remapper` and `tilt_scores`: immutable projection with explicit native cutoff,
  no label argument. `grid_basis` is a fixed cell definition, not a learned threshold.
- `build_comparison_plan` → existing `n7_single_plan` → `rank_double_candidates`,
  `n7_baseline_plan`, `next_overlap_group`: label-free support/routing/portfolio selection
  with explicit native cutoffs and frozen business constants. No expert training.
- `settle_n7_single` → existing component settlement: audited SP only after plans freeze.
  The current selector ranks coverage, so it does not rank on realized SP.
- `score_metrics`, R report aggregation: post-freeze descriptive evaluation only.
- `verify_experiment`: source/code/output hashes, separate-process byte equality,
  independent score-to-WDL projection, and authoritative settlement replay.
- Receipts inventory the entire transitive Python import closure, including shared
  components imported but not executed by this fixed C0E0 route. R/QMD/CLI hashes
  and pinned runtime config are separately bound.

## Reproduction

From this checkout, use the declared Python/R/Quarto versions in
`config/conditional_score_runtime.json`. Install dependencies during setup only.

```sh
python scripts/run_conditional_score.py --source-root /path/to/fundamentals_417 --output /path/to/new-output
quarto render quarto/93_conditional_score.qmd --execute --no-cache -P run_dir:/path/to/new-output
```

Repeat the first command in a separate process with a second new output path.
Call `src.conditional_score.verification.verify_experiment(first, second,
repository_root=...)`. Outputs are JSON/CSV and full score grids; QMD calls the
R reader and displays tibbles. No RDS. The actual candidate lives under the
parent work area `../delivery`; independent replay `../delivery-replay`.

Checks and logs are stored in the parent work area:
`python-tests-isolated-final.txt`, `r-tests-isolated.txt`, `render-ci.log`,
`render-delivery.log`, `verification-final.json`.
The initial R failures were setup/code-freeze errors (missing offline fixtures,
then changed implementation hashes during running tests), not passed checks;
the final run uses rebuilt fixture provenance and unchanged code.

Existing tracked source files are byte-unchanged from the checkout base. The new
issue partition client lives in `src/temporal_learning/issue_partitions.py`; it
reuses the old core rather than altering existing expert implementation hashes.
Final Python checks: 32 passed. Full R suite passed without skips after offline
fixture setup. Governance passed. Clean real-data and synthetic-data QMD rendering
and independent repeat-process checks form the remaining local acceptance evidence.
