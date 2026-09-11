# #422 implementation and current results

Read the [frozen contract](issue422_contract.md) and
[data issue ledger](issue422_data_issues.md) alongside this report.

## Scope and status

Release branch: `codex/422-score-remap-release`, based on main `327f5d04`.
The scoped delivery excludes 32 unrelated research commits and includes only four
existing ticket modules plus their function/replay tests as necessary dependencies.
No production expert version or raw data changed. No page download needed for this experiment.
The existing 48-issue archived packet supplies 2,561 unique fixtures. The earliest 19
issues lack the frozen prior-window support; the common evaluation cohort is
29 issues / 1,369 fixtures. All are previously exposed retrospective observations.

The owner authorized the external Codex review on 2026-09-11. The first two
reviews found five P2 issues: model cache identity collision, a fit-partition
ESS gap, label-delay identity, fixed-plan fixture/cutoff provenance, and null
audit status in overlay replay. All five have fixes and regression tests in
research model 422-score-remap-0.1.1. A third review identified that splitting
the fit partition could invalidate recent-state blend weights. The issue-wise
client now accepts only the frozen experiment's EXPANDING_EQUAL policy;
other weighting policies fail closed. The third review also identified missing
runtime dependency-version verification; replay now calls the shared
`verify_implementation_closure` check. Seven findings across three reviews have
implementation fixes. Independent review of final fix commit `86fe0594` found
no actionable regressions (log `review-last-fixes.txt`).
Remote CI and final acceptance remain pending until their recorded checks pass.

## Results (same fixture cohort)

These tables were regenerated with the current release implementation. Independent
repeat-process replay passed: 1,253,296 score cells, 87 artifacts, 232 plans;
source files, transitive code and dependency versions match (`final-verification.json`).

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
R reader and displays tibbles. No RDS. Verified outputs are
`../final-delivery` and `../final-replay`; output hashes and verification
evidence bind the current implementation.

Release evidence in the parent work area:
- `final-python.txt`: 81 passed, including the dependency-version regression.
- `release-r-tests.txt`: full R suite, no failures/skips.
- `final-render-ci.txt` and `final-render-real.txt`: executed, uncached QMD.
- `final-verification.json`: independent byte equality and settlement replay PASS.
- `review-last-fixes.txt`: final Codex fix review, no actionable findings.

Commands (activate the declared project Python/R environment first):
```sh
python -m pytest tests/test_conditional_score.py tests/test_fundamentals_n7_single.py tests/test_fundamentals_n7_baseline.py tests/test_fundamentals_n7_twocover.py tests/test_fundamentals_n67_overlay.py tests/scripts/test_cutoff_mapping.py tests/scripts/test_cutoff_governance.py -q
python scripts/check_cutoff_governance.py
python scripts/materialize_fundamentals_pipeline_fixture.py --output-dir /path/to/offline-bundle
FUNDAMENTALS_PIPELINE_TEST_BUNDLE=/path/to/offline-bundle FUNDAMENTALS_PYTHON=/path/to/project/python BEIJING_LOT_VENV_PYTHON=/path/to/project/python RETICULATE_PYTHON=/path/to/project/python Rscript tests/testthat.R
```

Function/test mapping: all functions in `src/conditional_score/` and
`src/temporal_learning/issue_partitions.py` are exercised by
`tests/test_conditional_score.py`; each copied ticket module has its same-named
test file; both R report functions use `tests/testthat/test-conditional-score.R`.
The two existing replay CLIs are exercised by their ticket module tests.
An earlier local render used an incorrectly relative input path and failed; all
accepted renders supply an absolute declared input directory.

The new issue partition client lives in
`src/temporal_learning/issue_partitions.py`, reusing the existing core without
altering production expert hashes. Fit weights, effective sample size and their
source ledger are separately recorded for the actual fitting partition. Model
method, version and candidate penalties bind distinct cache identities.
No actual page collection requirement was identified; the data issue ledger
records limitations without manufacturing an unavailable historical timestamp.
