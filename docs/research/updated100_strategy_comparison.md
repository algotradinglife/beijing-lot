# Updated 100-period fixed strategy comparison

User requested the eight previously compared arms on the updated period data.
This is a fixed-policy historical diagnostic under #419, still blocked by #421
for clean historical-learning acceptance. No issue closure, retraining,
parameter selection, best-seed selection, or new collection is authorized by
this comparison.

## Sources and cohort

- Original 48: 100402–100607, archived n5-single10-u3-mix-v1 results.
- New 100: 100608–101120, accepted next100 analysis v4 and market v3.
- Acceptance: next100-triage-v1/final-acceptance.json, status
  ACCEPTED_DIAGNOSTIC_BATCH; historical_admission=false.
- Preserve the 6,954-fixture scope and its declared identity exclusions.
  Model admission additionally requires the original window/market contracts.
- Titan primary; accepted Nowscore fills retained. No new source adjudications.
- Accepted analysis implementation is checked against its exact saved source
  snapshot where available. Current model code has a separate implementation
  closure; it is not substituted for the historical cleaning implementation.
- Freeze all new-period supports before roster outcome extraction and the
  authoritative R/SQLite SPF query. Settlement errors stay pending, never zero.

## Unchanged policies

Pure baseline p is the original same-role 10-match cross-mean independent
Poisson score distribution, projected to the published integer handicap.
Market q uses mean decimal Euro odds and the existing Asian OU-constrained
score mapping. No expert adjustment or score protection. Known neutral target
exclusions follow existing approved fixture rules.

Singles require baseline/market Top1 agreement and market Top1 >=0.5.
Exclude zero-handicap Top2-disagreement fixtures. Each group has two singles,
N-3 agreed-Top2 doubles and one differing-Top2 double; double supports use
baseline Top2. Candidate role ranking, disjoint-first search and tie policy
reuse the prior implementation.

- N5: P4, no effective reuse cap within budget (max64 funded groups).
- N6: P5, no effective reuse cap within budget (max32 funded groups).
- N7 U3/U6: P5, respective actual reuse caps; original assembly seeds41902.
- Swap arms: N5 single10/single25 and N6 single10, seeds0–99, only repeated
  single positions can change to market second outcome. No double swaps.
- Mix: N5 single10 budget512 + U3 budget512, whole source-order groups,
  max first32 N5 and first8 U3; unused wallets stay cash without transfer.
- Each standalone issue budget CNY1024, basic unit CNY2, ticket-level payout
  multiplier0.65 once. Each independently simulated account starts CNY100000.
  Equal budgets do not imply equal actual stakes.

## Reuse, execution, tests

- src/fundamentals_updated_scope.py: audited_scope_market validates exact
  approved keys/cutoffs/companies; prepare_updated_issue reuses cleaned form
  windows and clocks; updated_strategy_plans composes existing strategy APIs.
- src/fundamentals_updated_freeze.py: immutable per-issue persistence; four
  bounded worker processes write independent issue bundles. Final freeze marker
  is written only once every issue succeeds. No cross-issue learned caches.
- scripts/prepare_updated_scope.py, scripts/project_updated_scope.R and
  scripts/replay_updated_strategies.py are phase-separated entry points.
- The R projection imports existing functions and uses no expert predictions.
- QMD120 imports the existing authenticated report reader and equity function.
  Cohort metrics show original48, new100 and concatenated148 separately.
  Main figure fixes seed0; all100-seed summaries are reported.
- tests/test_fundamentals_updated_scope.py maps all four new project functions
  to automated tests: identities, missing markets, quote cutoff failures,
  source preservation, original completion exclusions, wallet/support contracts,
  insufficient pools and immutable writes.
- Independent checker rederives physical payouts and all reported financial
  curves, including mix prefixes. No authoritative settler is imported.
- One old issue100403 was replayed before target settlement: exact slots,
  supports and stakes match all six no-swap/single10 U3/U6/N5/N6 controls.


## Observed results

Prepared all100 issues and6,954 fixtures;6,547 pass both fixed window and
market gates and all6,547 have READY authoritative SPF audit rows.
Form statuses:6,566 OK,328 insufficient,25 neutral targets,26 original
not finished,9 unresolved source identity/date. Market READY6,878;76
not ready, overlapping the form exclusions. Every issue has404 sealed arms;
new results contain36,764 COMPLETE and3,636 cash-only NO_BET rows.

New100 seed0 main-figure results (CNY, ROI on actual stake):

