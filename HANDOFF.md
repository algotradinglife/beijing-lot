# #396 Engineer handoff

[SESSION] 20260825_201205_64d7db

## Current HEAD

Committed delivery on `engineer/bj396-2025-settlement`, rooted at `origin/main`.
Use the current HEAD as the immutable delivery reference.

## Completed

- Frozen and SHA-256-receipted all 57 requested 2025 500.com pages.
- Produced `results/bj396_2025_settlement_backfill_v1` with 16,117 native
  settlement rows and an exhaustive 120-row exclusion ledger.
- Added an offline builder, source-bound verifier, executable evidence notebook,
  and adversarial tamper tests.
- Verified: `7 passed`; package verifier returns PASS with a BLOCKED disposition.

## Key decisions

- A raw page plus terminal receipt is the primary settlement evidence. The
  legacy XLSM is crosscheck-only and ends at 25042; BJ268 supplies quote/identity
  evidence but no native winning SP.
- `winning_sp=1.0` is accepted as a source-published void/refund settlement even
  when its listed 3/1/0 conflicts with the final score; it is labelled
  `VOID_REFUND_NATIVE_SP_1`, never score-inferred.
- Any row without a published native result/SP is withheld from the canonical
  table. 97 have explicit `改期`; 23 have no direct non-settlement marker and
  keep the issue blocked.

## Known blocker / next step

Find an independently authoritative settlement source for the 23 rows listed in
`results/bj396_2025_settlement_backfill_v1/exclusion_ledger.csv` with reason
`UNRESOLVED_NATIVE_SETTLEMENT_ABSENT_ON_500_PAGE`, then rerun the package build
and verifier. Do not turn these rows into voids, outcomes, or SP proxies without
an explicit PI contract amendment.
