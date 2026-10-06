# Persistent Parquet layout (NAS) and the hot layer

Status: layout contract established 2026-10-04; first dataset (`settlement`) in conversion.
Machine-readable contract: [`config/parquet_layout.json`](../../config/parquet_layout.json).

## Decision

- Analytical datasets are persisted as **Parquet on the NAS** (`/mnt/nas/Data/beijing-lot`).
- The NAS is a **CIFS automount** (`//192.168.10.2/Data`, `x-systemd.automount,nofail,soft`). It may be
  absent; every reader and writer therefore **fails closed** rather than treating a missing mount as
  an empty dataset.
- **Short-lived data stays on the NVMe root** (`results/`): capture scratch, intermediates, caches,
  and anything a single run produces and consumes.
- R reads Parquet through **Arrow** (zero-copy tibbles) and aggregates through **DuckDB** over the
  same files.

This supersedes the SQLite-on-Sandisk default for *analytical* datasets. Acquisition-time raw
receipts and their collectors are unchanged by this decision; they are retired separately.

## Layout

```
/mnt/nas/Data/beijing-lot/
  registry/
    datasets.json                 # every published dataset version, with hashes
    <dataset>-current.json        # active version pointer + row counts + partitions
  datasets/<dataset>/
    versions/<version>/
      manifest.json               # source identity, hashes, tables, partitions
      tables/
        <table>/part-issue-year=<year>.parquet   # partitioned tables
        <table>.parquet                          # whole (small) tables
  tmp/                            # staging for atomic publish (same filesystem)
  quarantine/                     # failed conversions, never partially published
```

`<version>` is the **source release version** (for settlement: `20260907_history_five_play_v2`), so a
Parquet version always names the SQLite release it came from.

## Partitioning

Partitioned by `issue_year` (`part-issue-year=YYYY.parquet`). `issue_year` is derived from the issue
code prefix and matches the existing `issue_year` helper; it also separates the 6-digit era
(2007–2019) from the 5-digit era (2020+). Observed distribution in settlement: 18 year partitions,
2009 through 2026.

Only tables whose bulk is keyed by issue are partitioned (`observation`, `option_sp` in settlement).
Small batch/receipt tables are written whole so they stay trivially readable.

## Write policy

- `compression=snappy`, `row_group_size=250000`, dictionary encoding on, Parquet `version=2.6`.
- **Atomic publish**: write to `tmp/` on the same filesystem, fsync, then rename into
  `datasets/<dataset>/versions/<version>/`. A failed conversion leaves nothing published and the
  partial output is moved to `quarantine/`.
- Measured NAS write throughput is ~43 MB/s on a small-file probe; the 3.3 GB settlement release
  converts in minutes with per-year batching.

## Read policy

Readers go through the `beidan` package, never through raw file paths, so the version, the type
contract and the manifest hashes are all enforced in one place:

```r
beidan::parquet_root()                        # fail closed if the NAS is not mounted
beidan::dataset_registry("settlement")        # current version pointer
beidan::dataset_tables("settlement")          # published tables
beidan::dataset_contract("settlement", "option_sp")   # Arrow -> R type contract

# one partition, zero-copy, sha256-verified against the manifest
beidan::read_dataset("settlement", "option_sp", issue_year = 2026)

# whole table (all partitions), row count checked against the manifest
beidan::read_dataset("settlement", "option_sp")

# cross-partition aggregation
beidan::dataset_query("settlement",
  "SELECT play, count(*) AS n FROM observation GROUP BY play ORDER BY play", "observation")
```

`read_dataset()` casts each column to the declared R type (`int64 -> double`, `int16 -> integer`,
`string -> character`, `binary -> blob`, `timestamp -> POSIXct`), rejects Arrow types outside
`parquet_type_map()` rather than coercing them, and verifies every file's sha256 unless
`verify = FALSE`. `dataset_query()` runs DuckDB on a read-only connection over the same files.

