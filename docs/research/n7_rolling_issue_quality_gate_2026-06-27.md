# N=7 rolling issue-quality gate

Date: 2026-06-27

## Purpose

This note follows the fixed-stake N=7 selector work. The current question is
whether long losing streaks share observable pre-bet traits, and whether those
traits can be used before staking an issue.

Capital stop-loss and cooldown are intentionally kept out of scope here. This
test stays inside the fixed selector layer: after tickets are built for an
issue, decide whether the issue quality is high enough to deploy the fixed
256-unit stake.

## Inputs

Primary baselines:

- `results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named`
- `results/n7_ev_framework_selector_2014_1h_minodds4_optional`

Diagnostic inputs:

- `results/n7_loss_streak_diagnostics_7s0p_2014_1h_minodds4`
- `results/n7_loss_streak_diagnostics_optional_p0p85_2014_1h_minodds4`

Code:

- `scripts/analyze_n7_fixed_loss_streaks.py`
- `scripts/evaluate_n7_issue_quality_gate.py`

Compile:

```bash
python3 -m py_compile \
  scripts/evaluate_n7_ev_framework_selector.py \
  scripts/analyze_n7_fixed_loss_streaks.py \
  scripts/evaluate_n7_issue_quality_gate.py
```

## Losing-Streak Readout

For the `7s0p` fixed selector:

- 32 losing streaks have length >= 5.
- 585 of 669 active issues are inside those long losing streaks.
- Longest streaks are 64 issues in 2021-2022, 57 issues in 2023-2024, and 49
  issues in 2024.

The useful commonality is not league or selected direction. Both profitable and
long-loss issues are mostly negative-handicap away-side selections, with very
few draw selections.

The useful commonality is issue quality:

| feature | long-loss issues | profitable issues |
|---|---:|---:|
| avg ticket predicted hit | 0.00134 | 0.00173 |
| avg selected odds | 7.73 | 8.02 |
| avg p_hat | 0.3669 | 0.3781 |
| avg score | 2.646 | 2.842 |
| avg EV N=7 | 1.488 | 1.673 |
| realized selected-leg hit rate | 41.18% | 48.46% |

Interpretation: long losing streaks are structural for high-SP N=7, but the
worst stretches are biased toward weaker issue-level hit quality. That makes an
issue-level gate worth testing.

## Gate Design

The replay gate is walk-forward:

1. Build the issue tickets normally.
2. Compute observable issue features from the selected tickets and legs.
3. Compare current features to rolling quantiles from previous issues only.
4. If the current issue is below the gate threshold, skip the fixed stake.

Features tested:

- `avg_p_hat`
- `avg_ticket_pred_hit`
- `avg_score`
- `avg_p_hat + avg_ticket_pred_hit`

Default replay:

- rolling window: 96 prior issues
- minimum history: 48 issues
- quantiles: 10%, 20%, 30%
- active issue stake: 256 units

Command shape:

```bash
python3 scripts/evaluate_n7_issue_quality_gate.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named \
  --output-dir results/n7_issue_quality_gate_7s0p_2014_1h_minodds4 \
  --strategy-regex '7s0p__budget' \
  --rolling-window 96 \
  --min-history 48 \
  --quantiles 0.1,0.2,0.3 \
  --gate-features avg_p_hat,avg_ticket_pred_hit,avg_score \
  --combined-gates avg_p_hat+avg_ticket_pred_hit
```

Outputs:

- `issue_quality_gate_summary.csv`
- `issue_quality_gate_issue_rows.csv`
- `issue_quality_gate_annual_summary.csv`
- `issue_quality_gate_report.md`

## Main Results

For `7s0p`, the best balanced gates are `avg_ticket_pred_hit q20`,
`avg_p_hat + avg_ticket_pred_hit q20`, and the more defensive `avg_p_hat q30`.

| strategy | gate | active | skipped | profit | deployed ROI | signal ROI | ex-best ROI | maxDD | max loss streak | 2023-2025 profit | 2023-2025 ROI | 2023-2025 ex-best ROI |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 7s0p | none | 669 | 0 | 71,244 | 41.60% | 41.60% | 23.91% | -85.48% | 64 | 17,945 | 54.34% | -37.86% |
| 7s0p | avg ticket hit q20 | 533 | 136 | 92,915 | 68.10% | 54.25% | 45.94% | -53.70% | 28 | 24,857 | 95.19% | -21.25% |
| 7s0p | p_hat + ticket hit q20 | 507 | 162 | 88,044 | 67.83% | 51.41% | 44.54% | -50.08% | 28 | 26,137 | 105.26% | -17.15% |
| 7s0p | avg p_hat q30 | 472 | 197 | 79,470 | 65.77% | 46.40% | 40.74% | -46.70% | 17 | 27,161 | 114.08% | -13.55% |

For optional protection `p0.85`, the strongest full-sample result is
`avg_ticket_pred_hit q20`. It preserves the large 2018 payoff while cutting the
maximum active loss streak sharply.

| strategy | gate | active | skipped | profit | deployed ROI | signal ROI | ex-best ROI | maxDD | max loss streak | 2023-2025 profit | 2023-2025 ROI | 2023-2025 ex-best ROI |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| optional p0.85 | none | 669 | 0 | 141,089 | 82.38% | 82.38% | 27.20% | -36.57% | 62 | 21,048 | 63.73% | -28.39% |
| optional p0.85 | avg ticket hit q20 | 531 | 138 | 162,927 | 119.86% | 95.13% | 50.38% | -34.51% | 18 | 24,601 | 93.30% | -22.02% |
| optional p0.85 | p_hat + ticket hit q20 | 499 | 170 | 71,475 | 55.95% | 41.73% | 32.26% | -34.51% | 16 | 25,881 | 103.16% | -18.00% |
| optional p0.85 | avg p_hat q30 | 477 | 192 | 68,113 | 55.78% | 39.77% | 30.99% | -34.51% | 17 | 27,161 | 114.08% | -13.55% |

