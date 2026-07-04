# Recent 2023-2025 N3/N4 Combo Anatomy

## Question

How did N3 and N4 behave in 2023-2025, and what kind of winning combinations appeared?

Input:

- `results/binary_ev_pool_n_sweep_20260628/binary_ev_pool_n_sweep_budget_tickets.csv`
- `results/binary_ev_pool_n_sweep_20260628/binary_ev_pool_n_sweep_summary.csv`

All rows are same-budget replays at 256 units per issue.

## Recent Strategy Results

### N3

| strategy | recent profit | recent ROI | issue win rate | non-full-loss |
| --- | ---: | ---: | ---: | ---: |
| `n3 local60 t180 high70 low1_25 low2_5` | -6,362.5 | -19.3% | 34.1% | 83.6% |
| `n3 local60 t180 high80 low1_20` | -6,888.3 | -20.9% | 30.5% | 84.4% |
| `n3 local60 t240 high80 low1_20` | -7,264.2 | -22.0% | 32.7% | 87.4% |
| `n3 absq20 t180 high100` | -7,863.2 | -23.8% | 33.4% | 87.5% |

N3 had high ticket hit rate, around 7.4%-7.5%, but the median winning ticket unit payout was only about 9-9.5.  That payout was not enough to overcome the many small losses.

### N4

| strategy | recent profit | recent ROI | issue win rate | non-full-loss |
| --- | ---: | ---: | ---: | ---: |
| `n4 local60 t240 high100` | -5,181.1 | -15.7% | 26.3% | 61.5% |
| `n4 local60 t180 high100` | -6,357.7 | -19.3% | 24.4% | 55.1% |
| `n4 local60 t120 high100` | -6,563.6 | -19.9% | 23.4% | 48.4% |
| `n4 absq20 t180 high100` | -7,322.5 | -22.2% | 25.1% | 55.9% |

N4 had lower hit rate, around 3.2%-3.3%, but the median winning ticket unit payout rose to about 21-22.  This is closer to usable convexity than N3, but still did not turn positive in 2023-2025.

## Winning Shape

### N3 winners

Best recent N3 arm: `n3 local60 t180 high70 low1_25 low2_5`.

Winning ticket outcome composition:

| composition | count |
| --- | ---: |
| `0 x 3` | 1,318 |
| `0 x 2 + 3 x 1` | 325 |
| `0 x 1 + 3 x 2` | 63 |
| `0 x 2 + draw x 1` | 24 |
| `0 x 1 + 3 x 1 + draw x 1` | 6 |

Winning ticket handicap composition:

| composition | count |
| --- | ---: |
| all 3 legs negative handicap | 1,339 |
| 2 negative + 1 positive | 333 |
| 1 negative + 2 positive | 64 |

The N3 winners are overwhelmingly `negative handicap + outcome 0`.  Draws appeared, but almost never as the core winning shape.

Top N3 profitable issues:

| issue | year | arm | issue profit | notes |
| --- | ---: | --- | ---: | --- |
| `24121` | 2024 | local60 t180 high70/low | 890.7 | mostly `0 x 3`, all negative handicap |
| `24065` | 2024 | local60 t180 high80/low | 795.3 | mix of `0 x 3` and `0 x 2 + 3` |
| `23094` | 2023 | local60 t180 high80/low | 770.4 | almost pure `0 x 3` |
| `24024` | 2024 | local60/abs high100 | 753.6 | pure `0 x 3`, all negative handicap |

Even the top N3 issue wins were only around 700-900 units under a 256-unit issue budget.  N3 is better for reducing dead tickets than for creating enough positive EV.

### N4 winners

Best recent N4 arm: `n4 local60 t240 high100`.

Winning ticket outcome composition:

| composition | count |
| --- | ---: |
| `0 x 4` | 811 |
| `0 x 3 + 3 x 1` | 161 |
| `0 x 2 + 3 x 2` | 42 |
| `0 x 1 + 3 x 3` | 10 |
| `0 x 3 + draw x 1` | 1 |

Winning ticket handicap composition:

| composition | count |
| --- | ---: |
| all 4 legs negative handicap | 812 |
| 3 negative + 1 positive | 161 |
| 2 negative + 2 positive | 42 |
| 1 negative + 3 positive | 10 |

Top N4 profitable issues:

| issue | year | arm | issue profit | notes |
| --- | ---: | --- | ---: | --- |
| `23011` | 2023 | local60 t240 | 2,564.6 | same directional cluster as N7/N5 big winner |
| `24065` | 2024 | local60 t120/t180/t240 | 1,653-1,860 | N4 captured the N5-positive cluster |
| `24121` | 2024 | local60/abs t120 | 1,669.5 | pure `0 x 4`, all negative handicap |
| `23094` | 2023 | local60/abs t120 | 1,661.0 | pure `0 x 4` |
| `24024` | 2024 | local60/abs t120 | 1,620.4 | pure `0 x 4` |

N4 is more interesting than N3 because it keeps some payout convexity while still hitting more often than N5/N7.  But 2023-2025 still shows negative ROI.

## Read

1. N3 is not a good standalone profit engine in this recent window.

It improves experience metrics, but winning payouts are too small.  Its role is closer to "anti-dead-ticket smoothing" than EV generation.

2. N4 is the transition zone.

It is materially better than N3 on payout convexity and had stronger profitable issues, but still not enough to be standalone-positive in 2023-2025.

3. The same directional pattern repeats across N3/N4/N5/N7:

`negative handicap + outcome 0`, with occasional `positive handicap + outcome 3`.

4. Draws did not drive recent profits in these binary high-EV arms.

This does not prove draws are never useful, but it argues against adding draw coverage indiscriminately in the main EV sleeve.

## Strategy Implication

For the current framework:

- N3: use only as a small smoothing sleeve or when the goal is explicitly fewer dead tickets.
- N4: worth testing as a conditional sleeve when the issue has a strong directional cluster but N5/N7 convexity looks too fragile.
- N5/N7: remain the main convexity engines.
- Selector feature to add: directional cluster score, especially concentration of `negative handicap + 0` and symmetric `positive handicap + 3`.

