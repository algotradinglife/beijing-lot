# Issue #250 — BJ-UNIFIED-SOURCE-CENSUS-001 R2

## Scope, method, and baseline

This is an incremental, assessment-only source-role decision input bound to `HIST-DATA-CENSUS-001 R8` (`hist-data-census-001-r8`, commit `97a9c0a78d2fce0004cb1240113a070b980403b9`, manifest SHA-256 `ed16b296…e217cdc8`). It profiles only seven declared logical source families through the externally supplied `BEIJING_LOT_DATA_ROOT` using URI read-only SQLite connections.

No source data was crawled, written, appended, normalized, imputed, backfilled, modeled, or used for profitability/ticket decisions. Labels/settlement fields are profiled separately for completeness and are never inputs to a feature-role decision. Mutable source results are explicitly `MUTABLE_UNFROZEN`, not a frozen conclusion.

## Decision input

| Logical source | Disposition | Evidence / routing |
|---|---|---|
| `beidan_xlsm` | `HISTORICAL_PROXY` | Historical p34 proxy backbone candidate only. `initial`/`10h`/`1h` carry relative-time bucket semantics, not strict observed-at timestamps. Advance its identity questions to #251. |
| `beidan_features` | `RAW_ONLY` | Identity/schedule and market-family support; no source/capture observation clock. Advance the proposed-mapping question to #251, not causal inference. |
| `beidan_history` | `SETTLEMENT_ONLY` | Label/settlement truth. Completeness is measured but it remains outside inference. |
| `beidan_live` | `RAW_ONLY` | Capture clock is present but source clock is absent; mutable/unfrozen. Advance sealing/clock criteria to #252. |
| `bjdc_500_capture` | `RAW_ONLY` | p34 `handicap_3way` capture profiled for SP, triplets and clocks. Incomplete clocks and mutable storage prevent strict-forward promotion. Advance sealing/clock criteria to #252. |
| `beidan_modeling_plus`, `beidan_nowscore` | `EXCLUDE` | Derived from `beidan_xlsm`, deliberately not independent evidence. |

## Required decision views and exact backing

`results/bj250_source_census_v2/tables/` is the source of every count; all figures have committed CSV backing.

- `source_inventory.csv`: source path, layer, lineage, R8 basis, file hash for stable assets, and explicit mutable receipt state.
- `field_inventory.csv` and `field_profile.csv`: all decision-facing keys, clocks, feature/price and label/settlement fields; denominator, null/blank and impossible-value counts.
- `coverage_by_period.csv`: source-row denominator plus exact issue/match/cell counts for calendar 2024, 2025-01–03, 2025-04–2026-04, 2026-05 onward, null/unparseable dates, and each individual earlier calendar year actually present. This closes the formerly silent 2025 Q1/null-date gap.
- `duplicate_profile.csv`: native-key duplicate groups and extra rows (or deterministic unavailable reason).
- `outcome_triplet_profile.csv`: all `initial`/`10h`/`1h` market families and the p34 capture path, with triplet denominators and missing/invalid counts.
- `intersection_levels.csv`: exactly the four declared levels. Native intersection is exact only. Candidate mapping gives a non-authoritative lower/upper range measured as `beidan_xlsm` rows having at least one candidate: lower uses issue + normalized home/away + calendar date, upper relaxes date. The canonical causal intersection is `NOT_YET_EVALUATED` pending #251 + #252.
- `source_role_matrix.csv`: machine-routing has both strict-forward candidates advancing to #252 for sealing/clock criteria even though neither is currently promoted.

## Pi/user decision gate

1. Accept/reject `beidan_xlsm` as disclosed historical proxy backbone.
2. Decide whether the measured non-authoritative candidate range justifies #251 identity work; it does not authorize a canonical join.
3. Require #252 to define a sealed source/capture-clock receipt before either live lane can become strict-forward evidence.
4. Retain `beidan_history` as settlement-only and derived copies as excluded.
5. Review field-profile / outcome-triplet gap rows to route recovery needs to #235/#236/#237/#248; #250 makes no recovery change.

## Reproduction and tamper verification

```bash
BEIJING_LOT_DATA_ROOT=/path/to/data python scripts/build_bj250_source_census.py
BEIJING_LOT_DATA_ROOT=/path/to/data python scripts/execute_bj250_notebook.py
python scripts/build_bj250_source_census.py --verify-only
python -m pytest tests/test_bj250_source_census.py -q
```

The semantic verifier binds checksum closure and hashes of all decision-bearing tables: inventory, roles, intersections, field profile, time coverage, and outcome-triplet profile. The 13-test adversarial suite mutates each kind of conclusion artifact, the source trace, role decision and manifest while rewriting the checksum inventory; each attack must fail.
