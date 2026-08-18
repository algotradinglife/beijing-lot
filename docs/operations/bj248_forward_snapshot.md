# Issue #248 prospective Nowscore snapshot operations

## Scope

This is the prospective lane only. It polls Nowscore's TypeID=5 Beijing issue
page and the per-match `Sp值变化表`; it does not backfill historical movement,
fit models, construct tickets, calculate ROI, buy data, or bypass access
controls.

## Storage and cadence

Set `BEIJING_LOT_DATA_ROOT` to an operator-managed persistent volume. Git never
contains production SQLite, raw responses, views, or logs. A poll is normally
scheduled every five minutes while sales are open; its per-request pacing is
controlled with `--min-interval-seconds` (default 1 second).

```bash
export BEIJING_LOT_DATA_ROOT=/srv/beijing-lot-data
python scripts/collect_bj248_forward_snapshot.py --issue 26051
```

WSL example: choose an NTFS-mounted persistent directory explicitly, e.g.
`/mnt/d/beijing-lot-data`; native Ubuntu example: `/srv/beijing-lot-data`.
No source file contains either host path.

## Restart and idempotency

The collector key is issue + poll timestamp + match. A retry of the same key is
a no-op. A later poll, even with identical bytes, receives a distinct receipt;
the raw body remains content-addressed once while every capture receipt and its
complete source table are retained. Writes are temp-file + file fsync + rename
+ directory fsync. SQLite uses WAL, foreign keys, and `synchronous=FULL`.

`collector_failures.jsonl` records fetch/parser failures. A failure is never
coerced to a zero quote or a completed vector. Inspect it before assuming a gap
is market missingness.

## Causal views

`relative_horizon_view` selects the deterministic latest complete 3/1/0 state
at a configured horizon (default compatibility horizons: 10h and 1h).
`common_epoch_view` uses a passed issue epoch, or its schedule/sale-only fallback
(earliest sale-open kickoff minus 120 minutes). Both exclude a row unless both
Nowscore's source-change clock and the trusted local receive clock are no later
than the decision epoch and strictly before kickoff. Settlement, outcome and
`0.65` values are rejected at the capture boundary.

## Verification and migration

Call `store.seal_manifest()` after a controlled capture window and retain its
returned SHA-256 in an external release/operations record. Verify against that
external anchor with `verify_store`; this detects remanifesting as well as
quote, source-trace, raw-payload, and schema-ledger tampering. The raw issue
page, every raw history page, receipt ledger, and source-change vectors are
sufficient to rebuild the normalized views in a future store migration.

## Service wrapper

On either WSL Task Scheduler or native Ubuntu systemd, invoke the command above
on a five-minute cadence only during operator-approved sales hours. Capture
stdout/stderr centrally and stop/review on non-zero exit. Do not use an infinite
in-process loop: one scheduled invocation has one auditable poll boundary.
