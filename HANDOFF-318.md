# Issue #318 handoff

- SESSION: `20260822_165040_89f076`
- Original delivery HEAD: `4c36b3d23845afb8ede308a60db22dfe6c0c513e`
- Branch: `engineer/bj318-sp-proxy-audit`

## Follow-on source-boundary correction

The frozen #238 receipt names the exact candidate SQLite successor and its
accepted SHA-256. Replay now resolves only that receipt-named file when the
worktree-relative path is absent, hashes it, and fails closed with
`MANIFEST_MISMATCH` on a binding failure rather than calling it missing. The
verified successor hash is
`a51bdca8f3b0ef20a31ef606399daea82760a5230a8fc844ea5917178f1078d4`.

The other worktree-relative mandatory paths remain `SOURCE_MISSING` in this
package. Although the receipt names mutable label and registry locations, it
supplies no approved source-file hash for either; this follow-on intentionally
does not treat an unhashed external path as an admissible successor. The terminal
cap is therefore unchanged. The verified candidate successor is bound as an
input receipt only—it is not used to invent a historical SP vector or timestamp.
Focused tests: 8 passed; replay and package verifier passed. The repository-wide
pytest collection remains unavailable in this sparse/runtime environment
(missing external source paths and optional Flask/Matplotlib/nbformat modules),
not due to this package.

## Completed

Implemented package-first `BJ-UNIFIED-SP-PROXY-AUDIT-001/v1` code, replay and
verification scripts, adversarial tests, an executed notebook, immutable
artifacts, and decision documentation.

## Key decisions

1. The current clean worktree is missing the named `beidan_xlsm`, #268
   candidate, #238 materializer, and issue-registry SQLite paths. Replay emits
   deterministic `SOURCE_MISSING` receipts and caps the disposition at
   `NO_CAUSAL_PRICE_SUPPORT`.
2. The tracked #216 strict panel and #238 source receipt are SHA-256 bound.
   #216 supplies 11,355 prospective long-form cells, but without the
   contract-approved candidate inventory no kickoff/identity assertion is
   permitted; every vector is atomically `UNUSABLE/SOURCE_MISSING`.
3. No relative-horizon proxy or frozen `Q_EU_BJLINE` materializer is present,
   so no strict/proxy overlap or N7 capacity is fabricated.
4. The verifier pins the committed manifest SHA in source. Tamper tests modify
   decision, SP price, and provenance then re-manifest; all fail the external
   anchor. Grading tests separately reject settlement, future timestamp,
   incomplete triplet, and duplicate conflicts.

## Known limits / reviewer checks

- This truthful package does not claim that missing canonical databases never
  exist elsewhere; the frozen contract forbids substitute discovery.
- `ruff` is unavailable in the active runtime. `py_compile`, six focused tests,
  deterministic replay, and verifier passed.
- Replay/verify:

```bash
python scripts/run_sp_proxy_audit.py --output results/sp_proxy_audit
python scripts/verify_sp_proxy_audit.py --package results/sp_proxy_audit
```
