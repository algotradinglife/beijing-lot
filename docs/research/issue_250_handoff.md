# Issue #250 R4 handoff

[SESSION] 20260817_200202_6f8305

## Delivery state

- Branch: `engineer/bj250-rework-r1`, updating PR #255.
- Base: `engineer/bj234-issue`.
- Delivery implementation commits: `b4bf700ce75f41c47b28b339ae99f4bb895c8a9f` plus exact-field repair `3c5275cb90fb465873b06d1708f1a01f843e2842`.
- Evidence package: `results/bj250_source_census_v2`.
- Executed notebook: `notebooks/research/issue-250/bj250_source_census.ipynb`.
- R4 same-class sweep: `docs/research/issue_250_r4_rework_audit.md`.
- External data contract: `BEIJING_LOT_DATA_ROOT` is mandatory; all SQLite opens use URI `mode=ro` and mutable sources remain `MUTABLE_UNFROZEN`.

## R3 closure

The R3 blocker was an inheritance fail-open: fields inside an historical proxy container were promoted solely by the source role. R4 commits a 601-row crosswalk extracted read-only from the accepted `HIST-DATA-CENSUS-001 R8` evidence archive. For each discovered field in all seven logical sources, the build now:

1. binds R8 inheritance only when the current immutable source SHA equals the R8 source-inventory SHA;
2. permits `HISTORICAL_PROXY_CANDIDATE` only for explicitly R8-eligible, non-terminal historical-proxy rows;
3. keeps changed, unknown, descriptive, mapping/context, clock-unbound, and price-time-unbound fields `RAW_ONLY`;
4. keeps terminal/result/final/winning/official SP and settlement surfaces `SETTLEMENT_ONLY`;
5. makes the historical source role fail closed if it has no eligible proxy fields;
6. derives decision-field availability and source×feature availability from the same field lanes; and
7. recomputes every packaged field lane in the verifier from source identity + role + R8 crosswalk.

The crosswalk SHA is bound in both the package manifest and the external anchor along with implementation and payload hashes. This is semantic consistency checking; the external anchor is still required for package immutability and must be held/generated outside the worker worktree by EV.

## Executed evidence

```text
pytest tests/test_bj250_source_census.py -q                                    -> 35 passed
BEIJING_LOT_DATA_ROOT=<external> build_bj250_source_census.py                  -> INTERNAL_VERIFIED=True
BEIJING_LOT_DATA_ROOT=<external> execute_bj250_notebook.py                     -> 2 code cells
build_bj250_source_census.py --verify-only --trusted-anchor <local external>   -> VERIFIED=True
```

The local verification anchor used only to exercise the command is outside the package at `/tmp/bj250-r4-local-verification-anchor.json`; it is not an independent EV trust anchor and is not committed.

The current mutable p34 observation contains 4,008,003 scoped cells across 13 issues and 1,487 logical `(issue,row_idx)` matches. It is explicitly unfrozen. The executed R4 inventory has 8 `HISTORICAL_PROXY_CANDIDATE`, 515 `RAW_ONLY`, 158 `SETTLEMENT_ONLY`, and 328 `EXCLUDE` field rows; 564 fields are R8 exact-asset bound, 37 map to a changed R8 asset, and 408 have no R8 field record.

## PI / EV decision inputs and risks

- `beidan_xlsm` is a historical relative-time proxy candidate only; `initial`/`10h`/`1h` are never strict observed-at values.
- `beidan_live` and `bjdc_500_capture` remain `RAW_ONLY` and advance to #252 only to define source/capture-clock sealing criteria.
- Candidate mapping is non-authoritative pending #251; canonical causal intersection remains deferred to #251 + #252.
- The decision artifact prevents container-level leakage, but it does not authorize any identity, temporal, schema, modeling, ticket, ROI, acquisition, or backfill decision.

## Next action

EV should use a fresh checkout, independently obtain/hold an anchor, rerun the external-root build and notebook, verify the R8 archive/crosswalk provenance, sample all field lanes (especially R8-ineligible fields), and repeat a complete re-sign attack. PI/user should then decide the historical-proxy backbone and recovery routing.
