# #159 Gate A v2 — selected-baseline WOR cross-N

This is the replacement outcome-unexposed Gate-A freeze for
`BJ-HIST-SELECTED-WOR-CROSS-N-001`. It binds the accepted #127
`ESP300_GM305_LOWP20` selector and the accepted #145 Q-informed WOR allocator
contract.

## Complete-issue selection boundary

The candidate and companion search is applied once to all eligible rows in a
complete `issue@fold` analysis unit. Native `pool_id` and `segment_index` are
retained only in `source_pool_ids`, `source_segment_indices`, and role-level
source fields; they are not a selection or settlement boundary. The inherited
thresholds remain unchanged: `p_min <= 0.20`, candidate ranking by
`(p_min, match_idx, match_id)`, companions ranked by descending `E_SP`, and
`GM_E_SP >= 3.05` after adding `N-1` companions with `E_SP >= 3.00`.

The complete-issue counts are:

| N | identities |
|---:|---:|
| 2 | 38 |
| 3 | 335 |
| 4 | 648 |
| 5 | 844 |
| 6 | 937 |
| 7 | 1,005 |
| 8 | 1,042 |
| 9 | 1,077 |
| 10 | 1,094 |

The explicit N=7 bridge audit reports 371 legacy #127 native-segment
identities, 1,005 corrected complete-issue identities, 6 exact intersections,
365 legacy-only identities, and 999 corrected-only identities. The old equality
claim is superseded; these values document the semantic boundary correction.

## Nominal versus effective M

The frozen nominal grid is `M={32,64,128}` with seeds
`137001,137002,137003`. For every row, `effective_M=min(nominal_M,3^N)` and
`coverage_fraction=effective_M/(3^N)`. The 21 saturated rows (N=2 all M, N=3
all M, and N=4/M=128, across three seeds) use the full ticket space and are
one actual allocation per identity/seed, not duplicate WOR allocations. Gate B
must report actual draws and stake using `effective_M` while preserving the
nominal row labels.

Gate A reads no result code, score, final SP, payout, tax, ROI, or settlement
field. The immutable replacement package is
`results/bj159_gate_a_preoutcome_v2r1` (manifest is recorded in the PI review
request). Gate B is not run or authorized until this exact package is accepted.