|Policy|Stake|Net|ROI %|Hit issues|Maximum DD|
|---|---:|---:|---:|---:|---:|
|MIX_S000|83328.00|-2552.26|-3.06|55.00|14133.32|
|N5_S000|93184.00|3071.22|3.30|61.00|14273.60|
|N5_SWAP_S000|93184.00|-737.49|-0.79|66.00|13773.15|
|N6_S000|93184.00|-2652.49|-2.85|42.00|16614.98|
|N5_NO_SWAP|93184.00|6135.22|6.58|50.00|16616.84|
|N6_NO_SWAP|93184.00|-6163.62|-6.61|33.00|19763.84|
|U3_BASELINE|42880.00|-7523.28|-17.54|19.00|15939.17|
|U6_BASELINE|74432.00|-15729.75|-21.13|28.00|25261.05|

All100 seeds, new100 cohort:

|Source|Mean net|Mean ROI %|ROI P05|ROI P95|Median maximum DD|
|---|---:|---:|---:|---:|---:|
|MIX|-3627.45|-4.35|-7.85|-1.12|15698.37|
|N5|2930.79|3.15|-1.92|7.87|14576.97|
|N5_25|-3616.10|-3.88|-11.03|2.53|15192.95|
|N6|-6633.74|-7.12|-14.40|0.10|19410.09|

The new cohort does not sustain the old U3/U6 profitability. N5 no-swap
returns6.58%; single10 N5 averages3.15%, with a negative fifth-percentile
seed return. The mix averages-4.35%; its fifth-to95th percentile interval
is entirely negative. Combined148-period mix mean ROI19.14% still includes
old exposed profits and must not disguise the negative new-cohort return.
No policy or weights were retuned in response. Random-seed quantiles
describe this fixed historical sample, not future confidence intervals.

## Verification status

-15 Python tests passed before the unused-SP regression was added; all5
 current updated-scope tests (including the regression) passed.
-66 R assertions passed: pure-baseline13, clean-validation28, equity25.
- Cutoff governance scan passed.
- First Codex review found one checker defect: it wrongly required prices on
 already lost groups. Fixed; subprocess regression independently exercises it.
- Fresh live QMD executed successfully with cache disabled and errors fatal.
 Main PNG inspected: eight correct labels,148 periods, boundary after48,
 CNY100000 start, continuous equity, negative drawdown and fixed seed0.
- Portable fixture fresh render passed. Live/archive metrics, summaries,
  continuous curves and PNG are byte-identical. Both HTML reports contain
  24 cohort comparison rows,12 seed-summary rows,8 readiness rows and800
  per-period strategy rows; one two-panel image and no execution errors.
- Final Codex review found no actionable findings. It independently checked
  five task tests, fixture/raw and old48 equality,100 frozen plan hashes,
  implementation/cutoff bindings and1,212 cohort financial metrics. The
  reviewer did not claim full render or physical-check completion; those
  remain the root agent's separate acceptance checks.
- Nine cash-only periods are retained in the100-period denominator:
  100919,101004,101013,101014,101102,101107,101110,101115,101118.
- Full repository suite and remote CI execution are not claimed.
- Independent physical check completed:1,815,169 groups, all1,212 cohort-policy
  metrics and404 continuous equity/drawdown curves passed. All mix components
  match the exact funded source prefixes; no missing settlement rows.

Relevant check commands (configured project Python/R environments):

```text
python -m pytest tests/test_fundamentals_updated_scope.py tests/test_fundamentals_clean_validation.py tests/test_fundamentals_n5_u3_wallets.py tests/test_fundamentals_reuse_random.py -q
python -m pytest tests/test_fundamentals_updated_scope.py -q
python scripts/check_cutoff_governance.py
Rscript --vanilla -e 'testthat::test_file("tests/testthat/test-fundamentals-pure-baseline.R",stop_on_failure=TRUE);testthat::test_file("tests/testthat/test-fundamentals-clean-validation.R",stop_on_failure=TRUE);testthat::test_file("tests/testthat/test-fundamentals-equity-curves.R",stop_on_failure=TRUE)'
quarto render quarto/120_updated_strategy_comparison.qmd --execute-dir . --execute --no-cache
quarto render quarto/120_updated_strategy_comparison.qmd --execute-dir . --execute --no-cache -P study:data/derived/fundamentals_417/updated100-strategies-archive-v1 -P archived_report:true
python scripts/check_updated_strategies.py --study data/derived/fundamentals_417/updated100-strategies-v1
```
