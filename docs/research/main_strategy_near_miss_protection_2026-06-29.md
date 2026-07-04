# Main Strategy Near-Miss Protection Analysis

Date: 2026-06-29

## Scope

This analysis uses only the Beidan main strategy. The reconstructed fixed-256
main strategy is:

```text
144 units: core_base__budget256_fractional
48 units:  core_tp_only_draw_top_ev_k1__budget256_fractional
64 units:  dynamic_static_n5x90__budget256_fractional
```

The reconstruction matches `current_reference_256` except for three issues
where the N7 source components are missing and the missing allocation is
treated as cash loss. This is explicitly represented as
`missing_component_cash_loss` in the output.

Outputs:

- Ticket distance: `results/main_strategy_near_miss_20260629/near_miss_ticket_distance.csv`
- Missed legs: `results/main_strategy_near_miss_20260629/near_miss_missed_legs.csv`
- Ticket summary: `results/main_strategy_near_miss_20260629/ticket_distance_summary.csv`
- Missed-leg summary: `results/main_strategy_near_miss_20260629/missed_leg_summary.csv`
- Rule candidates: `results/main_strategy_near_miss_20260629/rule_candidate_summary.csv`
- Issue summary: `results/main_strategy_near_miss_20260629/issue_near_miss_summary.csv`

Verification:

```bash
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m py_compile scripts/analyze_main_strategy_near_miss.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/analyze_main_strategy_near_miss.py \
  --output-dir results/main_strategy_near_miss_20260629
```

## Ticket Distance

| n | bucket | tickets | stake | profit | readout |
| ---: | --- | ---: | ---: | ---: | --- |
| 7 | hit | 51 | 839 | 326274 | rare but dominates convex profit |
| 7 | miss 1 | 295 | 4485 | -4485 | direct protection candidates |
| 7 | miss 2 | 1041 | 14214 | -14214 | meaningful, but needs two-leg protection |
| 7 | miss 3 | 2112 | 28473 | -28473 | too wide for default protection |
| 7 | miss 4+ | 6280 | 79861 | -79861 | structural dead tickets |
| 5 | hit | 658 | 915 | 47735 | higher hit, much lower payout |
| 5 | miss 1 | 3926 | 4493 | -4493 | common, but rescue value is small |
| 5 | miss 2 | 10089 | 10568 | -10568 | common, still low payout |
| 5 | miss 3+ | 27255 | 26840 | -26840 | not the main convex lever |

Interpretation:

- There are real near-miss N7 tickets, especially miss-2 tickets.
- But most N7 losing stake is still miss-3 or worse. Large-scale full cover
  would spend too much to solve too few high-value misses.
- N5 near-misses are frequent, but their theoretical rescue delta is much
  smaller because the payout side is weaker.

## Issue-Level Readout

| bucket | issues | profit | full-loss issues | has N7 miss-1 | has N7 miss-2 | has N7 miss-1/2 | has N5 miss-1/2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all | 669 | 204500 | 375 | 25.9% | 66.1% | 69.2% | 99.1% |
| loss issues | 598 | -132647 | 375 | 22.6% | 64.4% | 67.4% | 99.0% |
| full-loss issues | 375 | -96000 | 375 | 12.3% | 55.7% | 57.3% | 98.4% |
| maxDD window `23013-25012` | 114 | -7511 | 67 | 21.1% | 55.3% | 61.4% | 100.0% |

Interpretation:

- The user's intuition is right: many full-loss issues are not infinitely far
  away. In full-loss issues, `57.3%` had at least one N7 ticket missing only
  one or two legs.
- The maxDD window is even more actionable: `61.4%` of issues had N7 miss-1/2.
- This supports targeted protection, but not broad protection. The protection
  must choose which one or two legs deserve extra outcomes.

## Missed Result Distribution

