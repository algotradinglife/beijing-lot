# N=7 capital model replay

Date: 2026-06-27

## Purpose

This note adds a capital-allocation layer to the N=7 EV framework. It replays
existing per-issue returns under several funding models:

1. `fixed_active_issue_budget`: bet 256 units only when the strategy has a
   signal.
2. `fixed_calendar_issue_budget`: same bets, but ROI denominator includes every
   calendar issue's 256-unit budget, including idle issues.
3. `fractional_bankroll_Xpct`: on active issues, bet X% of current bankroll.

This is a post-selection replay. It does not change the selector, retrain a
model, or introduce future information.

## Implementation

Script:

- `scripts/evaluate_n7_capital_models.py`

Inputs:

- `ev_framework_issue_profit.csv`
- `ev_framework_windows.csv`

Outputs:

- `results/n7_ev_framework_capital_models_2014_1h_minodds4/capital_model_summary.csv`
- `results/n7_ev_framework_capital_models_2014_1h_minodds4/capital_model_equity_curve.csv`
- `results/n7_ev_framework_capital_models_2014_1h_minodds4/capital_model_annual_summary.csv`
- `results/n7_ev_framework_capital_models_2014_1h_minodds4/capital_model_report.md`

Command:

```bash
python3 scripts/evaluate_n7_capital_models.py \
  results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named \
  results/n7_ev_framework_selector_2014_1h_minodds4_6s1p_named \
  results/n7_ev_framework_selector_2014_1h_minodds4_5s2p_named \
  --output-dir results/n7_ev_framework_capital_models_2014_1h_minodds4 \
  --strategy-regex '^ev_' \
  --initial-bankroll 10000 \
  --calendar-budget-units 256 \
  --fractions 0.005,0.01,0.02,0.05
```

Compile check:

```bash
python3 -m py_compile scripts/evaluate_n7_capital_models.py
```

## Fixed Budget vs Calendar Budget

Initial bankroll for drawdown accounting is 10,000 units. Fixed-budget rows
still bet 256 units per active issue.

| strategy | model | active/calendar | deployed stake | profit | ROI on deployed stake | ROI on calendar budget | bankroll return | annualized bankroll return | maxDD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 7s0p | fixed active | 669/672 | 171,264 | 71,244 | 41.60% | 41.60% | 712.44% | 19.07% | -85.48% |
| 7s0p | fixed calendar | 669/672 | 171,264 | 71,244 | 41.60% | 41.41% | 712.44% | 19.07% | -85.48% |
| 5s2p | fixed active | 454/672 | 116,224 | 35,128 | 30.22% | 30.22% | 351.28% | 13.38% | -37.68% |
| 5s2p | fixed calendar | 454/672 | 116,224 | 35,128 | 30.22% | 20.42% | 351.28% | 13.38% | -37.68% |
| 6s1p | fixed active | 534/672 | 136,704 | 24,804 | 18.14% | 18.14% | 248.04% | 10.95% | -104.53% |
| 6s1p | fixed calendar | 534/672 | 136,704 | 24,804 | 18.14% | 14.42% | 248.04% | 10.95% | -104.53% |

Interpretation:

- `7s0p` fires in almost every eligible issue, so calendar-budget ROI is almost
  identical to active-budget ROI.
- `5s2p` is much more selective. Its active ROI is 30.22%, but calendar-budget
  ROI drops to 20.42% after idle issues are counted.
- `6s1p` has positive total profit but would require bankroll replenishment
  under a strict 10,000-unit account because fixed 256-unit staking draws down
  more than 100% at one point.

## Fractional Bankroll Replay

| strategy | fraction | final bankroll | bankroll return | annualized return | maxDD | best issue profit share | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| 7s0p | 0.5% | 25,412 | 154.12% | 8.08% | -37.20% | 79.83% | watch |
| 7s0p | 1.0% | 34,080 | 240.80% | 10.76% | -60.82% | 134.60% | aggressive watch |
| 7s0p | 2.0% | 19,416 | 94.16% | 5.68% | -86.10% | 501.37% | too path-sensitive |
| 7s0p | 5.0% | 26 | -99.74% | -39.06% | -99.96% |  | reject |
| 5s2p | 0.5% | 17,390 | 73.90% | 4.72% | -26.80% | 64.16% | conservative watch |
| 5s2p | 1.0% | 24,209 | 142.09% | 7.65% | -48.95% | 96.09% | watch |
| 5s2p | 2.0% | 28,400 | 184.00% | 9.09% | -78.49% | 239.56% | too aggressive |
| 5s2p | 5.0% | 3,268 | -67.32% | -8.90% | -99.17% |  | reject |
| 6s1p | 0.5% | 13,128 | 31.28% | 2.29% | -28.20% | 110.54% | weak |
| 6s1p | 1.0% | 12,278 | 22.78% | 1.72% | -49.95% | 262.40% | weak |
| 6s1p | 2.0% | 5,286 | -47.14% | -5.17% | -77.41% |  | reject |
| 6s1p | 5.0% | 15 | -99.85% | -41.99% | -99.95% |  | reject |

## Decision Feedback

The capital model changes the strategy ranking:

- Fixed active budget favors `7s0p` by total profit and ROI.
- Calendar budget barely penalizes `7s0p` because it is active in 99.6% of
  calendar issues.
- Fractional bankroll does not monotonically improve results. At 2% and 5%,
  path dependence dominates; bad years after bankroll growth destroy a large
  part of compounded gains.
- `5s2p` has lower return but a much smoother fixed-budget drawdown. It remains
  useful as a defensive comparator.
- `6s1p` remains unattractive. It is both concentration-heavy and weak under
  fractional bankroll.

## Practical Takeaways

1. Do not use 5% bankroll per active issue. It is too large for this payoff
   distribution.
2. Treat 1% bankroll as an upper bound until drawdown gates are better.
3. For the current EV branch, `7s0p` at 0.5%-1.0% bankroll is the most relevant
   compound replay range.
4. If the goal is smoother capital survival, compare `7s0p 0.5%` against
   `5s2p 1.0%` rather than forcing one universal protection depth.
5. Add `capital_allocation` as the final stage of the decision chain:
   `outcome_estimation -> match_filter -> coverage_choice -> ticket_construction -> portfolio_result -> capital_allocation`.

## Next Tests

1. Add dynamic fractional sizing: reduce fraction after three large losing
   issues and restore only after recovery.
2. Add a drawdown stop or cool-down gate at the capital layer.
3. Combine marginal-EV coverage depth with fractional bankroll sizing:
   coverage depth controls death-ticket risk; bankroll fraction controls
   account survival.
4. Evaluate unit-time performance under fractional models, not just full-period
   final bankroll.
