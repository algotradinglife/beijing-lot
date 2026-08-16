# BJ #234 — HANDOFF (Engineer delivery)

Contract: BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (frozen 2026-08-16)
Branch: engineer/bj234-source-schema
HEAD: see git log (delivery commit on this branch)

## What was delivered

1. **Profiling evidence (executed notebook)** — `notebooks/research/issue-234/bj234_source_schema.ipynb`
   (15 code cells, all executed, 0 errors). Profiles all four source DBs
   (beidan_xlsm.sqlite, beidan_features.db, beidan_history.db, beidan_live.db)
   + #203/#214/#229 packages: tables, rows, keys, timestamp ranges, nulls,
   duplicates, journal modes, clock semantics.
2. **Versioned contract package** — `results/bj234_source_schema_v1/`
   - `schema.sql` — versioned SQLite DDL (capture / inference / settlement namespaces)
   - `pyarrow_schemas.json` — canonical PyArrow schemas for research Parquet
   - `domain_dictionary.csv` — column semantics + domain constraints
   - `identity_crosswalk.csv` + `identity_rule.json` — REQ-DS02 binding
   - `source_feasibility_matrix.csv` — 8 sources × cost/access/licensing/coverage/clock + selected source per branch
   - `replacement_plan.json` — migration-free replacement (no backward-compat tax)
   - `source_clock_classification.csv` — REQ-DS01 classification with evidence
   - `profile.json` — machine-readable profile
   - `contract.json` — machine-readable contract
   - `MANIFEST.json` + `SHA256SUMS.json` — REQ-DS07 hash binding
3. **Reusable code** — `src/source_schema/` (contract, schemas, profiler,
   crosswalk, feasibility, publication) + `scripts/build_bj234_source_schema.py`
   (build/verify/preflight) + `scripts/build_bj234_notebook.py` +
   `scripts/execute_bj234_notebook.py`.
4. **Tests** — `tests/test_bj234_source_schema.py` (29 tests incl. tamper
   self-tests attacking DDL/outcome-domain/manifest/crosswalk).

## Key decisions and rationale

- **Canonical identity**: `fixture_id` unique within `issue_code x match_idx`,
  deterministic sha256-derived. Legacy DBs bind via crosswalk; xlsm's 2560
  NULL-identity rows are *rejected* by canonical constraints, not migrated.
- **Clock semantics**: only `beidan_live.db` is STRICT_CAUSAL today
  (ISO-8601 Z snapshot_ts, prospective 2026-05+). xlsm `snapshot` column holds
  labels (initial/10h/1h/final) — RETROSPECTIVE_PROXY. history DB has no
  settled timestamp — SETTLEMENT_ONLY. features DB mixed kickoff formats —
  RETROSPECTIVE_PROXY.
- **Namespaces**: physically separate capture / inference / settlement tables;
  settlement carries no 0.65 coefficient (downstream ticket metadata only).
- **Stack**: SQLite WAL (one-writer append-only) + immutable partitioned
  Parquet read by pandas/PyArrow; no new service until measured concurrency
  requires it (live DB 262 MB / 1.49M snapshots today).
- **Source selection per branch**: #235 → Beijing official instant-SP
  (prospective) + beidan_live (2026-05+); #236 → Odds API (strict candidate,
  coverage verification pending) + xlsm/features as proxy; #237 → internal
  results + football-data; #238 consumes this contract's DDL.

## Known issues / risks

- `beidan_features.db` has no `match_idx` column — identity resolution must
  join kickoff/home/away into canonical fixtures; unresolved rows → UNRESOLVED.
- xlsm 1899-12-30 kickoff garbage (6 rows) and time-only `08:00:00` strings
  in features DB — excluded from strict temporal use.
- Odds API purchase requires PI/user authority (boundary respected).
- Live DB is actively appended by the collector; profile is a point-in-time
  snapshot, re-bind at each build.

## Next steps

1. EV audit (fresh checkout, re-run tests + notebook clean-run + package verify).
2. PI review; then #235/#236/#237/#238 consume `schema.sql` + crosswalk +
   feasibility matrix as the frozen interface.

## Reproduce

```bash
.venv/bin/python scripts/build_bj234_source_schema.py build     # publish package
.venv/bin/python scripts/build_bj234_source_schema.py verify    # replay
.venv/bin/python scripts/build_bj234_source_schema.py preflight --worktree .
.venv/bin/python scripts/build_bj234_notebook.py                # build+execute notebook
.venv/bin/python -m pytest tests/test_bj234_source_schema.py -q
```
