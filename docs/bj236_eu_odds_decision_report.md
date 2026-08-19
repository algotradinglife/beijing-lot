# #236 European Odds Historical Proxy — Decision Report

Contract: `BJ-UNIFIED-EU-ODDS-TIMESERIES-001`

## PI decision

The Nowscore/Titan-backed `beidan_xlsm` archive is accepted as a broad
historical European 1X2 proxy lane. Every `initial`, `10h`, and `1h` row remains
`RETROSPECTIVE_RELATIVE_PROXY`: it is neither Beijing SP nor an exact
decision-time observation.

The lane is useful to #238 in two different ways:

- `Q_EU_RAW_1X2` is available at high historical coverage for all three
  relative horizons.
- `Q_EU_BJLINE` is directly identifiable only for normalized Beijing line 0.
  Non-zero-line translation still requires a score/goal-difference
  distribution and remains unavailable.

## Coverage and data quality (executed 2026-08-19)

The source hash is
`7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f`.
It contains 192,709 eligible unique issue slots over 701 issues. The emitted
package has 1,731,423 probability rows and 192,443 issue slots with at least one
valid horizon. Calendar support is 2014–2025; 99 eligible fixtures have an
unknown/invalid kickoff year and remain explicitly reported.

| Relative horizon | Valid fixtures | Eligible-slot coverage | Median books | p05–p95 books |
|---|---:|---:|---:|---:|
| initial | 192,406 | 99.843% | 11 | 7–15 |
| 10h | 192,297 | 99.786% | 13 | 10–15 |
| 1h | 192,438 | 99.859% | 13 | 11–15 |

The dense source matrix contains a row for 100% of eligible slots at each label,
but those rows may be placeholders rather than valid quotes. Individual
bookmaker triplets are uneven. Invalid-triplet rates are 25.10% at `initial`,
14.26% at `10h`, and 13.07% at `1h`; missing-cell rates are 12.87%, 13.86%, and
13.03%. Redundancy across 15 bookmakers preserves high fixture-level coverage.
Consumers must therefore retain `n_available_books` rather than treating all
aggregates as equally supported. All 1,515,734 invalid bookmaker triplets plus
986 all-invalid fixture-horizon group receipts are represented in the exclusion
ledger (1,516,720 records total).

The exact issue/year, bookmaker, missingness, raw-odds moment, de-vig
probability-quantile, line-provenance and match-rate tables are committed under
`results/bj236_eu_odds_timeseries_v1/` and reproduced in the executed Notebook.

The same source also contains high-coverage Asian-handicap and over/under rows
at the three horizons. #236 profiles their native two-sided Hong-Kong-odds plus
line support in `AUXILIARY_MARKET_SUPPORT.csv`: valid fixture coverage ranges
from 98.92% to 99.92% across market/horizon cells. It does not relabel those
rows as European 1X2 or map them into the Beijing three-outcome space. This
preserves the optional source fields without inventing cross-market semantics;
#238 may consume them only through a separately declared native auxiliary
interface.

## Corrected BJ-line interpretation

The workbook's raw `handicap_line` field contains provider codes such as
96/99/105/133 for no handicap. The first delivery incorrectly treated those
codes as non-zero lines and consequently reported zero identity mappings. The
accepted source-schema layer already exposes `handicap_line_norm` and
`handicap_norm_source`; #236 now preserves both raw and normalized values but
uses only the normalized value for translation readiness.

Across 577,141 valid fixture-horizon rows:

| Translation decision | Rows | Share |
|---|---:|---:|
| zero-line identity available | 342,020 | 59.26% |
| non-zero; goal-difference distribution required | 232,979 | 40.37% |
| normalized line missing/conflicting | 2,133 | 0.37% |
| invalid non-integer normalized line | 9 | <0.01% |

This correction materially changes the handoff: approximately 59% of the
historical fixture-horizon surface can supply an honest European-to-Beijing
identity probability, while the remaining non-zero surface must stay masked.

## Consumer interface for #238

Probability rows bind the canonical Beijing issue-slot key, source match,
provider role, relative horizon, market, 3/1/0 outcome, de-vig probability,
available-book count, causal grade, translation status and separate probability
and translation masks. Translation rows additionally retain raw line,
normalized line and normalization provenance. The machine contract is
`schemas/bj236_eu_odds_proxy_handoff_v1.schema.json`.

| Required field family | Decision |
|---|---|
| Historical European 1X2, initial/10h/1h | usable only as retrospective relative proxy |
| Strict-forward European decision-time feature | unavailable; source labels are not exact observation clocks |
| Zero-line BJ outcome mapping | available by identity when the normalized native line is integer 0 |
| Non-zero-line BJ outcome mapping | unavailable pending a score/goal-difference distribution |
| Asian handicap / totals | native support profiled only; no BJ three-outcome probabilities emitted |

## Reproduction and integrity

```bash
export BEIJING_LOT_DATA_ROOT=/absolute/path/to/data
python scripts/build_bj236_eu_odds.py --data-root "$BEIJING_LOT_DATA_ROOT"
python scripts/verify_bj236_eu_odds.py --data-root "$BEIJING_LOT_DATA_ROOT"
python scripts/render_bj236_eu_odds.py --data-root "$BEIJING_LOT_DATA_ROOT"
python scripts/execute_bj236_notebook.py --data-root "$BEIJING_LOT_DATA_ROOT"
```

The raw workbook and full Parquet package remain external and hash-bound. The
manifest closes the Parquet inventory and report receipt; the verifier checks
source bytes, file hashes, row-count receipts, probability triplets, namespace
separation and translation masks. Settlement, winning SP, results, payout and
the 0.65 factor are never selected into this feature layer.
