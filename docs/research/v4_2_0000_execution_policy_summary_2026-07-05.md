# v4.2.0000 Execution Policy Summary

Date: 2026-07-05

## Goal

This layer turns v4.2.0000 decision-chain diagnostics into executable N-ticket
inputs. It does not change the model or the v4.2.0000 recommended codes.

## Policy

- `buy`: execute v4.2.0000 `selection_codes` directly.
- `wait_late_refresh`: strict mode keeps it no-buy; `late_proxy` simulates the
  state after a final refresh has happened.
- full-cover diagnostics: score the full cover by layer conflict, q/SP
  attraction, and value of the third code after double compression.
- full cover is capped by rolling segment. Over-cap fulls are downgraded to the
  best double when possible.
- low-value full conflicts are downgraded to double; skip is used only when the
  row cannot be compressed.

Default candidate: `late_proxy_fullcap2`, threshold `1.40`, max full covers per
rolling 12h segment `2`.

## 26072 Augmented Result

Current settlement source: NowScore augmented #1-45, with #27-45 still
provisional until 500 official `winning_sp` is complete.

| Policy | Full rows | Width profile | Settled hit |
| --- | ---: | --- | ---: |
| v4.2.0000 recommended | 32/65 | 1 single, 31 double, 32 full | 45/45 |
| strict_fullcap2 | 5/65 | 32 no-buy, 28 double, 5 full | 22/45 |
| late_proxy_fullcap2 | 8/65 | 1 no-buy, 2 single, 54 double, 8 full | 40/45 |

`strict_fullcap2` is pre-refresh state; it intentionally leaves all
`wait_late_refresh` rows out. It should not be compared as a final staking
selector.

## Rolling N-Ticket Replay

Settings: 12h rolling segment, extend 18/24/36h, N<=8, 1000 yuan per segment,
2 yuan per ticket, 100 seeds.

| Variant | Median ROI | Mean ROI | p10 | p90 |
| --- | ---: | ---: | ---: | ---: |
| v3 augmented | 13.10% | 14.02% | -11.63% | 41.07% |
| v4.1 recommended | 102.49% | 104.11% | 76.88% | 133.51% |
| v4.2.0000 recommended | 113.03% | 113.81% | 82.10% | 144.48% |
| v4.2.0000 strict_fullcap2 | 35.48% | 38.15% | 8.19% | 67.05% |
| v4.2.0000 late_proxy_fullcap2 | 143.07% | 145.85% | 112.34% | 184.07% |
| v4.2.0000 buy-only | 246.16% | 244.32% | 214.62% | 269.34% |

`buy-only` is not a full-budget comparable selector because it can leave
segments empty. `late_proxy_fullcap2` is the best current full-budget execution
candidate.

## Parameter Sweep

The best tested default was max full cover `2` per rolling segment.

- cap 0: median ROI 140.76%, hit 39/45, no full covers.
- cap 1: median ROI 126.85%, hit 39/45, 4 full covers.
- cap 2: median ROI 143.07%, hit 40/45, 8 full covers.
- cap 3: median ROI 131.96%-135.92%, hit 40/45, 10-11 full covers.

Thresholds 1.2/1.4/1.6 had little effect for cap 0/1/2 on this data; segment
cap is the dominant control.

## Practical Conclusion

For execution, keep v4.2.0000 recommended codes as the audit view, but feed N
tickets with `late_proxy_fullcap2` after a real late refresh. Before the late
refresh, use `strict_fullcap2`, which mostly waits rather than forcing bets.

This should be treated as a shadow execution policy until 26072 has full
official 500 settlement.

Artifacts:

- `scripts/apply_decision_execution_policy_v4_2.py`
- `results/backtest_v4_2_execution_20260705/26072_augmented_nowscore/structured_shadow_26072_v4_2_0000_exec_late_proxy_fullcap2.csv`
- `results/backtest_v4_2_execution_20260705/26072_augmented_nowscore/structured_shadow_26072_v4_2_0000_exec_strict_fullcap2.csv`
- `results/backtest_v4_2_execution_20260705/26072_augmented_nowscore/execution_policy_sweep_26072.csv`
- `results/rolling_segment_n_replay_latest_20260705/26072_augmented_v4_2_0000_execution_seed_sweep.csv`
