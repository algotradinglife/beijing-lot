# N=7 soft line_gap and issue K-line regime test

Date: 2026-06-27

## Goal

This test evaluates whether the Asian-handicap vs Beidan integer handicap
`line_gap` should be used as a soft feature instead of a hard selector, and
whether issue-level P&L can be treated like a K-line series for regime control.

The implementation is in `scripts/evaluate_n7_high_sp_anchor_protection.py`.

## Command

```bash
python3 scripts/evaluate_n7_high_sp_anchor_protection.py \
  --min-year 2014 \
  --train-issues 24 \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --snapshot 1h \
  --min-proxy-odds-values 4,8 \
  --protection-policies market_top,q_top,market_top_linegap_soft,q_top_linegap_soft \
  --protect-score-floor-ratio 0.85 \
  --composition-mode target_protection \
  --target-protected-per-ticket 2 \
  --require-target-protection \
  --max-full-cover-per-ticket 1 \
  --full-cover-min-proxy-odds 12 \
  --full-protect-score-floor-ratio 0.80 \
  --line-gap-threshold 0.5 \
  --draw-stability-max-abs-log-move 0.08 \
  --line-gap-soft-boost 1.12 \
  --line-gap-soft-haircut 0.85 \
  --regime-big-loss-roi-threshold -0.75 \
  --output-dir results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12
```

Compilation smoke:

```bash
python3 -m py_compile scripts/evaluate_n7_high_sp_anchor_protection.py
```

## Output Files

- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_report.md`
- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_budget_fractional_summary.csv`
- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_budget_fractional_annual_summary.csv`
- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_budget_fractional_regime.csv`
- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_budget_fractional_regime_summary.csv`
- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_budget_fractional_regime_switch_summary.csv`
- `results/n7_high_sp_anchor_soft_linegap_2014_1h_5s2p_full12/high_sp_anchor_decisions.csv`

## What Changed

Added two soft line_gap policies:

- `market_top_linegap_soft`: start from `market_top`, then boost or haircut the
  protection candidate if the two-outcome cover direction agrees/disagrees with
  `line_gap`.
- `q_top_linegap_soft`: same idea, but starts from `q_top`.

Direction interpretation:

- positive `line_gap`: Beidan home handicap is deeper than Asian consensus, so
  `1/0` is treated as the supported protection direction.
- negative `line_gap`: `3/1` is treated as the supported protection direction.

Draw protection also requires draw odds stability:
`abs(log(draw_current / draw_10h)) <= 0.08`.

Added issue-level K-line diagnostics:

- `prev_loss_streak`
- `prev_big_loss_streak`
- `prev3_profit_units`
- `prev3_roi`
- `regime_after_three_losses`
- `regime_after_three_big_losses`

Here, a big loss is defined as issue ROI `<= -75%`.

Also added no-leakage dynamic switch summaries:

- default strategy A, after three losses switch to strategy B for the next issue.
- default strategy A, after three big losses switch to strategy B for the next issue.

## Same-Budget Full-History Summary

All rows use same-budget fractional staking, 256 units per issue.

| arm | tickets | issues | hit_rate | issue_win_rate | profit | ROI | best_share | maxDD | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `o8_q_top_5s2p_full12` | 7,851 | 423 | 0.90% | 9.46% | 95,498 | 88.19% | 37.65% | -61.43% | pass |
| `o8_q_top_linegap_soft_5s2p_full12` | 7,881 | 425 | 0.82% | 9.65% | 40,292 | 37.03% | 64.74% | -80.90% | pass |
| `o4_market_top_linegap_soft_5s2p_full12` | 13,041 | 654 | 1.15% | 16.06% | 34,426 | 20.56% | 42.54% | -222.61% | pass |
| `o4_market_top_5s2p_full12` | 13,021 | 653 | 1.11% | 14.70% | 30,660 | 18.34% | 47.76% | -118.16% | pass |
| `o4_q_top_5s2p_full12` | 13,336 | 669 | 1.00% | 13.60% | 21,245 | 12.40% | 37.19% | -88.61% | pass |
| `o4_q_top_linegap_soft_5s2p_full12` | 13,350 | 669 | 0.88% | 12.41% | 658 | 0.38% | 1440.52% | -72.72% | fail concentrated |
| `baseline_q_high_sp` | 12,992 | 668 | 0.34% | 5.09% | -37,816 | -22.11% | | -306.18% | fail negative ROI |

## 2023-2025 Summary

| arm | tickets | hit_rate | profit | ROI |
|---|---:|---:|---:|---:|
| `o4_market_top` | 2,497 | 0.72% | 9,684 | 30.26% |
| `o4_market_top_linegap_soft` | 2,497 | 0.80% | 13,633 | 42.60% |
| `o8_q_top` | 1,551 | 0.52% | 12,897 | 55.98% |
| `o8_q_top_linegap_soft` | 1,546 | 0.19% | -12,462 | -54.70% |
| `baseline_q_high_sp` | 2,523 | 0.36% | -16,576 | -50.19% |

Recent years favor `market_top_linegap_soft`, but strongly reject
`q_top_linegap_soft`.