## Window Sensitivity

Window choice matters. A gate that is too reactive can skip large payoff
periods; a gate that is too slow can fail recent regimes.

Selected sensitivity:

| strategy | window | gate | profit | deployed ROI | maxDD | max loss streak | 2023-2025 profit | 2023-2025 ROI |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| 7s0p | 48 | p_hat + ticket hit q20 | 61,449 | 50.11% | -38.53% | 17 | 26,393 | 107.39% |
| 7s0p | 96 | p_hat + ticket hit q20 | 88,044 | 67.83% | -50.08% | 28 | 26,137 | 105.26% |
| 7s0p | 192 | p_hat + ticket hit q20 | 61,050 | 49.37% | -46.47% | 28 | -4,214 | -17.15% |
| optional p0.85 | 48 | avg ticket hit q20 | 46,460 | 35.10% | -44.49% | 17 | 24,601 | 93.30% |
| optional p0.85 | 96 | avg ticket hit q20 | 162,927 | 119.86% | -34.51% | 18 | 24,601 | 93.30% |
| optional p0.85 | 192 | avg ticket hit q20 | 139,799 | 105.42% | -34.51% | 19 | -5,238 | -20.46% |
| optional p0.85 | 192 | avg p_hat q20 | 165,083 | 124.01% | -34.51% | 19 | 25,113 | 97.13% |

Interpretation:

- `7s0p` is more stable under the `avg_ticket_pred_hit q20` or combined q20
  gate than optional protection.
- Optional protection has higher upside, but it is more sensitive to whether
  the gate keeps the large 2018 win.
- The 192-issue window is not consistently better for 2023-2025.
- The 48-issue window can reduce drawdown and streak length, but it often gives
  up too much full-sample profit.

## Annual Stability

For `7s0p + avg_ticket_pred_hit q20`, yearly profits are:

| year | active | profit | ROI |
|---:|---:|---:|---:|
| 2014 | 98 | 24,400 | 97.26% |
| 2015 | 57 | 2,502 | 17.15% |
| 2016 | 49 | 20,742 | 165.35% |
| 2017 | 42 | 845 | 7.86% |
| 2018 | 40 | 16,076 | 156.99% |
| 2019 | 40 | -3,239 | -31.63% |
| 2020 | 32 | 14,012 | 171.05% |
| 2021 | 27 | 4,497 | 65.06% |
| 2022 | 46 | -11,776 | -100.00% |
| 2023 | 41 | 22,540 | 214.75% |
| 2024 | 46 | -6,744 | -57.27% |
| 2025 | 15 | 9,061 | 235.97% |

For `optional p0.85 + avg_ticket_pred_hit q20`, yearly profits are:

| year | active | profit | ROI |
|---:|---:|---:|---:|
| 2014 | 96 | 22,188 | 90.28% |
| 2015 | 56 | 2,472 | 17.24% |
| 2016 | 48 | 8,302 | 67.56% |
| 2017 | 42 | -4,800 | -44.64% |
| 2018 | 39 | 110,721 | 1108.99% |
| 2019 | 43 | -4,205 | -38.20% |
| 2020 | 32 | 2,499 | 30.51% |
| 2021 | 25 | 13,181 | 205.95% |
| 2022 | 47 | -12,032 | -100.00% |
| 2023 | 41 | 22,540 | 214.75% |
| 2024 | 47 | -7,000 | -58.18% |
| 2025 | 15 | 9,061 | 235.97% |

The recurring weak years remain 2019, 2022, and 2024. The gate reduces how much
capital is spent in weak regimes, but it does not fully solve regime detection.

## Decision Chain Update

Current fixed selector chain:

`outcome estimation -> match filter -> issue-quality gate -> coverage choice -> ticket construction -> portfolio result`

Updated conclusions:

1. Long losing streaks are mostly issue-quality/regime problems, not a simple
   league or outcome-direction problem.
2. `avg_ticket_pred_hit` is the best first issue-level gate signal. It directly
   measures the predicted probability that the generated N=7 tickets hit.
3. `avg_p_hat` is useful as a defensive companion. It improves recent and
   drawdown behavior in some configurations, but can also miss large payoffs.
4. `avg_score` is not a good standalone issue gate in these tests.
5. Optional protection plus a mild ticket-hit gate is the highest upside branch,
   but still jackpot-concentrated.
6. A hard skip gate improves risk metrics, but the production version may need a
   soft depth gate: low-quality issues receive smaller budget or fewer tickets
   instead of being fully skipped.

## Recommendation

Near-term candidate arms:

| priority | arm | reason |
|---:|---|---|
| 1 | `optional p0.85 + avg_ticket_pred_hit q20, window 96` | best current full-sample profit and much shorter loss streak |
| 2 | `7s0p + avg_ticket_pred_hit q20, window 96` | cleaner, less jackpot-sensitive validation branch |
| 3 | `7s0p + avg_p_hat q30, window 96` | defensive branch with shortest loss streak and best recent ex-best behavior |

Next test:

1. Convert the hard issue gate into a soft budget/depth gate.
2. Use low-quality issue buckets to reduce tickets or budget, not necessarily
   drop the issue.
3. Keep the fixed 256-unit full budget for normal/high-quality issues.
4. Re-run full sample, 2023-2025, annual, ex-best, and max active loss streak.

