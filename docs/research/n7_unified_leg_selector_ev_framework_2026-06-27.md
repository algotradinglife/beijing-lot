# N=7 unified leg selector and EV framework

Date: 2026-06-27

## Goal

This note consolidates the current N=7 work into a cleaner selector framework:

1. Decide whether a match is worth trading.
2. Within tradable matches, rank the EV of each result.
3. Construct N=7 tickets from high-EV legs.
4. Use limited lower-EV coverage to reduce dead-leg risk, not as generic
   insurance.

The implementation is in:

- `scripts/evaluate_n7_unified_leg_selector.py`

The script evaluates two arms:

- balanced arm: `o4 + market_top_linegap_soft + 5 singles / 2 protected legs`
- tail arm: `o8 + q_top + 5 singles / 2 protected legs`

K-line state is emitted as monitoring data only.

## Commands

Default same-budget version, where unused tail budget can flow back to balanced:

```bash
python3 scripts/evaluate_n7_unified_leg_selector.py \
  --min-year 2014 \
  --train-issues 24 \
  --snapshot 1h \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --output-dir results/n7_unified_leg_selector_2014_1h_bal_tail
```

No-fallback version, where tail budget is spent only when the tail arm has a
signal:

```bash
python3 scripts/evaluate_n7_unified_leg_selector.py \
  --min-year 2014 \
  --train-issues 24 \
  --snapshot 1h \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --no-reallocate-unused-to-balanced \
  --output-dir results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback
```

Smoke check:

```bash
python3 -m py_compile scripts/evaluate_n7_unified_leg_selector.py
```

## Output Files

Fallback:

- `results/n7_unified_leg_selector_2014_1h_bal_tail/unified_leg_selector_report.md`
- `results/n7_unified_leg_selector_2014_1h_bal_tail/unified_leg_selector_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail/unified_leg_selector_recent_2023_2025_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail/unified_leg_selector_annual_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail/unified_leg_selector_ex_best_issue_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail/unified_leg_selector_regime_summary.csv`

No fallback:

- `results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback/unified_leg_selector_report.md`
- `results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback/unified_leg_selector_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback/unified_leg_selector_recent_2023_2025_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback/unified_leg_selector_annual_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback/unified_leg_selector_ex_best_issue_summary.csv`
- `results/n7_unified_leg_selector_2014_1h_bal_tail_no_fallback/unified_leg_selector_regime_summary.csv`

## Same-Budget Results

Fallback means unused tail budget is reallocated to balanced. No fallback means
tail budget is left unused when no tail signal exists.

| strategy | stake | profit | ROI | issue_win_rate | best_share | maxDD | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| `bal0_tail100_noFallback` | 108,288 | 95,498 | 88.19% | 9.46% | 37.65% | -61.43% | pass |
| `bal0_tail100_balFallback` | 167,936 | 105,013 | 62.53% | 11.43% | 34.24% | -97.28% | pass |
| `bal80_tail20_noFallback` | 155,597 | 63,246 | 40.65% | 17.84% | 18.44% | -94.31% | pass |
| `bal80_tail20_balFallback` | 167,936 | 64,739 | 38.55% | 17.84% | 18.02% | -105.79% | pass |
| `bal60_tail40_noFallback` | 143,770 | 59,573 | 41.44% | 18.14% | 23.89% | -74.23% | pass |
| `bal60_tail40_balFallback` | 167,936 | 63,071 | 37.56% | 18.14% | 22.56% | -95.51% | pass |
| `bal100_tail0` | 167,424 | 34,426 | 20.56% | 16.06% | 42.54% | -222.61% | pass |
| `baseline_q_high_sp` | 171,008 | -37,816 | -22.11% | 5.09% | | -306.18% | fail |

The best raw ROI remains pure tail without fallback, but it only fires in 423
issues. For a more regular operating strategy, `bal80_tail20_noFallback` and
`bal60_tail40_noFallback` are the cleanest candidates:

- `80/20 noFallback`: higher total profit and lower best-share.
- `60/40 noFallback`: lower max drawdown and slightly higher issue win rate.

## 2023-2025 Results

| strategy | stake | profit | ROI | issue_win_rate | best_share | maxDD | verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| `bal0_tail100_balFallback` | 32,512 | 19,938 | 61.32% | 7.87% | 76.31% | -65.35% | fail concentrated |
| `bal0_tail100_noFallback` | 23,040 | 12,897 | 55.98% | 4.44% | 117.97% | -100.09% | fail concentrated |
| `bal80_tail20_noFallback` | 30,208 | 15,561 | 51.51% | 12.60% | 74.96% | -51.32% | fail concentrated |
| `bal80_tail20_balFallback` | 32,512 | 16,559 | 50.93% | 12.60% | 70.44% | -52.81% | fail concentrated |
| `bal60_tail40_balFallback` | 32,512 | 15,848 | 48.74% | 12.60% | 54.80% | -54.34% | pass |
| `bal60_tail40_noFallback` | 28,416 | 13,339 | 46.94% | 12.60% | 65.10% | -60.08% | pass |
| `bal100_tail0` | 32,000 | 13,633 | 42.60% | 12.00% | 107.41% | -63.92% | fail concentrated |

