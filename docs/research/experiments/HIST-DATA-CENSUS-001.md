# HIST-DATA-CENSUS-001 — long-horizon historical asset census

Status: `frozen data-eligibility audit; pending fresh independent EV`

This is data archaeology, not a modelling or strategy result. It does not fit a
model, choose features, generate a prediction, compute calibration/EV/ROI, or
make a ticket recommendation.

## Frozen G0 boundary

The audit first froze a metadata-only inventory before opening any source
coverage, schema, workbook cell, CSV row, or capture manifest payload. The
final release receipt carries the authoritative inventory SHA-256; this prose
reports only the corresponding frozen inventory count of 2,649 logical assets.

The public inventory contains logical IDs, repository-relative locators,
filenames, byte counts and SHA-256 values only. It does not contain local
absolute paths, private URLs, credentials, source bytes, workbook cells or VBA
content. Workbook inspection is safe package-structure metadata only; macros
are never executed.

At the audit boundary the inventory contained:

| Candidate class | Count |
| --- | ---: |
| immutable forward-capture bundles | 2,117 |
| research-artifact bundles | 308 |
| freeze bundles | 1 |
| SQLite databases | 17 |
| SQLite sidecars | 18 |
| CSV/Parquet-like tabular exports | 53 |
| JSON artifacts | 65 (one sensitive configuration excluded) |
| auxiliary/non-tabular repository files | 30 |
| workbooks | 39 repository workbooks + 1 runtime-supplied vendor workbook |

All 2,426 immutable bundles selected from the G0 inventory passed exact
`SHA256SUMS` coverage and content verification in the read-only audit.

## Source-change boundary

The live collector continued writing while this audit ran. Four frozen logical
assets—the WAL/SHM sidecars of the live and 500-BJDC databases—changed after
G0. They are explicitly marked `SOURCE_DRIFT_FAIL_CLOSED` in the evidence
package and contribute no schema, coverage, price, or outcome evidence to this
release. Four later-discovered assets are likewise excluded rather
than retroactively added to G0.

This is an evidence boundary, not a data-loss claim. A future integration or
snapshot capability must obtain an immutable SQLite snapshot before those
mutable assets can be used in a frozen census or strict replay.

## Main historical findings

The stable XLSM-derived canonical database contains 195,269 matches across 701
issues. Its `exotic_odds` table has 7,615,491 rows:

| Historical market label | Rows | Observed outcome labels | Admissible boundary |
| --- | ---: | ---: | --- |
| total goals | 781,076 | 4 | `historical_proxy; descriptive_only` until price-time binding is established |
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

## Forward immutable subset

The audit found checksum-valid immutable capture bundles with declared
`complete_forward_open` rows:

| Play | Market | Rows | Classification |
| ---: | --- | ---: | --- |
| 40 | total goals | 45,567 | `conditional_strict_forward` only after row-level source/capture time, sale/open and cutoff checks |
| 42 | correct score | 20,501 | `conditional_strict_forward` only after the same row-level checks |
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
| immutable p40/p42 forward-complete-open bundle subset | `INTEGRATE_STRICT` | `strict_asof_v1` | exact bundle integrity, row-level capture/cutoff/sale proof; exclude terminal/backfill rows |
| XLSM named snapshots, rankings, context and raw historical 3-way exports | `INTEGRATE_PROXY` | `historical_exploratory_v1` | preserve source hash/time grade; do not call as-of |
| scores, result codes, final/winning SP and settlement state | `SETTLEMENT_ONLY` | `settlement_truth_v1` | terminal guard; never export as a feature or pre-match price |
| historical XLSM correct-score price vector | `PROHIBITED` | none | #37 provider/market/time failure and 26-vs-25 schema mismatch |
| raw workbooks / unknown auxiliary artifacts | `KEEP_RAW_ONLY` | raw provenance | future source-specific contract required |
| G0-drifting live DB assets | `PROHIBITED` in this freeze | none | take a new immutable snapshot before inspection |

## Designed research views (not productionized)

1. `strict_asof_v1`: immutable/append-only evidence with capture and cutoff
   proof, open sale state and no terminal inputs.
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
5. ingest only the p40/p42 `forward_complete_open` subset into strict staging;
6. keep historical XLSM context in proxy staging and retain correct-score price
   odds raw-only/prohibited; and
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
