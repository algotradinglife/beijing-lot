# Coverage report — bj235_bj_sp_timeseries_v1

Contract: BJ-UNIFIED-BJ-SP-TIMESERIES-001 / v1 (issue #235)
Mode: candidate. Owner role: Engineer. Milestone M1.

## What was covered

| Source | Rows/scale | Clock | Class | Role |
|---|---|---|---|---|
| data/beidan_live.db | 1,494,878 obs / 5,155 matches / 31 issues | snapshot_ts trusted receive | STRICT_CAUSAL | prospective pre-event SP + native line |
| derived/500_bjdc/500_bjdc.sqlite live_sp playid34 | 1,631,650 obs / 19 issues | fetched_at + source_updatetime | STRICT_CAUSAL | prospective pre-event SP + native line (per-obs line) |
| multimarket raw XML bundles | 5,221 batches w/ payload_sha256 + SHA256SUMS | fetched_at_utc + source_updated_at_hkt | STRICT_CAUSAL (raw capture evidence) | hash-bound raw payloads (playids 40/42) |
| beidan_history.db | 38,463 settlement rows | settled_ts | SETTLEMENT_ONLY | settlement cross-check only |
| beidan_xlsm.sqlite | 51,551,016 snapshots | label buckets only | RETROSPECTIVE_PROXY | historical presence, NOT causal |
| beidan_features.db | 190,746 matches | no clock | UNUSABLE | not ingested into inference |
| nowscore/okooo archives | 2-4 issues each | third-party change time | RETROSPECTIVE_PROXY | third-party cross-check only |

## Decision-epoch as-of replay

- Rule `asof_latest_complete_pre_kickoff_v1`; epochs at kickoff −24h / −6h / −1h / −0.5h
- Gates: obs_time <= decision_at; obs_time < kickoff_at; staleness <= 24h
- Selection: latest COMPLETE 3/1/0 triplet; incomplete observations → exclusion ledger
- Line states preserved per observation; never joined across different lines

## Acceptance evidence

- REQ-BJ01: every quote binds fixture + native line + outcome code + source + causal clock (source_registry, observation rows)
- REQ-BJ02: complete/finite/positive triplets; incomplete explicit in exclusion_ledger
- REQ-BJ03: no post-decision/post-kickoff row (gates + golden tests)
- REQ-BJ04: line changes retained per observation (per-obs handicap_line; test)
- REQ-BJ05: 0.65 absent; probability_estimate physically separate from settlement
- REQ-BJ06: issue-level support reported per cohort (strict_historical / retrospective_proxy / prospective)
- REQ-BJ07: INSERT OR IGNORE + batch keys; duplicate-ingestion test
- REQ-BJ08: prospective counts + `UNRECOVERABLE_HISTORICAL_BJ_SP` evidence for 2014-2025

## Test coverage

- tests/test_bj235_asof.py: 8 tests (replay gates, incomplete explicit, line state,
  0.65 separation, idempotency, golden selection, cohort classification)
- tests/test_bj235_tamper.py: 4 REQ-E06 attacks (quote tamper, ledger rebalance,
  manifest rewrite, forged source trace)
- Total: 11 passed

## Known limitations

1. 500 xml34 fixtures lack kickoff in that source → fixtures without kickoff get no decision epochs (explicit unavailable).
2. beidan_live snapshots carry no native source time → observed_at := received_at (documented).
3. sale_status not recorded in beidan_live / live_sp snapshots → NULL explicit unknown.
4. multimarket bundles cover playids 40/42 (not 34) → registered as raw-capture evidence only.
