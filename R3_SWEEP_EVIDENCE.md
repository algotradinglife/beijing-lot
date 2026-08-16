# Issue #229 R3 full-class sweep evidence

REWORK_TYPE=method. Fresh R3 reasoning against EV R2 audited SHA `6d198fb7f8eb`.
This document is the producer's auditable call-site declaration; executable
evidence is in `tests/test_bj229_r3_rework.py` and
`tests/test_bj229_divergence_profile.py`.

## 1. Leak / causal availability

Root-cause category: causal-mask bypass. R2 producers exposed raw vectors while
support, divergence and readiness consumers treated list presence as
availability; Q_BJ also omitted its representation observed-at column.

Full sweep scope and evidence:

- `contract.py`: one naming contract for every representation's
  `*_observed_at_utc`, `*_source_identity`, `*_available`, `*_reason`, and
  producer receipt.
- `probabilities.py`: `materialize_calibrated_and_line`, `materialize_sp_devig`,
  `materialize_eu_raw`, `materialize_eu_bjline`, and
  `materialize_power_bjline` publish source identity, observed-at and explicit
  source/partial/unidentifiable receipts. Pclose rows have no invented time;
  accepted average-EU rows bind `euro_1h_available_ts_utc`.
- `quality.py`: `apply_causal_availability` is the only representation mask
  computation and requires raw value + source observed-at + decision epoch +
  kickoff eligibility. The long causal receipt includes cell key and source.
- `builder.py`: scalar predicted-SP and uncertainty features receive the same
  observed-at/mask/reason contract before any consumer executes.
- `divergence.py`: `_vector_value`, EU/POWER divergence, uncertainty scaling,
  agreement and leg diagnostics require published causal masks; no
  raw-presence fallback.
- `profile.py`: probability distributions, reconciliation, scatter, missingness,
  intersections, drift, calibration and SP diagnostics use `_causal_mask`.
- `builder.py`: `disposition`, evidence, registry and manifest consume causal
  counts. Counts are published for every source.
- `handoff.py`: package-only validator independently recomputes masks,
  divergence, causal counts and honest disposition.

Executable attacks/boundaries:
`test_qbj_materializer_publishes_observed_at_by_actual_source`,
`test_all_causal_consumers_reject_raw_presence`,
`test_causal_eligibility_receipt_is_keyed_and_covers_line`, divergence golden
fixtures with explicit masks, and remanifested `availability`/`divergence`/
`source_trace` mutations.

Declaration: **checked all points of this class** — all representation producers
and all consumers in divergence, profile, intersections, disposition, registry,
manifest and the #209 package loader/validator.

## 2. Cohort / label boundary

Root-cause category: schema-semantic identity error. R2 parsed an opaque issue ID
prefix as a year, producing 2101/2201/2301 and false future-sealed counts.

Full sweep scope and evidence:

- `sources.py`: #203 `inference/cell_identity.parquet` is the authoritative
  source of `year`, `split`, match and outcome identity.
- `builder.py::prepare_label_namespaces`: one-to-one `cell_join_key` join to
  authoritative identity; development is `year <= 2023`; physical sealed
  receipts separately report `2024`, `2025+`, and aggregate `2024+`; no future
  rows enter the handoff.
- `builder.py::assemble_cells`: #204 prospective identities remain countable
  with explicit `NO_BJ203_IDENTITY` / `NO_BJ203_MATCH_META`; no identity is
  dropped or assigned a fabricated year.
- `profile.py::development_only_calibration` and
  `predicted_sp_vs_settlement_sp`: consume package-local authoritative `year`
  and `cohort`; no issue-prefix parsing or private map reload.
- `builder.py`: cohort registry, evidence, schema, report and manifest row counts
  are all derived from these namespaces.
- `handoff.py`: independently checks development-year maximum, cell-key FK,
  empty future namespaces and namespace counts.

Executable attacks/boundaries:
`test_label_namespaces_use_authoritative_identity_year`,
`test_label_boundary_seals_2024_and_2025_separately`, remanifested `labels` and
`future_label` mutations.

Declaration: **checked all points of this class** — every issue/year derivation,
authoritative join, development/calibration/2024+/2025+ namespace and every
report/schema/manifest count.

## 3. Metric / completeness profiling

Root-cause category: profiling coverage blind spot. R2 profiled raw vectors and
omitted the full source × outcome × cohort matrix and executable empty receipts.

Full sweep scope and evidence:

- `profile.py`: causal source distributions, missingness, intersections,
  reconciliation, scatter, drift, source × outcome × cohort reliability and
  predicted-SP diagnostics. Empty support emits `UNAVAILABLE_EMPTY_SUPPORT`
  rows rather than disappearing.
- `divergence.py::coverage_strata`: publishes raw and causal counts separately.
- `builder.py`: writes every machine-readable profile table including EU raw,
  chart-source mapping and empty receipts.
- `figures.py`: all chart writes are table-backed and atomic; unavailable
  support renders an explicit placeholder rather than an absent file.
- `handoff.py::_profile_problems`: package-only recomputation of core metric
  tables and chart/source path closure.

Executable attacks/boundaries:
`test_calibration_profiles_every_representation_outcome_and_cohort`,
`test_drift_and_probability_distribution_use_causal_mask`,
`test_chart_source_mapping_is_complete`, and remanifested `report` mutation.

Declaration: **checked all points of this class** — every probability source ×
outcome × cohort reliability path, SP diagnostic, drift/missingness/support
receipt, empty-support path and chart-source mapping.

