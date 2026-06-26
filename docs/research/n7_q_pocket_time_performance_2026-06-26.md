# N=7 Q-Pocket Unit-Time Performance

Date: 2026-06-26

## Scope

This report converts the trusted-settlement N=7 q-pocket backtest from cumulative ROI into unit-time views.

- Data: trusted settlement rows, 10h snapshot only.
- Selector: `rolling_ex_top1_roi_w24_dd0`.
- Baseline: selector full stake from `results/n7_q_pocket_gate_selector_2014_10h_trusted_no_skip/`.
- Allocators: `ex1_full_else_half` and `raw_full_ex1_half_floor_quarter` from `results/n7_q_pocket_gate_allocator_2014_10h_trusted_top_selectors/`.
- Issue span: 2014-2025, 679 issues. 2025 has only 15 issues in this slice, so 2014-2024 is the cleaner full-year comparison.

## Definitions

- `roi`: profit / stake inside the selected bucket. It is not annualized.
- `profit_per_year`: total profit divided by the number of calendar years in the selected span.
- `profit_per_100_issues`: total profit normalized to 100 issues.
- `max_drawdown_pct_on_10000`: issue-level drawdown on a synthetic 10,000-unit equity curve.
- `max_nonpositive_streak_issues`: longest issue streak with no equity growth; skipped issues count as zero-profit issues.
- `max_loss_streak_deployed_issues`: longest losing streak among deployed issues only.

## Total Unit-Time View

| policy | issues | stake | profit | ROI | profit/year | profit/100 issues | stake/year | max DD | non-growth streak | deployed loss streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_stake` | 679 | 12300.00 | 13240.65 | 1.0765 | 1103.39 | 1950.02 | 1025.00 | -13.35% | 66 | 57 |
| `ex1_full_else_half` | 679 | 7710.00 | 6258.59 | 0.8117 | 521.55 | 921.74 | 642.50 | -8.54% | 66 | 57 |
| `raw_full_ex1_half_floor_quarter` | 679 | 9015.00 | 7346.42 | 0.8149 | 612.20 | 1081.95 | 751.25 | -10.60% | 66 | 57 |

## Segment View

| policy | years | issues | stake | profit | ROI | profit/year | profit/100 issues | losing years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_stake` | 2014-2025 | 679 | 12300.00 | 13240.65 | 1.0765 | 1103.39 | 1950.02 | 3 |
| `full_stake` | 2014-2024 | 664 | 12020.00 | 12362.51 | 1.0285 | 1123.86 | 1861.82 | 3 |
| `full_stake` | 2021-2024 | 227 | 4100.00 | 5350.88 | 1.3051 | 1337.72 | 2357.22 | 1 |
| `ex1_full_else_half` | 2014-2025 | 679 | 7710.00 | 6258.59 | 0.8117 | 521.55 | 921.74 | 4 |
| `ex1_full_else_half` | 2014-2024 | 664 | 7440.00 | 5949.52 | 0.7997 | 540.87 | 896.01 | 4 |
| `ex1_full_else_half` | 2021-2024 | 227 | 2450.00 | 2592.01 | 1.0580 | 648.00 | 1141.85 | 2 |
| `raw_full_ex1_half_floor_quarter` | 2014-2025 | 679 | 9015.00 | 7346.42 | 0.8149 | 612.20 | 1081.95 | 4 |
| `raw_full_ex1_half_floor_quarter` | 2014-2024 | 664 | 8735.00 | 6468.29 | 0.7405 | 588.03 | 974.14 | 4 |
| `raw_full_ex1_half_floor_quarter` | 2021-2024 | 227 | 2660.00 | 4281.89 | 1.6097 | 1070.47 | 1886.30 | 2 |

## Rolling Window Stress

| policy | window | positive window rate | avg profit | worst profit | worst span | best profit | best span |
| --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| `full_stake` | 24 issues | 53.81% | 464.80 | -480.00 | 140603-140811 | 5059.30 | 150103-150602 |
| `full_stake` | 52 issues | 65.92% | 991.53 | -880.03 | 171201-181104 | 5740.15 | 141007-150604 |
| `full_stake` | 104 issues | 74.83% | 2057.34 | -1317.15 | 140313-141110 | 6898.61 | 141111-161001 |
| `ex1_full_else_half` | 24 issues | 54.42% | 222.79 | -470.00 | 150503-151002 | 2459.65 | 150102-150601 |
| `ex1_full_else_half` | 52 issues | 62.74% | 475.85 | -620.00 | 140401-140806 | 2780.08 | 140914-150502 |
| `ex1_full_else_half` | 104 issues | 74.65% | 999.31 | -838.58 | 140313-141110 | 3148.20 | 141102-160801 |
| `raw_full_ex1_half_floor_quarter` | 24 issues | 44.97% | 257.62 | -465.00 | 150503-151002 | 3409.50 | 21085-22014 |
| `raw_full_ex1_half_floor_quarter` | 52 issues | 57.80% | 546.11 | -820.01 | 171201-181104 | 3424.88 | 21041-22031 |
| `raw_full_ex1_half_floor_quarter` | 104 issues | 70.66% | 1091.91 | -1064.29 | 140313-141110 | 4320.05 | 191201-21125 |

## Readout

The full-stake selector is still the best unit-time performer. It has the highest cumulative ROI, highest profit per year, and highest profit per 100 issues. Because its annual stake is also higher, the raw profit/year advantage is partly exposure-driven, but the ROI advantage means it remains ahead even under equal stake normalization.

The two allocator variants are risk controls, not alpha improvements. `ex1_full_else_half` cuts max drawdown from -13.35% to -8.54%, but annual profit falls by roughly half. `raw_full_ex1_half_floor_quarter` preserves more upside, especially in 2021-2024, but gives up rolling-window consistency versus full stake.

The weak periods remain visible in unit-time space. For full stake, losing calendar years are 2014, 2018, and 2023. The worst 104-issue span is 140313-141110, with -1317.15 units. This reinforces that the production gate should be judged by rolling-window stress, not only by total ROI.

## Recommendation

Use `full_stake` as the current profit-density benchmark for N=7. Keep `ex1_full_else_half` as a conservative risk-mode candidate when drawdown budget is tight. Do not replace full stake with the current allocators as the default unless the objective function explicitly values lower drawdown more than unit-time profit.

The next optimization should make unit-time performance a first-class objective:

1. Maximize `profit_per_100_issues` or `profit_per_year`.
2. Constrain worst 52/104-issue loss and losing-year count.
3. Re-run after the 2007-2013 settlement backfill, because unit-time robustness needs longer pre-2014 stress coverage.

## Generated Files

- `scripts/summarize_issue_time_performance.py`
- `results/n7_q_pocket_time_performance_selector_full_2014_10h_trusted/time_performance_report.md`
- `results/n7_q_pocket_time_performance_allocator_2014_10h_trusted/time_performance_report.md`
- `time_segment_summary.csv` inside each generated result directory