`arrow`, `duckdb`, `DBI`, `jsonlite`, `digest` and `tidyselect` are package `Imports`, installed from
Posit Package Manager binaries (`.Rprofile` pins the `resolute` repo; see the dependency contract).

## Mount hardening (owner action required)

The NAS holds the sole copy of each converted dataset, so the CIFS mount options matter for
durability. Two current options are **kernel-module defaults, not choices recorded in `/etc/fstab`**:

| Option | Current | Source | Risk |
|---|---|---|---|
| `soft` | on | cifs module default (fstab does not override) | On a NIC flap or server timeout the kernel returns `EIO` mid-write instead of retrying; a half-written Parquet file or a silently failed read is possible. |
| `actimeo` | `1` | cifs module default | Attribute cache is 1 second, so every `read_dataset(verify = TRUE)` re-hashes and re-fetches file data. Slow, and it re-hits the network constantly. |
| `echo_interval` | `60` | cifs module default | Server liveness probe every 60 s; longer is cheaper. |

Recommended hardened `/etc/fstab` line (add the three trailing options):

```
//192.168.10.2/Data /mnt/nas/Data cifs credentials=/etc/samba/credentials-nas-data,uid=1000,gid=1000,_netdev,nofail,x-systemd.automount,x-systemd.mount-timeout=15s,nosuid,nodev,hard,actimeo=30,echo_interval=30 0 0
```

Apply and verify (requires the owner; this sandbox has no non-interactive sudo):

```bash
sudo cp /etc/fstab /etc/fstab.bak-$(date +%F)
sudo sed -i 's#\(x-systemd.mount-timeout=15s,nosuid,nodev\)#\1,hard,actimeo=30,echo_interval=30#' /etc/fstab
sudo systemctl daemon-reload
sudo umount /mnt/nas/Data && sudo mount /mnt/nas/Data
findmnt -T /mnt/nas/Data -o OPTIONS -n | tr ',' '\n' | grep -E 'hard|soft|actimeo|echo_interval'
```

Rollback: restore `/etc/fstab.bak-*` and remount. `hard` trades a mid-read hang (if the server is
unreachable) for the absence of silent corruption; the `x-systemd.mount-timeout=15s` still bounds
mount-time hangs, and `read_dataset(verify = TRUE)` catches any bad read via sha256 mismatch rather
than returning wrong data.

## Sandisk retirement

The Sandisk disk is **being physically removed by the owner**; agents take no further action on it.

- Ledger (historical record): `/mnt/nas/Data/beijing-lot/registry/sandisk-retirement.json`
  (`beijing_lot_sandisk_retirement_v1`), recording that the `settlement` slice's NAS successor
  verified (every manifest sha256 recomputed) and the original bytes were left untouched.
- Sandisk is **exFAT** with `fmask=0133,dmask=0022`; `chmod` reports success but has no effect, so
  the slice could not be made read-only. The ledger therefore recorded
  `MIGRATED_PENDING_READ_ONLY` with `verified_read_only: false`. Physical removal supersedes that.
- Only `settlement` had a verified NAS successor. `markets`, `clean_v1`, `fundamentals` and the rest
  of that disk were **not** migrated, so removing the disk discards them — this was the owner's
  explicit decision.
- The Parquet dataset is **self-contained**: the manifest embeds the source registry snapshot, so
  reading it needs no source disk. `convert_settlement_parquet.py` requires `--registry` explicitly
  and has no Sandisk default, so re-conversion fails closed rather than pointing at a removed path.

## Provenance

Each version's `manifest.json` binds: the source registry entry and its `sha256`, the source database
path and row counts, the converter implementation hash, per-file `sha256` and byte size, and the
conversion timestamp. A reader that trusts a version verifies the manifest before use.

## Scope of this change

- Established: root, layout, contract, partitioning, write/read policy, provenance fields.
- In progress: `settlement` conversion and the package reader.
- Not in scope: acquisition-time raw retention (unchanged), CI, and cross-dataset migration of
  `markets`/`fundamentals` (each gets its own validation when its turn comes).
