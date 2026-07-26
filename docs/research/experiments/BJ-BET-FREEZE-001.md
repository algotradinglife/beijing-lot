# BJ-BET-FREEZE-001 — exact-N and correct-score freeze for 26078

Status: `segment_2_checkpoint_missed`; read-only operational evidence receipt,
not a replacement freeze.

Audit cutoff: `2026-07-26T06:26:42Z`.

## Scoped conclusion

The declared Segment 2 prospective checkpoint at
`2026-07-26T00:55:00+08:00` was not published. Its expected event ID is
`59ee53b0e67f30a98b7328f511918bbf605591b9fe6a86f088ed37dbed4b4a56`.
At the audit cutoff:

- no matching ledger record exists;
- no matching immutable package exists;
- none of the required 15 Segment 2 exact-N × budget cells exists;
- no Segment 2 correct-score paper-only companion exists; and
- no Segment 2 terminal failure receipt exists.

This is a missed/incomplete prospective checkpoint. The existing Segment 1
recovery package is a different identity and cannot substitute for it. This
audit did not regenerate, overwrite, relabel, or backfill any artifact.
Segment 3 remains independently eligible at its registered future checkpoint.

## Available pre-freeze input, not a freeze

A structured decision input was generated inside the declared legal window:

- generated at `2026-07-26T00:52:34.631275+08:00`;
- receipt semantic SHA-256:
  `b74b9296fa9d09c29438b4ebe37ab87ddf422cb0bfc138cf7f84aef83f3d482d`;
- structured CSV SHA-256:
  `7661a74b3a7de55a2fa19e87bd3a990241e145dd069ccf6fcaabcd2a904b4627`;
- 173/173 active decision rows reported complete.

The receipt was never content-bound into a Segment 2 exact-N ledger/package.
It therefore proves that an input refresh occurred, not that the prospective
freeze contract was met.

## Coordinator and retry history

Read-only service receipts show that at `00:43`, `00:48`, and `00:53` HKT the
segment scheduler targeted Segment 2, while the exact-N coordinator returned
`already_published` for event
`f2526338ac3983f347335dab552604988bada052484dbb4e141920dd714a4f21`,
identity `segment_1_recovery_1`. At `00:58` HKT, after the Segment 2 freeze,
the scheduler advanced to Segment 3 while the exact-N result still referenced
that Segment 1 recovery.

There is no Segment 2 attempt, retry, failure, or terminal receipt in the exact-N
ledger. The structured missing reason is therefore coordinator identity
selection of an already-published recovery event during the Segment 2 window,
followed by advancement past the checkpoint without a Segment 2 publication.
It is not a verifier failure on a Segment 2 package, because no such package
was created.

## Read-only API visibility

The canonical read-only API projection at the audit cutoff reports:

- Segment 1: `MISSED_FREEZE`, 0 alternatives;
- Segment 2: `pending`, 0 alternatives;
- Segment 3: `pending`, 0 alternatives;
- `segment_1_recovery_1`: `published`, 15 alternatives;
- global `exact_n_frontend_selectable=true`, derived from the recovery;
- correct-score execution, frontend selection, and ROI authority: all `false`.

The API keeps the recovery under its distinct identity and does not label it as
Segment 2. It nevertheless has a status conflict: the already-passed Segment 2
checkpoint remains `pending` rather than a durable missed/terminal state, while
the global exact-N selectable flag is true because of the older recovery.
Consumers must not treat that global flag or recovery as Segment 2 evidence.

## Existing immutable recovery package

The only authoritative exact-N ledger entry is a fail-closed recovery child of
missed Segment 1:

- identity: `segment_1_recovery_1`, parent status `MISSED_FREEZE`;
- event ID:
  `f2526338ac3983f347335dab552604988bada052484dbb4e141920dd714a4f21`;
- immutable package:
  `results/exact_n_segment_freeze/26078/segment_1_recovery_1/f2526338ac3983f347335dab552604988bada052484dbb4e141920dd714a4f21/`;
- recovery freeze: `2026-07-25T05:25:00+08:00`;
- recovery manifest semantic SHA-256:
  `a2772130c3ec814a90a43a9e80051c0a3953ad153d135c274cbbe35dbcf077f4`;
- artifact manifest byte SHA-256:
  `71afc2286eeeeae25ecbe7c83ef0f8ec21feb4bce1a342711f02d5aaa85dec03`;
