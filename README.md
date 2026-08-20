# Beijing Lot

Research, data, and decision tooling for the Beijing single-match lottery.

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
