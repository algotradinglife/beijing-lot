# Issue #324 — Top-2 N7 selector × outcome × allocator factorial

## Decision

`NO_INCREMENT`; promotion is `false`. This is a retrospective complete-case
exploration. The fixed fallback is `S0O0A0`, the corrected #319 Top-2 center.

## Eight-cell primary results

Capital return on CNY100,000 is primary. The conservative column funds every active issue
but assigns zero return to unresolved settlement as a sensitivity bound; it is not imputed truth.

| Year | Cell | observable/active | ending capital | capital return | conservative return | hit rate |
|---|---|---:|---:|---:|---:|---:|
| 2023 | S0O0A0 | 43/53 | 93,901.88 | -6.10% | -8.66% | 18.60% |
| 2023 | S0O0A1 | 43/53 | 93,901.88 | -6.10% | -8.66% | 18.60% |
| 2023 | S0O1A0 | 43/53 | 92,261.54 | -7.74% | -10.30% | 4.65% |
| 2023 | S0O1A1 | 43/53 | 90,730.67 | -9.27% | -11.83% | 4.65% |
| 2023 | S1O0A0 | 47/53 | 100,746.83 | 0.75% | -0.79% | 19.15% |
| 2023 | S1O0A1 | 47/53 | 100,746.83 | 0.75% | -0.79% | 19.15% |
| 2023 | S1O1A0 | 47/53 | 102,282.13 | 2.28% | 0.75% | 8.51% |
| 2023 | S1O1A1 | 47/53 | 102,009.15 | 2.01% | 0.47% | 8.51% |
| 2024 | S0O0A0 | 58/66 | 103,567.30 | 3.57% | 1.52% | 34.48% |
| 2024 | S0O0A1 | 58/66 | 110,638.72 | 10.64% | 8.59% | 34.48% |
| 2024 | S0O1A0 | 58/66 | 113,243.85 | 13.24% | 11.20% | 17.24% |
| 2024 | S0O1A1 | 58/66 | 115,893.76 | 15.89% | 13.85% | 17.24% |
| 2024 | S1O0A0 | 60/66 | 98,293.89 | -1.71% | -3.24% | 20.00% |
| 2024 | S1O0A1 | 60/66 | 100,562.84 | 0.56% | -0.97% | 18.33% |
| 2024 | S1O1A0 | 60/66 | 116,708.29 | 16.71% | 15.17% | 11.67% |
| 2024 | S1O1A1 | 60/66 | 124,822.52 | 24.82% | 23.29% | 11.67% |

## Baseline-relative risk/return decision table

All paired values are `2023 / 2024`. Two-year matched lift is the sum of each
year's exact common-support lift versus `S0O0A0`; it is the primary strategy
comparison. `Recovery/open tail` reports the longest completed recovery episode
and the still-underwater issue count at year end. HHI measures payout
concentration, where larger values mean greater dependence on fewer winning issues.

| Cell | Strategy | capital return | two-year matched lift | max drawdown | longest losing | longest no-payout | recovery/open tail | payout HHI |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `S0O0A0` | Top-2 control | -6.10% / +3.57% | CNY+0 | 7.02% / 3.37% | 12 / 7 | 12 / 7 | 0/42 / 15/29 | 0.175 / 0.080 |
| `S0O0A1` | value allocator | -6.10% / +10.64% | CNY+6,811 | 7.02% / 1.95% | 12 / 7 | 12 / 7 | 0/42 / 27/0 | 0.175 / 0.095 |
| `S0O1A0` | support compression | -7.74% / +13.24% | CNY+7,256 | 7.74% / 3.41% | 24 / 15 | 24 / 15 | 0/43 / 32/0 | 0.778 / 0.145 |
| `S0O1A1` | compression + value allocator | -9.27% / +15.89% | CNY+7,855 | 9.27% / 3.36% | 24 / 15 | 24 / 15 | 0/43 / 32/0 | 0.706 / 0.127 |
| `S1O0A0` | learned selector | +0.75% / -1.71% | CNY+2,186 | 3.44% / 4.80% | 10 / 12 | 10 / 12 | 4/36 / 3/52 | 0.182 / 0.095 |
| `S1O0A1` | selector + value allocator | +0.75% / +0.56% | CNY+4,455 | 3.44% / 4.47% | 10 / 13 | 10 / 13 | 4/36 / 13/26 | 0.182 / 0.129 |
| `S1O1A0` | selector + compression | +2.28% / +16.71% | CNY+20,540 | 3.32% / 3.44% | 12 / 13 | 12 / 13 | 10/36 / 11/22 | 0.361 / 0.165 |
| `S1O1A1` | full joint stack | +2.01% / +24.82% | CNY+28,381 | 3.33% / 3.22% | 12 / 13 | 12 / 13 | 10/36 / 11/22 | 0.373 / 0.192 |

## Model diagnostics on 2022 tuning issues

Skill is `1 - model MSE / fit-mean baseline MSE`; it describes target prediction,
not strategy profitability.

| Horizon | selector-factor skill | Top1-vs-Top2 skill | mean predicted-SP skill |
|---|---:|---:|---:|
| 10h | -0.01% | 0.03% | 62.89% |
| initial | -0.01% | 0.07% | 50.95% |
| 1h | 0.00% | 0.01% | 65.33% |

The predicted-SP heads learn a substantial historical pricing relationship, but the
selector and Top1-vs-Top2 heads have essentially zero 2022 skill over a constant mean.
That asymmetry is the main model-level warning: payout magnitude is predictable, while
the present features do not reliably identify which selected support will realize it.

## Factorial attribution (matched CNY per issue)

