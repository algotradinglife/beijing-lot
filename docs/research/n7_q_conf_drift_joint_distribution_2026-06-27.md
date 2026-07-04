# N=7 q/confidence/SP-drift joint distribution

Date: 2026-06-27

## Question

Can q, result-model confidence, and predicted SP drift identify a tradable joint region?

Specifically:

- estimate `P(hit | q, confidence, drift_state)`;
- estimate `E(winning_sp / snapshot_odds | hit, q, confidence, drift_state)`;
- test whether high q + high confidence + high drift improves both hit rate and payout;
- test whether high drift with weak q/confidence is a trap.

## Implementation

Code:

```text
scripts/evaluate_n7_q_conf_drift_joint_distribution.py
```

Full result directory:

```text
results/n7_q_conf_drift_joint_2014_10h_trusted
```

Command:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/evaluate_n7_q_conf_drift_joint_distribution.py \
  --db /home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite \
  --output-dir results/n7_q_conf_drift_joint_2014_10h_trusted \
  --min-year 2014 \
  --train-issues 12 \
  --snapshot 10h \
  --settlement-quality trusted \
  --gate-specs keyed_pockets
```

Leakage controls:

- q model trains on prior issues only;
- confidence model trains on prior issues only;
- SP drift model trains on prior issues only;
- bucket labels are issue-local L/M/H tertiles;
- official winning SP is used only after ticket construction.

Definitions:

- `q_bucket`: issue-local tertile of raw q score.
- `confidence_bucket`: issue-local tertile of snapshot-pure confidence weight.
- `drift_bucket`: issue-local tertile of predicted `winning_sp / 10h_snapshot_odds`.
- `drift_adjusted_ev_proxy`: `(hit_rate / avg_snapshot_p) * avg_realized_sp_multiplier_on_hits`.

## Output Files

- `joint_leg_rows.csv`: per-leg q/conf/drift bucket and realized result.
- `joint_cell_summary.csv`: all 27 cells, full sample plus 2023-2025 summary.
- `joint_cell_annual_summary.csv`: annual cell stability.
- `joint_replay_summary.csv`: exact-cell and combination-gate same-budget replay.
- `joint_replay_recent_2023_2025_summary.csv`: replay behavior after 2023.
- `joint_distribution_report.md`: generated run report.

## Key Cell Results

| cell | n legs | hit rate | realized SP/10h on hits | EV proxy | 2023-25 hit | 2023-25 EV | exact replay issues | exact replay ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H q / H conf / H drift | 595 | 56.47% | 0.339 | 1.288 | 50.60% | 1.158 | 0 | n/a |
| H q / H conf / M drift | 2934 | 42.16% | 0.479 | 1.194 | 40.32% | 1.186 | 22 | -100.00% |
| H q / H conf / L drift | 3720 | 44.60% | 0.432 | 1.195 | 40.50% | 1.154 | 74 | 105.09% |
| L q / L conf / H drift | 8749 | 27.33% | 0.654 | 1.059 | 27.64% | 1.085 | 34 | -100.00% |
| L q / H conf / H drift | 3541 | 47.05% | 0.573 | 1.169 | 44.79% | 1.131 | 148 | 31.16% |

Interpretation:

1. H/H/H does not improve both hit and payout.
   It has the best hit rate, but the lowest realized SP multiplier among H q + H confidence cells.

2. H/H/L and H/H/M are stronger payout cells than H/H/H.
   H/H/L has lower hit rate than H/H/H, but better payout and more tradable volume.

3. L/L/H is the trap case.
   It has the highest payout multiplier, but hit rate is only 27.33%; exact replay produced 0 hits across 34 active issues.

4. L/H/H is interesting diagnostically, but not stable enough.
   It has decent hit rate and payout, but replay ROI is driven by very few wins and 2023-2025 replay was -100%.

## Replay Results

| gate | tickets | issues | hit rate | profit | ROI | note |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| all keyed baseline | 12773 | 670 | 0.290% | 9973.98 | 74.43% | current benchmark |
| H/H any drift | 2783 | 261 | 0.323% | 2252.50 | 43.15% | concentrated, 2023-25 -100% |
| H/H drift M/H | 411 | 68 | 0.730% | 2047.82 | 150.58% | insufficient volume, 2023-25 -100% |
| H/H drift L exact | 527 | 74 | 0.759% | 1555.37 | 105.09% | insufficient volume, mostly one year |
| L/H/H exact | 610 | 148 | 1.148% | 922.44 | 31.16% | jackpot dependent, 2023-25 -100% |
| drift H any q/conf | 8049 | 586 | 0.348% | -421.47 | -3.60% | high drift alone fails |
| drift H with low q or low conf | 4831 | 465 | 0.269% | 109.23 | 1.17% | best issue share 2299%, 2023-25 -100% |
| L/L/H exact | 182 | 34 | 0.000% | -680.00 | -100.00% | direct trap |

Recent 2023-2025 replay:

| gate | issues | tickets | hits | profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: |
| all keyed baseline | 128 | 2476 | 7 | 2468.67 | 96.43% |
| drift H any q/conf | 112 | 1617 | 3 | -1269.25 | -56.66% |
| H/H any drift | 39 | 310 | 0 | -780.00 | -100.00% |
| H/H drift M/H | 11 | 66 | 0 | -220.00 | -100.00% |
| L/H/H exact | 22 | 69 | 0 | -440.00 | -100.00% |
| drift H with low q or low conf | 94 | 911 | 0 | -1880.00 | -100.00% |

## Annual Stability

Leg-level EV proxy:

- H/H/H: EV proxy > 1 in 10 of 12 years; weak in 2018 and 2024.
- H/H/L: EV proxy > 1 in 12 of 12 years.
- H/H/M: EV proxy > 1 in 12 of 12 years.
- L/L/H: EV proxy > 1 in 12 of 12 years, but the hit rate stays around only 25-31%.
- L/H/H: EV proxy > 1 in 12 of 12 years.

This is the main tension: several cells look positive at the leg level, but they do not form robust N=7 tickets under keyed constraints. Ticket topology, same-match exclusion, and minimum core-leg constraints remove much of the apparent edge.

## Conclusion

Do not promote a hard joint selector yet.

The joint distribution is useful, but the tradable interpretation is:

- q and confidence should remain the primary hit-rate controls;
- drift should not be treated as an independent buy signal;
- high drift + low q/confidence is a payout-quality signal attached to too much dead-ticket risk;
- H/H/H is not enough because it improves hit rate but not payout, and is too sparse for exact-cell tickets;
- H/H/L or H/H/M may be better depth candidates than H/H/H, but their replay is still volume-light and recent-period weak.

Recommended next step:

Use joint cells as a soft depth/risk gate, not a hard selector:

```text
increase depth only when q/conf cell is strong and recent selector health is positive;
do not increase depth solely because drift is high;
haircut high-drift low-q/low-confidence legs unless they are needed for topology and have independent confidence support;
require trailing 52/104 issue replay health before enabling any H/H-only paper arm.
```
