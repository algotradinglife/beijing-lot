# N=7 Q-Pocket Dynamic Risk Walk-forward Validation

Date: 2026-06-26

## Scope

This validates dynamic risk-mode selection without choosing the policy from future issue PnL.

For each issue, the walk-forward selector:

1. Looks back over prior policy-level PnL only.
2. Scores each candidate risk policy on a trailing 52 or 104 issue window.
3. Selects the policy for the next issue.

This does not use the target issue's result. The policy candidate set still includes rules discovered earlier on the same 2014-2025 sample, so this is a stronger validation than fixed full-sample selection, but not a fully independent out-of-sample test.

## Candidate Policy Pool

The candidate pool used in this run:

- `full`: `rolling_ex_top1_roi_w24_dd0` + full stake proxy
- `best_live52`: `dyn_live52_dd_fm0p08_r0p5`
- `best_live52_075`: `dyn_live52_dd_fm0p08_r0p75`
- `conservative_live24`: `dyn_live24_dd_fm0p03_r0p5`
- `medium_live24`: `dyn_live24_dd_fm0p03_r0p75`
- `medium_live52`: `dyn_live52_dd_fm0p05_r0p75`
- `second_full`: `rolling_ex_top1_roi_w24_dd1` full stake proxy
- `second_live52`: `rolling_ex_top1_roi_w24_dd1` + `dyn_live52_dd_fm0p08_r0p5`

Walk-forward selectors tested:

- windows: 52, 104 issues
- metrics: `profit_per_100`, `roi`, `ex_top1_roi`
- drawdown penalty: 0, 250
- warmup: 52 issues, default policy = `full`

## Headline Result

| candidate | stake | profit | ROI | profit/100 issues | profit/year | max DD | worst 52 | worst 104 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| full stake baseline | 12300.00 | 13240.65 | 1.0765 | 1950.02 | 1103.39 | -13.35% | -880.03 | -1317.15 |
| fixed best dynamic `dyn_live52_dd_fm0p08_r0p5` | 11560.00 | 13414.01 | 1.1604 | 1975.55 | 1117.83 | -11.55% | -870.01 | -1181.65 |
| WF best `wf_roi_w52_dd0` | 11015.00 | 13456.52 | 1.2217 | 1981.81 | 1121.38 | -10.80% | -660.00 | -1057.15 |
| WF stable `wf_roi_w104_dd0` | 10680.00 | 13323.94 | 1.2476 | 1962.29 | 1110.33 | -10.18% | -725.69 | -1041.65 |

Readout: `wf_roi_w52_dd0` slightly beats the fixed best dynamic rule on unit-time profit and improves drawdown/rolling stress materially. `wf_roi_w104_dd0` gives up a little profit versus `wf_roi_w52_dd0`, but has the lowest drawdown and best 104-issue stress among the top candidates.

## Selected Policy Mix

`wf_roi_w52_dd0` selected:

- `full`: 273 issues
- `conservative_live24`: 267 issues
- `medium_live52`: 82 issues
- `best_live52`: 30 issues
- `second_live52`: 19 issues
- `medium_live24`: 8 issues

This is useful behavior: the selector did not simply rediscover the fixed best dynamic policy. It used full stake frequently, but shifted into the conservative live24 rule during weaker trailing regimes.

## Segment Check

| candidate | segment | profit | ROI | profit/100 issues | profit/year | max DD | losing years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed best dynamic | 2014-2024 | 12535.88 | 1.1113 | 1887.93 | 1139.63 | -11.55% | 3 |
| WF `wf_roi_w52_dd0` | 2014-2024 | 12578.38 | 1.1717 | 1894.34 | 1143.49 | -10.80% | 3 |
| WF `wf_roi_w104_dd0` | 2014-2024 | 12445.81 | 1.1967 | 1874.37 | 1131.44 | -10.18% | 3 |
| fixed best dynamic | 2021-2024 | 5366.58 | 1.3586 | 2364.13 | 1341.64 | -6.65% | 1 |
| WF `wf_roi_w52_dd0` | 2021-2024 | 5238.08 | 1.4371 | 2307.53 | 1309.52 | -5.91% | 1 |
| WF `wf_roi_w104_dd0` | 2021-2024 | 5139.97 | 1.3854 | 2264.30 | 1284.99 | -6.56% | 1 |

The walk-forward selector still beats the fixed dynamic rule over 2014-2024, so the headline result is not caused by the partial 2025 sample. In the 2021-2024 segment, fixed best dynamic has higher raw profit, while walk-forward has better ROI and drawdown. This makes the choice objective-dependent.

## Recommendation

Promote dynamic risk walk-forward selection into the main N=7 candidate set, with two production-style options:

- Profit-density candidate: `wf_roi_w52_dd0`
- Conservative stress candidate: `wf_roi_w104_dd0`

For now, keep `dyn_live52_dd_fm0p08_r0p5` as the fixed-rule benchmark and `full_stake` as the base benchmark.

Before treating walk-forward as production default, the next validation should be:

1. Re-run the same policy selection after the 2007-2013 settlement backfill.
2. Freeze the candidate policy set before evaluating the longer history.
3. Add transaction/budget constraints if actual issue-level stake cannot scale exactly as backtest units.

## Generated Files

- `scripts/evaluate_q_pocket_dynamic_risk_walkforward_selector.py`
- `results/n7_q_pocket_dynamic_risk_wf_selector_2014_10h_trusted/`
- `results/n7_q_pocket_dynamic_risk_wf_unit_time_2014_10h_trusted/`
- `results/n7_q_pocket_time_performance_dynamic_risk_wf_2014_10h_trusted/`
