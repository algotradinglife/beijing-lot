# Issue #254 implementation handoff — external-data replay pending

[SESSION] 20260818_223541_cfcaf2

## Current HEAD and completed work

- Branch: `engineer/bj254-issue`; HEAD includes accepted #250 (`99701cf`), #251 (`63729bc`), #252 (`17be9fd`) and #253 (`a086c47`) predecessor surfaces.
- Added `src/schema_integration/` and `scripts/build_bj254_schema_integration.py`.
  The integration package binds all four accepted predecessor manifests and SHAs,
  atomically builds a nested normalized SQLite/Parquet snapshot, verifies the
  physical M×3 and label-isolation invariants, and emits an exact five-consumer
  readiness matrix for #235/#236/#237/#248/#249.
- Added `tests/test_bj254_schema_integration.py`: normal replay plus adversarial
  re-signed predecessor rewrite, missing downstream contract, and label-column
  leak attacks. Focused #253+#254 suite passed: `10 passed`.

## Key decisions

- #253's issue-local `issue_code × match_idx × 3/1/0` key, proxy/strict
  namespace split, and physical settlement isolation are inherited unchanged.
- The readiness matrix preserves data limits: #235–#237 are `BLOCKED`; #248 and
  #249 are `READY_INTERFACE` only, with their own collection/portability gates.
- No external path is hard-coded; `BEIJING_LOT_DATA_ROOT` is mandatory.

## Blocking condition / next step

This host has no declared data root and neither checked candidate root contains
the three required predecessor inputs: `derived/beidan_xlsm/beidan_xlsm.sqlite`,
`beidan_live.db`, and `derived/bj251_canonical_identity_v3/tables/issue_slot_identity.csv`.
Supply an absolute mounted root containing those inputs, then run the #254 CLI,
execute the final notebook, and attach the real replay receipt before EV Review.

## Known verification note

`python -m ruff` is unavailable in the active runtime; `uvx ruff` retried and
failed because PyPI TLS negotiation ended with EOF. Python compilation and
focused tests completed successfully.
