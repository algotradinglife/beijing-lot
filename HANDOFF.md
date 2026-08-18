# Issue #254 PI handoff

## Scope completed

- Bound accepted #250–#253 review HEADs, merge commits, manifest paths and
  manifest SHA-256 values.
- Built the v2 external integration package with a 2014–2017 historical proxy
  sample and a strict-forward sample.
- Verified M×3 grain, temporal namespace separation, missingness, provenance,
  settlement isolation, byte-deterministic replay and isolated restore copy.
- Generated a physical data dictionary, downstream readiness matrix,
  REQ-to-evidence table, decision report and executed #254 notebook.

## Replay

```bash
export BEIJING_LOT_DATA_ROOT=/absolute/path/to/data
python scripts/build_bj254_schema_integration.py --data-root "$BEIJING_LOT_DATA_ROOT"
python scripts/build_bj254_schema_integration.py --data-root "$BEIJING_LOT_DATA_ROOT" --verify-only
python scripts/execute_bj254_notebook.py --data-root "$BEIJING_LOT_DATA_ROOT"
python -m pytest -q tests/test_bj254_schema_integration.py
```

The bulk package lives at
`$BEIJING_LOT_DATA_ROOT/derived/bj254_schema_integration_v2` and is not committed
to Git.  Git carries code, the executed notebook, reports and compact evidence.

## Decision boundary

#254 accepts the interface, not full data readiness.  #235/#236 remain recovery
work, #237 needs an entity-identity scope decision, and #248/#249 may consume the
interface under their own evidence gates.
