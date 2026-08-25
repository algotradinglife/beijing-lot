# #396 Engineer handoff — amendment v2 semantic reconciliation

[SESSION] 20260825_213034_ce8e56

## Current HEAD

`engineer/bj396-2025-settlement`; this handoff is included in the current commit
(`git rev-parse HEAD`). Its delivery parent is
`6773fd6242b8479265e77c7c693eba7bbdecea62`, which follows
`b6ba4afff04d27e14e5d866d0ae557fbd6c436a1` and preserves the v1 package / 57
frozen 500.com pages byte-for-byte as the v2 baseline receipt.

## Completed

- Applied the PI's two narrow rework requests without changing canonical settlement values, residual classifications, Nowscore pages, or strategy authorization.
- Regenerated the v2 `issue_ledger.csv`: all 57 calendar issues are `downstream_eligible=True`. The 36 issues with admissibly excluded fixtures are `INCLUDED_WITH_ADMISSIBLE_FIXTURE_EXCLUSIONS`; the 120 fixture-level exclusions remain only in `residual_disposition_v2.csv`.
- Replaced the misleading v2 decision field `excluded_issue_count` with `downstream_eligible_issue_count=57` and `issues_with_admissible_fixture_exclusions=36`.
- Added the verifier-bound `source_probe_receipts_v2.csv`: five declared lanes, paths/identities, observed timestamps, source hashes or pinned per-page evidence, exact-23-key hit counts, native-SP capability, admissible-use conclusion, and source result.
- Re-ran read-only exact `(issue, match_idx)` probes: `beidan_live.settlements=0/23`; local `official_500_settlements=0/23`; Nowscore=23/23 classification probes; the authoritative 500 baseline has all 23 rows but `SP=-`.
- Added tamper coverage for a re-manifested source-probe receipt mutation, a
  raw-500-acquisition-receipt anchor rewrite, and v2 issue eligibility semantics.
  The executed notebook now reports source-lane coverage and asserts all 57
  issues eligible.

## Key decisions

- Nowscore remains residual-classification evidence only. Its final score does not become a Beijing winning SP, payout, canonical settlement, or strategy input.
- The local SQLite/XLSM records are explicitly audit receipts and not promoted to an independent source authority. The `official_500_settlements` materialization is a non-independent derived duplicate of the 500 lane.
- `READY_FOR_394_FULL_2025_REPLAY` authorizes only the complete frozen data denominator. `strategy_execution_authorized=false` remains immutable.

## Verification

- `PYTHONPATH=. /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m pytest -q tests/test_bj396_settlement.py` → `18 passed`.
- `PYTHONPATH=. /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/verify_bj396_2025_settlement_package.py --package-root results/bj396_2025_settlement_backfill_v2` → `PASS`, 57 issues / 16,117 settlements / 120 excluded fixtures.
- `scripts/render_bj396_settlement_notebook_v2.py` executed cleanly and wrote `notebooks/bj396_settlement_recovery_v2.ipynb`.

## Next step

EV: use a fresh checkout, rerun the verifier and `tests/test_bj396_settlement.py`, then attack (1) `winning_sp`/result fields, (2) a ledger row while retaining count totals, (3) source-probe receipt contents plus MANIFEST rewrite, and (4) Nowscore source trace / future-information labels. Confirm the 57 issue-level eligibility semantics never cause #394 to discard a whole issue because of an admissibly excluded fixture.