| Year | Effect | mean | moving-block 95% interval |
|---|---|---:|---:|
| 2023 | A_main | 0.00 | [0.00, 0.00] |
| 2024 | A_main | 126.14 | [39.30, 245.85] |
| 2023 | O_main | -39.06 | [-171.08, 117.12] |
| 2024 | O_main | 164.75 | [-120.72, 491.71] |
| 2023 | OxA | -36.45 | [-104.40, 0.00] |
| 2024 | OxA | -86.69 | [-214.59, 29.74] |
| 2023 | S_main | 170.83 | [-14.96, 376.04] |
| 2024 | S_main | -92.38 | [-298.37, 99.56] |
| 2023 | SxA | 0.00 | [0.00, 0.00] |
| 2024 | SxA | -84.12 | [-242.01, 60.71] |
| 2023 | SxO | 26.02 | [-315.66, 434.98] |
| 2024 | SxO | 185.28 | [-219.65, 623.20] |
| 2023 | SxOxA | 29.95 | [-12.08, 101.93] |
| 2024 | SxOxA | 194.94 | [60.63, 335.41] |

## Cell lift on common eight-cell support

| Year | Cell | matched issues | total lift vs control | ex-largest lift | positive issues |
|---|---|---:|---:|---:|---:|
| 2023 | S0O0A0 | 42 | 0.00 | 0.00 | 0.0% |
| 2023 | S0O0A1 | 42 | 0.00 | 0.00 | 0.0% |
| 2023 | S0O1A0 | 42 | -1,640.34 | -3,780.79 | 4.8% |
| 2023 | S0O1A1 | 42 | -3,171.21 | -3,884.69 | 4.8% |
| 2023 | S1O0A0 | 42 | 7,174.68 | 2,889.23 | 19.0% |
| 2023 | S1O0A1 | 42 | 7,174.68 | 2,889.23 | 19.0% |
| 2023 | S1O1A0 | 42 | 6,627.19 | -890.59 | 7.1% |
| 2023 | S1O1A1 | 42 | 6,354.21 | -1,163.57 | 7.1% |
| 2024 | S0O0A0 | 54 | 0.00 | 0.00 | 0.0% |
| 2024 | S0O0A1 | 54 | 6,811.44 | 3,851.39 | 13.0% |
| 2024 | S0O1A0 | 54 | 8,896.61 | 2,934.64 | 16.7% |
| 2024 | S0O1A1 | 54 | 11,026.56 | 6,208.43 | 16.7% |
| 2024 | S1O0A0 | 54 | -4,988.66 | -6,815.15 | 16.7% |
| 2024 | S1O0A1 | 54 | -2,719.71 | -6,372.69 | 16.7% |
| 2024 | S1O1A0 | 54 | 13,912.97 | 6,607.02 | 13.0% |
| 2024 | S1O1A1 | 54 | 22,027.20 | 11,068.26 | 13.0% |

`S_main`, `O_main`, and `A_main` are standalone lifts from the control. `SxO`, `SxA`,
`OxA`, and `SxOxA` are differences-in-differences. A negative interaction means the
components compete in this frozen context; it is not a universal impossibility theorem.
Positive point lift in both years is still `NO_INCREMENT` when the 2023 gain disappears
after removing the largest lift issue.

## Mechanism diagnostics

| Year | Cell | mean S0/S1 match overlap | mean compressed legs | funded distinct tickets | mean max units/ticket |
|---|---|---:|---:|---:|---:|
| 2023 | S0O0A0 | 0.83/7 | 0.00 | 128.0 | 1.00 |
| 2023 | S0O1A1 | 0.83/7 | 2.00 | 32.0 | 5.83 |
| 2023 | S1O0A0 | 0.83/7 | 0.00 | 128.0 | 1.00 |
| 2023 | S1O1A1 | 0.83/7 | 1.55 | 51.5 | 4.91 |
| 2024 | S0O0A0 | 0.55/7 | 0.00 | 128.0 | 1.00 |
| 2024 | S0O1A1 | 0.55/7 | 2.00 | 32.0 | 6.30 |
| 2024 | S1O0A0 | 0.55/7 | 0.00 | 128.0 | 1.00 |
| 2024 | S1O1A1 | 0.55/7 | 1.52 | 52.4 | 4.92 |

S1 selects a substantially different seven-match identity rather than making a minor
rerank. The joint point signal is concentrated: issue `23042` contributes CNY7,517.79
of the 2023 `S1O1A1`/control contrast, so the remaining 2023 lift is negative. In 2024,
issue `24032` is also the largest contributor, although the remaining joint lift stays
positive. This is why the interaction is a development clue but not accepted progress.

## Claim boundaries

- The issue is the independent unit; tickets and model rows are nested mechanics.
- 2024 is a frozen transfer for this contract but not globally outcome-unseen.
- Historical official SP is used only as a past supervised label for predicted SP.
- Complete-case and full active schedules are distinct. Coverage is published in
  `coverage.csv`; unresolved settlement never triggers post-outcome reselection.
- Beijing 0.65 is applied once per complete winning N7 ticket.
- No result unlocks #210 without a later true held-out contract.

## Evidence

- Freeze/model receipts: `results/top2_factorial/freeze_receipt.json`, `model_receipt.json`
- Eight-cell/ticket ledgers: `cells.parquet`, `tickets.parquet`
- Effects and paths: `matched_issue_effects.parquet`, `factorial_effects.csv`, `capital_paths.csv`
- Executed notebook: `notebooks/research/top2-factorial/top2_factorial.ipynb`
- Figures: `docs/research/figures/issue_324_factorial_capital.png` and
  `issue_324_factorial_effects.png`
- Replay: `python scripts/run_top2_factorial.py --output results/top2_factorial`

Active coverage rows: 48. Contract requirements REQ-FAC-01 through REQ-FAC-08
are implemented by the receipts, ledgers, matched effects, tests, notebook and this report.
