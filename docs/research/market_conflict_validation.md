# #419 market/corrected-probability conflict replacement

This is an additional retrospective experiment on already exposed new48 results,
not a new holdout or a refit. Input: `new48-conditional-validation-v2`; all frozen
models, probabilities, groups, roles, budgets and settlement identities remain unchanged.
48 periods,33 betting/15 cash,56 policies per period,2688 result rows.
Draw1.1.0/high0.1.0 weights0.5/0.5. Each period CNY1024, each basic ticket CNY2,
one ticket-level0.65 payout factor, no score protection.

## Fixed gate

p and q are both handicap W/D/L projections of score distributions. q is prematch
Euro+OU, never settlement SP. For a later repeated double, preserve model Top1;
swap model Top2 for Top3 if q(Top3)-q(Top2)>=0.05 and TV(p,q)>=threshold.
TV is half the L1 distance. Fixed thresholds0/.10/.15/.20; zero is the TAIL05
rank-reversal-only control. Singles and first appearances never change. Original
BASE/GAP02/GAP05 controls are copied byte-identically from accepted source plans.
The gates do not require different first-ranked outcomes: they specifically require
market support for the omitted tail. No threshold is selected from these results.

## Original D2_TOP2_STRICT context

|Rule|Net CNY|Budget ROI|Max drawdown CNY|Winning groups|Changed legs|Gained/lost groups|
|---|---:|---:|---:|---:|---:|---:|
|BASE|-5629.95|-11.45%|6189.12|17|0|0/0|
|GAP02|-6005.12|-12.22%|6564.30|16|52|0/1|
|GAP05|-4935.26|-10.04%|5489.38|18|175|3/2|
|TAIL05|-3095.30|-6.30%|5100.42|22|286|7/2|
|TV10|-3408.24|-6.93%|5413.36|21|234|6/2|
|TV15|-5033.89|-10.24%|6403.84|19|130|4/2|
|TV20|-2744.29|-5.58%|5056.00|20|43|3/0|

TV20 improves by2885.65; removing the largest improvement period100407 leaves1045.42.
The strategy still loses2744.29. Effects do not generalize across group constraints:
D2_TOP2_FREE TV20 loses4425.42 relative to its BASE. Current-model expected payout
cannot improve under this swap because p2>=p3 and q3>q2 implies p2/q2>=p3/q3.
This tests whether market disagreement corrects model error, not whether the current
model considers the swap optimal. All8 contexts and per-period results are in QMD74.

## Implementation and checks

`src/fundamentals_market_conflict.py::replace_market_conflict_doubles` reuses the
existing source-plan/cutoff validation and candidate replacement, then adds only the
conflict gate and rebuilds actual tickets/support metrics. Existing implementation
files and original reports are untouched. Its3 parameterized tests cover gates,
boundaries, wrong-way conflict, money, roles, immutability and failure contracts.

`scripts/market_conflict_validation.py freeze` consumes only frozen predictors/plans;
`settle` verifies original full receipts before reusing the accepted R/SQLite audit.
`scripts/check_market_conflict.py` independently rebuilds gates, tickets, shared
scenarios and payouts; all2688 rows passed. Codex review: PASS for retrospective
diagnostic only, no P1/P2; additional independent checks covered5503 ledger rows.

```sh
python scripts/market_conflict_validation.py freeze --source data/derived/fundamentals_417/new48-conditional-validation-v2 --output /path/new-study
python scripts/market_conflict_validation.py settle --source data/derived/fundamentals_417/new48-conditional-validation-v2 --output /path/new-study
python scripts/check_market_conflict.py --study /path/new-study
quarto render quarto/74_market_conflict_validation.qmd --execute-dir . --execute --no-cache -P study:/path/new-study
```

A full run needs the original declared source/model/runtime/SQLite snapshots. The
compressed report fixture supports CI rendering only, explicitly not full replay.
QMD74 has no network, fitting or database writes. No data corrections were introduced.

## Acceptance evidence

Clean-index targeted tests39 passed:

```sh
python -m pytest tests/test_fundamentals_market_conflict.py tests/test_fundamentals_repeated_double.py tests/test_fundamentals_compression_bridge.py tests/test_fundamentals_n7_single.py -q
python scripts/check_cutoff_governance.py
Rscript -e 'testthat::test_file("tests/testthat/test-fundamentals-repeated-double.R",stop_on_failure=TRUE);testthat::test_file("tests/testthat/test-fundamentals-compression-bridge.R",stop_on_failure=TRUE)'
```

Cutoff governance passed; R29 assertions passed. Actual and archived QMD renders
passed with execution enabled, cache disabled and errors fatal; rendered tables
have56,56,15,2688 rows and no error cells. No required local checks were skipped.
Remote CI is tracked separately from local acceptance. The experiment is not a
prospective performance claim and does not change the default strategy.
