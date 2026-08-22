# Issue #318 — Historical Beijing SP / proxy admissibility audit

Contract: `BJ-UNIFIED-SP-PROXY-AUDIT-001/v1`.

## Replay

```bash
python scripts/run_sp_proxy_audit.py --output results/sp_proxy_audit
python scripts/verify_sp_proxy_audit.py --package results/sp_proxy_audit
```

The runner reads only the six contract-named source paths plus the exact #238
receipt-named candidate successor, and verifies that successor against the
receipt's accepted SHA-256 before classifying it as present. It records a
deterministic `SOURCE_MISSING` or `MANIFEST_MISMATCH` receipt where a mandatory
input is unavailable or its approved binding fails; it never searches for
replacement databases.

## Decision boundary

`STRICT_PRE_EVENT` needs an exact `(issue_code, match_idx)` identity, an actual
three-price Beijing vector, and proven `observed_at <= decision_epoch < kickoff`.
Relative `initial`, `10h`, and `1h` lanes remain `HISTORICAL_PROXY`; settlement,
winning-only, incomplete, conflicting, or timestamp-unproven vectors are
`UNUSABLE`. No payout factor is applied.

The committed decision artifact is the authority for the observed disposition
and its failed threshold list. A source-missing package is deliberately capped
at `NO_CAUSAL_PRICE_SUPPORT`; no historical ranking or promotion is authorized.

## Package contents

`graded_cells.parquet` is long-form M×3 evidence. `coverage_by_issue.csv` and
`exclusion_ledger.parquet` reconstruct denominators. `overlap_metrics.csv` is
empty when exact strict/proxy overlap is absent rather than synthesizing a best
horizon. `MANIFEST.json` has content hashes and the verifier compares it to a
trusted hash embedded in source, so an attacker cannot simply re-manifest a
modified package.
