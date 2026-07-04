# N7 Convexity Depth Overlay

Date: 2026-06-28

## Question

The capital layer should not be framed as a true cooldown. If an issue still has enough convex right tail, the strategy should keep playing, and may need more coverage depth to avoid missing the payout. This replay tests that idea on the current practical base:

`reference::draw_tail_to_n3::w5::dd2::ls4`

## Data And Setup

- Base issue file: `results/n7_dynamic_sleeve_allocator_n3_20260628_timefix/dynamic_sleeve_issue_profit.csv`
- Output: `results/n7_convexity_depth_overlay_20260628/`
- Equity figure: `docs/research/figures/n7_convexity_depth_overlay_equity_2026-06-28.svg`
- Trigger fields are pre-bet issue fields only: `state`, `tickets`, and chosen arm.
- Current convexity proxy:
  - `low30`: selected book has `tickets <= 30`
  - `ge100`: selected book has `tickets >= 100`
  - `low30_or_ge100`: either of the above

This is still a proxy, not the final convexity model. The next step should replace it with ticket-level predicted payout and hit-probability features.

## Main Result

| Model | Trigger issues | Profit | ROI on deployed stake | ROI on base budget | Non-full-loss | MaxDD | Recent ex-best on base budget | Read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| base | 0 | 306,788 | 89.6% | 89.6% | 78.3% | -29,268 | 35.5% | current reference |
| all_low30_scale2 | 97 | 344,065 | 87.7% | 100.4% | 78.3% | -31,282 | 66.4% | catches right tail, worse drawdown |
| all_low30_or_ge100_scale2 | 148 | 348,257 | 83.3% | 101.7% | 78.3% | -31,910 | 66.9% | highest profit, worst comfort |
| all_low30_add_n3_64_n5op_64 | 97 | 309,601 | 87.2% | 90.4% | 82.5% | -28,030 | 42.1% | best coverage-style improvement |
| all_low30_or_ge100_add_n3_64_n5op_64 | 148 | 309,337 | 85.6% | 90.3% | 83.6% | -28,234 | 41.7% | smoother, slightly lower ROI |
| bad_low30_or_ge100_reduce_lowconv_bad_0p5_add_n3_128 | 89 | 208,087 | 81.4% | 60.8% | 78.3% | -18,853 | 29.0% | drawdown control too expensive |

## Interpretation

1. Same-book sizing confirms the convexity point.

Scaling the selected book on high-convexity proxy issues materially increases profit. `all_low30_or_ge100_scale2` adds about 41,469 units versus base. But this is not solving "coverage"; it mostly doubles exposure to the same selected tickets. It worsens max drawdown from -29,268 to -31,910 and extends the longest underwater stretch from 137 to 169 issues.

2. Coverage depth is the better production direction.

Adding a small N3+N5 sleeve only on `low30` issues adds less profit, but it improves the experience:

- profit: 306,788 -> 309,601
- non-full-loss: 78.3% -> 82.5%
- maxDD: -29,268 -> -28,030
- recent ex-best: 35.5% -> 42.1%

This is closer to the target: "usually small loss or small win, occasionally large win." It does not rely on a hard cooldown and does not simply multiply the same ticket risk.

3. Reducing low-convexity bad-regime exposure is effective but too costly.

The reduce-low-convexity arm cuts maxDD to about -18.9k, but profit falls to about 208k. This belongs in a later capital-preservation layer, not the main EV strategy.

## Recommendation

Use this hierarchy next:

1. Keep `reference::draw_tail_to_n3::w5::dd2::ls4` as the base.
2. Add a paper/experimental production candidate:
   `all_low30_add_n3_64_n5op_64`
3. Keep same-book convexity scaling as a paper arm only:
   `all_low30_or_ge100_scale2`
4. Replace ticket-count proxy with a real convexity score:
   `expected_tail_payout = f(pred_hit_prob, predicted_payout_multiplier, q/confidence, coverage_overlap)`

The key decision-chain update is: there is no standalone cooldown. The policy should first ask whether the current issue has enough right-tail payoff and whether the miss risk is coverage-driven. If yes, increase coverage depth; if no, reduce exposure.

## Verification

- `python3 -m py_compile scripts/evaluate_n7_convexity_depth_overlay.py scripts/evaluate_issue_cooldown.py`
- `python3 scripts/evaluate_n7_convexity_depth_overlay.py --output-dir results/n7_convexity_depth_overlay_20260628`
