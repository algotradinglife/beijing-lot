# HIST-DATA-CENSUS-001 — long-horizon historical asset census

Status: `frozen data-eligibility audit; pending fresh independent EV`

This is data archaeology, not a modelling or strategy result. It does not fit a
model, choose features, generate a prediction, compute calibration/EV/ROI, or
make a ticket recommendation.

## Frozen G0 boundary

The audit first froze a metadata-only inventory before opening any source
coverage, schema, workbook cell, CSV row, or capture manifest payload. The
final release receipt and `source_inventory.csv` carry the authoritative
point-in-time count and inventory SHA-256. They are not duplicated in prose
because the live capture roots can legitimately acquire new assets between
separate freezes.

The public inventory contains logical IDs, repository-relative locators,
filenames, byte counts and SHA-256 values only. It does not contain local
absolute paths, private URLs, credentials, source bytes, workbook cells or VBA
content. Workbook inspection is safe package-structure metadata only; macros
are never executed.

At the audit boundary the inventory contained:

| Candidate class | Frozen evidence |
| --- | ---: |
| immutable forward-capture bundles | exact count in `source_inventory.csv` |
| research-artifact bundles and freeze bundles | exact count in `source_inventory.csv` |
| SQLite databases and sidecars | exact count in `source_inventory.csv` |
| CSV/Parquet-like exports and JSON artifacts | exact count in `source_inventory.csv`; sensitive configuration remains excluded |
| auxiliary/non-tabular repository files | deterministic raw-only inventory rows |
| repository and runtime-supplied workbooks | filenames, byte counts and SHA-256 only |

Only bundle rows that pass exact `SHA256SUMS` coverage and content verification
can contribute a strict candidate count; the exact status/count matrix is in
`bundle_integrity.csv`.

## Source-change boundary

The live collector continued writing while this audit ran. Any frozen logical
asset that changes after G0 is explicitly marked `SOURCE_DRIFT_FAIL_CLOSED` in
the evidence package and contributes no schema, coverage, price, or outcome
evidence to that release. Later-discovered assets are likewise excluded rather
than retroactively added to G0.

This is an evidence boundary, not a data-loss claim. A future integration or
snapshot capability must obtain an immutable SQLite snapshot before those
mutable assets can be used in a frozen census or strict replay.

## Main historical findings

The stable XLSM-derived canonical database contains 195,269 matches across 701
issues. Its `exotic_odds` table has 7,615,491 rows:

| Historical market label | Rows | Observed outcome labels | Admissible boundary |
| --- | ---: | ---: | --- |
| total goals | 781,076 | 4 | historical `odds` is `PROHIBITED`: the 4-way partition is not mechanically current 8-way p40, and mapping/market/time provenance is unproved; non-price labels/context remain separately classified |
| half/full | 1,757,421 | 9 | `historical_proxy; descriptive_only` until price-time binding is established |
| score | 5,076,994 | 26 | special prohibition below |

The modelling-plus XLSM derivative has 201,270 match rows across 735 issues.
Its ranks, named Euro snapshots and line/context fields are historical proxies,
not evidence that each value was observable at a strict decision cutoff.
Terminal fields such as score, final odds, result code, winning SP, hit, payout
or settlement state are never placed in a pre-match feature view.

### Correct-score dependency: unchanged from #37

`SCORE-PRICE-HIST-AUDIT-001` remains authoritative for the historical
26-outcome score-price vector. Its numeric presence is real, but the audit did
not establish provider identity, Beijing p42 market identity, a source
observation clock, or a binding between `ts_10h` and score-price cells. The
historical 26-way schema is also not mechanically equivalent to current 25-way
p42.

Therefore the source's correct-score `odds` field is frozen as:

```text
admissible_use = prohibited
integration_decision = PROHIBITED
destination_layer = none
timestamp_grade = UNVERIFIED_MARKET_AND_TIME
```

It is not a historical Beijing p42 pre-match SP panel and cannot be used for
strict replay, proxy price comparison, score-model evaluation, or ROI research.

### Total-goals schema compatibility: explicit p40 prohibition

The same historical `exotic_odds` source contains a four-outcome
`total_goals` price partition, while the declared current Beijing p40 contract
has eight outcomes. A matching market name does not establish an outcome
mapping, Beijing market identity, or row-level price-time binding. Its
`odds` field is therefore frozen as `prohibited` / `PROHIBITED` at the
`field_market` level for `total_goals`. This is a price-vector boundary only:
historical labels and non-price context retain their separately disclosed
proxy or label classifications. A future positive p40 mapping plus
market/time-provenance audit is required before any historical p40 price use.

## Forward immutable subset

The audit found checksum-valid immutable capture bundles with declared
`complete_forward_open` rows:

| Play | Market | Rows | Classification |
| ---: | --- | ---: | --- |
| 40 | total goals | exact released `bundle_integrity.csv` count | `conditional_strict_forward` only after non-empty source **and** capture clocks plus row-level sale/open and cutoff checks |
| 42 | correct score | exact released `bundle_integrity.csv` count | `conditional_strict_forward` only after the same source/capture-clock and row-level checks |
| 41 | upper/lower odd/even | 0 qualified | no strict price subset; capture rows remain unclassified |
| 51 | half/full | 0 qualified | no strict price subset; capture rows remain unclassified |

