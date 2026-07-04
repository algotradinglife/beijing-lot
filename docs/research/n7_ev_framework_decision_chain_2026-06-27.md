# N=7 EV framework decision chain

Date: 2026-06-27

## Purpose

This note records the first explicit EV-framework selector and the decision
chain that came out of the data feedback.

The working framing is:

1. Filter out matches with insufficient trade value.
2. Within tradable matches, estimate each result's value as probability times
   expected SP.
3. Build N=7 tickets from the best result legs.
4. Add extra coverage only when the marginal hit-rate gain justifies the
   stake-normalized EV haircut.

This is intentionally different from fixed "two protected legs per ticket"
logic. The decision chain is now an output artifact, not only a prose summary.

## Implementation

Script:

- `scripts/evaluate_n7_ev_framework_selector.py`

Primary outputs per run:

- `ev_framework_summary.csv`
- `ev_framework_recent_2023_2025_summary.csv`
- `ev_framework_ex_best_issue_summary.csv`
- `ev_framework_annual_summary.csv`
- `ev_framework_decision_chain.csv`
- `ev_framework_decisions.csv`
- `ev_framework_outcomes.csv`
- `ev_framework_coverages.csv`
- `ev_framework_report.md`

The EV proxy uses:

- `market_p = 1 / snapshot_odds`
- `p_hat = clamp(q * market_p, 0.001, 0.98)`
- `outcome_value = p_hat * estimated_sp`
- `outcome_ev_n7 = outcome_value / break_even_factor(7) - 1`
- `coverage_score = sum(p_hat * estimated_sp for covered outcomes) / cover_count`
- `coverage_ev_n7 = coverage_score / break_even_factor(7) - 1`

Settlement still uses realized official winning SP. Selection uses the 1h
snapshot by default.

## Commands

Compile check:

```bash
python3 -m py_compile scripts/evaluate_n7_ev_framework_selector.py
```

Named high-SP depth runs:

```bash
python3 scripts/evaluate_n7_ev_framework_selector.py \
  --min-year 2014 \
  --train-issues 24 \
  --snapshot 1h \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --min-single-odds 4 \
  --min-match-score-ratios 0.95 \
  --protection-score-floor-ratios 0.85 \
  --target-protected-per-ticket 0 \
  --output-dir results/n7_ev_framework_selector_2014_1h_minodds4_7s0p_named
```

```bash
python3 scripts/evaluate_n7_ev_framework_selector.py \
  --min-year 2014 \
  --train-issues 24 \
  --snapshot 1h \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --min-single-odds 4 \
  --min-match-score-ratios 0.95 \
  --protection-score-floor-ratios 0.8 \
  --target-protected-per-ticket 1 \
  --output-dir results/n7_ev_framework_selector_2014_1h_minodds4_6s1p_named
```

```bash
python3 scripts/evaluate_n7_ev_framework_selector.py \
  --min-year 2014 \
  --train-issues 24 \
  --snapshot 1h \
  --max-tickets-per-issue 20 \
  --issue-budget-units 256 \
  --min-single-odds 4 \
  --min-match-score-ratios 0.95 \
  --protection-score-floor-ratios 0.8 \
  --target-protected-per-ticket 2 \
  --output-dir results/n7_ev_framework_selector_2014_1h_minodds4_5s2p_named
```

## Same-Budget Results

All rows below use 256 units per active issue.

| depth | strategy | issues | tickets | hit_rate | issue_win_rate | profit | ROI | best_share | maxDD | recent_2023_2025_profit | recent_2023_2025_ROI | ex_best_ROI | verdict |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 7s0p | `ev_m0p95_p0p85_full_7s0p` | 669 | 12,946 | 0.50% | 7.03% | 71,244 | 41.60% | 42.60% | -85.90% | 17,945 | 54.34% | 23.88% | pass watchlist |
| 6s1p | `ev_m0p95_p0p8_full_6s1p` | 534 | 10,513 | 0.50% | 7.30% | 24,804 | 18.14% | 71.72% | -105.32% | 9,674 | 30.23% | 5.13% | fail concentrated |
| 5s2p | `ev_m0p95_p0p8_full_5s2p` | 454 | 8,958 | 0.81% | 11.89% | 35,128 | 30.22% | 43.46% | -38.72% | -1,061 | -3.54% | 17.09% | pass watchlist |

