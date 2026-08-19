# #236 Engineer Handoff

- Session: `20260819_075923_c636f3`
- Branch: `engineer/bj236-issue`
- Delivery state: evidence PR pending creation.

## Completed

- Recovered the Nowscore/Titan-backed `beidan_xlsm` historical European 1X2 lane.
- Materialized external hash-bound Parquet views at
  `/home/drwho1985/workspace/soccer/beijing-lot/data/derived/bj236/eu_odds_proxy_v1`.
- Verified 1,731,423 proxy probability rows and 192,443 matched canonical issue slots.
- Committed compact coverage, translation decision receipts, executed notebook,
  reusable ingestion/materialization/verifier code and tamper tests.

## Key decisions

- `initial`, `10h`, `1h` are `RETROSPECTIVE_RELATIVE_PROXY`, not strict-forward
  timestamps and not Beijing SP.
- Source identity requires the workbook's `source_meta.source_path` receipt for
  `beidan.xlsm`; adapters select only raw `matches` and `market_snapshots` 1X2
  columns and are read-only.
- Non-zero-line translation is unavailable without a score/goal-difference
  distribution. This build observed zero `AVAILABLE_ZERO_LINE_IDENTITY` rows.
- Invalid triplets and ambiguous source issue slots are excluded; raw source
  coordinates, row counts and source SHA-256 retain replay traceability.

## Verification

- `pytest tests/test_bj236_eu_odds.py -q` → 5 passed.
- `ruff check ...` → all checks passed.
- External view verifier passed: 352 parts / 1,731,423 probability rows.

## Known limitations / next step

- The full raw workbook and bulk Parquet views intentionally remain under
  `BEIJING_LOT_DATA_ROOT` and are Git-ignored. Rebuild with the documented
  build command, then run the verifier.
- #238 must consume the proxy namespace only and respect the machine-readable
  `UNAVAILABLE_*` non-zero-line translation decisions.
