# #159 Gate B — selected-baseline WOR cross-N settlement

Gate-A v2r1 was merged by PI at `cc05012a737cc34e4897eef7619b60e492f2f059`.
This one-shot Gate-B package settles only that immutable complete-issue
selection surface against the accepted trusted outcome join.

## Binding and accounting

- Gate-A manifest: `a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325`
- Gate-B outcome manifest: `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc`
- canonical outcome payload: `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`
- replacement package: `results/bj159_gate_b_outcome_settlement_v2`
- package manifest: `98932f8c5a24937db9a948377bfb6cc16c61803b4860b7dbc7fed1c83d5388f5`
- content identity: `eef1faf47766da52c29fe501e745c90b66c75d6defd239093500f49dd0ac4fd0`

Nominal `M={32,64,128}` is preserved as a reporting label. Every actual draw
and stake uses `effective_M=min(nominal_M,3^N)`. The 21 saturated plan cells
(N=2 all M, N=3 all M, N=4/M=128, across three seeds) are one full-space
allocation per identity/seed/effective-M, not additional WR tickets. The
settlement package contains 63,180 identity rows, 28,188 issue rows, and all
81 ALL N×M×seed surface rows; the complete numeric table is in `report.md`
and `surface_summary.csv`.

Each independent winning ¥2 ticket is its own tax unit: 20% applies only when
that ticket's gross is at least ¥10,000. No issue-level or policy-level tax
pooling is used. Pre-tax `no_tax_roi` is primary; tax-adjusted ROI is secondary.

## Settlement result

There are 56,988 settled identity rows and 6,192 rows with an unavailable
canonical outcome leg, which remain fail-closed and carry zero executed stake.
The M=64 seed-mean descriptive curve is:

| N | no-tax ROI | tax ROI | coverage | mean stake (¥) |
|---:|---:|---:|---:|---:|
| 2 | -0.319760 | -0.319760 | 1.000000 | 666 |
| 3 | -0.290905 | -0.290905 | 1.000000 | 17,604 |
| 4 | -0.250022 | -0.250022 | 0.782093 | 79,104 |
| 5 | -0.246416 | -0.246416 | 0.260256 | 99,840 |
| 6 | -0.224595 | -0.224595 | 0.083333 | 109,056 |
| 7 | -0.222262 | -0.263142 | 0.023599 | 115,712 |
| 8 | -0.110475 | -0.255208 | 0.007231 | 118,016 |
| 9 | 0.719670 | 0.375736 | 0.001769 | 120,576 |
| 10 | -0.910543 | -0.923506 | 0.000701 | 121,728 |

The positive N=9 cells are a descriptive same-window historical cluster with
very low coverage and concentrated outcomes; the package decision is
`POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV`, with `promotion_authorized=false`.
No purchase, production, betting, or strategy-promotion authority follows.
The package also includes YEAR/FOLD/LOYO summaries, issue bootstrap, matched
common-support N-vs-N7 deltas, overlap, largest-issue exclusion, and readable
ROI/coverage/stake charts.

Focused Gate-B tests: 4 passed. The package-local `settlement_runner.py`
fresh replay reproduced the exact manifest byte-for-byte without `/tmp`.
