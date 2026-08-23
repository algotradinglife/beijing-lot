# HANDOFF — Issue #358

[SESSION] 20260824_002447_5a30b9

## Current handoff point

- Source-package HEAD: `ac20b0cf9ad9e050ce0e629bf164244eeddf9fbe`
- Branch: `engineer/bj358-eu-value`
- Evidence package: `results/low_n_eu_value_proxy/`

## Completed

- Materialized 404,466 long European-average-odds value cells (134,822 fixtures × 3 outcomes) for 2017–2024 using the frozen #354 pre-outcome feature payload.
- Preserved outcome identity/order `3/1/0`; records raw average odds, implied probability, overround, two explicitly named de-vig semantics, #354 calibrated probability, `p × odds`, coverage/quality/provenance, and Top-2 ingredients.
- Bound raw source SQLite bytes to the accepted #236 hash and fail-closed on non-empty SQLite WAL/SHM sidecars.
- Added N3/N4/N5 full-cartesian accounting recipe: 8/16/32 tickets respectively and one `0.65` factor per complete ticket. No fixture selector or strategy was chosen.
- Generated and executed the profiling notebook and committed its output, report, schema, receipts, and source-bound semantic verifier.

## Key decisions / reasons

- `10h` is represented as `RETROSPECTIVE_RELATIVE_PROXY`, with a null exact source timestamp and explicit `RELATIVE_10H_LABEL_NO_EXACT_OBSERVATION_TIMESTAMP`; the source has a relative horizon label, not a strict common observation clock.
- European decimal odds remain a proxy and are never labelled Beijing official SP or used as Beijing payout calibration.
- `source_consensus_devig_probability` is the #354-compatible mean of independently de-vigged bookmaker triplets. `average_odds_devig_probability` is retained separately, because de-vigging arithmetic-average odds is a different transformation.

## Verification evidence

- `python scripts/run_low_n_eu_value.py --source-sqlite … --force` — completed; value-cell semantic hash `6adc99a6c001f01b155314cc0dbca0694eddf055187dea6cbfd22200c50b6bb1`.
- `python scripts/build_low_n_eu_value_notebook.py` — completed; six executed code cells, no errors.
- `python scripts/verify_low_n_eu_value.py --source-sqlite …` — PASS for manifest closure, implementation hashes, source-bound replay, semantic replay, temporal boundary, outcome identity, and N3–N5 boundary.
- `pytest -q tests/test_low_n_eu_value.py tests/test_low_n_eu_value_verifier.py` — 12 passed.
- Tamper coverage remanifests changed payout/value field, `0.65` field, raw ledger/source trace, future temporal label, calibrated probability while preserving local `p×odds`, and source receipt; verifier rejects every case.

## Known limitations

- The `10h` data is a retrospective relative horizon, not strict-forward evidence.
- This package supplies inputs only; #359 must make any low-N selection/frontier decision under its own protocol.
- `ruff` was unavailable in the active Hermes Python environment (`No module named ruff`); syntax compilation, focused tests, full source-bound verifier, and notebook execution did run successfully.

## PI / EV request

Please independently re-run the verifier against the declared external SQLite and inspect the explicit proxy-time boundary. Verify that no result/settlement column exists in `value_cells.parquet`, then review whether the transparent European `p × odds` diagnostic is acceptable as an input to #359 without being interpreted as Beijing payout calibration.