- artifact manifest semantic SHA-256:
  `353d8e132771faf3ee7396ee65267902d556c03dc5554effc165679731c785a4`;
- package `SHA256SUMS` SHA-256:
  `712dcc0608eb6b098d30380401f25b19b47ffefab8dc03bb406804c4c9d3f981`;
- decision input manifest semantic SHA-256:
  `a221dcdb41fa3076bd4f5726193d64f0b46400096dab46ac12a34197881117a1`;
- decision input SHA-256:
  `70c3bd0815385e7ca79f2d04384e50e876a2b9da93dce25d8918c144e6eea298`;
- correct-score audit semantic SHA-256:
  `f17399d9f483de84399d1c263bfcc8c90eb13be878e0e22dcb881d45cdac005a`;
- recursive verifier: `PASS`, 15 cells, common clock/input/segment linkage.

These verified recovery alternatives are documented only to account for the
existing ledger; they are not Segment 2 evidence.

| N | Budget (yuan) | Status | Actual / unused (yuan) | Tickets | Plan ID |
|---:|---:|---|---:|---:|---|
| 3 | 512 | `FROZEN_EXACT_N_BUDGET` | 512 / 0 | 25 | `26078_segment_1_recovery_1_n3_b512_f2526338ac39` |
| 3 | 768 | `FROZEN_EXACT_N_BUDGET` | 768 / 0 | 40 | `26078_segment_1_recovery_1_n3_b768_f2526338ac39` |
| 3 | 1024 | `FROZEN_EXACT_N_BUDGET` | 1024 / 0 | 52 | `26078_segment_1_recovery_1_n3_b1024_f2526338ac39` |
| 4 | 512 | `FROZEN_EXACT_N_BUDGET` | 512 / 0 | 15 | `26078_segment_1_recovery_1_n4_b512_f2526338ac39` |
| 4 | 768 | `FROZEN_EXACT_N_BUDGET` | 768 / 0 | 19 | `26078_segment_1_recovery_1_n4_b768_f2526338ac39` |
| 4 | 1024 | `FROZEN_EXACT_N_BUDGET` | 1024 / 0 | 25 | `26078_segment_1_recovery_1_n4_b1024_f2526338ac39` |
| 5 | 512 | `FROZEN_EXACT_N_BUDGET` | 512 / 0 | 8 | `26078_segment_1_recovery_1_n5_b512_f2526338ac39` |
| 5 | 768 | `FROZEN_EXACT_N_BUDGET` | 768 / 0 | 11 | `26078_segment_1_recovery_1_n5_b768_f2526338ac39` |
| 5 | 1024 | `FROZEN_EXACT_N_BUDGET` | 1024 / 0 | 14 | `26078_segment_1_recovery_1_n5_b1024_f2526338ac39` |
| 6 | 512 | `FROZEN_EXACT_N_BUDGET` | 512 / 0 | 4 | `26078_segment_1_recovery_1_n6_b512_f2526338ac39` |
| 6 | 768 | `FROZEN_EXACT_N_BUDGET` | 768 / 0 | 6 | `26078_segment_1_recovery_1_n6_b768_f2526338ac39` |
| 6 | 1024 | `FROZEN_EXACT_N_BUDGET` | 1024 / 0 | 8 | `26078_segment_1_recovery_1_n6_b1024_f2526338ac39` |
| 7 | 512 | `FROZEN_EXACT_N_BUDGET` | 512 / 0 | 4 | `26078_segment_1_recovery_1_n7_b512_f2526338ac39` |
| 7 | 768 | `FROZEN_EXACT_N_BUDGET` | 768 / 0 | 3 | `26078_segment_1_recovery_1_n7_b768_f2526338ac39` |
| 7 | 1024 | `FROZEN_EXACT_N_BUDGET` | 1024 / 0 | 4 | `26078_segment_1_recovery_1_n7_b1024_f2526338ac39` |

The verifier proves exact requested/artifact/recommended N and exact per-ticket
leg counts for all successful recovery cells. The recovery correct-score
companion is `UNAVAILABLE_CORRECT_SCORE_PLAN`: 40/40 matches have
`no_complete_snapshot`; all three budget scenarios are
`UNAVAILABLE_SCORE_STAKING_RULE`; execution, frontend selection, and ROI
authority are all false.

No purchase record, user-specific data, executable correct-score ticket, or
unredacted source payload is included in this receipt.
