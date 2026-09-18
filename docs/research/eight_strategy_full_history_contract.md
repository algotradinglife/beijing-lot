# Eight-strategy full-history comparison

Status: 939-issue comparison complete; independent replay, affected tests and final Codex review PASS.
This is exposed historical diagnostic research, not unseen evaluation or prospective admission.

## Contract and definitions

Compare the complete coupled group-construction and purchase strategies below.
Different selected seven-fixture groups are allowed; every arm shares the same
fixture probabilities within an issue. No expert retraining, new collection or
cleaning, score protection, target-label selection or parameter search is added.

| Arm | Authoritative implementation | Meaning |
|---|---|---|
| JOINT | `n7_probability_allocate`, QMD 200 | Original probability purchase and joint coverage |
| DEPTH_OPEN | `n7_purchase_pool`, QMD 200 | Original groups, open first then deepen using fixed depth menu |
| U4 | `n7_purchase_limits`, QMD 200 | Original groups, at most four group uses per fixture |
| CONFIDENCE | `n7_purchase_confidence_limits`, QMD 201 | Fixed p2–p3 gap-dependent reuse and money limits |
| TOP2_DIVERSE | `top2_fresh_groups` | Fresh candidate windows/swaps, incremental union selection, full 128 tickets |
| HARD1 | `joint_candidate_compare`, QMD 225 | Expanded pool, highest-Top1 leg single, full 64 tickets |
| HARD2 | `joint_candidate_compare`, QMD 225 | Expanded pool, highest two Top1 legs single, full 32 tickets |
| WITHIN0 | `joint_candidate_compare`, QMD 225 | Same expanded candidates, probability purchase constrained to Top2 |

HARD1/HARD2 are **not** historical U3/U6 renamed. The old RAW/CAL × C1/C2 ×
U3/U6 replay is shown separately on its original 784-issue scope and rules.
The present comparison jointly varies group construction and purchasing, so a
return difference is not an isolated causal effect of purchase ordering.

Parameters: seven fixtures, CNY 1,024 maximum per issue, CNY 2 unit, CNY 100,000
initial capital, one ticket-level 0.65 payout factor, no score protection.
The SP gate is 1.3 at probability Top1, priced by reciprocal market q. Official
North-single SP is used only for settlement. Actual stakes and idle budgets differ.

## Sources and scope

The persistent study is `audits/eight-strategy-full-history-v1` under the declared
mounted data root. `source-scope-reconciliation.json` binds the scope evidence:
745 issues in the registered market publication, 744 with usable probabilities,
plus 196 earlier archive issues, yielding 940 prepared issues (100101–150202).
This does not claim every calendar issue exists in the accepted releases.

- Early 106 issues, 100101–100707: hash-verified archives, explicitly RAW market
  p=q. Two disjoint 53-issue batches preserve all input/plan seals.
- Later 834 issues: existing archived p/q bundles, 784 old plus 50 new.
  `ARCHIVED_P_COLUMN` identifies the numerical p column; a complete historical
  calibrator recipe/version is not available. Do not call it strength probability
  or claim a single uniform calibrated model across all 940 issues.
- 110915: no usable market probabilities; never enters the prepared scope.
- 130511: not part of the published market scope; a fundamentals pilot does not
  establish accepted market-probability coverage.
- 100107: frozen but excluded from **all eight** comparable settlement ledgers
  because slot 81 lacks official winning SP. Thus the common result has 939 issues.

### Settlement exception retained for another data task

100107 slot 81, provider 356437, 海伦芬—埃因霍, handicap +1, actual 1:3,
winning handicap direction L. The SQLite official publication has an empty SP;
identity, score and handicap agree. Audit status is `spf:MISSING_WINNING_SP`.
Raw source SHA256:
`3e641b5bf78f682d68fc70a79441d639ec3c82e2e7ea5a5df3cca77200867b3a`.
Source: <https://cp.nowscore.com/beijingdanchang/rangqiushengpingfu/kaijiang_dc_5_100107.html>.

The existing frozen HARD2 and WITHIN0 group 28 wins with this fixture. Its price
therefore matters; it cannot be set to zero, one or estimated SP. No plans are
reselected. `early-settlement-106-v1/fixture-audit.csv` retains all 5,653 rows,
5,652 READY and one missing price. Each report exposes `unavailable-issues.csv`.
Missing identity, contradictory status, malformed READY prices and unknown
anomaly classes still fail; exclusion is not an arbitrary result filter.

