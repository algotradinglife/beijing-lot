# bj235_bj_sp_timeseries_v1 — Causal Beijing handicap + pre-event SP time series

Contract: BJ-UNIFIED-BJ-SP-TIMESERIES-001 / v1 (issue #235).
Package owner: Engineer (BJ Data Platform). Milestone M1. Parent #232.

## Contents

- `tables/*.parquet` — immutable canonical snapshot (source_registry,
  ingestion_batch, fixture, market_observation, market_quote, decision_epoch,
  as_of_selection, probability_estimate, settlement, exclusion_ledger)
- `RECOVERABILITY_REPORT.json` — build steps, raw→triplet→causal waterfall,
  issue-level support by cohort, historical disposition
- `ISSUE_SUPPORT.csv` — per-issue fixtures total vs complete as-of
- `MANIFEST.json` — package/table inventory
- `SHA256SUMS.json` — hash binding for every file in this package

## Terminal disposition

- **Prospective cohort (2026-05+): STRICT_CAUSAL support recovered** from
  `beidan_live_500` (trusted receive clock) and `bjdc_500_xml_34` (native
  source_updatetime + fetched_at). Complete as-of selections at decision
  epochs kickoff -24h/-6h/-1h/-0.5h.
- **Strict historical (2014-2025) pre-event SP: `UNRECOVERABLE_HISTORICAL_BJ_SP`**
  (evidence-backed). No pre-2026 source carries a native, verifiable pre-event
  SP observation clock. beidan_xlsm snapshots are label buckets
  (initial/10h/1h/final) with no exact clock; beidan_features has no clock;
  beidan_history is settlement-only; nowscore/okooo are third-party archives.
- Retrospective proxy sources are registered and ledged but never enter
  inference tables.

## Rebuild

```bash
python scripts/bj235_build.py --data-root <repo data/> \
  --bundles <repo results/data_collection> \
  --out results/bj235_bj_sp_timeseries_v1 \
  --canonical <tmp>/bj_sp_canonical.sqlite
python -m pytest tests/test_bj235_asof.py tests/test_bj235_tamper.py -q
python scripts/bj235_preflight.py --canonical <tmp>/bj_sp_canonical.sqlite \
  --out results/bj235_bj_sp_timeseries_v1
```

## Caveats

- 500 xml34 fixtures lack kickoff in that table; fixtures without kickoff get
  no decision epochs (explicit unavailable, counted in ISSUE_SUPPORT as total
  but not as complete).
- beidan_live snapshots have no native source time; observed_at := received_at
  (recorded in source_registry.clock_semantics).
- Sale/availability status for beidan_live is NULL (unknown); richer
  sale_status exists in live_market_sp_snapshots (playid-34 side table, not
  yet canonicalized — deferred to #238).
