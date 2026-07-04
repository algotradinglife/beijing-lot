# Dynamic N and issue-depth replay

Date: 2026-06-27

## Purpose

This test implements the corrected interpretation of dynamic N:

- low-quality issue does not mean spending less money;
- it means using the same fixed issue budget through lower N and more distinct
  tickets;
- high-quality issue can either use more distinct N=7 tickets or try a higher N.

The experiment reuses the same EV-framework leg pools and the same 256-unit
fixed issue budget. It changes only ticket shape.

## Code

Added:

- `scripts/evaluate_n_dynamic_issue_depth.py`

Compile:

```bash
python3 -m py_compile scripts/evaluate_n_dynamic_issue_depth.py
```

Important implementation detail:

- For optional protection, replay legs use `chosen_action`.
- For pure `7s0p`, replay legs use `best_single_code`.
- Settlement legs are looked up from SQLite action rows, so the replay does not
  accidentally settle `7s0p` with protected-leg outcomes.

Validation:

- Static `N7x20` replay reproduces optional p0.85 exactly: profit 141,089.
- Static `N7x20` replay reproduces pure 7s0p exactly: profit 71,244.

## Quality Buckets

Default quality state:

- feature: `avg_ticket_pred_hit`
- rolling window: 96 prior issues
- min history: 48 issues
- low bucket: below rolling q20
- high bucket: at or above rolling q80
- mid bucket: everything else

This is still a survival-quality signal. It is good at identifying bad N=7
periods, but it is not yet a dedicated high-payout signal.

## Commands

Optional p0.85 sweep:

```bash
python3 scripts/evaluate_n_dynamic_issue_depth.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_optional \
  --output-dir results/n_dynamic_issue_depth_optional_p0p85_low_high_sweep_2014_1h_minodds4 \
  --strategy-regex 'p0p85_full_opt__budget' \
  --arm-specs 'static_n7x20=low:N7x20,mid:N7x20,high:N7x20;low5_mid7_high7x20=low:N5x90,mid:N7x20,high:N7x20;low6_mid7_high7x20=low:N6x60,mid:N7x20,high:N7x20;low5_mid7_high7x30=low:N5x90,mid:N7x20,high:N7x30;low5_mid7_high7x40=low:N5x90,mid:N7x20,high:N7x40;low5_mid7_high7x50=low:N5x90,mid:N7x20,high:N7x50;low5_mid7_high8x20=low:N5x90,mid:N7x20,high:N8x20'
```

Pure 7s0p sweep:

```bash
python3 scripts/evaluate_n_dynamic_issue_depth.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named \
  --output-dir results/n_dynamic_issue_depth_7s0p_low_high_sweep_2014_1h_minodds4 \
  --strategy-regex '7s0p__budget' \
  --arm-specs 'static_n7x20=low:N7x20,mid:N7x20,high:N7x20;low5_mid7_high7x20=low:N5x90,mid:N7x20,high:N7x20;low6_mid7_high7x20=low:N6x60,mid:N7x20,high:N7x20;low5_mid7_high7x30=low:N5x90,mid:N7x20,high:N7x30;low5_mid7_high7x40=low:N5x90,mid:N7x20,high:N7x40;low5_mid7_high7x50=low:N5x90,mid:N7x20,high:N7x50;low5_mid7_high8x20=low:N5x90,mid:N7x20,high:N8x20'
```

## Optional p0.85 Results

All active issues still spend 256 units.

| arm | profit | ROI | issue win rate | ex-best ROI | maxDD | max loss streak | 2023-2025 profit | 2023-2025 ROI | 2023-2025 ex-best ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static N7x20 | 141,089 | 82.38% | 6.73% | 27.16% | -36.57% | 62 | 21,048 | 63.73% | -28.17% |
| low N5x90, high N7x20 | 160,878 | 93.94% | 11.66% | 38.71% | -34.51% | 52 | 25,921 | 78.49% | -13.42% |
| low N5x90, high N7x30 | 166,500 | 97.22% | 11.96% | 42.00% | -34.51% | 52 | 26,993 | 81.74% | -10.17% |
| low N5x90, high N7x40 | 166,040 | 96.95% | 12.11% | 41.73% | -34.51% | 52 | 24,459 | 74.06% | -17.84% |
| low N5x90, high N7x50 | 164,299 | 95.93% | 12.11% | 40.71% | -34.51% | 52 | 24,296 | 73.57% | -18.34% |
| low N6x60, high N7x20 | 158,326 | 92.45% | 9.27% | 37.22% | -34.51% | 62 | 21,252 | 64.35% | -27.55% |
| low N5x90, high N8x20 | 125,870 | 73.49% | 10.31% | 18.27% | -73.69% | 52 | 19,219 | 58.20% | -33.71% |

Best optional arm in this sweep:

- `low5_mid7_high7x30`
- profit 166,500
- ROI 97.22%
- ex-best ROI 42.00%
- 2023-2025 ex-best ROI improves from -28.17% to -10.17%

