# Beijing Lot

Research, data, and decision tooling for the Beijing single-match lottery.

## Start here after the Ubuntu migration

Read the [Ubuntu migration and project continuation handoff](docs/handoffs/ubuntu-migration-project-handoff.md)
before restoring data or starting new research. It records the current N7 evidence,
GitHub control-plane state, external-data snapshot boundary, verified restore steps,
and the planned transition into fundamental-data collection and modeling. The
[2026-08-27 migration acceptance record](docs/handoffs/ubuntu-migration-acceptance-2026-08-27.md)
documents the restored 2026-08-20 rollback boundary and its remaining limitations.

## R / Quarto analysis

- [Documentation index](docs/README.md): architecture, data contracts, operations, and historical evidence.
- [Environment and analysis commands](docs/operations/rstudio_quarto_data_workflow.md): locked R setup, explicit paths, tests, and rendering.
- [Architecture](docs/architecture.md): R analysis, Python storage, and shared temporal-learning boundaries.
- [Session handoff for #413](docs/handoffs/r-qmd-structure-413-2026-09-05.md): repaired interfaces, moved paths, validation, and continuation notes.
- Migration and restore documents above remain at their original paths. Read them before restoring data; re-read GitHub for current lifecycle and dependencies.

Offline report from repository root after environment setup:

```bash
R_LIBS_USER="$PWD/r_lib" TZ=UTC quarto render quarto/03_500_nowscore_datatable_demo.qmd --execute --no-cache
```

The default report uses synthetic saved response fixtures, performs no network requests, and writes no database.

## Forward market snapshots

Issue [#248](https://github.com/algotradinglife/beijing-lot/issues/248)
provides the prospective Nowscore `3/1/0` SP collection lane. It stores raw
source evidence and append-only receipts outside Git, then materializes causal
10-hour, 1-hour, and issue-level common-epoch views.

Choose an operator-managed persistent volume before running any command. For
the current WSL host, the recommended location is the mounted data drive:

```bash
export BEIJING_LOT_DATA_ROOT=/mnt/f/beijing-lot-data
```

Run one auditable poll for an active issue:

```bash
python scripts/collect_bj248_forward_snapshot.py --issue <issue-number>
```

Materialize the derived views and operations report:

```bash
python scripts/materialize_bj248_views.py
```

The persistent layout is:

```text
$BEIJING_LOT_DATA_ROOT/forward_snapshot/
├── control/forward_snapshot.sqlite
├── raw/
├── capture_manifest.json
├── logs/collector_failures.jsonl
└── views/
```

Do not enable unattended scheduling until a fresh issue has a demonstrably
future source schedule and at least one complete causal `3/1/0` vector. After
that check, the intended cadence is one process invocation every five minutes
during operator-approved sales hours; the collector is deliberately not an
infinite in-process loop.

Entry points and documentation:

- [Collector CLI](scripts/collect_bj248_forward_snapshot.py)
- [View materializer](scripts/materialize_bj248_views.py)
- [Collector implementation](src/forward_snapshot/collector.py)
- [Storage and verification](src/forward_snapshot/store.py)
- [Causal views](src/forward_snapshot/views.py)
- [Operations guide](docs/operations/bj248_forward_snapshot.md)
- [Manual shadow-capture report](docs/research/bj248_manual_shadow_capture.md)
- [Source-retention probe](docs/research/bj248_source_retention_probe.md)
- [Operational notebook](notebooks/research/issue-248/bj248_forward_snapshot.ipynb)

## External snapshots and restore

Issue [#249](https://github.com/algotradinglife/beijing-lot/issues/249)
protects the local research databases and source files before host migration.
Runtime SQLite databases stay on Linux ext4; the removable drive stores only
versioned snapshots.

```bash
export BEIJING_LOT_DATA_ROOT=/mnt/f/beijing-lot-data
python scripts/manage_bj249_data_snapshot.py snapshot \
  --config config/bj249_data_snapshot.json \
  --source-root /absolute/path/to/beijing-lot \
  --snapshot-id bj249-core-YYYYMMDDTHHMMSSZ
```

- [Snapshot, verification, and restore CLI](scripts/manage_bj249_data_snapshot.py)
- [Canonical asset configuration](config/bj249_data_snapshot.json)
- [Snapshot and restore runbook](docs/operations/bj249_data_snapshot_restore.md)
- [Portability notebook](notebooks/research/issue-249/bj249_data_portability.ipynb)
