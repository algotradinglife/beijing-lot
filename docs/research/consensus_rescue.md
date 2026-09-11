# N7 consensus rescue: retention and large-handicap market projection

Fixed exposed diagnostic on48issues100402–100607. Current U3/U6 controls,
1024CNY wallet,64CNY group,2singles/5doubles,2CNY unit, one ticket-level.65,
P5, first disjoint then capped reuse. No expert training, score protection,
conversion purchases, new threshold search or automatic promotion.
Issue419 remains OPEN blockedBy421 OPEN; this does not satisfy cross-year acceptance.

Four rules per U: original TOP1; RETENTION; market weight1 at abs(handicap)>=2;
and combination. A eligibility unchanged: shared favorite and q>=.5.
RETENTION A score=q(baseline favorite)/q(baseline Top2 set), the probability
retained from the original double, not necessarily market Top2. D/C objectives
unchanged. The ratio is not absolute hit probability and can favor lower-q A.
Role assignment and group formation are rerun, not fixed-group re-selection.
The old missed25 rescue involved another pool/mixture; its results are not this
experiment's controls and cannot be transferred as expected improvements.

Market grid projection uses existing blend_market_scores at weight1; smaller
handicaps preserve original p exactly, q preserved exactly. Current p/q role
eligibility recomputed. A formerly different-Top2 large-handicap fixture may
become D, reducing C supply; every group still requires1C. This is intentional
fixed-contract testing, not a fallback to zero-C groups. 100412 becomes no-bet;
overall no-bet issues3->4. Zero-handicap Top2 disagreement exclusion unchanged.

All384plans frozen before audit labels, native Cutoffs, full source and
transitive implementation hashes, parameters and label-pointer bindings.
Control slot/role/support/cost/cash match prior U3/U6 plans across all48issues.
No new historical fit; proxy chronology remains diagnostic, not prospective
or simultaneous ticket admission. All source bytes preserved.
No new dependencies, no new R functions or copied chronology implementation.

## Results

|U|Rule|Stake|Net|Stake ROI|Hit issues|Rescued/lost|Max DD|
|---|---|---:|---:|---:|---:|---:|---:|
|3|Original|16960|19946.49|117.61%|19|0/0|2057.14|
|3|Retention|16576|6791.79|40.97%|11|1/9|3659.51|
|3|Market|16384|11053.41|67.46%|10|1/10|3396.57|
|3|Both|15424|6725.45|43.60%|9|2/12|3144.14|
|6|Original|31808|24713.37|77.70%|19|0/0|4416.06|
|6|Retention|31232|10700.09|34.26%|14|3/8|4608.00|
|6|Market|31232|30188.96|96.66%|11|2/10|6707.99|
|6|Both|30080|16080.86|53.46%|12|4/11|7918.30|

All monetary units CNY; initial capital100000. Budget ROI and384period rows
are in QMD102. Rescued means at least one group hits, not profitable issue.
U6 market-only net lift5475.59; excluding greatest paired-lift issue100514
changes lift to-6536.10. Fewer winning issues, higher drawdown and tail-dependent
gain do not support replacement or reliable rescue. All other variants lower
net and increase drawdown relative to same-U control.

The old probability calibration finding can coexist with worse portfolio
performance: changed supports, role eligibility and joint group construction
matter. Retention changes a relative-loss objective, not guaranteed hit rate;
market mean q on actual A holdings falls slightly: U3 .536->.532,
U6 .537->.534 (holding-weighted). This alone does not causally explain the loss.
No evidence here for a robust upgrade; keep original default. Do not claim
all market calibration or retention formulations fail.

## Reuse, tests and evidence

Changed consensus_candidates, next_consensus_roles and independent_consensus_portfolio
accept anchor_score TOP1/RETENTION. Default unchanged; returned parameters bind it.
Existing consensus_component and settlement unchanged. New test checks differing
second-direction denominator, unchanged eligibility/D/C objective, native cutoff
and label rejection, invalid rule, deterministic full portfolio, archive restore.
Existing consensus, N6/N7 and unique-single tests exercise shared paths.

Commands with project Python interpreter:
```
python scripts/consensus_rescue.py freeze --study NEW_DIRECTORY
python scripts/consensus_rescue.py settle --study NEW_DIRECTORY
python scripts/check_consensus_rescue.py --study NEW_DIRECTORY
python -m pytest tests/test_fundamentals_consensus_portfolio.py tests/test_fundamentals_consensus_n6_n7.py tests/test_fundamentals_unique_single.py tests/test_fundamentals_candidate_exclusion.py tests/test_fundamentals_consensus_rescue.py tests/test_fundamentals_market_blend.py -q
python scripts/check_cutoff_governance.py
quarto render quarto/102_consensus_rescue.qmd --execute-dir . --execute --no-cache -P study:NEW_DIRECTORY
```

Study: data/derived/fundamentals_417/consensus-rescue-v1.
Fixture: tests/fixtures/consensus_rescue.json.gz, report-only archive.
Independent checker verifies384rows/2964groups, corrected probability endpoints,
unchanged small-handicap p and all q, role support, exclusion, U/P, complete
Cartesian tickets and one payout factor independently of production settlement.
R reuses hit_improvement_summary, missed_strategy_summary and equity/read APIs.
Affected R tests executed with Rscript/testthat::test_file(stop_on_failure=TRUE);
logs in data/derived/fundamentals_417/consensus-rescue-r-tests.txt.
Full unrelated repository suites and remote CI are not claimed executed.

## Final acceptance record

-28affected Python tests passed (consensus, N6/N7, unique-single, exclusion,
 retention and market blend), including portable archive restoration.
-Four reused R reporting test files passed with no failures.
-Independent checker passed384rows/2964groups; separate arithmetic checks
 reconciled all8summaries for ROI, drawdown, rescued/lost and ex-best lift.
-Live and portable archive QMD fresh execution passed with cache/freeze off;
 programmatic inspection confirmed8/8/384table rows,2figures and no error cells.
 No pixel inspection claimed.
-Cutoff governance PASS.
-Codex bounded review: no actionable findings; independently ran17requested
 tests and full checker, reconciled report totals/archive. Reviewer did not
 rerender QMD. Evidence: data/derived/fundamentals_417/consensus-rescue-review.txt.
-No remote CI/full-repository pass claimed, no issue closure/merge.
