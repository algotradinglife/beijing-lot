# #154 independent validation — fixed #137 WOR/M64 cluster

## Disposition

**PASS — reproduction only; strict independent EV remains required.**

This validation used a fresh authenticated detached checkout at PR #153 exact
HEAD `e7cb6ece9bbc4f2722d7eccc33419a6debc72aee`. The remote PR ref was read at
the beginning and end and remained unchanged. The author worktree and PR
source branch were not used for computation, and PR #153 was not modified.

## Immutable inputs and replay

- #151 Gate-A manifest:
  `3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6`
- #151 Gate-B manifest:
  `7b88be8af887674875f831f2da0951a1bf7664041f40c10be00d09194ce6fbe2`
- canonical #95 final-SP payload:
  `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`
- independent package manifest:
  `f81146959fd734c3d15a2579a3921b2afc86d6f633e174c8294763279f9937c5`

Both accepted #151 manifests were independently verified from their payload
hashes. Running each archived runner from the detached checkout produced a
byte-identical `SHA256SUMS.json`. The independent validator then recomputed
the candidate outcomes without importing the #151 settlement engine.

## Independent sampler and support audit

The validator independently reconstructed #137's hash sampler:

- namespace `bj137|WR` / `bj137|WOR`;
- WR draw key `seed, selected_match_ids, draw - 1`;
- WOR truth and ordinal keys `seed, selected_match_ids, truth/ordinal`;
- first eight SHA-256 bytes mapped with `(value + 0.5) / 2**64`.

The Gate-A surface contained 348 frozen issues and 1,356 fixed identities.
Requiring all four identities in an issue to have trusted canonical outcomes
left 254 complete settled issues. Missing-outcome issues were excluded from
executed settlement, not partially filled or replaced.

## Recomputed result

The independently recomputed fixed-candidate WOR/M64 pre-tax ROI is:

| Seed | ROI |
| --- | ---: |
| 137001 | +16.3755668115% |
| 137002 | +11.7735771069% |
| 137003 | +2.6680342104% |

Cross-seed mean is **+10.2723927096%**. Neighboring frozen points remain
positive in mean but decline with M: M48 `+5.3029857212%`, M80
`+4.2926037147%`, and M128 `+0.8607767181%`. The independently enumerated
matched FULL control is `-15.7696718701%` pre-tax ROI.

The result is an exact reproduction of #151's WOR surface (`0` independent /
package mismatches across 171 WOR rows), not an independent out-of-sample
performance claim. Scanning the 58-point M grid and three seeds is descriptive
multiple comparison; notably an even higher descriptive point exists at M16
for seed 137002. This reinforces that the M64 cluster cannot be promoted as a
post-outcome-selected edge.

## Robustness and risk views

At M64, the three independent issue-level bootstrap intervals (1,000
replicates) all cross zero:

| Seed | 95% bootstrap interval | Positive fraction |
| --- | ---: | ---: |
| 137001 | [-40.63%, +100.06%] | 67.5% |
| 137002 | [-33.52%, +57.07%] | 68.9% |
| 137003 | [-39.26%, +50.30%] | 53.1% |

Largest-issue exclusion changes the M64 ROI to -11.47% (seed 137001),
`+0.08%` (137002), and -9.46% (137003). The top issue's gross share is
24.23%, 10.82%, and 12.16% respectively; issue HHI is 0.0915, 0.0469, and
0.0565. YEAR/FOLD/LOYO rows are included in the package for direct inspection.

Tax was independently applied per winning ticket only: 20% iff that ticket's
gross payout is at least ¥10,000, with no issue/policy/identity pooling.

## Conclusion

The fixed #137 WOR/M64 positive cluster is reproducible under an independent
implementation and immutable-input boundary. It is not yet a strict EV:
bootstrap intervals cross zero, seed dispersion is material, the dense-M
surface is subject to multiple comparison, and the positive cluster is a
same-historical-sample reproduction. No purchase, production, betting, or
promotion authority follows. Any promotion requires a separately designed
strict independent EV and the PI's explicit decision.
