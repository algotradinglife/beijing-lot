# SCORE-PRICE-HIST-AUDIT-001 — historical correct-score price provenance

Status: `g4_frozen_price_vector_presence_and_time_semantics_unverified; no replay or strategy use`

This is a read-only data archaeology audit. It makes no prediction, calibration,
EV, q, ROI, ticket, stake, selection, or strategy claim.

## Result

The long-horizon XLSM conversion does contain a populated historical score-price
vector: `exotic_odds.market="score"` has 5,076,994 rows across 195,269 matches
in the canonical converted database. The prior shorthand that the long history
has no per-score prices is therefore incorrect.

That presence result is not market or time provenance. The audit did not
establish a provider, did not establish that the 26-column tail is Beijing p42
as opposed to another correct-score display, and did not establish that the
row-level `ts_10h` value applies to its score-price cells. The frozen G4
classification is consequently:

| Dimension | Classification |
| --- | --- |
| presence | `POPULATED` |
| provider identity | `UNRESOLVED` |
| market identity | `UNRESOLVED` |
| timestamp grade | `UNVERIFIED` |
| replay eligibility | `PROHIBITED` |
| evidence level | `D` |

The verdict is `PRICE_VECTOR_PRESENCE_AND_TIME_SEMANTICS_UNVERIFIED`. No strict
as-of replay, historical proxy analysis, score model, SP-consistency result,
or return-oriented analysis is authorized from this asset.

## G0 — source inventory and redaction

The audit opens the vendor XLSM and each SQLite candidate read-only, hashes them
before coverage inspection, and checks that their bytes remain unchanged after
inspection. Public artifacts retain only a logical identifier, filename, byte
count, SHA-256, and observed filesystem mtime; they never contain local paths,
workbook bytes, raw macro source, passwords, credentials, or database rows.

| Logical input | Filename | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `historical_xlsm` | `beidan.xlsm` | 808,551,905 | `f825020658f2b0e95715659381107c246a24ec36b87801eebb63233921072d59` |
| `xlsm_canonical` | `beidan_xlsm.sqlite` | 6,872,944,640 | `7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f` |
| `nowscore_update` | `beidan_nowscore_2026.sqlite` | 191,561,728 | `3948176d42e7799a986e406a75266fe840eadf977c21d8331146eabf31b86927` |
| `modeling_plus` | `beidan_modeling_plus_2026.sqlite` | 1,087,799,296 | `c35a42800a7998ede97c5105371cd78a293a151a9c004a6fef54081e7646fdc7` |

Filesystem mtime is inventory metadata only, never a market observation clock.

## G1 — workbook layout and mapping

The workbook data sheet resolves from workbook relationships to
`xl/worksheets/sheet1.xml`. Its two tail header rows exactly match the converter
contract:

| Group | Columns | Header | Outcomes | Converter mapping |
| --- | --- | --- | ---: | --- |
| `sclassid` | `AEH` | `sclassid` | — | matched |
| `goals` | `AEI:AEL` | `入球数` | 4 | matched |
| `half_full` | `AEM:AEU` | `半全场` | 9 | matched |
| `score` | `AEV:AFU` | `比分` | 26 | matched |

Relevant merged ranges are `AEH1:AEH2`, `AEI1:AEL1`, `AEM1:AEU1`, and
`AEV1:AFU1`. Header/layout alignment proves that the converter copied the
workbook’s intended 26 score columns; it does not identify their provider,
market, or observation time. Workbook external-link/connection/VBA metadata
were inspected statically without executing macros and without publishing their
contents. None supplied positive provider or timestamp binding evidence.

## G2 — database population and coverage

| Database logical ID | `source_meta.no_exotic` | Presence | Score-price rows | Matches with any vector | Complete valid 26-way vectors |
| --- | --- | --- | ---: | ---: | ---: |
| `xlsm_canonical` | `0` | `POPULATED` | 5,076,994 | 195,269 | 157,405 |
| `nowscore_update` | `UNKNOWN` | `EMPTY` | 0 | 0 | 0 |
| `modeling_plus` | `UNKNOWN` | `UNKNOWN` — `exotic_odds` absent | 0 | 0 | 0 |

For the canonical database, 4,523,064 values are non-null and 4,515,630 are
valid decimal prices (`>1`, finite). There are 553,930 null prices and 7,434
non-finite-or-`<=1` values. No duplicate `(match_id, market, outcome)` key was
found. Every populated match uses the same 26-outcome schema, and its outcome
labels match the workbook/header contract exactly. The frozen package contains
the complete per-calendar-year and per-issue denominators, not only this
summary.

The population audit joins 195,269 score-vector matches to the converted
`matches` table; 192,703 have both a kickoff and a `ts_10h` value. That is join
coverage only. It does not convert `ts_10h` into evidence that a score price was
observed ten hours before kickoff.

## G3 — timestamp and identity audit

The converter reads `ts_10h` from column `P`, but writes each score cell only
as `exotic_odds(match_id, market, outcome, odds)`. That table has neither a
snapshot field nor a timestamp field. The score-tail header itself has outcome
labels but no named snapshot/time header. A common match row is therefore only
coexistence, not a binding between the timestamp and a price vector.

The static evidence produced no direct provider identifier or source observation
clock for the score tail. Cached numeric cells and a timestamp elsewhere in the
same workbook row are insufficient under this audit contract. The result fails
closed as `UNVERIFIED`; it must not be described as historical pre-match Beijing
p42 SP.

## Schema reconciliation

The XLSM tail has 26 outcomes: 22 exact scorelines, explicit `4:3`, `4:4`, and
`3:4`, plus one undifferentiated `其他`. Current Beijing p42 uses 25 outcomes:
22 shared exact scorelines plus `home_other`, `draw_other`, and `away_other`.
The three historical explicit tail scorelines fall into current directional
other categories, while the historical `其他` cannot be split mechanically into
those three categories. The schemas are not mechanically equivalent.

## Reproduction and immutable evidence

The audit requires runtime-supplied source paths and deliberately does not
embed them in its evidence package:

```bash
python scripts/run_score_price_hist_audit.py audit \
  --workbook historical_xlsm=<runtime-workbook.xlsm> \
  --database xlsm_canonical=<runtime-canonical.sqlite> \
  --database nowscore_update=<runtime-update.sqlite> \
  --database modeling_plus=<runtime-modeling.sqlite> \
  --output-dir <new-audit-output> \
  --freeze-dir <new-freeze-output> \
  --frozen-at-utc <explicit-UTC>

python scripts/run_score_price_hist_audit.py verify \
  --package-dir <unpacked-package> \
  --workbook historical_xlsm=<runtime-workbook.xlsm> \
  --database xlsm_canonical=<runtime-canonical.sqlite> \
  --database nowscore_update=<runtime-update.sqlite> \
  --database modeling_plus=<runtime-modeling.sqlite>
```

The independently downloadable R5 evidence package is published with tag
`score-price-hist-audit-001-r5`. Its manifest and reproduction receipt both
bind the exact full 40-character Git commit; verification rejects abbreviated
or mismatched commit identifiers. Together with `SHA256SUMS`, source
identities, redacted structural evidence, full coverage, and classification,
they are the authority for this result. Source workbooks/databases are not
published.

## Boundary

This audit corrects an existence claim only. It does not alter
`SCORE-HCAP-HIST-001`, authorize `SP-CONSISTENCY-001A`, or change any strategy,
ticket, release, API, frontend, or production behavior. Any attempt to use this
vector requires a separately scoped Issue with positive provider/market/time
evidence and a new preregistered decision rule.
