# N=7 Q-pocket Gate Allocator

Date: 2026-06-26

## Purpose

Test conservative stake allocation on top of the no-skip rolling gate selector.

Input:

- `results/n7_q_pocket_gate_selector_2014_10h_trusted_no_skip/gate_selector_issue_profit.csv`

New script:

```text
scripts/evaluate_q_pocket_gate_allocator.py
```

The allocator only uses trailing metrics already available to the selector before each issue:

- `trailing_roi`
- `trailing_ex_top1_roi`

## Policies Tested

| policy | rule |
| --- | --- |
| `ex1_full_else_half` | full stake if trailing ex-top1 ROI > 0, else half stake |
| `ex1_full_raw_half_floor_quarter` | full if ex-top1 > 0, half if raw ROI > 0, else quarter |
| `ex1_full_raw_half_else_skip` | full if ex-top1 > 0, half if raw ROI > 0, else skip |
| `raw_full_ex1_half_floor_quarter` | full if raw ROI > 0, half if ex-top1 > 0, else quarter |

## Best Selector Baseline

Base selector, no stake scaling:

| selector | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `rolling_ex_top1_roi_w24_dd0` | 12300 | 13240.65 | 1.0765 | 0.7093 | 0.4509 | -0.1335 | robust |

## Allocator Results

For `rolling_ex_top1_roi_w24_dd0`:

| policy | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `raw_full_ex1_half_floor_quarter` | 9015 | 7346.42 | 0.8149 | 0.4631 | 0.2858 | -0.1060 | robust |
| `ex1_full_else_half` | 7710 | 6258.59 | 0.8117 | 0.5186 | 0.3124 | -0.0854 | robust |
| `ex1_full_raw_half_floor_quarter` | 6615 | 4293.85 | 0.6491 | 0.4093 | 0.2380 | -0.0751 | robust |
| `ex1_full_raw_half_else_skip` | 5520 | 2329.11 | 0.4219 | 0.1340 | -0.0112 | -0.0938 | top2_sensitive_positive |

Interpretation:

- Allocation reduces drawdown, but also gives up a lot of profit.
- Hard skip is not attractive: it loses too much signal and fails ex-top2.
- `ex1_full_else_half` is the cleanest conservative option: it cuts issue DD from -13.35% to -8.54% while staying robust.
- `raw_full_ex1_half_floor_quarter` keeps more profit, but with higher drawdown.

## Multi-selector Check

Across top selectors, the best allocator rows were:

| selector | policy | stake | profit | ROI | issue DD | verdict |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `rolling_ex_top1_roi_w24_dd0` | `raw_full_ex1_half_floor_quarter` | 9015 | 7346.42 | 0.8149 | -0.1060 | robust |
| `rolling_roi_w48_dd0` | `raw_full_ex1_half_floor_quarter` | 11105 | 6436.41 | 0.5796 | -0.1255 | robust |
| `rolling_ex_top1_roi_w24_dd0` | `ex1_full_else_half` | 7710 | 6258.59 | 0.8117 | -0.0854 | robust |
| `rolling_ex_top1_roi_w24_dd1` | `raw_full_ex1_half_floor_quarter` | 9805 | 6174.73 | 0.6298 | -0.1060 | robust |

The original `rolling_ex_top1_roi_w24_dd0` remains the best selector base.

## Period Notes

`rolling_ex_top1_roi_w24_dd0 + ex1_full_else_half`:

| period | stake | profit | ROI | ex_top1 ROI | ex_top2 ROI | issue DD | verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2014-2017 | 3300 | 2440.04 | 0.7394 | 0.0531 | -0.1111 | -0.0854 | top2_sensitive_positive |
| 2018-2020 | 1690 | 917.47 | 0.5429 | 0.1807 | -0.1305 | -0.0522 | top2_sensitive_positive |
| 2021-2023 | 1910 | 1391.44 | 0.7285 | -0.1048 | -0.3299 | -0.0404 | jackpot_dependent |
| 2024-2025 | 810 | 1509.63 | 1.8637 | 0.8869 | 0.1778 | -0.0221 | robust |

Period-level robustness is still not solved. The allocator smooths exposure, but it does not create new edge in weak regimes.

## Recommendation

Use allocation as a bankroll/risk control layer, not as alpha.

Research candidate:

- Gate selector: `rolling_ex_top1_roi_w24_dd0`
- Conservative allocator: `ex1_full_else_half`
- Higher-profit allocator: `raw_full_ex1_half_floor_quarter`

Operational interpretation:

- If prioritizing drawdown control, use `ex1_full_else_half`.
- If prioritizing profit while still reducing risk versus full stake, use `raw_full_ex1_half_floor_quarter`.
- Avoid hard skip for now.

Next step:

Add a bankroll planner that translates these unit-level drawdowns into RMB recommendations, e.g. 2 RMB/unit, 10000 RMB bankroll, max drawdown target 10-15%.
