# Draw Odds Sensitivity

Date: 2026-06-27

## Question

There is a claim that draw odds are more sensitive to odds movement. Test this as
a separate research topic before wiring it into N=7 selection or protection.

## Implementation

Script:

```bash
python3 scripts/analyze_draw_odds_sensitivity.py \
  --min-year 2014 \
  --output-dir results/draw_odds_sensitivity_2014
```

Data:

- Source: `outcome_features`.
- Outcomes: single `3/1/0` only.
- Settlement: trusted Beidan settlement rows only.
- Years: 2014+.
- Windows:
  - `10h_to_1h`: observable before a 1h decision.
  - `1h_to_final`: closing drift, not observable at 1h.
  - `10h_to_final`: total pre-close drift.

Caveat: `euro_*_odds` are European 1X2 proxy odds. For non-zero Beidan
handicap, Beidan draw means handicap draw, so this first pass is not a direct
handicap-draw odds study.

## Main Finding

The volatility version of the claim is not supported. In this data, draw odds
move less than home/away odds.

Draw vs side average:

| Segment | Window | Draw / Side Mean Abs Move | Draw / Side P90 Abs Move |
|---|---:|---:|---:|
| all | 10h->1h | 0.496 | 0.496 |
| all | 1h->final | 0.453 | 0.448 |
| all | 10h->final | 0.482 | 0.493 |
| 2023-2025 | 10h->1h | 0.504 | 0.494 |
| 2023-2025 | 1h->final | 0.451 | 0.450 |
| 2023-2025 | 10h->final | 0.486 | 0.493 |

So draw odds are roughly half as volatile as side odds in this proxy.

## Action Summary

All years, `10h->1h`:

| Action | Hit | Mean Abs Move | P90 Abs Move | Abs Move >10% | q vs Current P | Hit SP Mult |
|---|---:|---:|---:|---:|---:|---:|
| `3` home | 37.10% | 3.67% | 8.63% | 8.17% | 0.855 | 1.288 |
| `1` draw | 27.25% | 2.10% | 4.92% | 2.38% | 1.045 | 1.071 |
| `0` away | 35.64% | 4.79% | 11.23% | 13.72% | 1.168 | 0.953 |

Recent 2023-2025, `10h->1h`:

| Action | Hit | Mean Abs Move | P90 Abs Move | Abs Move >10% | q vs Current P | Hit SP Mult |
|---|---:|---:|---:|---:|---:|---:|
| `3` home | 37.76% | 3.90% | 9.14% | 9.14% | 0.872 | 1.249 |
| `1` draw | 27.51% | 2.23% | 5.11% | 2.40% | 1.073 | 1.055 |
| `0` away | 34.72% | 4.96% | 11.57% | 14.54% | 1.119 | 0.975 |

Draw does show a positive q/value signal relative to current market probability,
especially recently, but that is not because draw odds move more.

## Draw Move Buckets

Recent 2023-2025, draw `10h->1h`:

| Move Bucket | n | Hit | q vs Current P | Hit SP Mult | EV after 65% |
|---|---:|---:|---:|---:|---:|
| odds down >=15% | 99 | 23.23% | 1.213 | 0.861 | -37.35% |
| odds down 5-15% | 1698 | 25.80% | 1.065 | 1.022 | -34.76% |
| flat +/-5% | 32524 | 27.71% | 1.061 | 1.068 | -32.12% |
| odds up 5-15% | 1992 | 26.66% | 1.310 | 0.884 | -30.27% |
| odds up >=15% | 194 | 20.10% | 1.269 | 0.744 | -43.81% |

Interpretation:

- Large draw odds moves are rare.
- Flat draw odds are the dominant population and carry most usable volume.
- Large odds-up draw moves mechanically create higher `q_vs_current_p`, but
  realized hit rate and hit SP multiplier deteriorate.
- Large odds-down draw moves do not clearly improve value either.

## Strategy Implication

Do not turn "draw odds moved a lot" into a direct buy signal.

Better use:

- Draw value may exist as a structural q/pocket feature.
- Draw odds stability may be a quality filter.
- If draw is selected as protection, avoid relying on large positive drift as a
  pure upside signal; it may indicate worse result confidence and poorer
  realized SP multiplier.

For the current strategy framework, this suggests:

```text
draw_protection_candidate
  requires: match has value
  prefers: stable draw odds, q/confidence support, line-gap support
  avoids: large draw odds spike unless compensated by another strong thesis
```

## Next Research

1. Fit draw/non-draw models with and without odds-move features; compare draw
   AUC/logloss/lift. This tests predictive sensitivity rather than volatility.
2. Re-run with Asian handicap and Beidan integer line gap, because handicap draw
   is not the same as European 1X2 draw.
3. Test whether draw odds stability improves the 5单2保护 selector as a depth
   gate.

## Outputs

- `results/draw_odds_sensitivity_2014/draw_odds_sensitivity_report.md`
- `results/draw_odds_sensitivity_2014/odds_sensitivity_action_summary.csv`
- `results/draw_odds_sensitivity_2014/odds_sensitivity_draw_vs_side_contrast.csv`
- `results/draw_odds_sensitivity_2014/odds_sensitivity_move_bucket.csv`
- `results/draw_odds_sensitivity_2014/odds_sensitivity_odds_move_bucket.csv`
- `results/draw_odds_sensitivity_2014/odds_sensitivity_annual_summary.csv`
- `scripts/analyze_draw_odds_sensitivity.py`