## Pure 7s0p Results

| arm | profit | ROI | issue win rate | ex-best ROI | maxDD | max loss streak | 2023-2025 profit | 2023-2025 ROI | 2023-2025 ex-best ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| static N7x20 | 71,244 | 41.60% | 7.03% | 23.88% | -85.48% | 64 | 17,945 | 54.34% | -37.57% |
| low N5x90, high N7x20 | 93,821 | 54.78% | 12.71% | 37.06% | -66.52% | 40 | 25,605 | 77.53% | -14.37% |
| low N5x90, high N7x30 | 94,038 | 54.91% | 12.71% | 37.19% | -66.52% | 40 | 26,677 | 80.78% | -11.13% |
| low N5x90, high N7x40 | 89,329 | 52.16% | 12.86% | 34.44% | -66.52% | 40 | 24,273 | 73.50% | -18.41% |
| low N5x90, high N7x50 | 88,321 | 51.57% | 12.86% | 33.85% | -66.52% | 40 | 24,065 | 72.87% | -19.04% |
| low N6x60, high N7x20 | 88,683 | 51.78% | 9.57% | 34.06% | -64.51% | 50 | 21,882 | 66.26% | -25.65% |
| low N5x90, high N8x20 | 59,569 | 34.78% | 10.91% | 17.06% | -62.89% | 45 | 18,902 | 57.24% | -34.67% |

Best pure 7s0p arm in this sweep:

- `low5_mid7_high7x30`
- profit 94,038
- ROI 54.91%
- ex-best ROI 37.19%
- max active loss streak improves from 64 to 40
- 2023-2025 ex-best ROI improves from -37.57% to -11.13%

## Bucket Readout

The low bucket is the main win from dynamic N.

Optional p0.85:

| bucket/shape | issues | avg tickets | profit | ROI | issue win rate |
|---|---:|---:|---:|---:|---:|
| static low N7x20 | 138 | 18.9 | -21,838 | -61.82% | 2.17% |
| low bucket N5x90 | 138 | 60.4 | -2,050 | -5.80% | 26.09% |
| low bucket N6x60 | 138 | 42.8 | -4,602 | -13.03% | 14.49% |

Pure 7s0p:

| bucket/shape | issues | avg tickets | profit | ROI | issue win rate |
|---|---:|---:|---:|---:|---:|
| static low N7x20 | 136 | 18.9 | -21,671 | -62.25% | 2.21% |
| low bucket N5x90 | 136 | 58.8 | 906 | 2.60% | 30.15% |
| low bucket N6x60 | 136 | 42.1 | -4,233 | -12.16% | 14.71% |

This confirms the user's correction: low quality should not automatically mean
less budget. Same budget with lower N and more tickets materially improves
survival.

## High Bucket Readout

Increasing N to 8 is bad in both source strategies:

- optional high N8x20: -24,650, ROI -69.78%
- pure 7s0p high N8x20: -26,654, ROI -75.45%

More N=7 tickets has a local optimum:

- optional p0.85 high bucket:
  - N7x20: 10,358 profit
  - N7x30: 15,980 profit
  - N7x40: 15,520 profit
  - N7x50: 13,779 profit
- pure 7s0p high bucket:
  - N7x20: 7,598 profit
  - N7x30: 7,815 profit
  - N7x40: 3,106 profit
  - N7x50: 2,098 profit

Conclusion: high quality should not mean "raise N". If expanding high-quality
issues, use more N=7 combinations, and the cap should be moderate. In this run,
N7x30 is better than N7x40/50.

## Interpretation

The current `avg_ticket_pred_hit` quality signal is excellent for identifying
where N=7 is too brittle. It is not a complete signal for when to pursue
larger payouts.

Decision-chain update:

`outcome estimation -> match filter -> issue quality bucket -> dynamic N/depth -> ticket construction -> portfolio result`

Practical reading:

1. Low bucket: switch to N=5 and use many more tickets.
2. Mid bucket: keep N=7x20; this bucket contains most of the current profit.
3. High bucket: do not use N=8. At most expand to N7x30.
4. Optional protection remains the stronger source branch, but pure 7s0p also
   benefits from the same dynamic N idea.

## Recommendation

Current best candidate:

- `optional p0.85 + low N5x90 / mid N7x20 / high N7x30`

Conservative validation branch:

- `7s0p + low N5x90 / mid N7x20 / high N7x20 or N7x30`

Next step:

1. Split issue quality into two signals:
   - survival quality: controls low bucket N reduction;
   - payout quality: controls high bucket ticket expansion.
2. Keep `avg_ticket_pred_hit` for survival quality.
3. Test payout quality using q / avg odds / pred EV / drift-adjusted score,
   instead of assuming high `avg_ticket_pred_hit` means high payout opportunity.
4. Compare dynamic N against hard issue skip gates. The dynamic N arm keeps
   all issues active and improves profit, while hard skip reduces streak length
   more aggressively.