Year detail:

| arm | 2023 ROI | 2024 ROI | 2025 ROI |
|---|---:|---:|---:|
| `o4_market_top` | -20.54% | 69.09% | 68.17% |
| `o4_market_top_linegap_soft` | 11.08% | 74.79% | 35.95% |
| `o8_q_top` | -60.87% | 57.56% | 401.90% |
| `o8_q_top_linegap_soft` | -100.00% | -39.79% | 38.78% |

## Remove Largest Winning Issue

| arm | ROI ex-best | profit ex-best | best_share |
|---|---:|---:|---:|
| `o4_market_top` | 9.58% | 16,016 | 47.76% |
| `o4_market_top_linegap_soft` | 11.82% | 19,782 | 42.54% |
| `o8_q_top` | 54.98% | 59,540 | 37.65% |
| `o8_q_top_linegap_soft` | 13.06% | 14,206 | 64.74% |

This supports the earlier view that lottery-style strategies can be acceptable
even when the best issue contributes heavily, as long as ex-best EV stays
positive. `o8_q_top` remains the best tail arm by this criterion.

## Soft line_gap Diagnostics

Decision rows show why the soft feature behaves differently by base policy.

| arm | fallback_single | neutral | supported | opposed |
|---|---:|---:|---:|---:|
| `o4_market_top_linegap_soft` | 88.06% | 10.37% | 1.57% | 0.00% |
| `o8_q_top_linegap_soft` | 87.22% | 8.78% | 1.21% | 2.78% |

The soft line_gap layer barely opposes `market_top`, but it opposes `q_top`
more often. This is consistent with the result: line_gap is useful as a
market-protection tiebreaker, but harmful when it disturbs a q-driven high-SP
tail selector.

## K-line Regime Findings

The K-line idea is valid as a monitoring frame, but this run does not support a
simple "three large red candles means risk-off" rule.

Same-budget regime summary:

| arm | regime | issues | issue_win_rate | profit | ROI | maxDD |
|---|---|---:|---:|---:|---:|---:|
| `o4_market_top` | all | 653 | 14.70% | 30,660 | 18.34% | -118.21% |
| `o4_market_top` | after_three_big_losses | 386 | 16.06% | 44,891 | 45.43% | -57.66% |
| `o4_market_top_linegap_soft` | all | 654 | 16.06% | 34,426 | 20.56% | -224.21% |
| `o4_market_top_linegap_soft` | after_three_big_losses | 367 | 17.17% | 38,729 | 41.22% | -59.42% |
| `o8_q_top` | all | 423 | 9.46% | 95,498 | 88.19% | -60.95% |
| `o8_q_top` | after_three_big_losses | 312 | 9.29% | 64,537 | 80.80% | -87.04% |

After three losses, the next issues are not obviously worse. In several arms,
they are better. This is probably because N=7 returns are sparse and lumpy:
several losing issues are normal waiting time, not necessarily factor decay.

No-leakage dynamic switch test:

| dynamic rule | profit | ROI | maxDD |
|---|---:|---:|---:|
| default `o4_market_top_linegap_soft`, switch to `o4_market_top` after 3 losses | 37,939 | 22.66% | -188.88% |
| default `o4_market_top_linegap_soft`, switch to `o4_market_top` after 3 big losses | 37,323 | 22.29% | -196.24% |
| default `o4_market_top`, switch to `o4_market_top_linegap_soft` after 3 losses | 28,902 | 17.26% | -180.35% |
| default `o8_q_top`, switch to `o8_q_top_linegap_soft` after 3 losses | 75,740 | 69.29% | -65.10% |
| default `o8_q_top_linegap_soft`, switch to `o8_q_top` after 3 losses | 78,152 | 71.49% | -80.72% |

The only modestly useful switch is: use `o4_market_top_linegap_soft` as default,
then switch back to original `o4_market_top` after a three-loss sequence. It
improves ROI vs both static `o4` arms, but max drawdown is still too large.

For `o8_q_top`, the static original arm remains better than dynamic switching.

## Conclusions

1. `line_gap` should not be a hard selector.
2. `line_gap` can be used as a soft modifier for `market_top` protection.
3. `line_gap` should not be applied to the current `q_top` high-SP tail arm.
4. The K-line framing is useful, but three-loss or three-big-loss streaks are
   not sufficient evidence to reduce stake mechanically.
5. For the balanced arm, the next candidate is:
   `o4_market_top_linegap_soft_5s2p_full12`.
6. For the tail arm, keep:
   `o8_q_top_5s2p_full12`.

## Recommended Next Step

Build one unified `leg_selector/depth_gate` around the following logic:

1. First filter bad matches: no value, low payout, adverse drift, unstable draw,
   or weak q/confidence.
2. For retained matches, classify into `single`, `double`, `full`, or `skip`.
3. Use `market_top_linegap_soft` only for the balanced protection arm.
4. Use raw `q_top` for the high-SP tail arm.
5. Add issue-level K-line state as a monitoring input first, not a stake-off
   rule. It may later become a factor-weight switch, but only if walk-forward
   tests show stable improvement in both ROI and maxDD.