Recent-period concentration remains a concern. The current best practical
choice is `60/40` if recent concentration and drawdown matter more than full
sample profit.

## Ex-Best Issue

| strategy | ROI ex-best | profit ex-best | best_share |
|---|---:|---:|---:|
| `bal0_tail100_noFallback` | 54.98% | 59,540 | 37.65% |
| `bal0_tail100_balFallback` | 41.12% | 69,054 | 34.24% |
| `bal80_tail20_noFallback` | 33.15% | 51,582 | 18.44% |
| `bal80_tail20_balFallback` | 31.60% | 53,075 | 18.02% |
| `bal60_tail40_noFallback` | 31.54% | 45,343 | 23.89% |
| `bal60_tail40_balFallback` | 29.08% | 48,841 | 22.56% |
| `bal100_tail0` | 11.82% | 19,782 | 42.54% |

This is a meaningful improvement over the standalone balanced arm: mixed arms
keep ex-best EV strongly positive while reducing single-issue dependence.

## Annual Notes

`bal80_tail20_noFallback` annual ROI:

- 2014: -28.81%
- 2015: 84.14%
- 2016: -20.16%
- 2017: -44.40%
- 2018: 14.24%
- 2019: 129.19%
- 2020: 100.76%
- 2021: 164.55%
- 2022: -1.48%
- 2023: 1.57%
- 2024: 72.29%
- 2025: 151.39%

`bal60_tail40_noFallback` annual ROI:

- 2014: -22.49%
- 2015: 107.17%
- 2016: -6.91%
- 2017: -46.59%
- 2018: 13.27%
- 2019: 111.55%
- 2020: 70.45%
- 2021: 178.15%
- 2022: -16.38%
- 2023: -12.31%
- 2024: 69.42%
- 2025: 169.96%

Both still have bad years. The selector is not yet a finished risk-managed
strategy.

## K-Line Regime

K-line state remains a monitor, not a stake rule.

For `bal80_tail20_noFallback`:

- all issues: ROI 40.65%, maxDD -93.58%
- after three big losses: ROI 61.84%, maxDD -41.25%
- after three losses: ROI 62.29%, maxDD -46.33%

For `bal60_tail40_noFallback`:

- all issues: ROI 41.44%, maxDD -73.40%
- after three big losses: ROI 63.61%, maxDD -35.02%
- after three losses: ROI 76.28%, maxDD -39.50%

The data still does not support a naive "three red candles means reduce stake"
rule. Losing streaks are often just the normal waiting time for N=7 payouts.

## EV Framework

The cleaner model should be expressed around EV, not around ad hoc arms.

### 1. Match EV

For each match, estimate the aggregate tradeability:

```text
match_ev = max_over_cover_sets(
  sum(P(result=o) * estimated_sp(o) for o in cover_set)
  * return_rate
  / cover_count
  - 1
)
```

If `match_ev` is too low, skip the match entirely. This captures both cases:

- high win probability but SP too low;
- high SP but probability or drift-adjusted payout is too weak.

### 2. Outcome EV

For a tradable match:

```text
outcome_ev(o) = P(result=o) * estimated_sp(o) * return_rate - 1
```

`P(result=o)` should combine q, result prediction confidence, market implied
probability, and possibly line_gap. `estimated_sp(o)` should use 1h odds and
SP-drift estimation.

### 3. Coverage EV

Single/double/full should be selected by marginal EV and dead-leg reduction:

```text
coverage_ev(S) = sum(P(result=o) * estimated_sp(o) for o in S)
                 * return_rate
                 / |S|
                 - 1
```

The main outcome should be high EV. Lower-EV outcomes can still receive small
coverage if:

- the match has high match-level EV;
- the lower-EV outcome meaningfully reduces dead-leg probability;
- the extra cover count does not destroy ticket-level EV;
- portfolio constraints still hold, such as 5 singles + 2 protected legs.

This reframes protection as "paying for survival with bounded EV leakage", not
as blind insurance.

### 4. Ticket EV

For an N=7 ticket:

```text
ticket_ev = return_rate * product(coverage_value_i) - stake_units
```

where each `coverage_value_i` is the sum of drift-adjusted payout probabilities
for selected outcomes in leg `i`.

### 5. Portfolio Allocation

After candidate tickets are ranked by ticket EV and hit probability:

- balanced allocation buys more issue-win stability;
- tail allocation buys convexity;
- no-fallback tail budget is preferable when tail is treated as a true
  opportunistic high-EV signal;
- fallback is preferable when the operating goal is to keep stake utilization
  stable every issue.

## Recommendation

For the next implementation step:

1. Keep `bal80_tail20_noFallback` and `bal60_tail40_noFallback` as the two
   candidate operating allocations.
2. Implement explicit `match_ev`, `outcome_ev`, `coverage_ev`, and `ticket_ev`
   columns in the selector decisions.
3. Replace fixed `market_top/q_top` protection choice with EV-ranked cover sets.
4. Keep the existing 5 singles + 2 protected portfolio constraint while testing.
5. Use K-line state only for reporting until a walk-forward rule improves both
   ROI and maxDD.

