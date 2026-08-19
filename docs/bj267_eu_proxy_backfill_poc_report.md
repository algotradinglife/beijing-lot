# #267 Historical Nowscore/Titan Proxy Backfill — PoC Decision

Contract: `BJ-UNIFIED-EU-PROXY-BACKFILL-POC-001`

## Decision

`FULL_BACKFILL_EXECUTABLE`.

The exact historical completion target is 808 issues and 213,263 fixtures.
Every one of the 73 issues absent from the accepted #236/2026-extension union
is still present on Nowscore with a complete embedded issue membership matrix
and provider match IDs. A retry-protected Titan sample from every missing issue
was readable and contained initial/10h/1h European 1X2 history.

This is an acquisition decision, not a canonical publication. #236, the 2026
extension, and the historical database were opened read only; those three
SQLite inputs and the complete 54MB #236 canonical package tree had identical
SHA-256 digests before and after both the network run and raw-payload replay.
The actively updated live database is first copied through SQLite's consistent
backup API into the isolated staging namespace. All inventory work uses that
hash-bound snapshot, so normal concurrent live collection cannot alter a run.

## Corrected denominator

| Component | Issues | Fixtures |
|---|---:|---:|
| Accepted #236 | 701 | 192,709 |
| Existing schema-compatible 2026 extension | 34 | 6,001 |
| Recovered issue-page membership | 73 | 14,553 |
| Final reconciled target | 808 | 213,263 |
| Excluded live-cache carry-over | 13 affected issues | 1,930 |

The previous 215,193-row local union was not a valid fixture denominator.
During issue transitions, `beidan_live.db` retains rows from the preceding
issue. Thirteen 2026 issue codes therefore appeared to contain 1,930 fixtures
that do not belong to those issue pages. They are retained in an explicit
exclusion ledger rather than treated as source gaps.

The visible Nowscore HTML table was also incomplete for settled/cancelled
fixtures. The corrected parser reads the embedded `M[row][field]` matrix and
then uses visible table rows only for enrichment. This restored, for example,
issue 25114 match 77 and issue 26086 matches 1–11 without using result fields.
Its timestamp is retained only as `issue_deadline_ts`; it is not mislabeled as
kickoff. The full crawl obtains kickoff from the Titan match payload.

## Source and schema findings

- All 73 issue pages produced non-empty, unique issue-slot/provider-ID maps.
- All 73 bounded Titan samples were available after normal transient-network
  retry and exposed at least one complete initial/10h/1h bookmaker triplet.
- The existing 34-issue extension contains 6,001 fixtures and the required
  `matches`, `market_snapshots`, and `source_meta` columns.
- A staged execution through the unchanged #236 normalizer has exact Parquet
  schema parity with the accepted package. Its market, 3/1/0 outcome, three
  horizon, probability, availability, provenance and causal-grade domains all
  pass; strict-forward rows remain zero.
- The normalized extension yields 54,000 probability rows across 6,000 of
  6,001 fixtures. The remaining fixture is retained as
  `UNAVAILABLE_NO_VALID_EURO_1X2_HORIZON`, not removed from the denominator.
- Its complete bookmaker-triplet counts are 75,981/90,015 at initial,
  75,734/90,015 at 10h, and 75,933/90,015 at 1h.
- No result, winning SP, settlement, payout, or 0.65 field enters the inventory
  or source-row interface.

## Reproduction

The external raw payloads and full ledgers live under
`$BEIJING_LOT_DATA_ROOT/staging/bj267_eu_proxy_backfill_poc_v3`. Compact tables,
the figure, and the executed notebook are committed to Git.

```bash
python scripts/profile_bj267_eu_proxy_backfill.py \
  --data-root "$BEIJING_LOT_DATA_ROOT" \
  --staging-root "$BEIJING_LOT_DATA_ROOT/staging/bj267_eu_proxy_backfill_poc_v3" \
  --output-root results/bj267_eu_proxy_backfill_poc_v3 \
  --titan-samples-per-issue 1 --replay
python scripts/execute_bj267_notebook.py --data-root "$BEIJING_LOT_DATA_ROOT"
```

Replay verifies every raw payload against its recorded size and SHA-256 and
reproduces the compact issue and Titan tables byte-for-byte.

## #268 handoff

#268 should build a resumable full Titan crawl for all 14,553 recovered
fixtures, merge the 34-issue extension and accepted #236 rows into a **new**
immutable version, normalize with the existing #236 de-vig implementation,
record unavailable cells explicitly, and atomically promote only after all
schema, cardinality, manifest, notebook, and source-integrity checks pass. The
1,930 live-cache carry-over rows must remain exclusions.
