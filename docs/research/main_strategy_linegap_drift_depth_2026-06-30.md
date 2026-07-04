# Main Strategy Line-Gap / Drift Depth Gate

Date: 2026-06-30

## Scope

Hermes card: `t_c676bdab`.

Goal: after the Asian handicap line backfill, evaluate whether `q`, prediction confidence, SP-drift state, and Beidan-vs-Asian line-gap can become a selector or depth gate for the main Beidan strategy.

Inputs:

- DB: `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`
- q/conf/drift legs: `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv`
- high-N selector tickets: `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- 384 sleeve baseline: `results/n7_sleeve_mix_capital_plus2026_linefill_20260630/sleeve_mix_issue_profit.csv`

Outputs:

- `results/main_strategy_linegap_drift_depth_20260630/joint_q_conf_drift_linegap_cells.csv`
- `results/main_strategy_linegap_drift_depth_20260630/joint_q_conf_drift_linegap_annual.csv`
- `results/main_strategy_linegap_drift_depth_20260630/paper_arm_summary.csv`
- `results/main_strategy_linegap_drift_depth_20260630/paper_arm_annual.csv`
- `results/main_strategy_linegap_drift_depth_20260630/paper_arm_issue_profit.csv`

## Method

Line-gap is computed at `1h`:

```sql
line_gap = -match_features.handicap_line_norm - market_consensus.v2_avg
```

The selected result is classified as:

- `support`: line-gap direction supports the chosen non-draw result.
- `oppose`: line-gap direction opposes the chosen non-draw result.
- `neutral`: draw result, unknown line, or absolute gap below `0.5`.

Paper arms are intentionally diagnostic:

- `baseline_384_convex`: current 384 convex candidate.
- `baseline_384_smooth`: lower-DD 384 smooth candidate.
- `existing_linegap_selector_v4_256`: existing high-N line-gap selector.
- `paper_drift_top8_256`: each issue keeps top 8 core tickets by predicted SP multiplier.
- `paper_linegap_drift_hybrid_top8_256`: top 8 core tickets by drift plus line-gap support.

## Joint Cell Readout

Top high-volume cells by single-leg EV proxy are still negative after the 65% return-rate assumption. This does not invalidate N-leg convexity, but it means no cell is good enough as a standalone leg-level hard gate.

| q | conf | drift | line-gap | legs | hit rate | avg SP on hits | EV proxy after 65% | 2023-2025 hit |
|---|---|---|---|---:|---:|---:|---:|---:|
| M | L | H | neutral | 825 | 38.8% | 3.06 | -22.8% | 34.8% |
| M | L | M | neutral | 1742 | 40.5% | 2.89 | -23.8% | 38.1% |
| H | L | M | neutral | 2554 | 37.4% | 3.10 | -24.6% | 38.8% |
| M | M | H | neutral | 1250 | 39.3% | 2.94 | -24.9% | 42.2% |
| H | H | L | support | 1046 | 58.3% | 1.92 | -27.2% | 66.7% |
| H | H | H | support | 418 | 59.8% | 1.94 | -24.4% | 51.0% |

High q + high confidence cells show the main tradeoff:

| drift | line-gap | legs | hit rate | avg SP on hits | EV proxy after 65% | 2023-2025 hit |
|---|---|---:|---:|---:|---:|---:|
| H | neutral | 190 | 48.9% | 2.59 | -17.4% | 50.0% |
| H | support | 418 | 59.8% | 1.94 | -24.4% | 51.0% |
| L | neutral | 2724 | 39.5% | 2.82 | -27.6% | 39.1% |
| L | support | 1046 | 58.3% | 1.92 | -27.2% | 66.7% |
| M | neutral | 2580 | 39.5% | 2.79 | -28.5% | 38.4% |
| M | support | 420 | 58.1% | 1.92 | -27.4% | 54.8% |

Interpretation:

- `line-gap support` tends to improve hit rate.
- But it also tends to lower realized SP on hits.
- `high q + high confidence + high drift + support` is not a clear payout-improving cell. It is a hit-rate cell.
- High-drift low-q/low-confidence cells are not reliable enough as selector cells; they may pay when they hit but do not stabilize tickets.

## Paper Replay

| arm | issues | profit | profit/256 | ROI | issue win | non-full-loss | maxDD | max loss streak | recent profit | recent ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| paper_drift_top8_256 | 695 | 371995 | 535 | 209.1% | 3.9% | 3.9% | -29184 | 114 | 75749 | 229.4% |
| baseline_384_convex | 702 | 369217 | 351 | 137.0% | 18.1% | 71.4% | -14936 | 30 | 120062 | 242.4% |
| existing_core80_exact20_256 | 695 | 236897 | 341 | 133.1% | 5.3% | 5.3% | -23629 | 56 | 81531 | 246.9% |
| paper_core_equal_256 | 695 | 225248 | 324 | 126.6% | 5.3% | 5.3% | -25219 | 56 | 52103 | 157.8% |
| existing_linegap_selector_v4_256 | 702 | 183855 | 262 | 102.3% | 2.1% | 2.1% | -44841 | 112 | 180111 | 545.4% |
| paper_linegap_drift_hybrid_top8_256 | 695 | 171846 | 247 | 96.6% | 4.3% | 4.3% | -26377 | 57 | 103082 | 312.1% |
| paper_linegap_support_top8_256 | 695 | 171025 | 246 | 96.1% | 4.3% | 4.3% | -26377 | 56 | 109153 | 330.5% |
| baseline_384_smooth | 702 | 258525 | 246 | 95.9% | 18.7% | 71.4% | -13691 | 30 | 111792 | 225.7% |

## Decision

Do not promote line-gap or SP drift into the production depth gate yet.

Recommended treatment:

- `line-gap`: diagnostic feature only. It repairs 2026 coverage and explains some line-gap selector differences, but hard line-gap selection worsens maxDD and produces too many full-loss issues.
- `SP drift`: useful convexity signal, but not a drawdown-control signal. `paper_drift_top8_256` has high profit/ROI, but its issue win rate is only `3.9%`, non-full-loss is `3.9%`, and max loss streak reaches `114`. It is not tolerable as a main sleeve.
- `line-gap + drift hybrid`: not good enough. The hybrid top-8 arm underperforms the plain core and does not improve drawdown.
- Keep current 384 candidates as the production research baseline:
  - `b384_dd32_smooth100` for lower absolute maxDD.
  - `b384_dd32_smooth80_convex19` for stronger profit/256 and convex upside.

Next useful work:

1. Keep `paper_drift_top8_256` as a very small convex paper arm only, capped at a small fraction of extra budget.
2. Study why drift-top tickets have such long dead streaks before any capital allocation.
3. Add line-gap state to the frontend as a diagnostic tag, not a buy/sell gate.
4. If a future depth model uses drift, it must be paired with an issue-level drawdown guard or protection sleeve, not used alone.
