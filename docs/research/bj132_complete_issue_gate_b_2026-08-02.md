# #132 Gate B — complete-issue p-min vs q-min global-code deletion

## Primary settlement boundary

This is the only primary Gate-B settlement for #132. It reads the accepted
complete-issue Gate-A freeze
`results/bj132_gate_a_complete_issue_preoutcome_v1r1/` (manifest
`6583503ee80fd2b40bb1c000917ff094afa0551b6a3f0af4b8d175a6432872f9`) and
the canonical final-SP outcome join from #95. The prior segment-compatible
result is a non-controlling sensitivity and is not read by this runner.

The retained denominator is 348 complete `(issue, fold)` instances, 52,534
portfolio identities, 160,734 frozen frontier rows and 3,132 explicit no-bet
controls. Every available identity retains the same seven matches in all three
arms: `MATCHED_FULL_N7` (K=2187), `P_MIN_DELETE_N7` (K=1458), and
`Q_MIN_DELETE_N7` (K=1458). Candidate competition, N7 construction, tax,
participation, overlap, folds and leave-one-year-out accounting all remain
issue-level.

## Outcome accounting

- 128,964 rows settled; 28,638 rows retained as unavailable canonical-outcome
  rows with zero realised stake; 3,132 Gate-A no-bets remain explicit.
- A winning sequence uses `¥2 × 0.65 × product(final winning SP)` exactly once.
- Tax is evaluated independently within the frozen
  `issue_instance|variant|arm` bucket at the ¥10,000 threshold; 7,413 bucket
  records preserve that accounting and the intact LOYO unit.
- The result package `results/bj132_gate_b_complete_issue_outcome_settlement_v1r1`
  has immutable manifest
  `deb3d39f937e11ff71638cb6b2d3c1e1d63c5ca25c0ac972f3e785b2a8cbf4f5` and
  content identity
  `7c8668beb068a76d4a4771f77eaaabd00977edf6ad5cc28425ffa790300bab36`.

## Result

All 27 non-control ALL-scope rows are negative before and after tax. The
best tax-adjusted result by arm is:

| Arm | Best frozen variant | No-tax ROI | Tax-adjusted ROI |
| --- | --- | ---: | ---: |
| MATCHED_FULL_N7 | ESP300_GM305_LOWP30 | -15.95% | -32.76% |
| P_MIN_DELETE_N7 | ESP300_GM305_LOWP20 | -16.90% | -29.68% |
| Q_MIN_DELETE_N7 | ESP290_GM300_LOWP20 | -21.13% | -33.34% |

`P_MIN_DELETE_N7` lowers stake to exactly two-thirds of matched FULL, but the
best result remains negative. `Q_MIN_DELETE_N7` does not improve on this
primary outcome. YEAR, FOLD and LEAVE_ONE_YEAR_OUT tables are retained in the
package, alongside explicit per-issue support and payout-loss-severity fields;
no promotion is authorized.

## Reproduction

Run `python3 scripts/settle_bj132_complete_issue_gate_b.py`. The focused
integrity test is
`tests/scripts/test_settle_bj132_complete_issue_gate_b.py`; a clean replay
from the same frozen inputs reproduces both the content identity and manifest.
