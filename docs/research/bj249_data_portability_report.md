# Issue #249 — external data portability decision report

## Decision summary

The first complete migration snapshot is valid and restorable. The live data
remains on Linux ext4; the removable `F:` drive is used only as immutable,
versioned snapshot storage.

The accepted snapshot is `bj249-core-20260820-v1`. It contains 464 files
(8 SQLite databases and 456 source/derived files), totalling 35,538,877,815
bytes (about 33.1 GiB). Its canonical manifest SHA-256 is
`fada8656907ebe4dcb9f2b493e06699c52b095e22159bf23b9a26af4c45f3d6f`.

## What was proved

1. Each SQLite source was copied with the native SQLite backup API, so committed
   WAL state is included without copying a possibly inconsistent database file.
2. Before publication, all SQLite copies passed `integrity_check`; their schema
   hashes, complete per-table row counts and configured time ranges were frozen
   in the manifest.
3. The external snapshot was published only after verification, using a staging
   directory followed by an atomic rename and a manifest-bound `COMPLETE`
   marker.
4. A separate full verification reread every file on the removable drive and
   reproduced all 464 hashes and 35,538,877,815 bytes.
5. A real restore copied the snapshot back to a fresh ext4 directory. Every
   restored file was byte-identical to its verified manifest entry; the restore
   receipt reports `PASS` for all 464 assets.
6. Focused tests cover source immutability, WAL-consistent SQLite backup,
   rejection of incomplete/tampered snapshots, exact file-set verification and
   refusal to overwrite an existing restore target.

The compact, Git-tracked evidence is in
[`evidence/bj249_data_portability_v1`](../../evidence/bj249_data_portability_v1).
The large snapshot itself is intentionally outside Git at
`$BEIJING_LOT_DATA_ROOT/snapshots/bj249-core-20260820-v1`.

## Data scope

The canonical asset list is
[`config/bj249_data_snapshot.json`](../../config/bj249_data_snapshot.json). It
includes the eight current SQLite truth/cache databases, the historical raw
source tree, the accepted divergence materialization and the external-market
proxy panel used by the current model line.

The largest database, `data/derived/500_bjdc/500_bjdc.sqlite`, freezes 26 tables.
Its match schedule spans 2013-12-28 through 2026-08-20, while its live market-SP
snapshot table spans 2026-07-16 through 2026-08-20. These ranges describe what
was backed up; they do not assert uniform causal feature coverage across that
whole period.

## Boundaries and next decision

This issue establishes a reliable full-snapshot and restore path, not an
incremental backup service. Retention, pruning and unattended scheduling remain
explicitly outside the first version. Adding those now would not improve the
model evidence and would delay the return to the model line.

The correct next move is therefore to close the data-portability prerequisite,
reconcile its parent data-readiness issue, and resume the divergence-aware value
model. Future accepted data assets must be added deliberately to the canonical
configuration and included in the next versioned snapshot.
