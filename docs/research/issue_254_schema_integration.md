# Issue #254 final source-schema integration

## Contract

`BJ-UNIFIED-SCHEMA-INTEGRATION-001-v1` binds the accepted #250, #251, #252 and #253 manifests by commit and SHA-256, creates a normalized SQLite/Parquet representative package under `BEIJING_LOT_DATA_ROOT`, and verifies the package plus every downstream interface.

## Interpretation boundary

- Historical exploration may use only the declared `historical_proxy` European 1X2 lane; its horizon labels are not wall-clock observations.
- Forward validation may use only `strict_forward` rows with a pre-kickoff poll-start timestamp. This is not received-at or reschedule-as-of authority.
- Feature readers have no settlement table or label fields. Labels remain in a physically separate SQLite database and Parquet namespace.
- #235, #236 and #237 are explicitly data-limited; #248 and #249 may start against the frozen interface but retain their own collection/portability evidence gates.

## Replay

```text
python scripts/build_bj254_schema_integration.py --data-root "$BEIJING_LOT_DATA_ROOT"
python scripts/build_bj254_schema_integration.py --data-root "$BEIJING_LOT_DATA_ROOT" --verify-only
pytest -q tests/test_bj254_schema_integration.py
```

The external root is intentionally mandatory. Bulk SQLite and Parquet snapshots are never committed to Git.
