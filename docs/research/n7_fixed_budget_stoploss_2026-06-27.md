# N=7 fixed-budget stop-loss replay

Date: 2026-06-27

## Purpose

The current preference is fixed staking rather than fractional compounding.
This test keeps fixed 256-unit active-issue staking and adds stop-loss rules at
the capital-allocation layer.

The selector and tickets are unchanged. Stop-loss rules only decide whether to
skip a later issue after earlier realized losses or drawdown.

## Implementation

Script:

- `scripts/evaluate_n7_capital_models.py`

New stop-loss model families:

- `fixed_stop_dd{X}_cool{N}`: after equity drawdown reaches X, skip the next N
  calendar issues.
- `fixed_stop_loss{K}_cool{N}`: after K consecutive losing active issues, skip
  the next N calendar issues.
- `fixed_stop_bigloss{K}_cool{N}`: same as loss streak, but only counts issues
  with ROI <= -0.75 as a big loss.

The replay writes `signal` and `stopped` columns in the equity curve, so active
skips can be separated from no-signal idle issues.

Command:

```bash
python3 scripts/evaluate_n7_capital_models.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named \
  results/n7_ev_framework_selector_2014_1h_minodds4_6s1p_named \
  results/n7_ev_framework_selector_2014_1h_minodds4_5s2p_named \
  --output-dir results/n7_ev_framework_capital_stoploss_2014_1h_minodds4 \
  --strategy-regex '^ev_' \
  --initial-bankroll 10000 \
  --calendar-budget-units 256 \
  --fractions 0.005,0.01 \
  --stop-drawdowns 0.3,0.5 \
  --stop-loss-streaks 3,5 \
  --stop-cooldowns 3,6,12 \
  --big-loss-roi-threshold -0.75
```

Compile check:

```bash
python3 -m py_compile scripts/evaluate_n7_capital_models.py
```

## Main Results

Fixed staking uses 256 units per active issue. Initial bankroll for drawdown
accounting is 10,000 units.

| strategy | capital model | active | stopped | profit | ROI on stake | bankroll return | annualized return | maxDD | best share |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 7s0p | fixed active | 669 | 0 | 71,244 | 41.60% | 712.44% | 19.07% | -85.48% | 42.60% |
| 7s0p | loss5 cool3 | 459 | 210 | 84,878 | 72.23% | 848.78% | 20.62% | -49.99% | 35.76% |
| 7s0p | dd50 cool3 | 651 | 18 | 74,557 | 44.74% | 745.57% | 19.47% | -60.80% | 40.71% |
| 7s0p | loss3 cool12 | 155 | 514 | 20,870 | 52.60% | 208.70% | 9.85% | -38.00% | 139.54% |
| 5s2p | fixed active | 454 | 0 | 35,128 | 30.22% | 351.28% | 13.38% | -37.68% | 43.46% |
| 5s2p | loss3 cool6 | 216 | 238 | 39,581 | 71.58% | 395.81% | 14.27% | -23.95% | 38.57% |
| 5s2p | loss3 cool3 | 278 | 176 | 44,264 | 62.20% | 442.64% | 15.14% | -41.74% | 34.49% |
| 6s1p | fixed active | 534 | 0 | 24,804 | 18.14% | 248.04% | 10.95% | -104.53% | 71.72% |
| 6s1p | loss5 cool6 | 298 | 236 | 30,963 | 40.59% | 309.63% | 12.47% | -70.43% | 57.46% |

## 7s0p Fine Sweep

After the coarse run, a focused `7s0p` sweep was run around the best region:

```bash
python3 scripts/evaluate_n7_capital_models.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named \
  --output-dir results/n7_ev_framework_capital_stoploss_7s0p_fine_2014_1h_minodds4 \
  --strategy-regex '^ev_' \
  --initial-bankroll 10000 \
  --calendar-budget-units 256 \
  --fractions '' \
  --stop-drawdowns '' \
  --stop-loss-streaks 4,5,6 \
  --stop-cooldowns 2,3,4,5 \
  --big-loss-roi-threshold -0.75
```

Top rows:

| capital model | active | stopped | profit | ROI on stake | bankroll return | annualized return | maxDD | best share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| loss5 cool2 | 515 | 154 | 97,682 | 74.09% | 976.82% | 21.90% | -57.38% | 31.07% |
| loss5 cool3 | 459 | 210 | 84,878 | 72.23% | 848.78% | 20.62% | -49.99% | 35.76% |
| loss6 cool2 | 535 | 134 | 76,116 | 55.58% | 761.16% | 19.65% | -70.04% | 39.88% |
| fixed active | 669 | 0 | 71,244 | 41.60% | 712.44% | 19.07% | -85.48% | 42.60% |

Fine-sweep interpretation:

- `loss5 cool2` is the return-maximizing fixed-stop variant in this grid.
- `loss5 cool3` is the better risk-control candidate because it is the only
  top-return row with maxDD better than -55%.
- `loss4` and `loss6` are less attractive. `loss4` can over-stop and create bad
  path behavior; `loss6` waits too long and leaves too much drawdown.

## 2023-2025 Check

| strategy | capital model | active | stopped | profit | ROI on stake | period return | maxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| 7s0p | fixed active | 129 | 0 | 17,945 | 54.34% | 28.35% | -24.67% |
| 7s0p | loss5 cool3 | 87 | 42 | 28,697 | 128.85% | 43.36% | -13.84% |
| 7s0p | dd50 cool3 | 129 | 0 | 17,945 | 54.34% | 26.94% | -23.85% |
| 7s0p | loss3 cool12 | 31 | 98 | -3,755 | -47.32% | -10.84% | -16.11% |
| 5s2p | fixed active | 117 | 0 | -1,061 | -3.54% | -2.30% | -27.97% |
| 5s2p | loss3 cool6 | 46 | 71 | -3,307 | -28.09% | -6.25% | -16.53% |
| 5s2p | loss3 cool3 | 64 | 53 | -1,372 | -8.37% | -2.47% | -22.65% |
| 6s1p | fixed active | 125 | 0 | 9,674 | 30.23% | 38.49% | -36.29% |
| 6s1p | loss5 cool6 | 66 | 59 | 8,461 | 50.08% | 26.03% | -19.81% |

## Interpretation

The best fixed-stake stop-loss candidate is:

- `7s0p + fixed_stop_loss5_cool3`

Reasons:

- It improves full-period profit from 71,244 to 84,878.
- It improves max drawdown from -85.5% to -50.0%.
- It improves 2023-2025 profit from 17,945 to 28,697.
- It skips 210 of 669 signal issues, so it is not just a tiny accounting
  adjustment. The data suggests losing regimes cluster.
- Best issue share falls from 42.6% to 35.8%, so concentration improves.

If the operating objective permits maxDD around -57%, `loss5 cool2` is the
aggressive alternative. It has higher total profit, higher annualized return,
and lower best-share concentration, but gives up about 7.4 percentage points of
drawdown protection versus `loss5 cool3`.

The drawdown-trigger rule is less attractive:

- `7s0p + dd50 cool3` improves full-period profit modestly and reduces maxDD,
  but it does almost nothing in 2023-2025 because the trigger did not fire.
- Drawdown stops are reactive. By the time drawdown threshold is hit, a large
  part of the damage has already happened.

The overly strict rule is not acceptable:

- `7s0p + loss3 cool12` gives a low maxDD, but it skips 514 of 669 signals and
  loses money in 2023-2025. This is too much opportunity cost.

For `5s2p`:

- `loss3 cool6` is the best full-history drawdown smoother.
- It does not fix the recent-period weakness. The 2023-2025 result remains
  negative, so this is not a better main branch than `7s0p loss5 cool3`.

## Decision Chain Update

The decision chain now has a concrete capital-allocation branch:

`outcome_estimation -> match_filter -> coverage_choice -> ticket_construction -> portfolio_result -> capital_allocation`

Current capital-allocation recommendation:

- Main fixed-stake branch: `7s0p + loss5 cool3`.
- Aggressive fixed-stake branch: `7s0p + loss5 cool2`.
- Defensive comparator: `5s2p + loss3 cool6`.
- Reject: fixed 5% bankroll, `6s1p` as main branch, and `loss3 cool12` for
  `7s0p`.

## Next Tests

1. Test half-size instead of full skip during cooldown.
2. Test a recovery rule: after cooldown, resume only if the last rolling K-line
   is no longer negative.
3. Combine stop-loss with marginal-EV protection depth, because stop-loss deals
   with issue-level regime risk while coverage depth deals with ticket-level
   dead-leg risk.
