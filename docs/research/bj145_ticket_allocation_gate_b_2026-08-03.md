# #145 Gate B — ticket-allocation outcome settlement

## Immutable binding

Gate B consumes only the accepted Gate-A freeze and the canonical trusted
outcome/final-SP join. The published package is
`results/bj145_gate_b_outcome_settlement_v1` with `SHA256SUMS.json` SHA-256
`818bbf1c8c547478e158e127ad267e365705e54df9227e0c1cde180a31640ec2`.

- Gate-A manifest: `da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c`
- canonical outcome manifest: `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc`
- canonical outcome payload: `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`
- accepted source chain: #137, #148, #151, and #154 manifests are retained in `settlement_card.json` as transitive Gate-A inputs.

The settlement has 1,006,416 issue/configuration rows across 2,892 frozen
configurations, six weight sources, both authorized arms, the full M grid
`16..256` plus `512, 1024, 1458, 2187`, all frozen caps/seeds, YEAR/FOLD/LOYO
and ALL scopes. The outcome-code frequency table is stored as deterministic
`outcome_code_frequency.csv.gz` to keep the artifact portable.

## Accounting and integrity

The primary accounting field is pre-tax `no_tax_roi`, including the 0.65
Beijing Single Match factor. Tax is secondary and is computed per individual
winning ticket: 20% applies when that ticket's gross is at least ¥10,000;
there is no issue/policy pooling or aggregation. `tax_reconciliation.csv`
covers all 2,892 configurations, including configurations with no winning
ticket; all rows are `PASS`. The compressed ticket ledger contains 626,782
winning-ticket rows.

The package also contains 63,360 FULL-control deltas, 5,760 bootstrap rows,
2,880 Holm-family rows, the complete mechanism/weight surface, pairwise
mechanism and weight contrasts, and the deterministic Python/C++ allocator
sources. Focused replay checks verify the Gate-A allocator binding, golden
vectors, WR/WOR/residual/capped/FULL metric parity, row denominators, and
manifest coverage. No SQLite database is published in the package; the large
stage-local SQLite index was used only for streaming post-processing.
`mechanism_surface_median.svg` is the chart integration candidate: it plots
median pre-tax ROI by M and mechanism across frozen weight/cap/seed cells for
each arm, without selecting a winning cell.

## Descriptive result

The exact FULL controls are negative on the common settled support:

| arm | FULL pre-tax ROI | FULL tax-adjusted ROI | settled issues |
|---|---:|---:|---:|
| `PRIMARY_NO_GATE_K4` | -15.77% | -18.88% | 254 |
| `SECONDARY_ESP300_GM290_K8` | -16.12% | -18.30% | 191 |

Some same-window surfaces are positive relative to those FULL controls. For
example, the descriptive maximum is `PRIMARY_NO_GATE_K4 / Q_WEIGHT /
WOR_DISTINCT / M16 / seed 137002`: pre-tax ROI 84.76%, tax-adjusted ROI
71.15%, with a +100.53 percentage-point pre-tax delta versus FULL. The
secondary arm's corresponding maximum is 72.05% pre-tax. These are selected
cells from a large historical surface, not independent evidence; many other
cells are negative and the support is only 254 or 191 settled issue units.

The terminal decision is **`DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION`**. The
package grants no purchase, production, betting, or promotion authority.
Positive cells require strict independent-EV analysis and held-out/forward
validation before any strategy decision.
