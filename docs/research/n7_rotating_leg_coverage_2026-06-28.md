# N7 rotating leg coverage

Date: 2026-06-28

## Question

The useful coverage unit is not necessarily "every ticket gets more outcomes".
For one issue, we can keep the same N=7 batch and allocate only a small share of
tickets to protection. Example: if an issue has 30 N7 tickets, keep most tickets
as high-EV singles, and convert only 5% / 10% / 20% of tickets into draw / alt /
full-cover hedges.

## Method

- Base production strategy: `dynamic_low5_mid7_high7x30`.
- Budget: fixed issue budget, fractional replay. Main comparison below uses
  `512` units per issue.
- Full production replay keeps non-N7 issues from the base strategy and replaces
  only N7 issues with the tested arm.
- `t30` means the same top-30 N7 tickets used by the current high-quality arm.
- `tail` protects lower-ranked tickets inside the top-30 batch, preserving the
  highest EV tickets as pure singles.
- `head` protects the highest-ranked tickets.
- `draw_k1` adds draw to one leg on each protected ticket.
- `full_k1` fully covers one leg on each protected ticket.
- `alt/uncertain_k2` protects two legs on each protected ticket using the
  alternate/uncertain leg selector.

Generated outputs:

- `results/n7_rotating_leg_coverage_t30_20260628/rotating_cover_production_budget512_summary.csv`
- `docs/research/n7_rotating_leg_coverage_selected_2026-06-28.csv`

## Selected 512-unit production results

| arm | profit | ROI | issue win | non-full-loss | max dead | max loss | max DD | ROI ex-best | recent ROI | recent ex-best |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| current main | 332999 | 0.972 | 0.120 | 0.145 | 31 | 52 | -39463 | 0.420 | 0.817 | -0.102 |
| t30 base | 332999 | 0.972 | 0.120 | 0.145 | 31 | 52 | -39463 | 0.420 | 0.817 | -0.102 |
| 5% tail draw_k1 | 364907 | 1.065 | 0.121 | 0.146 | 31 | 52 | -39882 | 0.537 | 0.738 | -0.137 |
| 20% tail draw_k1 | 362011 | 1.057 | 0.129 | 0.154 | 31 | 35 | -40581 | 0.590 | 0.809 | 0.045 |
| 5% head full_k1 | 312748 | 0.913 | 0.127 | 0.152 | 26 | 52 | -37972 | 0.407 | 0.942 | 0.107 |
| 5% head alt_k2 | 302367 | 0.883 | 0.130 | 0.157 | 26 | 52 | -36030 | 0.397 | 0.670 | -0.128 |
| 10% head uncertain_k2 | 275683 | 0.805 | 0.139 | 0.164 | 26 | 52 | -31613 | 0.371 | 0.789 | 0.083 |
| all tickets full_k2 | 87943 | 0.257 | 0.281 | 0.347 | 17 | 19 | -21516 | 0.194 | 0.464 | 0.250 |

## Interpretation

`t30 base` exactly matches current main, so this is a same-batch N7 comparison.

Small-share draw protection is promising. The best profit arm is `5% tail
draw_k1`: profit rises from `332999` to `364907`, ROI from `0.972` to `1.065`.
It does not meaningfully reduce dead streaks, so it should be treated as an EV
enhancement rather than a risk hedge.

`20% tail draw_k1` looks more balanced: profit remains higher than current
main, issue win improves from `12.0%` to `12.9%`, non-full-loss improves from
`14.5%` to `15.4%`, and max loss streak falls from `52` to `35`. The tradeoff
is a slightly worse max drawdown (`-40581` vs `-39463`).

Head-side full/alt protection is the risk-control family. `5% head full_k1`
keeps most of the current EV (`ROI 0.913`), improves max dead streak from `31`
to `26`, and improves max drawdown from `-39463` to `-37972`. `10% head
uncertain_k2` reduces max drawdown further to `-31613`, but gives up more
profit.

Protecting every ticket is too expensive as a default. `all tickets full_k2`
has the best non-full-loss and drawdown metrics, but ROI falls to `0.257`. This
is better viewed as a stress-regime / emergency arm, not the base strategy.

## Current decision

Use rotating protection as an issue-level overlay, not as same-ticket global
coverage.

Recommended next candidates:

1. `20% tail draw_k1` as the default smoothing candidate: it preserves EV and
   reduces max loss streak.
2. `5% head full_k1` as the conservative risk candidate: it improves drawdown
   and max dead streak with moderate EV cost.
3. `10% head uncertain_k2` as an aggressive risk-reduction candidate for bad
   regimes only.

Next experiment should gate between these arms using issue-level quality/K-line
state: normal regime uses `20% tail draw_k1`; after deteriorating streaks switch
part of the N7 sleeve to `5% head full_k1` or `10% head uncertain_k2`.
