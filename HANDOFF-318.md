# Issue #318 handoff

- SESSION: `20260822_162749_6e2ba8`
- Base HEAD: `5ed9670dfc0b03cbe9fd7b8f44a17d690ce7288b`
- Branch: `engineer/bj318-sp-proxy-audit`

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
