# Issue #250 — existing-source assessment and admissible-use decision

## Decision summary

Issue #250 is an **assessment-only** census. It did not crawl, backfill, impute, train a model, construct tickets, or calculate ROI.

The historical `beidan_xlsm` source can proceed only as a **retrospective relative-time proxy**, not as strict decision-time evidence. Its role is supported by one coherent, same-source surface: native match identity and Beijing handicap line plus positive `euro_1x2` vectors at all three accepted relative horizons (`initial`, `10h`, `1h`). There are **189,587** matches satisfying that common gate.

This does not yet make the data canonical model input. Native/candidate identity reconciliation remains #251 work, while causal availability and sealing remain #252 work. Both live sources remain `RAW_ONLY`.

## What R4 got wrong and the PI correction

The rejected R4 package combined unrelated evidence:

- it counted complete `market_snapshots.v1/v2/v3` rows across all markets;
- it separately counted generic R8-eligible fields from other tables; and
- it used those unrelated counts to grant the whole source a historical role.

It also called every three-column vector an outcome triplet and copied source-row counts into a `cell_count` column. That obscured both market semantics and missingness.

The PI takeover replaces that logic with an Issue-250 scoped surface policy:

| Surface | Actual semantics | Use in #250 |
| --- | --- | --- |
| `euro_1x2` | three mutually exclusive 1X2 prices | historical-proxy role gate |
| `kelly_1x2` | derived three-value Kelly vector | descriptive only; not an independent price |
| `asian_handicap` | two prices plus a handicap line | auxiliary; not a p34 outcome triplet |
| `over_under` | two prices plus a totals line | auxiliary; not a p34 outcome triplet |
| live `handicap_3way` | p34 outcome cells | raw/unfrozen until #252 |

The generic R8 field dictionary and the scoped proxy policy are reported separately. R8's two field-by-market prohibitions—`correct_score` and `total_goals` under `exotic_odds.odds`—are preserved explicitly rather than collapsed into a generic field row.

## Coverage at the correct grain

The delivery now distinguishes:

1. logical matches;
2. market-vector rows; and
3. physical cells inside those vectors.

The 2024 historical proxy panel is the audit anchor:

| Grain | Count |
| --- | ---: |
| Matches | 16,192 |
| Market × snapshot vector rows | 3,206,016 |
| Physical vector cells | 9,618,048 |
| Non-null physical cells | 8,438,821 |

The earlier rejected report showed only `16,192` as if it were cell coverage. The corrected period table provides market × snapshot missingness for every represented year, calendar 2024, 2025-01–03, 2025-04–2026-04, 2026-05 onward, and null/unparseable dates.

Notable source-period facts:

- the historical proxy container has 195,269 rows across 701 issues, including 16,192 matches in 2024, 3,829 in 2025-01–03, and 1,024 in the 2025-04–2026-04 stratum;
- it also has 2,566 rows with null/unparseable kickoff dates, requiring fail-closed treatment;
- the settlement source covers 17,873 rows in 2025-04–2026-04 and 397 rows from 2026-05 onward, but settlement presence does not create feature availability;
- the mutable p34 capture currently covers 13 issues and 1,487 logical matches; it is an observation, not a frozen receipt.

## Identity and intersection findings

The four levels remain deliberately distinct:

- `RAW_PRESENT`: the historical relative-time surfaces physically exist;
- `NATIVE_KEY_INTERSECTION`: 1,748 exact `(issue, match_idx)` matches between the two live lanes;
- `CANDIDATE_MAPPED_RANGE`: 188,197–188,199 historical rows under a proposed normalized team/date mapping;
- `CANONICAL_CAUSAL_INTERSECTION`: not yet evaluated.

The candidate range is not permission to join, train, or propagate labels. #251 must decide identity; #252 must decide clock/sealing semantics.

## Source dispositions

| Source | Disposition | Reason |
| --- | --- | --- |
| `beidan_xlsm` | `HISTORICAL_PROXY` | 189,587 common valid Euro 1X2 matches across all three relative horizons |
| `beidan_features` | `RAW_ONLY` | support data; no independently accepted causal lane |
| `beidan_history` | `SETTLEMENT_ONLY` | result/SP truth, never inference input |
| `beidan_live` | `RAW_ONLY` | clock/sealing policy incomplete |
| `bjdc_500_capture` | `RAW_ONLY` | mutable and clock/sealing policy incomplete |
| `beidan_modeling_plus` | `EXCLUDE` | derived copy, not independent evidence |
| `beidan_nowscore` | `EXCLUDE` | derived copy, not independent evidence |

## Integrity and reproducibility

The package is write-once and published by staged atomic rename after file and directory `fsync`; an existing target is never deleted or replaced. The verifier binds **every** payload—including coverage, availability, duplicates, REQ evidence, report, and figures—to an externally held anchor. Rewriting a changed payload, manifest, and checksum file still fails against the original anchor.

The executed notebook is [bj250_source_census.ipynb](../../notebooks/research/issue-250/bj250_source_census.ipynb). Machine-readable evidence is under `results/bj250_source_census_v3/`.

## PI conclusion

The useful outcome is not “all required data are ready.” It is narrower:

- the large historical relative-time panel is sufficiently coherent to justify the next identity and temporal assessments;
- its Euro proxy is useful for historical exploration but is not yet strict causal evidence;
- market layouts must be translated explicitly before an M×3 p34 tensor is built;
- recovery work should be driven by measured gaps after #251/#252, not by file presence alone.

Therefore #250 can close after independent EV and user/PI acceptance of this source-role decision. It should unlock the assessment sequence, not authorize model training by itself.

## Reproduction

```bash
BEIJING_LOT_DATA_ROOT=/path/to/data python scripts/build_bj250_source_census.py
python scripts/render_bj250_notebook.py
python scripts/execute_bj250_notebook.py
python scripts/build_bj250_source_census.py --verify-only --trusted-anchor /outside/package/expected-anchor.json
python -m pytest tests/test_bj250_source_census.py -q
```