## Reusable pipeline

| Entry | Responsibility |
|---|---|
| QMD 230 | Verified early archive projection using existing R market functions |
| `scripts/build_eight_strategy_early_candidates.py` | Thin native candidate construction; no fitting or settlement |
| QMD 227 | Four original JOINT arms, prediction-only sealed plans |
| QMD 228 | Fresh Top2 and existing expanded-pool arms, sealed plans |
| QMD 231 | R/SQLite settlement audit after all applicable freezes exist |
| QMD 229 | Paired-input settlement and per-batch ledgers; explicit unavailable issues |
| QMD 232 | Continuous full account, separate phase/block accounts and final report |

QMDs receive an explicit JSON configuration. Inputs, manifests, parameters, source
hashes, implementation closure and output paths are explicit. Imports do not scrape
or write data. New selection chronology comes through existing native cutoff
interfaces and `src/temporal_learning`; actual historical availability remains
unproven and `historical_admission` stays false. No new fitting, tuning, recency
weighting, threshold search or learned gate was introduced.

The transitive source inventory for the freeze roots is in each receipt's
`closure.files`, with R dependencies in `code`; candidate roots include the thin
entry and native builder dependencies. Shared cutoff/provenance utilities are
reused. Legacy historical fits are inventoried evidence, not new clean interfaces.

## Accounting and diagnostic interpretation

- Order the complete account by issue identity, initialize once, settle each issue
  before the next. This does not simulate overlapping unsettled capital exposure.
- Stop when the account cannot pay its frozen complete plan; report SHADOW
  alongside FUNDED so bankruptcy is not mistaken for reduced risk.
- Phase and fixed 100-issue block accounts initialize independently. Interleaved
  processing batches must be restored to issue order before any drawdown calculation.
- `cash_cny` means cumulative unused per-issue budget, not bank balance.
- Hit issues, profit issues and hit groups are distinct. Purchase depth counts
  distinct purchased outcome combinations, not the ex-post winning rank.
- Remove only the best positive-profit 1/3/5 issues for concentration diagnostics.
  This describes the executed ledger; it does not reroute a counterfactual bankroll.
- Compare chronological phases, actual outlay, ROI and drawdown, not just net money.
  Probability-base differences across phases cannot be attributed to purchasing.

## Independent verification and tests

`check_eight_strategy_report.R` reads **all requested parent plans**, verifies both
Top2 fixture universes against JOINT before exclusion, derives absent prices from
the audited labels, and independently decodes canonical winning states. It checks
stake, depth, probability mass, p/q-derived estimated returns, actual SP products,
exactly one payout factor, period totals and funding accounts.

`check_eight_strategy_combined.R` verifies the complete parent rows **and group
columns**, source scope, excluded/admitted union, continuous/phase/block accounts,
curves, stop fields, paired results, trimming, streaks and legacy proof bindings.
An unrelated PASS proof cannot serve as the original JOINT replication proof.

| Functions / entry | Automated checks |
|---|---|
| Five `eight_strategy_validation.R` functions | `test-eight-strategy-validation.R` |
| `eight_strategy_completion_evidence` | `test-eight-strategy-settlement.R` |
| `eight_strategy_detail_audit` | `test-eight-strategy-detail-audit.R` |
| Early candidate command | `test_eight_early_candidate_entry.py`, offline normal and hash-tamper paths |
| Both proof commands | `test-eight-strategy-proof-entry.R`, completed full fixture and rehashed mutations |

Regression mutations include combined groups, requested scope and curves;
parent depth, coverage, estimated return; and divergent Top2 inputs on an excluded
issue. Control receipts must pass, so a generic failed process is not sufficient.
The integration file requires explicit `EIGHT_STRATEGY_REPORT_FIXTURE`; it must be
executed against completed output for acceptance, not treated as passed when skipped.

Prior native selection and settlement tests were rerun. The tracked R test sweep
covers 184 files and passed with two unrelated #408 integration skips. The shared
worktree also contains untracked old expert tests tied to retired data; that broader
untracked sweep is not reported as green. Those unrelated files were not changed.

## Execution notes

All 1,880 paired plan files (940 issues × two families) passed source/code/byte
integrity checks. The original four JOINT arms exactly reproduce all 784 shared
issues, 3,136 plans. The old compression archive independently replays 6,272 plans,
73,901 groups and 3,164,640 tickets; that is an archived support replay, not a new
optimization run.

