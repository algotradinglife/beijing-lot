# #249 external data snapshot and restore

This runbook protects the current ext4 runtime data before migration. The
removable drive is snapshot storage only: never point a live SQLite WAL database
at DrvFS/exFAT.

## Snapshot

Choose the mounted persistent volume without hard-coding it in source code:

```bash
export BEIJING_LOT_DATA_ROOT=/mnt/f/beijing-lot-data
python scripts/manage_bj249_data_snapshot.py snapshot \
  --config config/bj249_data_snapshot.json \
  --source-root /absolute/path/to/beijing-lot \
  --snapshot-id bj249-core-YYYYMMDDTHHMMSSZ
```

SQLite files are copied with `sqlite3.Connection.backup()`, including committed
WAL content. Raw and Parquet files are streamed into the same staging tree. A
snapshot becomes visible only after integrity, row/time-range, size and SHA-256
checks pass and `MANIFEST.json` plus `COMPLETE` are written.

## Verify

```bash
python scripts/manage_bj249_data_snapshot.py verify \
  --snapshot-id bj249-core-YYYYMMDDTHHMMSSZ
```

Verification checks the externally anchored manifest hash, every file hash and
size, every SQLite integrity result, schema digest, table row count and declared
time range.

## Restore rehearsal

Restore only to a new directory on an ext4 filesystem:

```bash
python scripts/manage_bj249_data_snapshot.py restore \
  --snapshot-id bj249-core-YYYYMMDDTHHMMSSZ \
  --target /absolute/new/ext4/restore-directory
```

The completion envelope is verified before the restore staging directory is
created. Each external asset is hashed while it is streamed, and each restored
file is hashed again on ext4 before the staging directory is atomically renamed.
Byte identity to the snapshot binds every restored SQLite database to the
manifest's already-verified integrity, schema, row-count and time-range receipt
without a redundant full-table scan. Existing targets fail closed. Snapshot and
restore never delete, move or mutate source data.

## Scope

`config/bj249_data_snapshot.json` is the reviewed canonical asset list. Update
that file deliberately when a new runtime truth asset is accepted. Staging
directories, interrupted runs and snapshots without a valid `COMPLETE` marker
are never valid backups. Incremental snapshots, cleanup and automated retention
are intentionally out of scope for the first complete path.
