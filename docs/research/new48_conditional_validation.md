# New48 fixed-rule validation (#419)

Approved release: `data/derived/fundamentals_417/new48-verified-v2/cleanup-manifest.json`.
48 issues 100402–100607, 3149 fixtures, 3146 native IDs; 18926 manifest-bound files verified.
Titan is primary; Nowscore cross-check/fill only. Integrated historical rows: 181980.
Collection/cleanup release exists; this does not mean every field is usable for this experiment.

## Frozen comparison

1886 fixtures jointly pass original form and prior-market gates; no native-ID overlap with old40.
33 issues bet, 15 have fewer than seven eligible fixtures and retain cash. All48 are settled,
with 40 strategies per issue (1920 result rows). Fixed budget CNY1024/issue, CNY2 units,
one ticket-level0.65 factor. No correct-score protection, model retraining or threshold selection.
Exact frozen draw1.1.0/high0.1.0 releases, weights0.5/0.5. Historical timestamp proxies are diagnostic,
not prospective availability evidence. Old40 variable budgets are not amount-comparable with new48.

Only later repeated doubles may replace Top2 by Top3, with fixed gaps2/5/10 percentage points;
BASE never replaces and ALL always replaces. Singles and original groups are unchanged.
Eight predeclared group contexts are shown, without promoting the best observed context.

## D2_TOP2_STRICT results

Budget denominator is 48 ×1024 =49152, including cash periods. Actual stake24960.

|Rule|Net CNY|Budget ROI|Stake ROI|Maximum drawdown CNY|Winning groups|
|---|---:|---:|---:|---:|---:|
|BASE|-5629.95|-11.45%|-22.56%|6189.12|17/390|
|GAP02|-6005.12|-12.22%|-24.06%|6564.30|16/390|
|GAP05|-4935.26|-10.04%|-19.77%|5489.38|18/390|
|GAP10|-6078.16|-12.37%|-24.35%|8325.00|19/390|
|ALL|-6938.30|-14.12%|-27.80%|8339.68|18/390|

The old40 GAP02 improvement did not transfer to this context: new48 uplift is -375.18.
GAP05 improves by694.68 but remains negative. Other FREE contexts have positive observed
results, so this is not a claim that all40 strategies lose. Selecting their winners now would
reuse this validation set. See QMD73 for all contexts, per-issue returns, tail removal and drawdown.

## Data quality follow-up (raw bytes preserved)

|Observation|Count|Handling/evidence|
|---|---:|---|
|Same-company same-minute different OU prices|750 fixture occurrences|QUOTE_CLOCK_CONFLICT; preserve both, do not choose arbitrary quote|
|OU month/day clock bounds/ambiguity|17|Same existing strict clock gate; no future quote substitution|
|SQLite SPF blank handicap_raw but original same-fixture roster explicitly0|980 eligible fixtures|EXPLICIT_ROSTER_ZERO_DB_FIELD_BLANK; original native ID and final score also agree; database unchanged|
|Insufficient jointly eligible fixtures|15 issues|NO_BET, hold1024; full roster retained|

The750 conflicts include native393472 (100510/1), company35, same5-13 19:59,
line2.75, over/under0.83/1.03 versus0.88/0.98; not just duplicated company display names.
Blank database fields are not generally converted to zero: NA, nonzero roster, wrong identity
or score remain failures. Settlement v1 is explicitly UNACCEPTED; v2 reuses identical frozen
predictions/plans and changes only this evidence-backed settlement binding.

## Entry points and reproducibility

QMD: `quarto/73_new48_conditional_validation.qmd`.
Python module `src/fundamentals_clean_validation.py`: verified release, form windows,
prior market rows, predictor clocks. R `r/fundamentals_clean_validation.R`: existing baseline,
market and feature projections. R `r/fundamentals_clean_settlement.R`: SPF identity/score/handicap audit.
Thin `scripts/*clean_validation*` entries freeze prepare/project/predict/fuse/plan before labels,
then query R/SQLite, settle, independently replay and package the report.

Full replay requires declared release files, model catalogs/artifacts/runtimes and settlement SQLite;
these large immutable inputs are not embedded in Git. The compressed report fixture enables clean
CI rendering only, explicitly not model replay. The new commit includes existing reusable module
and test dependencies previously absent from Git; it does not retrain their models.

Actual render:

```sh
quarto render quarto/73_new48_conditional_validation.qmd --execute-dir . --execute --no-cache
```

Archived render:

```sh
python scripts/prepare_n7_single_fixture.py --fixture tests/fixtures/clean_validation_report.json.gz --output /path/new48-report
quarto render quarto/73_new48_conditional_validation.qmd --execute-dir . --execute --no-cache -P study:/path/new48-report -P archived_report:true
```

Checks: independent checker verifies all1920 results, replays original selections and manually
reconstructs changed supports, physical tickets, shared scenarios and payouts. New Python functions
map to `tests/test_fundamentals_clean_validation.py`; new R functions map to
`tests/testthat/test-fundamentals-clean-validation.R` (28 assertions). R SQLite integration62 assertions.
Final acceptance and Codex review evidence are stored with the local v2 study.

Final Codex re-review: PASS for historical diagnostic only; no actionable P1/P2.
The initial receipt-verification P2 was fixed with full transitive catalog/runtime/SQLite bindings
and14 mutation tests. Clean-index Python263 tests passed, plus6 published dependency tests;
actual and archived QMD renders each contain tables with1,48,15,40,40,240,1920 rows.
The original frozen predictions and plans are unchanged.

Final local checks: Python263+6+35 passed across the comparison and published dependency suites;
R651 published-interface assertions passed (14 files582 plus the final report-contract file69),
with63 additional compression assertions. Missing legacy test assets found during clean-index
checks were added as offline fixtures; the final69-assertion rerun passed after publishing its
QMD12 dependency. The high-margin legacy test now expands saved gzip evidence, without depending
on a developer data directory. Model code and frozen target predictions were not changed.
