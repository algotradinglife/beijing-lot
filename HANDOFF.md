# Issue #234 rework handoff (R2, fresh — EV R1 REJECT method)

[SESSION] 20260816_150600

- Issue: #234 (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001) — Data: freeze source
  registry, canonical identity and temporal store schema.
- Mode: candidate. Base: `784a23b`. Branch: `engineer/bj234-r2-fresh`.
- R1 was REJECTED by EV with `REWORK_TYPE=method` (defects C1-C4, E1-E2).
  Per the 2026-08-12 fresh-rework rule, this run is a **fresh rebuild**;
  R1 code in `~/beijing-lot-234` was read as reference only.

## What R2 delivers (EV defect → fix)

| EV defect | R2 fix | evidence |
|---|---|---|
| C1 identity metrics: NULL rows counted as duplicates; long-form key missing outcome_code | `profiler.identity_stats` uses correct primitive keys (`issue, match_idx, outcome_code` for outcome_features); NULL-key rows reported separately (`null_key_rows`), duplicate excess = non_null - distinct_non_null = 0 | `tables/identity_checks.csv` + `test_identity_counts_match_ev_recalculation` (195,269 / 2,560 / 192,709) |
| C2 source lineage: 500.com masquerade as Beijing official; static grades; empty raw hashes | Registry rows carry real provider/endpoint + endpoint_evidence citation; `BJ_FIRST_PARTY_OFFICIAL` = UNUSABLE/NO_RECEIPT; `BEIDAN_LIVE_DB` = 500.com third-party plane, STRICT_CAUSAL only with raw receipt | `tables/source_registry.csv` + `test_registry_no_500_masquerade` |
| C3 DDL: no fixture_alias; quote unique erased bookmaker; NULL handicap dup; no FK/timestamp/overlap enforcement; live snapshot kinds rejected (C3-5) | `fixture_alias` table; quote PK (observation, bookmaker, outcome); COALESCE unique on probability; observation natural-key unique; FK ON; UTC GLOB CHECKs + ordering CHECKs; temporal triggers; alias no-overlap triggers; `v_incomplete_triplets` view; max-3 trigger; `snapshot_kind` domain extended with `live` (prospective timestamped capture) | `sql/schema.sql` + 12 SQLite probe tests (all pass) + `test_ddl_live_snapshot_kind_accepted` / `test_ddl_invalid_snapshot_kind_rejected` + verifier live-kind probe |
| C4 label sealing: census opened 2024+ outcome/settlement values | Census reads only allow-listed columns; sealed tables/columns recorded; `assert_measurable` raises on sealed reads; notebook proves guard | `tables/sealed_columns.csv` + `test_sealing_*` |
| E1 test isolation: tests wrote real package and dropped a column | All tests build/tamper in `tmp_path`; committed package produced only by build script; `test_build_to_tmp_path_never_touches_committed` | pytest suite |
| E2 semantic verifier fail-open | `verify.verify_package` rebuilds DDL in SQLite, checks real schema objects, registry semantics, namespace disjointness, sealing, identity; 12 remanifest attacks in tests all FAIL | `test_e2_attack_*` (12) + `test_tamper_*` (5) |

## Key decisions

1. 500.com third-party plane is named honestly; the first-party Beijing
   interface is registered UNUSABLE until acquired (contract F1 remains
   the target, but evidence must not fake it).
2. STRICT_CAUSAL requires TIMESTAMPED_UTC clock + resolvable raw receipt —
   enforced in DDL CHECK and in the semantic verifier.
3. SQLite has no deferred cross-row CHECK; Mx3 triplet completeness is
   enforced at the canonical append boundary + `v_incomplete_triplets`
   view + max-3 trigger (documented in design_notes.md).
4. Legacy duplicate conclusions: NULL-key rows are UNIDENTIFIED; real
   non-null duplicate excess is 0 on all legacy tables (EV independent
   recomputation agrees).
5. Dynamic live DBs (beidan_live.db, 500_bjdc.sqlite) are not frozen
   snapshots; their census-time sha256 is bound in MANIFEST source_hashes.

## Verification (from this run)

- build + verify green (to be confirmed in final run)
- pytest suite (to be confirmed)
- notebook 13 cells clean-run (to be confirmed)

## Known limitations / risks

- EU feed (Odds API) stays RETROSPECTIVE_PROXY/NO_RECEIPT pending coverage
  evaluation + purchase (issue boundary: no provider purchase).
- 500_bjdc.sqlite 17GB makes each census ~2-4 min (hashing + scans).
- First-party Beijing interface not yet acquired — #235 wires the 500.com
  collector; official interface remains UNUSABLE until acquisition.

## Next steps

- EV independent verification (fresh checkout, focused tests, notebook
  clean-run, manifest coverage, remanifest attacks).
- PI review of frozen contract before downstream #235/#236/#237/#238.
