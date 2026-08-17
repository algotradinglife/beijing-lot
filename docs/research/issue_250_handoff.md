# Issue #250 R2 handoff

[SESSION] 20260817_171000_2c600f

## Delivery state

- Branch: `engineer/bj250-rework-r1` (to be pushed over the existing PR #255 head)
- Base / prior delivery: `396c204a7ca1cc769228038b9af069c39a964147`
- Evidence package: `results/bj250_source_census_v2`
- Executed notebook: `notebooks/research/issue-250/bj250_source_census.ipynb`
- External data contract: `BEIJING_LOT_DATA_ROOT` is mandatory; all source SQLite opens use URI read-only mode.

## R1 reject root-cause classes and complete class sweep

| EV defect class | R2 corrective evidence | All same-class locations checked |
|---|---|---|
| Profiling / validation blind spot | `field_profile.csv`, `duplicate_profile.csv`, `outcome_triplet_profile.csv`; profiles declared decision fields for all 7 logical sources, labels separately | `SOURCES[*].decision_fields`, `_source_aggregate`, `_duplicate_profile`, `_snapshot_completeness`, notebook, report, verifier and tests |
| Denominator / time-strata semantics | `coverage_by_period.csv` has source denominator plus issue/match/cell counts for 2024, explicit 2025 Q1, 2025-04–2026-04, prospective, null/anomalous and every present earlier year | `_coverage_strata`, `_coverage_row`, all 7 coverage tables, report/notebook/figure backing |
| Intersection / disposition contract | `intersection_levels.csv` has all four levels; candidate lower/upper counts use explicitly stated proposed mapping; `source_role_matrix.csv` routes both forward lanes to #252 sealing criteria | `_intersections`, `_candidate_mapping`, `_roles`, package report/docs/notebook/role table |
| Verifier closure | manifest semantic hashes bind every decision-bearing table, in addition to complete checksum inventory | `verify_package`, required artifact list, 13 adversarial tests including re-manifested intersection/field/coverage/triplet/source/role/manifest attacks |

This table is the explicit same-class sweep evidence required by EV. No outcome/settlement values are used to select source roles; their completeness is measured only in separately marked label/settlement profiles.

## Completed facts / decisions

- `beidan_xlsm` remains the historical relative-time proxy backbone candidate only; `initial`/`10h`/`1h` are never called strict observed-at fields.
- `beidan_live` and `bjdc_500_capture` are `RAW_ONLY`: current files are mutable/unfrozen and do not have complete required source/capture clock evidence. Both are nevertheless routed to #252 for the precise sealing/clock policy question.
- `beidan_history` is settlement-only. Derived `beidan_modeling_plus` and `beidan_nowscore` are excluded as independent evidence via lineage roots.
- The native `beidan_live` ↔ `bjdc_500_capture` `(issue, match_idx)` intersection is exact-only. Candidate mapping is measurable but non-authoritative; canonical causal overlap remains `NOT_YET_EVALUATED` for #251+#252.

## Known limitations / explicit risks

- Mutable databases can change after this committed read. Their inventory rows are intentionally marked `MUTABLE_UNFROZEN_NO_HASH`; do not treat their dynamic counts as frozen source receipts.
- Candidate-map bounds are not identities and cannot be used to train/join/label. #251 owns acceptance.
- No `method.yaml` was provided for #250, so REQ-M preflight is not applicable.

## Verified commands

```bash
BEIJING_LOT_DATA_ROOT=/home/drwho1985/workspace/soccer/beijing-lot/data \
  /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/build_bj250_source_census.py
BEIJING_LOT_DATA_ROOT=/home/drwho1985/workspace/soccer/beijing-lot/data \
  /home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/execute_bj250_notebook.py
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python scripts/build_bj250_source_census.py --verify-only
/home/drwho1985/workspace/soccer/beijing-lot/.venv/bin/python -m pytest tests/test_bj250_source_census.py -q
```

The last focused test execution returned `13 passed`; literal verifier returned `VERIFIED=True`. One earlier chained attempt timed out only because it invoked the large external-root build twice serially; the first build completed and verified before the timeout. The final notebook execution is intentionally a fast readable layer over that verified package, while the builder remains the clean-execution entrypoint.

## Next action

Push this commit to `engineer/bj250-issue`, update PR #255 with this R2 evidence and request a fresh independent EV rerun of the builder plus semantic re-manifest attacks. Resume only for a local/small EV correction: `hermes --resume 20260817_171000_2c600f`.
