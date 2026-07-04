# N7 384 Sleeve Plus-2026 Chain Validation

Date: 2026-06-29

## Scope

This is a full-chain replay of the current N7 sleeve stack after appending the
new 2026 Nowscore/settlement update DB to the historical Beidan modeling DB.

The rebuilt combined DB is:

```text
data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite
```

It now includes the support tables required by high-N selectors and drift/line
features: `matches`, `market_consensus`, `match_features`, `outcome_features`,
`action_candidates`, `action_definitions`, and `source_meta`.

Sanity check:

| table | rows |
|---|---:|
| matches | 201270 |
| market_consensus | 3172312 |
| match_features | 201270 |
| outcome_features | 603810 |
| action_candidates | 1610160 |

Issue range is `140101` to `26051`; the 2026 update contributes 34 issues
from `26011` to `26051`.

## Rebuilt Chain

The following outputs were regenerated from the plus-2026 DB:

| step | output |
|---|---|
| EV ticket pool | `results/n7_ev_framework_selector_2014_1h_minodds4_optional_plus2026/` |
| q/conf/drift joint rows | `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026/` |
| high-N selector | `results/high_n_selector_plus2026_20260629/` |
| N5 overlap sleeve | `results/n_dynamic_issue_smoothing_optional_budget256_overlap050_plus2026_20260629/` |
| core ticket protection | `results/n7_core_ticket_protection_plus2026_20260629/` |
| fixed-256 allocation grid | `results/n7_protection_allocation_grid_plus2026_20260629/` |
| large protection overlay | `results/n7_multi_leg_protection_overlay_large_plus2026_20260629/` |
| final sleeve mix | `results/n7_sleeve_mix_capital_plus2026_20260629/` |

Leakage note: replay features are walk-forward or pre-bet features. The selected
384 profile itself is treated as the previously chosen profile, not selected
because of 2026. However, this is still a historical replay, not a live bet log.

## Key Full-History Results

| portfolio | budget | profit | profit/256 | ROI | issue win | non-full-loss | maxDD | maxDD/256 | max dead | recent profit/256 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| current_reference_256 | 256 | 209569 | 209569 | 116.6% | 9.0% | 67.5% | -16932 | -16932 | 5 | 86207 |
| b384_dd32_smooth100 | 384 | 256999 | 171332 | 95.3% | 18.5% | 71.4% | -13691 | -9127 | 5 | 74528 |
| b384_dd32_smooth80_convex19 | 384 | 367730 | 245153 | 136.4% | 17.9% | 71.4% | -14936 | -9957 | 5 | 80041 |
| b320_dd32_safe80_convex19 | 320 | 277503 | 222002 | 123.5% | 13.8% | 71.8% | -14406 | -11525 | 4 | 89592 |
| b512_dd64_smooth100 | 512 | 304428 | 152214 | 84.7% | 18.9% | 71.4% | -13915 | -6957 | 5 | 68688 |

The previously preferred 384 convex profile remains attractive:

```text
b384_dd32_smooth80_convex19
= current fixed-256
  + 32 same_ticket2_alt_risk
  + 76.8 same_ticket4_full_risk
  + 19.2 same_ticket2_draw_risk
```

It improves profit/256 and absolute maxDD versus `current_reference_256`, while
lifting issue-win and non-full-loss rates.

If strict drawdown control is the priority, `b384_dd32_smooth100` is cleaner:
lower absolute maxDD and higher issue win, but materially lower ROI/profit.

## 2026-Only Slice

Only 33 active replay issues appear after training/startup filters.

| portfolio | issues | stake | profit | ROI | issue win | non-full-loss | worst issue | best issue |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| current_reference_256 | 33 | 8448 | 4524 | 53.6% | 24.2% | 57.6% | -256 | 7949 |
| b320_dd32_safe80_convex19 | 33 | 10560 | 2920 | 27.7% | 21.2% | 57.6% | -320 | 7885 |
| b384_dd32_smooth100 | 33 | 12672 | 1869 | 14.8% | 27.3% | 57.6% | -384 | 7821 |
| b384_dd32_smooth80_convex19 | 33 | 12672 | 1632 | 12.9% | 27.3% | 57.6% | -384 | 7821 |

This changes the earlier 2026 read. The raw/core N7 2026 test was very weak,
but the full current stack is positive in 2026 because N5/protection/sleeve
components change the payoff shape. For 2026 alone, the fixed-256 current arm
has the best profit and ROI; the 384 arms are still positive but mainly buy a
higher issue-win rate and lower long-run drawdown, not 2026 excess profit.

## Annual Read

The 384 convex profile is strong in jackpot years and survives weak years, but
it is still not a smooth compounding curve.

| year | current profit | 384 convex profit | 384 convex ROI |
|---|---:|---:|---:|
| 2014 | 6406 | 14385 | 32.3% |
| 2015 | -2885 | -4897 | -22.8% |
| 2016 | 1916 | 103514 | 518.4% |
| 2017 | -6903 | -2773 | -15.7% |
| 2018 | 111435 | 110521 | 496.2% |
| 2019 | 11562 | 15523 | 73.5% |
| 2020 | 2515 | 9943 | 61.6% |
| 2021 | -3250 | -157 | -0.7% |
| 2022 | -1957 | -22 | -0.1% |
| 2023 | 82415 | 114278 | 541.1% |
| 2024 | -5234 | -2325 | -10.3% |
| 2025 | 9026 | 8109 | 140.8% |
| 2026 | 4524 | 1632 | 12.9% |

## Conclusion

The plus-2026 full-chain replay supports keeping the 384 sleeve candidate as a
production research profile, especially if the goal is to reduce absolute
drawdown while retaining convex upside.

Recommended operating view:

| use case | preferred profile |
|---|---|
| balanced current recommendation | `b384_dd32_smooth80_convex19` |
| stricter maxDD / smoother experience | `b384_dd32_smooth100` |
| 2026 sample only / lower stake | `current_reference_256` |

Important caveats:

- 2026 has only 33 active replay issues, so it is useful as a holdout sanity
  check but not enough to reselect the strategy.
- The 2026 Nowscore update has euro/Kelly data, but Asian line-gap data is not
  fully backfilled. Any line-gap edge in 2026 is therefore under-tested or
  neutralized.
- The 384 profile remains lottery-convex: bad years still exist. The improvement
  is lower maxDD and fewer full-dead periods, not a guarantee of steady monthly
  gains.

Next practical step: keep `b384_dd32_smooth80_convex19` as the main paper arm,
run `b384_dd32_smooth100` beside it as the drawdown-control paper arm, and keep
filling 2026 Asian/line data before making drift/line-gap gates more aggressive.