## 4. Schema / handoff

Root-cause category: partial schema and private-map coupling. R2 described only
inference columns and left #209 unable to validate package tables independently.

Full sweep scope and evidence:

- `builder.py::build_schema`: every physical package table has path, row count,
  physical/logical type, units, nullability, domain, list shape, PK/FK and
  cardinality metadata.
- Package payload includes inference cells, separate development labels, sealed
  namespaces, feature dictionary, probability registry, cohort registry,
  causal receipt, DQ ledgers, evidence and profile tables.
- `handoff.py::load_package` / `validate_package`: public package-only API;
  validates hashes, schema, keys, FKs, list shape, domain boundaries, labels,
  causal masks, divergence, profile tables, report and provenance without
  opening #203/#204/#214/#180.
- `__init__.py`: public `load_handoff_package` and `validate_handoff_package`.

Executable attacks/boundaries:
`test_schema_describes_every_table_with_physical_logical_contracts`,
`test_package_loader_api_is_public`, remanifested `schema` and `labels`
mutations.

Declaration: **checked all points of this class** — all package payload tables,
physical/logical contracts, list/vector fields, PK/FK/cardinality relations and
the independent #209 loader.

## 5. Verifier / provenance

Root-cause category: presence/hash-only verifier. R2 could remanifest semantic
forgeries and carried stale commit assertions.

Full sweep scope and evidence:

- `handoff.py`: independent recomputation rejects altered inference divergence,
  availability, labels, schema, evidence, report, source trace and future labels.
- `builder.py` manifest binds symbolic `PR_HEAD` (resolved during delivery),
  exact package producer commit, source-code directory hash, notebook semantic
  source-cell hash and dependency hash. This avoids the impossible self-SHA
  cycle while `post_handoff.py` binds PR #231's exact final HEAD.
- `manifest.py`: replay and SHA manifests are inside the one atomic staging
  publication.
- `scripts/build_bj229_divergence_profile.py verify`: hash verification plus the
  complete package-only semantic validator; no presence-only PASS.

Executable attacks/boundaries:
parametrized `test_remanifested_mutation_fails` for divergence, availability,
labels, schema, evidence and report; `test_tamper_source_trace_and_future_label_fail`.

Declaration: **checked all points of this class** — PR/code/notebook/dependency
bindings, all semantic payloads, evidence/report closure and remanifest attacks.

## 6. Atomicity

Root-cause category: incomplete durability protocol. R2 had live-package
finalizers, swallowed fsync errors and fsynced the wrong notebook parent.

Full sweep scope and evidence:

- `publication.py`: shared fail-closed atomic text/JSON/CSV/Parquet/PNG writers;
  file fsync, rename and actual parent-directory fsync; no swallowed OSError.
- `publication.atomic_publish_directory`: same-parent staging, full tree fsync,
  pre/post-rename parent fsync, old-package `.previous` protection, BaseException
  rollback, stale staging/previous recovery and immediate retry.
- `builder.py`: all package tables, ledgers, evidence, schema, report, manifest,
  replay, SHA and figures are completed in staging before one directory swap.
- `figures.py`, `manifest.py`, and notebook executor: only shared atomic writers;
  no direct live-package finalization.
- Notebook package cell relies on `builder.write_package`; executor atomically
  persists only the executed notebook.

Executable attacks/boundaries:
`test_fsync_dir_failure_is_not_swallowed`,
`test_atomic_write_text_fsyncs_actual_parent`,
`test_atomic_directory_post_rename_fsync_fault_restores_old_package`, and the
normal/OSError/BaseException/stale-retry publication tests in the original test
file.

Declaration: **checked all points of this class** — every Issue #229 CSV,
Parquet, JSON, PNG, notebook, SHA, manifest and replay write path.

## 7. Source / boundary paths

Root-cause category: silent source-shape coercion. R2 allowed partial/duplicate
source paths and had insufficient empty/no-overlap receipts.

Full sweep scope and evidence:

- `sources.py`: #203/#204 canonical axes require non-empty exact 3/1/0 triplets,
  unique source rows and full feature/mask key closure. Match metadata must be
  constant within a match. Labels and feature values require unique cell keys.
- `probabilities.py::materialize_sp_devig`: #214 snapshot panels select the
  latest snapshot at/before each exact decision epoch; empty input retains the
  three cells as unavailable; duplicate match+snapshot fails; a partial 3/1/0
  SP triplet keeps all cells with `PARTIAL_SOURCE_TRIPLET`.
- `materialize_eu_raw` / `materialize_eu_bjline`: partial source values retain
  identity and explicit receipts; invalid lines and unidentifiable translation
  are explicit and never filled to zero/current overlap.
- `materialize_power_bjline`: #180 empty/partial inputs retain all cells with
  explicit receipts; duplicate issue-match rows fail fast.
- `builder.py::assemble_cells`: prospective no-overlap cells remain on the
  #204 3-cell axis with explicit missing-#203 status and unavailable causal
  times; no silent row drop.

Executable attacks/boundaries:
#214 exact-three-cell, duplicate and partial tests; canonical empty/partial/
duplicate axis tests; #180 empty/partial/duplicate tests; invalid quarter-line,
half-goal and explicit unidentifiable-translation tests.

Declaration: **checked all points of this class** — #203/#204/#214/#180 empty,
partial, duplicate, no-overlap, invalid-line and unidentifiable translation
paths, each preserving exact three-cell identity or raising an explicit contract
error.
