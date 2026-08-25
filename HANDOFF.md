# #396 Engineer handoff — amendment v2

[SESSION] 20260825_201205_64d7db

## Current HEAD

`engineer/bj396-2025-settlement`; this delivery extends commit `d9aaa10` and
keeps its 57 frozen 500.com pages and v1 manifest as `baseline_manifest_v1.json`
in the new v2 package.

## Completed

- Claimed #396 from Ready and applied the PI's amendment-v2 source-lane work.
- Re-read the accessible `beidan_live.settlements` lane read-only: it contains
  no 2025 issue rows. The local `official_500_settlements` name is an importer
  materialization, not a second accessible raw source.
- Captured and SHA-256-bound 16 Nowscore issue snapshots for all 23 former
  unresolved issue/slot keys, then replayed their provider status/result rows.
- Published v2 with 16,117 canonical native-SP records and an exhaustive,
  admissible 120-row residual disposition ledger: 102 postponed/cancelled and
  18 official-no-SP.
- Added semantic replay coverage for Nowscore source trace and v2 inclusion
  labels, in addition to the original settlement/result/SP/raw-ledger tamper
  tests.

## Key decisions

- A Nowscore final score is not a Beijing winning SP. Finished Nowscore rows are
  `NEVER_SETTLED_OFFICIAL_NO_SP` when the frozen official 500 row has `SP=-`.
- Exact Nowscore issue/slot rows directly marked `取消` are
  `POSTPONED_OR_CANCELLED`; the 97 v1 `改期` rows keep the same disposition.
- No strategy execution is authorized. The v2 READY decision only releases the
  complete, source-bound data denominator for #394's independently gated replay.

## Verification

- `PYTHONPATH=. ... python scripts/verify_bj396_2025_settlement_package.py --package-root results/bj396_2025_settlement_backfill_v2`
  → PASS; `READY_FOR_394_FULL_2025_REPLAY`; 57 issues / 16,117 canonical / 120 exclusions.
- `PYTHONPATH=. ... python -m pytest -q tests/test_bj396_settlement.py` → 10 passed.
- A re-manifested mutation of v2 residual disposition was rejected with
  `v2 residual disposition differs from source evidence`.

## Next step

EV should independently run the verifier and mutation suite from a fresh
checkout, then assess whether the v2 exclusion treatment meets the frozen
contract before PI review. The package is at
`results/bj396_2025_settlement_backfill_v2/`; the concise report is
`docs/research/396_bj_data_2025_settlement_backfill_v2.md`.