| actual missed result | missed legs | avg SP | readout |
| --- | ---: | ---: | --- |
| win | 77349 | 2.94 | most common missed result |
| draw | 68712 | 3.96 | slightly less common, much higher payout |
| loss | 15177 | 2.90 | much less common |

Top missed cells:

| actual | SP bucket | handicap bucket | missed legs | avg SP |
| --- | --- | --- | ---: | ---: |
| draw | 3-5 | -1 | 33524 | 3.78 |
| win | 2-3 | -1 | 28129 | 2.50 |
| win | 3-5 | -1 | 17303 | 3.58 |
| draw | 3-5 | <=-2 | 13657 | 4.01 |
| win | 2-3 | <=-2 | 10403 | 2.51 |
| win | 3-5 | <=-2 | 10240 | 3.73 |
| draw | 3-5 | +1 | 7178 | 3.79 |
| loss | 2-3 | +1 | 6622 | 2.49 |

Readout:

- The main missed outcomes are not away-loss-side protection; they are mostly
  missed home win and missed draw.
- Draw misses are especially attractive for protection because their average SP
  is materially higher.
- The strongest repeated miss pattern is draw at SP `3-5` under negative
  Beidan handicap. This matches the "strong favorite pushed by handicap, buy
  reverse/draw protection" idea.

## Rule Candidate Support

| rule | support tickets | share of losing tickets | losing stake | avg rescue delta if all missed legs covered |
| --- | ---: | ---: | ---: | ---: |
| protect draw | 40038 | 78.5% | 138889 | 299 |
| protect win | 39149 | 76.8% | 148346 | 309 |
| protect loss | 9756 | 19.1% | 14846 | 53 |
| protect high SP | 8795 | 17.2% | 36164 | 471 |
| protect 1-or-2 miss | 15351 | 30.1% | 33759 | 293 |
| linegap weak ticket | 4543 | 8.9% | 55921 | 1388 |
| LL bad ticket | 2 | ~0.0% | 19 | 486 |

Important caveats:

- `avg_rescue_delta` is an after-the-fact diagnostic. It is not a tradable
  profit estimate unless the selector can identify those legs pre-bet.
- `linegap_weak_ticket` has low support but very high rescue leverage. It is a
  strong paper direction after Asian line backfill completes.
- Current `source_ll_bad_count` barely fires in this ticket set, so LL is not a
  useful near-miss selector in the current data form.

## Existing Replay Links

The sleeve-depth v2 replay already tells how these near-miss ideas behave when
converted into spend:

| portfolio | interpretation | result |
| --- | --- | --- |
| `b320_dd32_safe80_convex19` | small targeted protection + small convex draw rescue | best small-step candidate; maxDD improves to `-14517` |
| `b384_dd32_smooth80_convex19` | current operating mix with smoothing + convex sleeve | best main balance; maxDD `-15077`, ROI `1.409` |
| `b384_dd32_smooth100` | more smoothing, less convexity | best 384 DD `-13203`, but ROI drops to `0.973` |
| convex-heavy variants | heavy rescue of rare high-payout misses | high ROI but poor absolute DD; paper only |

## Decision

Near-miss protection is worth pursuing, but it should be targeted.

Promote to next experiment:

1. Protect one or two N7 legs when the missed-side candidate is draw with SP
   `3-5`, especially under negative Beidan handicap.
2. Keep a small high-SP protection sleeve because high-SP misses are less
   frequent but high-leverage.
3. Evaluate line-gap weak tickets after Asian line backfill; this looks
   potentially high value but needs cleaner pre-bet line features.

Do not promote:

- Broad full-cover of many N7 legs. Too many losing tickets are miss-3 or
  miss-4+.
- N5-heavy rescue as the primary answer. N5 produces more near misses, but
  the payout is too low to carry the N7 drawdown problem.
- LL as a current selector, because it barely appears in this ticket set.

The next EV/depth card should use these findings as constraints: protection
depth should favor high-EV N7 tickets with one or two plausible fragile legs,
especially draw/strong-handicap reverse cases and high-SP misses.
