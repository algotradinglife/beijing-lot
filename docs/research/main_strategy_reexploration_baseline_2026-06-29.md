# Main Strategy Re-Exploration Baseline

Date: 2026-06-29

## Scope Lock

This baseline resets strategy exploration to the Beidan main-strategy replay
only. External allocator corpora, including PA Feitian / option timing
`events -> option_matches -> outcomes`, are invalid for lottery performance
claims.

Allowed baseline files:

- `results/n7_sleeve_mix_capital_20260629/sleeve_mix_summary.csv`
- `results/n7_sleeve_mix_capital_20260629/sleeve_mix_issue_profit.csv`
- `docs/strategy/current_n7_operating_profile_384.md`
- `docs/strategy/main_strategy_exploration_scope_2026-06-29.md`

Every next experiment must compare against:

1. `current_reference_256`
2. `b384_dd32_smooth80_convex19`

## Frozen Baselines

| portfolio | stake | profit | ROI | profit/256 | issue win | non-full-loss | full-loss | maxDD | maxDD/256 | max loss streak | max dead streak | best issue | ex-top1 ROI | ex-top2 ROI | 2023-2025 profit/256 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| `current_reference_256` | 171264 | 204500 | 1.194 | 204500 | 10.6% | 43.9% | 56.1% | -17102 | -17102 | 31 | 8 | 180203 | 0.658 | 0.141 | 82986 |
| `b384_dd32_smooth80_convex19` | 256896 | 361874 | 1.409 | 241249 | 17.8% | 51.6% | 48.4% | -15077 | -10051 | 30 | 7 | 23011 | 0.937 | 0.545 | 77894 |

Interpretation:

- The selected 384 profile is the current main paper operating candidate. It
  improves full-history ROI, profit per 256, issue win rate, non-full-loss
  rate, absolute maxDD, and dead-streak versus the 256 reference.
- The 384 profile is not a pure risk-reduction strategy. It still depends on
  convex winners, but ex-top1 and ex-top2 remain positive on the full replay.
- The 2023-2025 window is weaker than the headline full-history result. On a
  per-256 basis, 256 did better than the selected 384 in 2023-2025, while 384
  had better issue win rate and less severe absolute maxDD.

## Main Alternatives For Context

These are not promoted by this baseline card, but they define useful comparison
points for the next sleeve-depth card.

| portfolio | budget | profit | ROI | profit/256 | issue win | non-full-loss | maxDD | maxDD/256 | ex-top2 ROI | 2023-2025 profit/256 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `b320_dd32_safe80_convex19` | 320 | 273351 | 1.277 | 218681 | 14.2% | 51.7% | -14517 | -11613 | 0.324 | 87156 |
| `b384_dd32_smooth100` | 384 | 250018 | 0.973 | 166678 | 18.7% | 51.4% | -13203 | -8802 | 0.187 | 72381 |
| `b512_dd64_smooth80_convex19` | 512 | 519248 | 1.516 | 259624 | 18.8% | 51.6% | -16193 | -8096 | 0.479 | 75348 |

Readout:

- `b320_dd32_safe80_convex19` is a strong small-step comparison: lower absolute
  maxDD than 384, positive full-history ROI, and better 2023-2025 profit/256.
- `b384_dd32_smooth100` is the defensive 384 reference: best absolute maxDD
  among these rows, but full-history profit and ROI fall sharply.
- `b512_dd64_smooth80_convex19` improves full-history profit/ROI but worsens
  absolute maxDD versus selected 384. It is a pressure-test, not a default.

## Annual View

### `current_reference_256`

| year | issues | profit | ROI | issue win | non-full-loss | maxDD | dead streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2014 | 116 | 8727 | 0.294 | 14.7% | 36.2% | -8696 | 8 |
| 2015 | 56 | -961 | -0.067 | 5.4% | 41.1% | -5613 | 6 |
| 2016 | 52 | 2354 | 0.177 | 15.4% | 55.8% | -6887 | 7 |
| 2017 | 46 | -6713 | -0.570 | 6.5% | 56.5% | -6713 | 4 |
| 2018 | 58 | 111474 | 7.508 | 12.1% | 44.8% | -4090 | 7 |
| 2019 | 55 | 11347 | 0.806 | 7.3% | 41.8% | -6869 | 5 |
| 2020 | 42 | 947 | 0.088 | 14.3% | 59.5% | -2690 | 4 |
| 2021 | 58 | -3006 | -0.202 | 10.3% | 43.1% | -9377 | 7 |
| 2022 | 57 | -2655 | -0.182 | 8.8% | 38.6% | -5893 | 8 |
| 2023 | 55 | 84425 | 5.996 | 12.7% | 41.8% | -6313 | 5 |
| 2024 | 59 | -10580 | -0.700 | 5.1% | 40.7% | -10580 | 6 |
| 2025 | 15 | 9142 | 2.381 | 13.3% | 40.0% | -1442 | 5 |

