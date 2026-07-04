# Recent 2023-2025 Profitable Combo Anatomy

## Question

What kind of combinations actually made money in 2023-2025?

The focus is ticket-level anatomy, not only strategy-level ROI.  I compared:

- N7 EV framework budget tickets:
  - `ev_m0p95_p0p85_full_opt__budget256_fractional`
  - `ev_m0p95_p0p8_full_opt__budget256_fractional`
- N5 binary high-EV pool tickets:
  - `binary_n5_absq20_t120_high100__budget256_fractional`
  - `binary_n5_local60_t120_high100__budget256_fractional`
  - `binary_n5_local60_t180_high100__budget256_fractional`

## Strategy-Level Recent Result

2023-2025, same 256 units per issue:

| strategy | tickets | stake | profit | ROI | ticket hit rate | hit unit payout median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `ev_m0p95_p0p85_full_opt` N7 | 2,518 | 33,024 | 21,047.6 | 63.7% | 0.357% | 136.9 |
| `ev_m0p95_p0p8_full_opt` N7 | 2,518 | 33,024 | 533.1 | 1.6% | 0.318% | 163.3 |
| `binary_n5_local60_t180_high100` N5 | 23,046 | 33,024 | -3,363.4 | -10.2% | 1.467% | 51.2 |
| `binary_n5_local60_t120_high100` N5 | 15,366 | 33,024 | -3,606.9 | -10.9% | 1.490% | 50.6 |
| `binary_n5_absq20_t120_high100` N5 | 15,381 | 33,024 | -6,785.7 | -20.5% | 1.404% | 49.1 |

## Main Anatomy

The recent money-making tickets were not draw-heavy.  In the hit tickets inspected here, every N7/N5 winner had zero draw outcomes (`1`).

### N7 winners

`ev_m0p95_p0p85_full_opt` had 9 winning N7 tickets in 2023-2025.

Outcome composition:

| composition | count |
| --- | ---: |
| `0 x 7` | 4 |
| `0 x 6 + 3 x 1` | 2 |
| `0 x 5 + 3 x 2` | 1 |
| `0 x 4 + 3 x 3` | 1 |
| `0 x 2 + 3 x 3` | 1 |

Handicap composition:

| composition | count |
| --- | ---: |
| all 7 legs negative handicap | 4 |
| 6 negative + 1 positive | 2 |
| 5 negative + 2 positive | 1 |
| 4 negative + 3 positive | 1 |
| 2 negative + 3 positive | 1 |

The dominant pattern is therefore:

`negative handicap + outcome 0`, sometimes mixed with a few `positive handicap + outcome 3`.

This looks like a directional anti-cover / handicap-reversal cluster, not a balanced W/D/L cover.

Top recent N7 winning issues:

| issue | year | strategy profit | notes |
| --- | ---: | ---: | --- |
| `23011` | 2023 | 30,351.6 | one huge N7 hit, unit payout about 2,391 |
| `25011` | 2025 | 9,132.8 | pure `0 x 7`, all negative handicap |
| `25032` | 2025 | 3,256.6 | pure `0 x 7`, all `@-2` |
| `24015` | 2024 | 3,023.3 | mixed `0` with a few positive-handicap `3` |
| `24092` | 2024 | 2,846.4 | mixed negative `0` and positive `3` |

### N5 winners

The best N5 recent arm, `binary_n5_local60_t180_high100`, had 338 winning N5 tickets, but the arm still lost money overall in 2023-2025.

Outcome composition:

| composition | count |
| --- | ---: |
| `0 x 5` | 268 |
| `0 x 4 + 3 x 1` | 47 |
| `0 x 3 + 3 x 2` | 20 |
| `0 x 2 + 3 x 3` | 3 |

Handicap composition:

| composition | count |
| --- | ---: |
| all 5 legs negative handicap | 268 |
| 4 negative + 1 positive | 47 |
| 3 negative + 2 positive | 20 |
| 2 negative + 3 positive | 3 |

Top N5 profitable issues:

| issue | year | arm | issue profit | notes |
| --- | ---: | --- | ---: | --- |
| `23011` | 2023 | local60 t180 | 5,402.7 | same regime as N7 big winner |
| `24065` | 2024 | local60 t120 | 3,160.4 | N5-specific positive issue |
| `24121` | 2024 | abs/local t120 | 2,970.7 | N5-specific positive issue |
| `24024` | 2024 | abs/local t120 | 2,369.9 | N5-specific positive issue |
| `24031` | 2024 | abs t120 | 2,283.1 | also had N7 positive ticket |

## Candidate Pool Context

The biggest N7 winner `23011` did not require a thick candidate pool:

| issue | q20 matches | q23 matches | decision matches | top q |
| --- | ---: | ---: | ---: | ---: |
| `23011` | 27 | 4 | 32 | 4.12 |
| `25011` | 50 | 7 | 52 | 4.31 |
| `25032` | 127 | 17 | 138 | 4.69 |
| `24015` | 81 | 29 | 113 | 4.51 |
| `24031` | 84 | 25 | 131 | 4.84 |

This means candidate breadth alone is not enough.  A thin but directionally concentrated issue can still produce a large convex N7 win.

## Read

The 2023-2025 profitable shape is:

1. Mostly `0` outcomes under negative handicap.
2. No draw-heavy winning tickets in this inspected set.
3. N7 made money from a tiny number of very high unit-payout hits.
4. N5 found many more hits, but the hit payout was not enough to make the recent window positive.
5. The useful selector signal may be directional concentration: many high-EV options pointing to the same handicap-side result, especially `negative handicap + 0`, rather than just raw candidate count.

## Strategy Implication

The next selector should not simply ask "how many candidates are there?"

It should ask:

- Are high-EV candidates directionally clustered?
- Is the cluster mostly `negative handicap + 0` or its symmetric `positive handicap + 3`?
- Is there enough payout convexity to justify N7?
- If there are many such legs but N7 convexity is weak, does N5 capture enough of the same cluster with lower variance?

