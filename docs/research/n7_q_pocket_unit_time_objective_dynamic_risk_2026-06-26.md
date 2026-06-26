# N=7 Q-Pocket Unit-Time Objective And Dynamic Risk Mode

Date: 2026-06-26

## Scope

This pass does two things:

1. Re-ranks N=7 q-pocket selector and allocator candidates by unit-time performance instead of cumulative ROI alone.
2. Tests dynamic risk-mode stake scaling on the best unit-time selectors.

All tests use trusted settlements and the 10h snapshot.

## Unit-Time Objective

The optimizer ranks candidates by `profit_per_100_issues`, with these stress constraints:

- worst 52-issue profit >= -900 units
- worst 104-issue profit >= -1400 units
- max drawdown on 10,000-unit equity >= -14%
- losing calendar years <= 4
- profit per 100 issues > 0

The first pass included:

- full stake: all 18 selector candidates
- static allocator: all 18 selectors x 4 allocator policies

Result: the prior production-style selector remains the best static unit-time candidate.

| source | selector | policy | profit/100 issues | profit/year | ROI | max DD | worst 52 | worst 104 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| full stake | `rolling_ex_top1_roi_w24_dd0` | `full_stake` | 1950.02 | 1103.39 | 1.0765 | -13.35% | -880.03 | -1317.15 |
| full stake | `rolling_ex_top1_roi_w24_dd1` | `full_stake` | 1710.44 | 967.82 | 0.9366 | -13.35% | -880.03 | -1317.15 |
| static allocator | `rolling_ex_top1_roi_w24_dd0` | `raw_full_ex1_half_floor_quarter` | 1081.95 | 612.20 | 0.8149 | -10.60% | -820.01 | -1064.29 |
| static allocator | `rolling_ex_top1_roi_w24_dd0` | `ex1_full_else_half` | 921.74 | 521.55 | 0.8117 | -8.54% | -620.00 | -838.58 |

Readout: the static allocators are still risk controls, not profit-density improvements.

## Dynamic Risk Mode

The useful dynamic rule is based on the strategy's own past issue-level PnL, not on future outcomes.

Best rule:

- selector: `rolling_ex_top1_roi_w24_dd0`
- policy: `dyn_live52_dd_fm0p08_r0p5`
- live signal: compute trailing 52-issue drawdown from the selector's own prior full-stake issue PnL
- action: if trailing 52-issue drawdown <= -8%, stake scale = 0.5; otherwise stake scale = 1.0
- warmup: first 24 issues use full stake
- trigger count: full 577 issues, half-stake 78 issues, warmup 24 issues

This uses only data available before the target issue.

## Dynamic Result

| policy | stake | profit | ROI | profit/100 issues | profit/year | max DD | worst 52 | worst 104 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_stake` baseline | 12300.00 | 13240.65 | 1.0765 | 1950.02 | 1103.39 | -13.35% | -880.03 | -1317.15 |
| `dyn_live52_dd_fm0p08_r0p5` | 11560.00 | 13414.01 | 1.1604 | 1975.55 | 1117.83 | -11.55% | -870.01 | -1181.65 |
| `dyn_live24_dd_fm0p03_r0p5` | 9780.00 | 11750.26 | 1.2015 | 1730.52 | 979.19 | -9.40% | -600.01 | -961.65 |

The best dynamic rule improves profit by 173.36 units while reducing stake by 740 units. The gain is modest in profit density (+25.53 units per 100 issues), but the risk profile is better: max drawdown improves from -13.35% to -11.55%, and worst 104-issue profit improves from -1317.15 to -1181.65.

The conservative dynamic rule `dyn_live24_dd_fm0p03_r0p5` gives up profit, but materially reduces drawdown and rolling-window losses. It is a risk-mode candidate, not the default profit benchmark.

## Segment Check

| policy | years | profit | ROI | profit/100 issues | profit/year | max DD | losing years |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full_stake` | 2014-2024 | 12362.51 | 1.0285 | 1861.82 | 1123.86 | -13.35% | 3 |
| `dyn_live52_dd_fm0p08_r0p5` | 2014-2024 | 12535.88 | 1.1113 | 1887.93 | 1139.63 | -11.55% | 3 |
| `dyn_live24_dd_fm0p03_r0p5` | 2014-2024 | 10872.13 | 1.1444 | 1637.37 | 988.38 | -9.40% | 3 |
| `full_stake` | 2021-2024 | 5350.88 | 1.3051 | 2357.22 | 1337.72 | -6.94% | 1 |
| `dyn_live52_dd_fm0p08_r0p5` | 2021-2024 | 5366.58 | 1.3586 | 2364.13 | 1341.64 | -6.65% | 1 |
| `dyn_live24_dd_fm0p03_r0p5` | 2021-2024 | 3792.57 | 1.1964 | 1670.73 | 948.14 | -5.67% | 1 |

The best dynamic rule is not relying on 2025's partial sample. It also stays ahead on the cleaner 2014-2024 segment.

## Recommendation

Promote `dyn_live52_dd_fm0p08_r0p5` to the current N=7 candidate benchmark, but keep `full_stake` as the reference baseline. The improvement is real but small enough that it needs longer-history validation after 2007-2013 settlement backfill.

Operationally:

- default: `rolling_ex_top1_roi_w24_dd0`
- stake mode: full stake unless prior 52-issue live drawdown is <= -8%
- risk mode: half stake while the trigger holds
- conservative fallback: `dyn_live24_dd_fm0p03_r0p5` if drawdown control is prioritized over profit density

## Generated Files

- `scripts/optimize_q_pocket_unit_time.py`
- `scripts/evaluate_q_pocket_dynamic_risk_mode.py`
- `results/n7_q_pocket_gate_allocator_2014_10h_trusted_all_selectors/`
- `results/n7_q_pocket_unit_time_objective_2014_10h_trusted/`
- `results/n7_q_pocket_dynamic_risk_mode_live_top2_2014_10h_trusted/`
- `results/n7_q_pocket_unit_time_with_dynamic_live_2014_10h_trusted/`
- `results/n7_q_pocket_time_performance_dynamic_live_top2_2014_10h_trusted/`