### `b384_dd32_smooth80_convex19`

| year | issues | profit | ROI | issue win | non-full-loss | maxDD | dead streak |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2014 | 116 | 16313 | 0.366 | 22.4% | 43.1% | -6809 | 6 |
| 2015 | 56 | -2973 | -0.138 | 16.1% | 46.4% | -6849 | 6 |
| 2016 | 52 | 103951 | 5.206 | 23.1% | 65.4% | -6956 | 5 |
| 2017 | 46 | -2582 | -0.146 | 13.0% | 58.7% | -8340 | 4 |
| 2018 | 58 | 109985 | 4.938 | 17.2% | 51.7% | -5838 | 4 |
| 2019 | 55 | 15454 | 0.732 | 18.2% | 52.7% | -8542 | 5 |
| 2020 | 42 | 6494 | 0.403 | 19.0% | 71.4% | -2864 | 4 |
| 2021 | 58 | -887 | -0.040 | 15.5% | 51.7% | -10790 | 6 |
| 2022 | 57 | -720 | -0.033 | 12.3% | 43.9% | -7301 | 4 |
| 2023 | 55 | 116288 | 5.506 | 20.0% | 52.7% | -7069 | 5 |
| 2024 | 59 | -7672 | -0.339 | 15.3% | 49.2% | -7683 | 6 |
| 2025 | 15 | 8225 | 1.428 | 13.3% | 40.0% | -2338 | 5 |

## 2023-2025 Stress

| portfolio | issues | stake | profit | ROI | issue win | non-full-loss | maxDD | best issue | ex-top1 ROI | ex-top2 ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| `current_reference_256` | 129 | 33024 | 82986 | 2.513 | 9.3% | 41.1% | -17102 | 23011 | -0.168 | -0.459 |
| `b384_dd32_smooth80_convex19` | 129 | 49536 | 116841 | 2.359 | 17.1% | 49.6% | -15077 | 23011 | -0.090 | -0.281 |
| `b384_dd32_smooth100` | 129 | 49536 | 108571 | 2.192 | 17.8% | 49.6% | -12905 | 23011 | -0.036 | -0.227 |
| `b320_dd32_safe80_convex19` | 129 | 41280 | 108945 | 2.639 | 14.0% | 48.8% | -14517 | 23011 | -0.079 | -0.309 |
| `b512_dd64_smooth80_convex19` | 129 | 66048 | 150696 | 2.282 | 15.5% | 49.6% | -16193 | 23011 | -0.051 | -0.217 |

Stress interpretation:

- 2023-2025 is positive only because of the large issue `23011`; all tested
  profiles turn negative after removing the best issue.
- This does not invalidate the lottery strategy, but it means every promoted
  change must show both full-history convexity and tolerable ex-best behavior.
- The worst selected-384 drawdown still runs from `23013` to `25012`, with
  maxDD `-15077`. Future protection work should focus on that interval first.

## Required Report Template For Next Experiments

Every new strategy report should include:

| section | requirement |
| --- | --- |
| Data source | Identify the exact Beidan issue-profit CSV and whether 2026 is included. |
| Baseline | Compare against `current_reference_256` and `b384_dd32_smooth80_convex19`. |
| Change type | Label as ticket-generator, sleeve-mix, depth-score, line-gap/drift, or live-bankroll-only. |
| Full-history metrics | profit, ROI, profit/256, issue win, non-full-loss, maxDD, maxDD/256, dead streak. |
| Stress metrics | annual table, 2023-2025, ex-top1, ex-top2, worst drawdown window. |
| Leakage check | State whether only pre-bet/current/prior issue features are used. |
| Decision | Promote, paper arm, diagnostic only, or reject. |

## Next Work Order

1. Re-run main-strategy sleeve depth at fixed budgets 256/320/384/512.
2. Run near-miss analysis on the N7 main tickets and identify rule-based
   protection legs.
3. Integrate q, confidence, and result probability into per-leg EV/depth
   scoring inside the main ticket universe.
4. After Asian line backfill and combined DB rebuild complete, evaluate
   line-gap and SP drift only as main-strategy selector/depth gates.