Use the project Python and declared R library. Render a copy of the QMD in an
isolated report directory with an explicit config, outside the shared Quarto
project. The full QMD227 computation produced verified plans but its final shared
project HTML step failed; the early QMD227 runs rendered successfully. Full QMD228
rendered successfully. Final report rendering and proof results are recorded with
the final receipt, not inferred from progress files.


## Results and convergence

FUNDED results below use the common 939-issue scope. ROI divides net return by
actual paid stake. Three Top2-family accounts stop for insufficient funding;
their later flat curves do not imply safety. SHADOW outcomes are also all negative
for these families, so funding stop is not the source of the adverse conclusion.

| Policy | Stake CNY | Net CNY | ROI % | Max drawdown CNY | Hit issues | Stopped issues |
|---|---:|---:|---:|---:|---:|---:|
| JOINT | 838,080 | 35,686.83 | 4.26 | 35,125.71 | 404 | 0 |
| DEPTH_OPEN | 906,504 | 27,106.80 | 2.99 | 34,073.95 | 427 | 0 |
| U4 | 597,302 | 23,794.61 | 3.98 | 30,246.32 | 389 | 0 |
| CONFIDENCE | 303,572 | 7,095.36 | 2.34 | 16,214.10 | 328 | 0 |
| TOP2_DIVERSE | 656,384 | -99,556.86 | -15.17 | 121,701.26 | 289 | 298 |
| HARD1 | 486,400 | -99,871.09 | -20.53 | 108,189.77 | 228 | 464 |
| HARD2 | 841,728 | -99,344.69 | -11.80 | 105,606.34 | 449 | 117 |
| WITHIN0 | 961,536 | -92,945.05 | -9.67 | 99,583.35 | 510 | 0 |

Supported: retain original JOINT as the research comparator. U4 offers a lower-
exposure tradeoff without dominating it. Not supported: upgrade to the tested
open/deepen or Top2-family versions. DEPTH_OPEN buys 23 additional hit issues,
spends CNY68,424 more, and earns CNY8,580.03 less. WITHIN0 hits more issues while
losing money, illustrating why hit counts alone do not establish capital efficiency.

Inconclusive: whether a different candidate constructor would establish a strong
Top2 baseline. The present coupled comparisons cannot isolate the responsible
component. All four positive policies turn negative after removing their own
five largest profit issues; none establishes robust or prospective profitability.

Final output: `combined-939-v2/receipt.json` and
`combined-939-final-proof.json` within the persistent study. The combined proof
passes all939 issues; completed-fixture integration tests pass20 assertions with
no skips, including controls and rehashed corruptions. The three R helper files
pass58 assertions; the Python entry has2 passing offline tests. Storage and
cutoff governance checks pass. Final HTML has17 tables and2 inspected embedded
plots (`reports/eight-history-939-v2/report.html`).

Verification commands, run from the repository with the configured project
Python/R environments:

```sh
Rscript --vanilla scripts/check_eight_strategy_report.R <batch-report-directory>
Rscript --vanilla scripts/check_eight_strategy_combined.R <combined-report-directory>
EIGHT_STRATEGY_REPORT_FIXTURE=<combined-report-directory> Rscript --vanilla -e 'testthat::test_file("tests/testthat/test-eight-strategy-proof-entry.R", stop_on_failure=TRUE)'
python -m pytest tests/test_eight_early_candidate_entry.py -q
python scripts/check_cutoff_governance.py
python scripts/check_persistent_data_layout.py --contract config/persistent_data_layout.json
```

The full QMD uses the frozen `combined-939-final-config.json`. Copy it into an
isolated report directory and pass `-P config:<absolute-config-path>` when
rendering. New output paths are required; immutable historical outputs are not
overwritten. The human interpretation is specific to this source-bound study
and must be reviewed when changing its scope.

Review logs and regression evidence are under
`/home/drwho1985/.codex/review-artifacts/n7-low-sp/`:
`eight-final-review-v3.txt`, `eight-final-acceptance-review-v2.txt`,
`eight-proof-integration-final.log`, `eight-exclusion-tests.log`,
`eight-python-acceptance.log`, `eight-tracked-r-tests.log`,
`eight-storage-check-acceptance.log`, and `eight-cutoff-check-final.log`.
