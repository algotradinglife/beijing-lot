# #148 Gate A — dense N7 M-grid common-support freeze

Status: outcome-unexposed Gate A; settlement is not run or authorized.

The immutable package is `results/bj148_gate_a_preoutcome_v1` with
`SHA256SUMS.json` SHA-256
`fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6`.

## Fixed source boundary

The freeze joins only two accepted outcome-unexposed packages:

| Source | Exact manifest | Contribution |
| --- | --- | --- |
| #137 Gate A v2 | `0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df` | 348 complete `NO_GATE/K_ALL` issue/fold rows, including five explicit no-bet rows |
| #133 Gate A v1 | `1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79` | inherited rank-32 candidate identities and their frozen calibrated `Q_WEIGHT` role vectors |

For each of the 343 available issue/fold rows, every inherited common-support
identity is retained: 8,550 identities and 59,850 role rows in total. There
is no K/allocator selection or per-issue stake cap. The five source no-bet
rows are retained at every M point with zero planned draws and stake.

## Frozen sampling surface

The dense M grid has 58 points:

- `16..512` in steps of 16;
- `576..1024` in steps of 64;
- `1088..2112` in steps of 64;
- `2187`, the exact FULL enumeration control.

For every non-FULL M point and issue/fold, the plan freezes all three seeds
`133001`, `133002`, and `133003` for both:

- `Q_INFORMED_WR_DUPLICATE_STAKE` — primary natural baseline. Each independent draw is a separate ¥2 ticket, including exact duplicate code vectors.
- `Q_INFORMED_WOR_DISTINCT` — sensitivity only, with distinct draws within an identity.

`M=2187` is an exact all-ticket control, not a with-replacement draw. The
result is 119,364 deterministic replay-plan rows; ticket draws and settlement
remain unavailable until a Gate-B authorization.

## Gate-B preregistration

If authorized, report the full WR M curve before interpreting any candidate
interval. Required outputs are pre-tax ROI (primary), tax-adjusted ROI
(reference), complete-issue hit and ticket coverage, issue-stake distribution,
total stake/capital utilization, duplicate/unique coverage, deltas from FULL,
and YEAR/FOLD/LOYO plus issue bootstrap views. WOR remains a sensitivity.

No individual seed or M point can nominate a policy. Any apparent positive
region needs a separate strict independent EV review and later validation;
this historical work does not authorize purchasing, production, or betting.

## Integrity checks

- `pytest -q tests/scripts/test_freeze_bj148_dense_m_grid_gate_a.py` → `4 passed`.
- A fresh replay written beneath `.scratch/bj148-replay/` produced the same
  payload manifest byte-for-byte.
- The runner stages alongside its requested output and never uses `/tmp`.
