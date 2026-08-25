# #396 — 2025 Settlement Truth Recovery, amendment v2

Contract: `BJ-DATA-2025-SETTLEMENT-BACKFILL-001/v2`

## Decision

`READY_FOR_394_FULL_2025_REPLAY` — this is a data-denominator decision only.
It does not run, select, tune, rank, weight, allocate, or otherwise authorize a
strategy. `strategy_execution_authorized=false` remains bound in the package.

The v1 recovery froze 57 authoritative 500.com issue pages for the complete
2025 calendar (`25011`–`25125`) and reconstructed 16,237 source rows. 16,117
rows have the native handicap result and a positive native winning SP and are in
`canonical_settlements.parquet`. The remaining 120 rows are now all directly
classified exclusions:

| Disposition | Fixtures | Direct evidence |
|---|---:|---|
| `POSTPONED_OR_CANCELLED` | 102 | 97 rows have `改期` on the frozen 500 page; 5 of the former 23 have an exact Nowscore issue/slot row with status `取消`. |
| `NEVER_SETTLED_OFFICIAL_NO_SP` | 18 | Frozen 500 rows retain `winning_sp=-`; exact Nowscore issue/slot probes show a completed result, but do not provide a native Beijing winning SP. |

A Nowscore final score is recorded only as independent result/cancellation
provenance. It is never converted into a Beijing winning SP or ticket payout.

## Source-lane readback

- **500.com kaijiang:** 57 GB18030 pages and one terminal receipt per issue are
  carried forward unchanged from v1. They remain the canonical result/native-SP
  authority.
- **Nowscore issue/provider lane:** 16 UTF-8 issue-page snapshots were captured
  for the exact 23 formerly unresolved issue/slot keys. The package records URL,
  filesystem capture timestamp, byte count, SHA-256, provider match ID, status,
  score/result code, native handicap, and provider SP URL in
  `nowscore_probe_ledger.csv`. Each snapshot is copied under
  `raw/nowscore_issue_pages/` and is semantically re-parsed by the verifier.
- **Local `beidan_live.settlements`:** a read-only/WAL-aware exact
  `(issue, match_idx)` audit returned 0/23 records, therefore no final score or
  native SP. DB SHA-256: `e532397f84eff1ba1e0eb4850d9e45faf4c59a4654440e599e3d438cbc795036`.
- **Local XLSM/BJ268 lane:** `历史数据` has 365,161 rows × 75 columns; the audit
  found three weak fixture candidates but 0 source-native Beijing settlement
  receipts. Workbook SHA-256:
  `f2b1d7df6c431d4f3d2974e975dbd51f2945f34fabb2e2e1bdbf3087948fee22`.
  It remains a legacy/crosscheck lane and was not promoted into the canonical
  settlement table.
- **`official_500_settlements`:** a downstream SQLite materialization shape, not
  an independent raw lane. Its exact-key audit produced 0/23 records; expected
  local derived files were absent at the active workspace path at delivery, which
  is recorded as absence rather than manufactured source data. Its importer reads
  the same 500 source database and cannot provide a second source for a residual.

## Evidence package

`results/bj396_2025_settlement_backfill_v2/` extends the v1 package without
modifying its raw 500 pages or v1 exclusion ledger. New v2 artifacts are:

- `baseline_manifest_v1.json` — the preserved v1 package receipt;
- `raw/nowscore_issue_pages/*.html` — 16 immutable probe snapshots;
- `nowscore_probe_ledger.csv` — one exact issue/slot provider probe per former
  unresolved fixture, with URL, SHA-256 and capture timestamp;
- `residual_disposition_v2.csv` — 120-row admissible-exclusion ledger;
- updated `decision.json` and package-wide `MANIFEST.json`.

The verifier checks the full file census and hashes, reparses all 57 500 pages,
reconstructs canonical settlements and the v1 ledger, reparses every Nowscore
snapshot, recomputes all 120 v2 dispositions, and rejects a changed winning SP,
result identity, ledger label, source row, source trace, or re-manifested package.
The 16 Nowscore page hashes are additionally pinned in the verifier's frozen v2
contract, so an attacker cannot replace a raw snapshot and simply rewrite the
package manifest/derived ledger.

## Reproduction

```bash
PYTHONPATH=. /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/extend_bj396_settlement_package_v2.py \
  --baseline-root results/bj396_2025_settlement_backfill_v1 \
  --nowscore-raw-root /tmp/bj396-nowscore \
  --package-root results/bj396_2025_settlement_backfill_v2
PYTHONPATH=. /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/verify_bj396_2025_settlement_package.py \
  --package-root results/bj396_2025_settlement_backfill_v2
PYTHONPATH=. /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  scripts/render_bj396_settlement_notebook_v2.py
PYTHONPATH=. /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python \
  -m pytest -q tests/test_bj396_settlement.py
```

## PI review request

Please review the source-bound v2 denominator and its explicit treatment of all
120 non-canonical fixtures. If accepted, #394 may consume this complete 2025
settlement interface; any strategy decision remains independently gated.
