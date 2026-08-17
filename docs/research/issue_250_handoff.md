# Issue #250 delivery handoff

[SESSION] 20260817_160451_269ea0

## Delivery state

- Branch: `engineer/bj250-issue`
- Evidence package: `results/bj250_source_census_v1`
- Executed notebook: `notebooks/research/issue-250/bj250_source_census.ipynb` (2 code cells, no errors)
- Literal verifier: `python scripts/build_bj250_source_census.py --verify-only`

## Completed

- Bound the accepted #40 R8 release as the incremental baseline.
- Implemented a portable, read-only census requiring `BEIJING_LOT_DATA_ROOT` and refusing repository-data fallback.
- Produced machine-readable lineage, source roles, field schemas, four-level intersections, period coverage, M-per-issue distribution, relative-time coverage, unresolved decision ledger, role matrix, figures, checksums, and semantic manifest binding.
- Classified `beidan_xlsm` as the historical proxy; settlement data separately; derived copies excluded from independent evidence; live assets raw-only because strict source/capture-clock evidence is incomplete and the files are mutable/unfrozen.

## Key decisions and rationale

- `initial`/`10h`/`1h` are profileable historical relative-time proxy buckets only—not strict timestamps.
- The exact native overlap is reported only under `(issue, match_idx)`; candidate mapping and canonical/causal overlap are deliberately deferred to #251/#252.
- No data acquisition, source-data write, imputation, modeling, or profitability work occurred.

## Known risks / next review focus

- A sealed snapshot plus complete source and capture clock receipts are required before either current live source can be promoted to strict-forward evidence.
- The missing source-clock path in `beidan_live` and 1,503 p34 clock-incomplete `bjdc_500_capture` rows are recovery/temporal-policy inputs for downstream owners, not repaired here.
- EV should independently rerun the external-data-root build and semantic remanifest attacks.

## Re-run

```bash
BEIJING_LOT_DATA_ROOT=/path/to/data python scripts/execute_bj250_notebook.py
python scripts/build_bj250_source_census.py --verify-only
python -m pytest tests/test_bj250_source_census.py -q
```
