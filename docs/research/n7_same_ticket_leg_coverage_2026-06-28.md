# Same-ticket N7 leg coverage

Date: 2026-06-28

## Question

Instead of adding a separate N5 smoothing sleeve, can we keep the same N7 ticket
match sets and cover more outcomes on selected legs?

This test starts from existing current-main raw tickets and does not change the
match combination. It only changes selected leg action codes:

- `draw_k*`: add draw to non-draw legs, e.g. `3 -> 31`, `0 -> 10`.
- `alt_k*`: add the highest 1h market-probability missing outcome.
- `full_k*`: convert selected legs to full cover `310`.
- `uncertain_k*`: add the highest missing outcome on the most uncertain legs.

Coverage selection uses the 1h snapshot only. Settlement uses actual winning SP.

## Production口径

The current production candidate already uses low-quality issues as N5. To make
the comparison fair, this table keeps those low-N5 issues unchanged and applies
same-ticket leg coverage only to the N7 issues.

Budget is 512 units per issue.

| portfolio | profit | ROI | issue win | non-full-loss | small-loss | max dead streak | max loss streak | max DD | recent ex-best ROI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| base current main | 332,999 | 97.2% | 12.0% | 14.5% | 2.5% | 31 | 52 | -39,463 | -10.2% |
| draw k1 | 311,585 | 91.0% | 14.2% | 16.9% | 2.7% | 31 | 35 | -40,808 | -19.5% |
| draw k2 | 174,639 | 51.0% | 15.8% | 19.3% | 3.4% | 31 | 35 | -37,771 | -24.8% |
| full k1 | 99,976 | 29.2% | 17.6% | 20.9% | 3.3% | 26 | 32 | -25,795 | 20.2% |
| full k2 | 40,070 | 11.7% | 26.8% | 33.6% | 6.9% | 15 | 17 | -24,570 | 22.2% |
| full k3 | 25,712 | 7.5% | 31.2% | 46.9% | 15.7% | 8 | 17 | -24,049 | 8.2% |
| alt k2 | 59,022 | 17.2% | 20.0% | 24.8% | 4.8% | 18 | 19 | -23,356 | -7.0% |

## Interpretation

Same-ticket N7 coverage works mechanically, but the tradeoff is steep.

Light protection:

```text
draw k1 / draw k2
```

preserves much of the profit, but it barely changes the full-dead issue problem.
`draw k1` keeps ROI above 90%, but non-full-loss only improves from 14.5% to
16.9%, and max dead streak stays 31.

Strong protection:

```text
full k2 / full k3
```

does reduce dead tickets. `full k3` gets close to the N5 smoothing objective:

- issue win: 31.2%;
- non-full-loss: 46.9%;
- max dead streak: 8;
- max drawdown: -24,049.

But the cost is severe:

- ROI falls from 97.2% to 7.5%;
- profit falls from 332,999 to 25,712.

## Comparison to N5 smoothing sleeve

The previous best balanced smoothing candidate was:

```text
384 main + 128 N5op05
```

It produced:

- profit 261,418;
- ROI 76.3%;
- non-full-loss 45.7%;
- max dead streak 9;
- max DD -28,657.

So, for a similar non-full-loss / dead-streak profile, the N5 sleeve retains far
more EV than same-ticket full-covering N7 legs.

## Decision

Same-ticket N7 coverage should not replace the N5 smoothing sleeve.

Useful role:

```text
emergency defense / drawdown mode:
  temporarily apply full k2 or full k3 when the goal is survival rather than EV
```

Not recommended as default:

```text
always-on same-ticket full cover
```

Reason:

```text
it buys survival by giving up too much payout convexity.
```

The current better default remains:

```text
75% main N7 jackpot engine
25% N5x90 overlap_penalty=0.5 smoothing sleeve
```

## Files

- `scripts/evaluate_n7_same_ticket_leg_coverage.py`
- `results/n7_same_ticket_leg_coverage_20260628/`
- `docs/research/n7_same_ticket_leg_coverage_production_budget256_2026-06-28.csv`
- `docs/research/n7_same_ticket_leg_coverage_production_budget512_2026-06-28.csv`

