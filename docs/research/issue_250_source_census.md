# Issue #250 — BJ-UNIFIED-SOURCE-CENSUS-001

## Scope and baseline

This is an assessment-only, incremental source-role decision input. It binds the accepted `HIST-DATA-CENSUS-001` R8 release (`hist-data-census-001-r8`, commit `97a9c0a78d2fce0004cb1240113a070b980403b9`, manifest SHA-256 `ed16b29626b4af70e80cdfee3130d6d5e89cd79d09e06110d4d55570e217cdc8`, archive SHA-256 `7de5e20d0a3b2185bcaf8e4229544c28100cd2d29c9cc315adbc6afe48f4a38d`).

The census opened named SQLite assets read-only through `BEIJING_LOT_DATA_ROOT`. It neither crawled, wrote source data, backfilled, imputed, trained, chose a model, nor read outcome/settlement values for feature admissibility. Tables and columns whose names indicate results, scores, settlement, payout, hit, profit, or ROI are schema-flagged rather than value-profiled.

## Decision input

| Logical source | Role | Evidence and decision |
| --- | --- | --- |
| `beidan_xlsm` | `HISTORICAL_PROXY` | 192,709 native issue×match rows. `initial`, `10h`, and `1h` each have 12,887,754 rows. These are explicitly relative-time labels, not observation timestamps. Candidate historical p34 proxy backbone only. |
| `beidan_features` | `RAW_ONLY` | 190,746 rows of schedule/identity support with no accepted observed/capture clock. It may inform later identity investigation, not causal inference. |
| `beidan_history` | `SETTLEMENT_ONLY` | 38,463 rows. It remains label/settlement truth; never an inference feature source. |
| `beidan_live` | `RAW_ONLY` | 5,155 mutable rows; its table has a capture clock but no source clock. It is not a strict-forward backbone until a sealed snapshot supplies both clock receipts. |
| `bjdc_500_capture` | `RAW_ONLY` | 3,964,461 mutable p34 `handicap_3way` capture rows. Both clock fields exist, but 1,503 p34 rows are missing a source clock, so no source-wide strict promotion is permitted. |
| `beidan_modeling_plus`, `beidan_nowscore` | `EXCLUDE` | Derived copies of `beidan_xlsm`; lineage deduplication prevents them inflating independence or coverage. |

## Required period views

`tables/coverage_by_period.csv` records four profiling strata—not train/tune/test splits. It shows 16,192 `beidan_xlsm` match rows in calendar 2024, 1,024 from 2025-04 through 2026-04, and no prospective rows. `beidan_live` has 5,154 prospective rows, while the p34-filtered `bjdc_500_capture` table has 3,962,958 prospective capture rows. The full counts and every source's zero/unknown strata are committed rather than summarized only here.

The executed notebook exposes these backing tables together with `source_feature_availability.csv` (source × relative-time/clock availability) and `m_per_issue_distribution.csv`. The package includes the corresponding `figures/coverage_rows.svg` and `figures/m_per_issue.svg`; figures are derived views, never sole evidence.

## Intersections and lineage

- `RAW_PRESENT`: p34 relative-time `initial`/`10h`/`1h` fields are present in `beidan_xlsm`.
- `NATIVE_KEY_INTERSECTION`: exact `(issue, match_idx)` overlap between `beidan_live.matches` and `bjdc_500_capture.matches` is 1,748. No proposed mapping was used.
- `CANDIDATE_MAPPED_RANGE`: not computed because canonical identity policy is intentionally unfrozen.
- `CANONICAL_CAUSAL_INTERSECTION`: `NOT_YET_EVALUATED`, owned jointly by #251 and #252.

## Downstream decision requests

1. PI/user: accept or reject `beidan_xlsm` as the explicitly disclosed historical proxy backbone.
2. #251: determine whether schedule/identity support can resolve candidate mappings; this census does not make or consume them.
3. #252: define snapshot sealing and source/capture-clock criteria. Neither mutable current database is strict evidence now.
4. #235/#236/#237/#248: decide whether the missing source-clock receipts and 19,903 incomplete 500-capture clock rows justify targeted recovery. This issue makes no recovery change.

## Reproduction and verification

```bash
BEIJING_LOT_DATA_ROOT=/path/to/external/data python scripts/build_bj250_source_census.py
python scripts/build_bj250_source_census.py --verify-only
BEIJING_LOT_DATA_ROOT=/path/to/external/data python scripts/execute_bj250_notebook.py
python -m pytest tests/test_bj250_source_census.py -q
```

The package verifier checks full checksum closure and semantic bindings: manifest issue, source-inventory trace hash, and exact recomputation of source-role rows. The test suite remanifests role, source-trace, and manifest attacks; all must fail.