“Conditional strict forward” is deliberately narrower than a blanket source or
family classification. Terminal, post-cutoff, incomplete and backfill rows stay
outside `strict_asof_v1` even when stored beside valid captures.

## Per-play readiness

| Play | Labels | Features | Prices | Chronological split | Coarse baseline | ROI |
| ---: | --- | --- | --- | --- | --- | --- |
| 34 handicap 3/1/0 | ready | historical proxy | conditional forward only | historical proxy | constructible | not ready |
| 40 total goals | ready | historical proxy | conditional strict forward | conditional strict forward | constructible | not ready |
| 41 upper/lower odd/even | ready | historical proxy | not ready | historical proxy | constructible | not ready |
| 42 correct score | ready from settlement truth | historical proxy | conditional strict forward only; historical score prices prohibited | conditional strict forward | constructible | not ready |
| 51 half/full | ready | historical proxy | not ready | historical proxy | constructible | not ready |

`constructible` means only that a fixed, non-optimized data pipeline can be
specified under its stated proxy boundary. It does not say the model predicts
well, that a price is tradable, or that the play is profitable.

## Frozen integration decisions

| Asset/table class | Decision | Destination | Required guard |
| --- | --- | --- | --- |
| immutable p40/p42 forward-complete-open bundle subset | `INTEGRATE_STRICT` | `strict_asof_v1` | exact bundle integrity, non-empty source and capture clocks, row-level capture/cutoff/sale proof; exclude terminal/backfill rows |
| XLSM named snapshots, rankings, context and raw historical 3-way exports | `INTEGRATE_PROXY` | `historical_exploratory_v1` | preserve source hash/time grade; do not call as-of |
| scores, result codes, final/winning SP and settlement state | `SETTLEMENT_ONLY` | `settlement_truth_v1` | terminal guard; never export as a feature or pre-match price |
| historical XLSM correct-score price vector | `PROHIBITED` | none | #37 provider/market/time failure and 26-vs-25 schema mismatch |
| historical XLSM total-goals price vector | `PROHIBITED` | none | 4-way historical schema is not mechanically current 8-way p40; mapping/market/time provenance unproved |
| raw workbooks / unknown auxiliary artifacts | `KEEP_RAW_ONLY` | raw provenance | future source-specific contract required |
| G0-drifting live DB assets | `PROHIBITED` in this freeze | none | take a new immutable snapshot before inspection |

## Designed research views (not productionized)

1. `strict_asof_v1`: immutable/append-only evidence with non-empty source and
   capture clocks, cutoff proof, open sale state and no terminal inputs.
2. `historical_exploratory_v1`: row-level proxy grades retained; terminal fields
   removed before any feature projection.
3. `settlement_truth_v1`: result, special-state and payout truth only; it cannot
   join into either pre-match view as a feature.

No database migration is performed by this Issue.

## Scope for `HIST-DATA-INTEGRATION-001`

The later Engineer-owned integration Issue should:

1. create immutable source-version and snapshot records before ingestion;
2. normalize source, bundle, batch, capture/source clock, sale-state and
   checksum lineage separately from match/output values;
3. materialize the three views above with an enforced terminal-field denylist;
4. use explicit, source-specific deduplication keys rather than team-name or
   row-adjacency inference;
5. ingest only the p40/p42 `forward_complete_open` subset with non-empty
   source and capture clocks into strict staging;
6. keep historical XLSM context in proxy staging and retain correct-score and
   four-way total-goals price odds raw-only/prohibited; and
7. create an immutable snapshot workflow for continuously changing live SQLite
   databases before any later frozen audit or replay.

## Reproduction and verification

Runtime source paths are supplied locally and are never emitted by these
commands:

```bash
python scripts/run_hist_data_census.py inventory \
  --source-root <main-repository-root> \
  --runtime-input historical_xlsm=<runtime-workbook.xlsm> \
  --output-dir <new-inventory-output> \
  --freeze-dir <new-inventory-freeze> \
  --frozen-at-utc <explicit-UTC>

python scripts/run_hist_data_census.py audit \
  --inventory-package <verified-g0-package> \
  --source-root <main-repository-root> \
  --runtime-input historical_xlsm=<runtime-workbook.xlsm> \
  --output-dir <new-census-output> \
  --freeze-dir <new-census-freeze> \
  --frozen-at-utc <explicit-UTC>

python scripts/run_hist_data_census.py verify \
  --inventory-package <verified-g0-package> \
  --package-dir <unpacked-census-package> \
  --skip-current-source-check
```

The immutable package's `manifest.json`, `SHA256SUMS`, source inventory hash,
redaction receipt and full 40-character Git commit are the authority for each
frozen run. A clean checkout with the same runtime-supplied source identities
reproduces the same public evidence bytes; changed live sources are explicitly
reported as drift rather than silently substituted.

## Boundary

This audit does not authorize a strategy, score model, price comparison,
backtest, EV/q/ROI analysis, ticket, production integration, collector change,
or frontend/API release. It only identifies which next capability can make a
narrower, verifiable claim.
