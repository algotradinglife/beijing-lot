# BJ #234 — Unified Data Source Schema (frozen contract)

Contract: BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1 (frozen 2026-08-16T00:00:00Z)

This package is the immutable interface for all #232 recovery branches (#235 BJ SP, #236 EU odds, #237 power features, #238 materializer).

## Artifacts

- `schema.sql` — versioned SQLite DDL (capture/inference/settlement namespaces)
- `pyarrow_schemas.json` — canonical PyArrow schemas for research Parquet partitions
- `domain_dictionary.csv` — column semantics and domain constraints
- `identity_crosswalk.csv` — legacy DB → canonical fixture binding
- `source_feasibility_matrix.csv` — cost/access/licensing/coverage/clock grade per source, selected source per branch
- `replacement_plan.json` — migration-free replacement plan
- `source_clock_classification.csv` — REQ-DS01 admissible-use classification with evidence
- `profile.json` — machine-readable DB profile (tables/rows/keys/ts ranges/nulls/duplicates)
- `contract.json` — machine-readable contract
- `MANIFEST.json` + `SHA256SUMS.json` — binding hashes (REQ-DS07)

## Replay

```bash
.venv/bin/python scripts/build_bj234_source_schema.py verify --package results/bj234_source_schema_v1
```
