# Issue #234 rework handoff (R2, fresh — EV R1 REJECT method)

[SESSION] 20260816_144119_dae29e

- Issue: #234 (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001) — Data: freeze source
  registry, canonical identity and temporal store schema.
- Mode: candidate. Base: `784a23b`. Branch: `engineer/bj234-r2-fresh`.
- PR: https://github.com/algotradinglife/beijing-lot/pull/247 (Closes #234)
- HEAD: `9a13d66` (144c988 verified state + same_class_sweep evidence)
- R1 was REJECTED by EV with `REWORK_TYPE=method` (defects C1-C4, E1-E2).
  Per the 2026-08-12 fresh-rework rule, this run is a **fresh rebuild**;
  R1 code in `~/beijing-lot-234` was read as reference only.

## What R2 delivers (EV defect → fix)

| EV defect | R2 fix | evidence |
|---|---|---|
| C1 identity metrics: NULL rows counted as duplicates; long-form key missing outcome_code | `profiler.identity_stats` uses correct primitive keys (`issue, match_idx, outcome_code` for outcome_features); NULL-key rows reported separately (`null_key_rows`), duplicate excess = non_null - distinct_non_null; fail-closed key-column existence guard | `tables/identity_checks.csv` + `test_identity_*` (EV numbers reproduced: 195,269 / 2,560 / 192,709 / excess=0) |
| C2 source lineage: 500.com masquerade as Beijing official; static grades; empty raw hashes | Registry rows carry real provider/endpoint + endpoint_evidence citation; `BJ_FIRST_PARTY_OFFICIAL` = UNUSABLE/NO_RECEIPT; `BEIDAN_LIVE_DB` = 500.com third-party plane, STRICT_CAUSAL only with raw receipt (DDL CHECK) | `tables/source_registry.csv` + `test_registry_no_500_masquerade` |
| C3 DDL: no fixture_alias; quote unique erased bookmaker; NULL handicap dup; no FK/timestamp/overlap enforcement | `fixture_alias` table; quote PK (observation, bookmaker, outcome); COALESCE unique on probability + observation natural-key; FK ON; UTC GLOB CHECKs + ordering CHECKs; temporal triggers; alias no-overlap triggers; `v_incomplete_triplets` view; max-3 trigger | `sql/schema.sql` + 12 SQLite probe tests (all pass) |
| C4 label sealing: census opened 2024+ outcome/settlement values | Census reads only allow-listed columns; sealed tables/columns recorded; `assert_measurable` raises on sealed reads; bounded scans on 51M/20M-row tables | `tables/sealed_columns.csv` + `test_sealing_*`; notebook cell 4 |
| E1 test isolation: tests wrote real package and dropped a column | All tests build/tamper in `tmp_path`; committed package produced only by build script; `test_build_to_tmp_path_never_touches_committed` | pytest suite |
| E2 semantic verifier fail-open | `verify.verify_package` rebuilds DDL in SQLite, checks real schema objects, registry semantics, namespace disjointness, sealing, identity; 12 remanifest + 5 tamper attacks all FAIL | `test_e2_attack_*` + `test_tamper_*` |

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
   non-null duplicate excess is 0 on beidan_xlsm tables (EV independent
   recomputation agrees).  beidan_features.matches has 3 REAL duplicate
   match_id rows (190,743 distinct of 190,746) — named, not hidden.
5. Dynamic live DBs (beidan_live.db, 500_bjdc.sqlite) are not frozen
   snapshots; their census-time sha256 is bound in MANIFEST source_hashes.

## Verification (confirmed)

- `build` + `verify`: VERIFIED (semantic checks pass; 19 files byte-bound)
- `pytest tests/test_bj234_source_schema.py`: 44 passed
- Notebook: 11/11 code cells executed, 0 errors (clean run)
- MANIFEST source_hashes: 7 database SHA-256 receipts

## Fresh-audit rework pass (2026-08-16, session 20260816_1550 — pre-EV self-audit)

R2 was re-verified from a fresh auditor perspective before submission. Three
internal inconsistencies found and fixed (same-class sweep, EV R1 "next EV
looks outside your declared scope" rule):

1. **REQ-DS05 builder/verifier drift** — `builder.py` computed REQ-DS05 by
   full column-set intersection across inference/proxy/settlement, but join
   keys (`fixture_id`, `issue_code`, `match_idx`, …) are shared by design, so
   the evidence row was permanently FAIL while the semantic verifier's
   `check_namespaces` correctly exempted join keys. Single source of truth
   added in `ddl.namespace_semantic_overlap()` / `ddl.namespaces_disjoint()`
   (join-key-exempt); both builder evidence and verifier consume it. REQ-DS05
   now PASS in `req_ds_evidence.csv`.
2. **REPLAY portability** — `replay_md` hardcoded an absolute R1 worktree
   path (`~/beijing-lot-234/.venv/bin/python`), unreproducible from a fresh
   checkout. Rewritten to relative `python3 scripts/...` commands with
   `DATA_ROOT` override note.
3. **same-class sweep evidence closure** — the EV R1 mandate document
   (`contract/same_class_sweep.md`, six-category complete-sweep evidence)
   existed only as a manually committed file inside the immutable package;
   a rebuild deleted it and verify would not notice. Moved the source of
   truth to `docs/bj234_same_class_sweep.md`; `builder` copies it into the
   package deterministically; `verify.check_sweep_evidence` fails closed if
   the file or any required sweep category is missing; two tests added
   (`test_sweep_evidence_present_and_complete`,
   `test_e2_attack_delete_sweep_evidence`).

Same-class sweep performed: all presence-only/string checks in builder
(DS01..DS08 recomputed from measured facts), all verifier semantic checks
(byte manifest, DDL rebuild probes, registry/namespace/sealing/identity/
sweep), and the test isolation boundary (tests build/tamper in `tmp_path`
only — re-verified green in a clean environment after a concurrent session
rebuilt the committed package mid-run).

## Known limitations / risks

- EU feed (Odds API) stays RETROSPECTIVE_PROXY/NO_RECEIPT pending coverage
  evaluation + purchase (issue boundary: no provider purchase).
- 500_bjdc.sqlite 17GB makes each census ~2-4 min (hashing + bounded scans).
- First-party Beijing interface not yet acquired — #235 wires the 500.com
  collector; official interface remains UNUSABLE until acquisition.
- Same-class out-of-scope areas documented in
  `contract/same_class_sweep.md` §6 for next EV probing.

## Next steps

- EV independent verification (fresh checkout, focused tests, notebook
  clean-run, manifest coverage, remanifest attacks).
- PI review of frozen contract before downstream #235/#236/#237/#238.
