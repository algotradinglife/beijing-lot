# Issue #388 — shared cutoff-learning hardening

Contract: `BJ-UNIFIED-CUTOFF-HARDENING-001/v1`

## Decision

`SHARED_CUTOFF_HARDENING_READY`. The merged #382 equal-weight mapping remains numerically identical across 48,658 rows, but its availability claim is narrowed to `KICKOFF_PLUS_4H_HISTORICAL_PROXY_ONLY`.

## Corrections

- Decision-epoch cutoff structurally excludes the target issue even when its label timestamp is earlier.
- Implementation receipts bind the transitive local import closure and external package versions.
- Static governance scans `src/` and `scripts/` and uses exact AST occurrence counts, not file allowlists.
- Recent-state weighting is a convex mixture: long-history mass 0.75 plus recent-state mass 0.25 in the demonstration.
- Historical proxy availability cannot authorize prospective use.

## Acceptance evidence

| Gate | Result |
| --- | --- |
| Real mapping parity | PASS — 48,658 rows, all nine probability columns exact at `1e-12` |
| Target identity exclusion | PASS — 3/3 synthetic target rows excluded independently of timestamp |
| Same-target mutation | PASS — selection identity unchanged |
| Static governance | PASS — exact AST occurrence baseline across `src/` and `scripts/` |
| Implementation provenance | PASS — transitive local imports and external versions receipt-bound |
| Availability | PASS — historical proxy is rejected for prospective use |
| Convex recency mixture | PASS — long/recent masses reconcile separately |
| Package replay | PASS — source-bound scientific reconstruction and byte replay |

## Weight evidence

| policy | rows | effective_sample_size | long_history_mass | recent_state_mass | target_rows_seen | target_rows_excluded |
| --- | --- | --- | --- | --- | --- | --- |
| EXPANDING_EQUAL | 288 | 288.0 | 1.0000000000000002 | 0.0 | 3 | 3 |
| EXPANDING_EXPONENTIAL | 288 | 185.03978923139618 | 1.0 | 0.0 | 3 | 3 |
| RECENT_STATE_BLEND | 288 | 200.3478260869566 | 0.75 | 0.25 | 3 | 3 |

## Reproduction

```bash
PYTHONPATH=. python scripts/run_cutoff_hardening.py --data-root /path/to/data --force
PYTHONPATH=. python scripts/verify_cutoff_hardening.py --data-root /path/to/data
PYTHONPATH=. pytest tests/scripts/test_cutoff_mapping.py tests/scripts/test_cutoff_governance.py tests/scripts/test_cutoff_hardening.py -q
```

## Boundary

This is infrastructure evidence, not a betting Edge. #383 may start only after this package lands. #210/#218 are unchanged.
