# Issue #235 — BJ SP timeseries recovery handoff

[SESSION] 20260818_234459_2b166b

## Current delivery state

- Branch: `engineer/bj235-issue`, based on accepted #234 foundation at
  `origin/main` commit `671c728`.
- Contract: `BJ-UNIFIED-BJ-SP-TIMESERIES-001` plus PI amendment v2
  (2026-08-17).
- Execution scope: `historical_proxy_only`. The amendment makes this the valid
  historical primary lane; strict/prospective live replay remains separately
  represented by the prior v1 evidence package and its source-specific tests.

## Delivered in this run

- Reconciled the committed #235 v1 checkpoint onto current `main`/#234 source
  schema without modifying the separate legacy worktree.
- Added append-only `relative_horizon_panel` and its settlement-free
  `relative_horizon_view` M×3 Parquet export. Each cell binds fixture, issue,
  native line, outcome, snapshot bucket, source, availability and provenance;
  no exact clock is fabricated.
- Executed the full 6.9 GB archive ingestion into
  `results/bj235_bj_sp_timeseries_v2/`:
  - 192,709 fixtures, 701 issues;
  - 2,312,508 cells: 2,309,166 present and 3,342 explicit missing;
  - `initial`, `10h`, `1h`, and `final` profiled; the first three are primary;
  - 12,800 padding/unknown source rows explicitly excluded;
  - provenance verification: 2,312,508 checked, 0 mismatches.
- Clean-ran the executed notebook against the generated canonical SQLite store;
  its outputs have 0 errors.

## Verification

```bash
python -m pytest tests/test_bj235_asof.py tests/test_bj235_tamper.py tests/test_bj235_panel.py -q
# 22 passed

python scripts/bj235_preflight.py \
  --canonical data/derived/bj235_v2/bj_sp_canonical.sqlite \
  --out results/bj235_bj_sp_timeseries_v2 --proxy-only
# PREFLIGHT PASS
```

The ignored local `data/derived/bj235_v2/` SQLite is reproducible from the
tracked build script plus the configured data root; the committed immutable
Parquet package is hash-bound by `SHA256SUMS.json`.

## Boundaries and known limitations

- This is `RETROSPECTIVE_RELATIVE_PROXY`, not exact-clock causal replay:
  snapshot labels are the temporal key, and proxy support is never pooled with
  strict historical or prospective support.
- The full mixed live+historical runner was not used for this v2 artifact after
  a prior run exhausted `/tmp` while materializing its temporary canonical DB.
  The v2 `--proxy-only` execution path intentionally writes the historical
  primary lane on persistent storage and reports that scope explicitly.
- No probability model, EU/ticket construction, outcome opening, settlement
  inference, or downstream materialization is included. #238 consumes only the
  documented common v2 view under its own gate.

## Next action

Independent EV should rerun the three test modules, v2 preflight, and the
notebook with `BJ235_CANONICAL` and `BJ235_OUT` bound to its own regenerated
proxy-only output. Review the explicit proxy limitation before treating the
view as a decision-time signal.
