# Issue #254 delivery handoff — external replay verified

[SESSION] 20260818_225058_234960

## Current HEAD and completed work

- Branch: `engineer/bj254-issue`; inherited HEAD `79b1dc5` binds accepted #250
  (`99701cf`), #251 (`63729bc`), #252 (`17be9fd`) and #253 (`a086c47`)
  predecessor artifacts.
- `src/schema_integration/` atomically builds a nested normalized SQLite/Parquet
  snapshot, validates all predecessor bindings, M×3 and label-isolation
  invariants, and writes the exact five-consumer #235/#236/#237/#248/#249
  readiness matrix.
- `tests/test_bj254_schema_integration.py` covers normal replay, re-signed
  predecessor rewrite, downstream-contract deletion, and label-column leak.
- Added `notebooks/research/issue-254/bj254_schema_integration.ipynb`; it was
  clean-executed against the declared external root and committed with outputs.

## Resolved blocked prerequisite

The earlier blocker was a root-layout discovery error, not an unavailable input.
A temporary external root was assembled by symlinking the existing declared
inputs into the contract layout without copying bulk data:

- `beidan_live.db`;
- `derived/beidan_xlsm/beidan_xlsm.sqlite`;
- `derived/bj251_canonical_identity_v3/tables/issue_slot_identity.csv`.

The actual replay returned `PASS`: 4 predecessor bindings, 5 downstream
contracts, 8 issue slots, 16 observations, 60 feature cells (58 available,
2 explicit missing), 36 historical-proxy cells, 24 strict-forward cells, and
4 physically isolated settlement labels. Re-running `--verify-only` returned
the same PASS receipt.

## Verification

- `pytest tests/test_bj254_schema_integration.py tests/test_bj253_physical_schema.py -q` → `10 passed`.
- CLI real external-root build + verify → `status: PASS`.
- Notebook execution → same PASS receipt and the #250/#251/#252/#253 binding list.

## Key boundaries and next step

- Historical proxy and strict-forward rows share M×3 shape but remain separate
  namespaces; settlement remains physically separate from feature readers.
- #235/#236/#237 remain `BLOCKED` by their source/identity evidence gaps;
  #248/#249 are `READY_INTERFACE` only and retain their own evidence gates.
- No raw database, Parquet, or source payload is committed to Git.

Next: EV should use a clean checkout, run the 10 focused tests, provide an
external root in the declared three-input layout, run the CLI and execute the
#254 notebook, then repeat the adversarial re-sign and label-leak cases.
