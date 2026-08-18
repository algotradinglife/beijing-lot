# Issue #235 handoff — v2 historical relative-horizon panel

[SESSION] 20260818_234440_3e0f3e

## Current delivery state

- Branch: `engineer/bj235-bj-sp-timeseries`
- Base: `main` at `671c72866af6e03785d1725d84eeecfc385b6f95` (the accepted #234 integration landing).
- Package: `results/bj235_bj_sp_timeseries_v2`.
- Build source: read-only `/home/drwho1985/workspace/soccer/beijing-lot/data/derived/beidan_xlsm/beidan_xlsm.sqlite`; its SHA-256 is recorded in the package manifest.

## Completed

- Implemented a fail-closed adapter that reads only `matches` identity/native handicap and `market_consensus` `euro_1x2` values for `initial`, `10h`, `1h`.
- Materialized 1,734,381 long 3/1/0 cells, retaining missing vectors as explicit unavailable records; authoritative per-horizon counts are in the coverage table.
- Kept source-relative labels distinct from wall-clock time and emitted zero accepted strict-historical / prospective cells in this historical-only package.
- Separated raw SP from normalized inverse-SP probability and excluded `final`, settlement/outcome/winning-SP and payout-factor inputs.
- Added remanifested semantic tamper coverage for probability, source label, horizon/future-label substitution and coverage-ledger manipulation.
- Executed `notebooks/research/issue-235/bj235_historical_proxy.ipynb` with the local fallback executor because the host lacks nbformat/nbclient and PyPI TLS fetches failed.

## Verification

- `python -m pytest tests/test_bj235_historical_proxy.py tests/test_bj235_package.py tests/test_bj235_tamper.py -q` → `8 passed`.
- `python scripts/build_bj235_historical_proxy.py --verify --output results/bj235_bj_sp_timeseries_v2` → `PASS`, 1,734,381 proxy cells and 2,103 issue×horizon coverage rows.

## Key decisions / limitations

- This is `RETROSPECTIVE_PROXY`, not strict causal data: source labels are not reinterpreted as timestamps and no global decision epoch/as-of selection is claimed for history.
- The historical workbook supplies `euro_1x2` consensus vectors alongside native Beijing handicap, not an authenticated first-party Beijing SP tape. The package is useful only within its explicit proxy grade.
- The source is mutable at rest; the builder hashes before and after reading and aborts on a change, but its manifest is a reproducible read receipt rather than external-provider authentication.
- Strict-forward raw-capture reconciliation remains out of scope for this historical package and prospective collection is owned by the parallel issue.

## Next step

EV should fresh-checkout the PR, rerun the focused tests, package verifier, and notebook; then adversarially remanifest cell, coverage, source, and forbidden-field/horizon changes. Do not use this package for model, ROI, settlement, or ticket claims.
