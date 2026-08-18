# #159 Gate A — selected-baseline WOR cross-N freeze

This package is the outcome-unexposed Gate-A freeze for
`BJ-HIST-SELECTED-WOR-CROSS-N-001`. It binds the accepted #127
`ESP300_GM305_LOWP20` selector and the accepted #145 Q-informed WOR allocator
contract. The selector is applied independently of outcomes for N=2 through
N=10: a p-min candidate (`p_min <= 0.20`) is paired with the highest-E_SP
companions (`E_SP >= 3.00`), the completed identity must pass `GM_E_SP >= 3.05`,
and only the first deterministic 32 candidate ranks are searched.

The generated N=7 set is an exact identity-set reproduction of #127's accepted
target: 371 identities. The cross-N identity counts are:

| N | identities | issue numbers |
|---:|---:|---:|
| 2 | 8 | 7 |
| 3 | 52 | 36 |
| 4 | 133 | 83 |
| 5 | 240 | 119 |
| 6 | 322 | 135 |
| 7 | 371 | 140 |
| 8 | 397 | 145 |
| 9 | 388 | 142 |
| 10 | 377 | 141 |

The low-N counts are intentionally sparse: the inherited candidate and
companion floors are not relaxed merely to fill a curve. All 2,659 native
pools and 348 issue instances remain in the denominator, with explicit
`NO_BET_NO_IDENTITY` participation rows where no identity passes.

For each identity, Gate B will apply `Q_INFORMED_WOR_DISTINCT` using the
normalized outcome-unexposed `q=p_cal×predicted_SP` vector, M={32,64,128}, and
seeds {137001,137002,137003}. The exact selected-match pipe string is the
identity signature; each N uses a `3^N` ticket space and an independent ¥2
ticket. Tax is not calculated here; when authorized, each winning ticket is a
separate tax unit and no issue/policy pooling is permitted.

Gate A reads no result code, score, final SP, payout, tax, ROI, or settlement
field. The immutable package is
`results/bj159_gate_a_preoutcome_v1` (manifest is recorded in the PI review
request). Gate B is not run or authorized by this package.