## Decision Chain Feedback

| depth | match_filter_pass_rate | avg_best_single_ev_n7 | avg_match_ev_n7 | avg_chosen_ev_n7 | protected_candidate_rate | tickets | ticket_double_legs | ticket_full_legs | portfolio_ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 7s0p | 35.32% | 1.2622 | 1.2739 | 1.2664 | 2.09% | 12,946 | 0 | 0 | 41.60% |
| 6s1p | 35.32% | 1.2622 | 1.2739 | 1.2495 | 7.60% | 10,513 | 10,509 | 4 | 18.14% |
| 5s2p | 35.32% | 1.2622 | 1.2739 | 1.2495 | 7.60% | 8,958 | 17,907 | 9 | 30.22% |

Interpretation:

- The high-SP EV filter is meaningful. It passes 35.3% of base matches and
  gives high average single-leg N=7 EV proxy.
- Forced protection is not yet justified. `7s0p` has the best full-history ROI,
  best recent ROI, and best ex-best ROI.
- `5s2p` improves issue win rate and max drawdown, but it failed the recent
  2023-2025 slice. This is not enough to make it the main selector.
- `6s1p` is the weakest of the three because the largest issue explains too
  much of the profit and ex-best ROI falls to 5.1%.
- The current data supports "optional coverage depth" rather than "fixed
  protection quota".

## Annual Notes

`7s0p` annual ROI:

| year | issues | profit | ROI |
|---:|---:|---:|---:|
| 2014 | 116 | 19,792 | 66.65% |
| 2015 | 58 | 2,246 | 15.13% |
| 2016 | 53 | 19,718 | 145.32% |
| 2017 | 47 | -435 | -3.61% |
| 2018 | 54 | 19,400 | 140.33% |
| 2019 | 55 | -7,079 | -50.28% |
| 2020 | 42 | 11,452 | 106.51% |
| 2021 | 58 | 2,797 | 18.84% |
| 2022 | 57 | -14,592 | -100.00% |
| 2023 | 55 | 18,956 | 134.63% |
| 2024 | 59 | -10,072 | -66.69% |
| 2025 | 15 | 9,061 | 235.97% |

The yearly profile is still lottery-like. Removing the best issue leaves ROI
positive, but 2022 and 2024 are hard failure years. This keeps `7s0p` in
watchlist status rather than production status.

## Decisions

1. Keep the EV framework as the main organizing abstraction.
2. Treat `7s0p` as the current best EV-framework branch, not because it is
   "single only" philosophically, but because the current protection rule
   fails to pay for itself.
3. Do not use a fixed two-protected-leg quota as the default. The historical
   result says protection must be conditional.
4. Preserve the decision-chain CSV for every future run. A strategy is not
   accepted from ROI alone; it must explain which stage created the gain or
   damage.

## Next Tests

1. Replace fixed `target_protected_per_ticket` with marginal EV depth:
   start from the best single, then add a second or third result only if the
   incremental hit probability compensates for the coverage score haircut.
2. Add SP-drift into `estimated_sp` before computing outcome and coverage EV.
   This should be a multiplier by outcome/state, not a single global correction.
3. Add confidence as an uncertainty term for depth. High EV plus low confidence
   may justify a second result; high EV plus high confidence should usually stay
   single.
4. Audit 2022 and 2024 as negative regimes. The current K-line monitoring says
   drawdown state is useful for monitoring, but it has not yet become a selector.
5. Keep the 2023-2025 slice and ex-best issue ROI as mandatory gates. Full
   history ROI alone is not enough.

## Current Best Interpretation

The best current EV-framework result is not "buy more protection". It is:

- filter to high expected value matches,
- use high-SP single outcomes as the core exposure,
- add protection only when marginal EV says the dead-leg reduction is worth the
  extra capital.

This is consistent with the broader lottery objective: normal periods may be
thin or negative, but the strategy needs enough positive EV after removing the
largest win to justify waiting for occasional large payouts.
