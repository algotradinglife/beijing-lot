# The single data entry (catalog)

Status: established 2026-10-06; `settlement` registered as the first dataset.
Authoritative implementation: `packages/beidan/inst/python/beidan_backend/catalog/`.

## Why

Three things had drifted apart, each with a measurable symptom:

1. **Data locations.** Four root conventions coexisted (`BEIJING_LOT_DATA_ROOT` 93
   references, `BEIJING_LOT_RUNTIME_ROOT` 18, `BEIDAN_LIVE_SQLITE` 7,
   `BEIDAN_PARQUET_ROOT` 3) plus a hard-coded `data/derived/500_bjdc/500_bjdc.sqlite`
   in 20+ files.
2. **Database structure.** 16+ files declared their own `CREATE TABLE`. Two
   "unified" schema contracts existed as research deliverables — BJ-234
   `source_schema` and BJ-253 `physical_schema`, overlapping only on
   `source_registry` — and **production adopted neither**: `control.sqlite` reports
   `titan_clean_control_v1`, and the discovery/settlement/market stores each use
   bespoke tables.
3. **Management code.** Collectors, layouts, schema contracts, releases and
   retention were described across `config/*.json` and a NAS `registry/` of 18
   files; no single document said what data exists, where, with what structure,
   owned by whom.

## Design

```
beidan_backend/catalog/
  paths.py      roots + location resolution (fail closed)
  registry.py   catalog reads + schema registry
```

### Roots (one variable each, no machine defaults)

| Tier | Variable | Meaning |
|---|---|---|
| `frozen` | `BEIDAN_PARQUET_ROOT` | persistent store (NAS Parquet) |
| `hot` | `BEIDAN_HOT_ROOT` | short-lived working set (NVMe) |
| `data` | `BEIDAN_DATA_ROOT` | disposable scratch, recollectable |

`root_path()` raises — never falls back — on an unknown tier, an unset variable, a
relative path, or a missing directory. This is the pattern already proven by the
deleted `physical_schema.resolve_data_root`.

### Locations

A location is the token `tier:relative/path`. `location()`, `dataset_path()` and
`schema_path()` own the path shape, so consuming code never writes an absolute
path or repeats `datasets/<name>/versions/<version>`. This is the single welding
point the repository lacked.

### Catalog and schema registry

- `<frozen>/registry/catalog.json` (`beijing_lot_catalog_v1`) is the only list of
  what data exists: kind, format, location token, version, `schema_id`, owner,
  retention state. Reading it is validated; a malformed catalog stops the caller
  rather than silently yielding an empty dataset universe.
- `<frozen>/schemas/<schema_id>.json` (`beijing_lot_schema_registry_v1`) is the
  authoritative column contract per dataset version, **derived from the actual
  Parquet** so it cannot drift from the bytes. `beidan::parquet_type_map()` turns
  its Arrow types into the R boundary types.

## Removed (superseded)

The two research schema contracts were deleted, not frozen: production never used
them, and `catalog/` is their authoritative replacement.

- `src/physical_schema/` (BJ-253) and `src/schema_integration/` (BJ-254), with
  their self-only scripts and tests.
- `src/source_schema/{ddl,builder,identity,feasibility,plan,handoff,manifest}.py`
  and the BJ-234 build script/test — the candidate schema the census never
  produced tuples for.

`source_schema/contract.py` was **kept**: its `CLOCK_*` and `FAMILY_*` constants are
still used by `census.py` and `sources.py`. Distinguishing "unused candidate
schema" from "shared constants with an aspirational name" mattered — the first
draft deleted `contract.py` and broke the census import.

## Registered so far

| Dataset | Format | Version | Tables | Rows | Schema |
|---|---|---|---:|---:|---|
| settlement | parquet | 20260907_history_five_play_v2 | 19 | 10,820,092 | `beijing_lot_settlement_v1` |

## Incremental path

Only `settlement` is registered. The remaining stores (titan `control.sqlite`,
`market-history-v1.sqlite`, discovery, 500_bjdc) still declare their own tables and
paths. Each is migrated one at a time: give it a `schema_id` derived from its real
bytes, register it in the catalog, repoint its consumers to `catalog.paths`, then
delete the local `CREATE TABLE` and path constants. Storage is converging on
Parquet/DuckDB; SQLite remains acceptable as an ingest-time buffer only.
