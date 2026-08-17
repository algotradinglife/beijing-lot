# Issue #250 R4 method rework — same-class sweep

[SESSION] 20260817_200202_6f8305

## Trigger

This rework starts fresh from the R3 EV REJECT at `5b6954cf9768`. It treats the prior delivery and audit comments as evidence, not authority. The controlling scope remains assessment-only source-role profiling against the `HIST-DATA-CENSUS-001 R8` baseline.

## Root-cause classes and complete sweep

| Class | Root cause | Complete sweep and executable evidence |
| --- | --- | --- |
| Admissibility / inheritance fail-open | `field_admissible_use()` promoted a field merely because its containing source had a historical role. It did not consume R8's per-field `pre_match_feature_eligible`, terminal flag, admissible-use, and timestamp grade. | `src/source_census/resources/hist40_field_crosswalk.csv` is a 601-row exact extraction of the R8 `schema_dictionary.csv` for six R8-covered logical assets. `hist40_baseline_record`, `hist40_baseline_applies`, and `profile_field_lane` evaluate every discovered field in all seven declared `SourceSpec` paths. An R8 record is usable only when the immutable file hash equals the R8 source-inventory hash. Unmapped, changed, descriptive, unclassified, mapping-only, clock-unbound, and price-time-unbound fields are `RAW_ONLY`; terminal fields are `SETTLEMENT_ONLY`; derived copies remain `EXCLUDE`. |
| Source role fail-open | A positive proxy-triplet count could yield `HISTORICAL_PROXY` even if no field was admissible after inheritance. | `role_from_profile` now receives the count of actual `HISTORICAL_PROXY_CANDIDATE` fields. Missing coverage remains `RECOVER`; zero proxy triplets or zero admissible fields becomes `RAW_ONLY`. All role consumers are the source inventory, source-role matrix, decision-field profile, field inventory, source×feature availability table, report, notebook, and verifier. |
| Consumer divergence | `field_profile` and source-feature availability previously used name heuristics / source-level role rather than the same field lane emitted to `field_inventory`. | `annotate_decision_field_profiles` copies the canonical table/field lane to every decision-field nullness profile and sets `availability_used_for_role` only for a historical-proxy candidate. `source_feature_availability` is now calculated directly from `field_inventory` and reports observed versus admissible field counts. |
| Verifier boundary | The existing anchor stopped post-anchor re-signing but did not independently recompute field lanes from R8 source identity and the checked-out policy resource. | `verify_field_lane_crosswalk` recomputes every package field lane from source inventory SHA + source role + committed R8 crosswalk. `verify_package` executes it. The package manifest and external anchor bind the crosswalk SHA as well as the producer implementation and all package payload hashes. This is an independent semantic consistency check, while the external anchor remains the immutability boundary. |

## R8 extraction provenance

- Release tag: `hist-data-census-001-r8`
- Evidence archive SHA-256: `7de5e20d0a3b2185bcaf8e4229544c28100cd2d29c9cc315adbc6afe48f4a38d`
- R8 manifest SHA-256: `ed16b29626b4af70e80cdfee3130d6d5e89cd79d09e06110d4d55570e217cdc8`
- Source files extracted read-only: `inputs/source_inventory.csv`, `inputs/schema_dictionary.csv`, and `decision/admissible_use_matrix.csv`.

The committed crosswalk is intentionally a small derived lookup, not an additional data source or a replacement policy. It preserves the R8 logical asset ID and immutable source SHA for every row so a new or changed asset cannot inherit a candidate lane.

## Regression tests / adversarial probes

`tests/test_bj250_source_census.py` includes:

1. unclassified/descriptive and unknown fields stay `RAW_ONLY`; an explicit historical-proxy R8 row may become a candidate only with the bound SHA;
2. a changed source SHA disables R8 inheritance;
3. a historical source with zero admissible fields fails closed to `RAW_ONLY` even if a proxy triplet exists;
4. decision-field profile and source availability use the same canonical field lane;
5. field-lane semantic recomputation rejects an altered packaged lane;
6. re-manifested decision-table, source-trace, manifest, and complete package re-sign attacks require the independently held anchor and fail closed.

## Explicit statement

All same-class role-collapse / leakage points were checked: all seven logical sources, every discovered table/field, all field inventory and decision-field profile rows, source-feature availability, source-role routing, report/notebook inputs, manifest/anchor inputs, and verifier recomputation. No crawler, source write, imputation, model, ticket, ROI, identity-policy, temporal-policy, or physical-schema work was introduced.
