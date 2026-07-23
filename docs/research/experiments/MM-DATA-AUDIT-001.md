# Research Phase 1: Multi-Market Data Audit (MM-DATA-AUDIT-001)

**Audit Cutoff (UTC):** 2026-07-23T10:42:02+00:00
**Status:** `engineering_validation`

## 1. Research Question

For each target market, does the current forward data chain provide sufficient evidence
to support strict as-of research under Freeze Protocol v1?

## 2. Markets Under Audit

| Market | PlayID | Outcomes | Data Source |
| --- | ---: | ---: | --- |
| Handicap 3/1/0 | 34 | 3 | beidan_live |
| Total Goals | 40 | 8 | 500_bjdc |
| Correct Score | 42 | 25 | 500_bjdc |
| Half/Full Time | 51 | 9 | 500_bjdc |

## 3. Readiness Matrix

| Market | Pre-Event Input | Freeze Support | Settlement Support |
| --- | --- | --- | --- |
| Handicap 3/1/0 | `PARTIAL` | `PARTIAL` | `READY_STRICT` |
| Total Goals | `PARTIAL` | `READY_STRICT` | `READY_STRICT` |
| Correct Score | `PARTIAL` | `READY_STRICT` | `READY_STRICT` |
| Half/Full Time | `PARTIAL` | `UNAVAILABLE` | `UNAVAILABLE` |

### Readiness Legend

- `READY_STRICT`: every gate passes for a clearly stated forward scope.
- `PARTIAL`: timestamped data exists, but one or more strict gates fail or coverage is insufficient.
- `SETTLEMENT_ONLY`: usable for outcome verification but prohibited as a pre-event input.
- `UNAVAILABLE`: no auditable asset for the required purpose.

## 4. Per-Market Audit Details

### 4.34 Handicap 3/1/0 — Pre Event Input

**Classification:** `PARTIAL`

Handicap 3/1/0 pre_event_input: PARTIAL. 3/4 relevant gates passed, avg score=0.72

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 0.58 | 559,880/969,378 snapshots (57.8%) have complete 3/1/0 SP vectors across 3,519 matches. Outcome mapping is hard-coded in ... |
| g2_source_timestamps | ✓ | 1.00 | 969,378/969,378 snapshots (100.0%) have snapshot_ts. Sources: ['merged']. No dual-clock (fetched_at + source_updated_at)... |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 3519/3519 matches (100.0%) have kickoff_ts. 453,777 snapshots are pre-kickoff. 2,256/3,519 matches (64.1%) have a comple... |
| g7_no_leakage | ✗ | 0.30 | beidan_live.db snapshots are captured live (source='zqdc', 'live500'). No post-event terminal SP substitution detected —... |

#### Key Metrics

```json
{
  "total_snapshots": 969378,
  "total_matches": 3519,
  "complete_vector_snapshots": 559880,
  "complete_vector_pct": 57.76,
  "has_source_column": true,
  "sources": [
    "merged"
  ],
  "has_snapshot_ts": true,
  "timestamped_snapshots": 969378,
  "timestamped_pct": 100.0,
  "matches_with_kickoff": 3519,
  "kickoff_coverage_pct": 100.0,
  "pre_kickoff_snapshots": 453777,
  "complete_pre_kickoff_matches": 2256,
  "complete_pre_kickoff_match_pct": 64.11,
  "discovered_match_markets": 3519
}
```

### 4.34 Handicap 3/1/0 — Freeze Support

**Classification:** `PARTIAL`

Handicap 3/1/0 freeze_support: PARTIAL. 1/2 relevant gates passed, avg score=0.50

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✗ | 0.30 | beidan_live.db is append-only by convention but lacks per-snapshot SHA-256 hashes or file-level bundle verification. No ... |
| g5_asof_freeze | ✓ | 0.70 | 9 segment_decision_windows in 500_bjdc provide freeze_at timestamps. beidan_live.db snapshots have snapshot_ts which can... |

#### Key Metrics

```json
{
  "immutable_append_only": true,
  "has_bundle_hashes": false,
  "segment_decision_windows": 9,
  "freeze_protocol_v1_capable": true
}
```

### 4.34 Handicap 3/1/0 — Settlement Support

**Classification:** `READY_STRICT`

Handicap 3/1/0 settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=0.66

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 0.66 | 2308 settlement rows cover 2308/3519 matches (65.6% of DB matches). 2308 have final scores. 0 cancellations/postponement... |

#### Key Metrics

```json
{
  "total_settlements": 2308,
  "total_settlement_rows": 2308,
  "settled_matches": 2308,
  "total_match_rows": 3519,
  "settled_with_score": 2308,
  "cancelled_or_postponed": 0,
  "sp1_void": 1,
  "settlement_coverage_pct": 65.59,
  "result_codes": {
    "0": 804,
    "1": 630,
    "3": 874
  },
  "settlement_sourced_separately": true,
  "sources": [
    "500_kaijiang",
    "detail",
    "live500",
    "live500+detail",
    "zqdc",
    "zqdc+detail"
  ]
}
```

### 4.40 Total Goals — Pre Event Input

**Classification:** `PARTIAL`

Total Goals pre_event_input: PARTIAL. 3/4 relevant gates passed, avg score=0.73

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 0.94 | 157,264 rows classified as forward_complete_open. 19,658/41,950 capture-vectors have the exact 8-outcome set priced (46.... |
| g2_source_timestamps | ✓ | 0.99 | Dual-clock (fetched_at_utc + source_updated_at_hkt): 332,400/335,600 rows (99.0%) have both timestamps. |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 19,641 capture-vectors with both sale_status=open and forward_complete_open classification (46.8%). 182/349 match-market... |
| g7_no_leakage | ✗ | 0.00 | 121,584 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_... |

#### Key Metrics

```json
{
  "total_rows": 335600,
  "total_match_markets": 349,
  "forward_complete_open_rows": 157264,
  "total_capture_vectors": 41950,
  "complete_capture_vectors": 19658,
  "complete_match_markets": 182,
  "complete_match_vectors": 182,
  "complete_vector_pct": 46.86,
  "complete_match_market_pct": 52.15,
  "has_dual_clock": true,
  "dual_clock_complete_rows": 332400,
  "dual_clock_pct": 99.05,
  "pre_cutoff_eligible_capture_vectors": 19641,
  "pre_cutoff_eligible_match_markets": 182,
  "pre_cutoff_eligible_match_vectors": 182,
  "pre_cutoff_eligible_pct": 46.82,
  "pre_cutoff_eligible_match_market_pct": 52.15,
  "pre_cutoff_rejection_reasons": {
    "non_open_sale": 0,
    "missing_cutoff_clock": 17,
    "missing_dual_clock": 0,
    "fetched_at_or_after_cutoff": 0,
    "source_updated_at_or_after_cutoff": 0
  },
  "discovered_match_markets": 349
}
```

### 4.40 Total Goals — Freeze Support

**Classification:** `READY_STRICT`

Total Goals freeze_support: READY_STRICT. 2/2 relevant gates passed, avg score=0.90

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✓ | 1.00 | 540 capture batches for Total Goals. 540 bundle directories on disk. 540 bundles verified by recomputing SHA256SUMS entr... |
| g5_asof_freeze | ✓ | 0.80 | Verified 10h freeze package found: multimarket_asof_freeze_v1 with 231 frozen rows for this market. |

#### Key Metrics

```json
{
  "capture_batches": 540,
  "bundle_dirs": 540,
  "sha256_verified_bundle_dirs": 540,
  "sha256_failed_bundle_dirs": 0,
  "sha256_failure_samples": [],
  "all_sha256_verifiable": true,
  "has_existing_freeze": true,
  "freeze_manifest": "multimarket_asof_freeze_v1",
  "freeze_verification": {
    "status": "valid",
    "output_dir": "/home/drwho1985/workspace/soccer/beijing-lot/results/research/multimarket_10h_freeze_v1/26075_p0_20260716",
    "frozen_outcome_rows": 231,
    "rejected_match_markets": 36,
    "sha256s_sha256": "4d2fee436ef450dfde6cdce8ba744eb0d0f949a732a3bc2c4e516beac83f91bf"
  },
  "freeze_verification_failures": []
}
```

### 4.40 Total Goals — Settlement Support

**Classification:** `READY_STRICT`

Total Goals settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 348 match-markets in settlement truth: 323 settled (92.8%), 24 pending, 1 cancelled, 0 SP=1 voids. Score source is separ... |

#### Key Metrics

```json
{
  "total_settlement_rows": 348,
  "settled": 323,
  "pending_or_unknown": 24,
  "cancelled": 1,
  "void_sp1": 0,
  "settlement_coverage_pct": 92.82,
  "has_separate_score_source": true,
  "settlement_sourced_separately": true
}
```

### 4.42 Correct Score — Pre Event Input

**Classification:** `PARTIAL`

Correct Score pre_event_input: PARTIAL. 2/4 relevant gates passed, avg score=0.57

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✗ | 0.49 | 276,650 rows classified as forward_complete_open. 11,066/45,408 capture-vectors have the exact 25-outcome set priced (24... |
| g2_source_timestamps | ✓ | 0.99 | Dual-clock (fetched_at_utc + source_updated_at_hkt): 1,125,200/1,135,200 rows (99.1%) have both timestamps. |
| g3_pre_cutoff_evidence | ✓ | 0.81 | 11,049 capture-vectors with both sale_status=open and forward_complete_open classification (24.3%). 181/349 match-market... |
| g7_no_leakage | ✗ | 0.00 | 447,425 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_... |

#### Key Metrics

```json
{
  "total_rows": 1135200,
  "total_match_markets": 349,
  "forward_complete_open_rows": 276650,
  "total_capture_vectors": 45408,
  "complete_capture_vectors": 11066,
  "complete_match_markets": 181,
  "complete_match_vectors": 181,
  "complete_vector_pct": 24.37,
  "complete_match_market_pct": 51.86,
  "has_dual_clock": true,
  "dual_clock_complete_rows": 1125200,
  "dual_clock_pct": 99.12,
  "pre_cutoff_eligible_capture_vectors": 11049,
  "pre_cutoff_eligible_match_markets": 181,
  "pre_cutoff_eligible_match_vectors": 181,
  "pre_cutoff_eligible_pct": 24.33,
  "pre_cutoff_eligible_match_market_pct": 51.86,
  "pre_cutoff_rejection_reasons": {
    "non_open_sale": 0,
    "missing_cutoff_clock": 17,
    "missing_dual_clock": 0,
    "fetched_at_or_after_cutoff": 0,
    "source_updated_at_or_after_cutoff": 0
  },
  "discovered_match_markets": 349
}
```

### 4.42 Correct Score — Freeze Support

**Classification:** `READY_STRICT`

Correct Score freeze_support: READY_STRICT. 2/2 relevant gates passed, avg score=0.90

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✓ | 1.00 | 578 capture batches for Correct Score. 578 bundle directories on disk. 578 bundles verified by recomputing SHA256SUMS en... |
| g5_asof_freeze | ✓ | 0.80 | Verified 10h freeze package found: multimarket_asof_freeze_v1 with 231 frozen rows for this market. |

#### Key Metrics

```json
{
  "capture_batches": 578,
  "bundle_dirs": 578,
  "sha256_verified_bundle_dirs": 578,
  "sha256_failed_bundle_dirs": 0,
  "sha256_failure_samples": [],
  "all_sha256_verifiable": true,
  "has_existing_freeze": true,
  "freeze_manifest": "multimarket_asof_freeze_v1",
  "freeze_verification": {
    "status": "valid",
    "output_dir": "/home/drwho1985/workspace/soccer/beijing-lot/results/research/multimarket_10h_freeze_v1/26075_p0_20260716",
    "frozen_outcome_rows": 231,
    "rejected_match_markets": 36,
    "sha256s_sha256": "4d2fee436ef450dfde6cdce8ba744eb0d0f949a732a3bc2c4e516beac83f91bf"
  },
  "freeze_verification_failures": []
}
```

### 4.42 Correct Score — Settlement Support

**Classification:** `READY_STRICT`

Correct Score settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 348 match-markets in settlement truth: 323 settled (92.8%), 24 pending, 1 cancelled, 0 SP=1 voids. Score source is separ... |

#### Key Metrics

```json
{
  "total_settlement_rows": 348,
  "settled": 323,
  "pending_or_unknown": 24,
  "cancelled": 1,
  "void_sp1": 0,
  "settlement_coverage_pct": 92.82,
  "has_separate_score_source": true,
  "settlement_sourced_separately": true
}
```

### 4.51 Half/Full Time — Pre Event Input

**Classification:** `PARTIAL`

Half/Full Time pre_event_input: PARTIAL. 2/4 relevant gates passed, avg score=0.50

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 0.60 | 452,394 rows across 349 match-markets. Outcome codes: ['0-0', '0-1', '0-3', '1-0', '1-1', '1-3', '3-0', '3-1', '3-3']. A... |
| g2_source_timestamps | ✓ | 0.80 | 452,394/452,394 rows (100.0%) have fetched_at. Dual-clock (fetched_at_utc + source_updated_at_hkt): present. No batch_id... |
| g3_pre_cutoff_evidence | ✗ | 0.10 | All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. No sale_status, sale_cutoff, o... |
| g7_no_leakage | ✗ | 0.50 | No terminal classification exists; all data is non_target_market_unclassified. Risk unknown — data may contain post-even... |

#### Key Metrics

```json
{
  "total_rows": 452394,
  "total_match_markets": 349,
  "outcome_codes_found": [
    "0-0",
    "0-1",
    "0-3",
    "1-0",
    "1-1",
    "1-3",
    "3-0",
    "3-1",
    "3-3"
  ],
  "expected_outcome_match": true,
  "has_timestamps": true,
  "timestamped_rows": 452394,
  "timestamped_pct": 100.0,
  "has_dual_clock": true,
  "discovered_match_markets": 349
}
```

### 4.51 Half/Full Time — Freeze Support

**Classification:** `UNAVAILABLE`

Half/Full Time freeze_support: UNAVAILABLE. 0/2 relevant gates passed, avg score=0.05

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✗ | 0.10 | No market_sp_capture_batches for playid=51. No SHA256SUMS, no immutable bundles, no batch provenance. Data exists as raw... |
| g5_asof_freeze | ✗ | 0.00 | No freeze package exists for playid=51. Freeze Protocol v1 requires capture batches which don't exist. Data is available... |

#### Key Metrics

```json
{}
```

### 4.51 Half/Full Time — Settlement Support

**Classification:** `UNAVAILABLE`

Half/Full Time settlement_support: UNAVAILABLE. 0/1 relevant gates passed, avg score=0.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✗ | 0.00 | No settlement truth rows for Half/Full Time. Half/full-time settlement mapping is not available until separately sourced... |

#### Key Metrics

```json
{
  "settlement_sourced_separately": false,
  "total_settlement_rows": 0
}
```

## 5. Cross-Market Metrics

### 5.1 Discovered Matches and Expected Match-Markets

| Market | Discovered Match-Markets | Expected per Match |
| --- | ---: | ---: |
| Handicap 3/1/0 | 3,519 | 3 |
| Total Goals | 349 | 8 |
| Correct Score | 349 | 25 |
| Half/Full Time | 349 | 9 |

### 5.2 Settlement Coverage

| Market | Settlement Rows |
| --- | ---: |
| Handicap 3/1/0 | 2,308 |
| Total Goals | 348 |
| Correct Score | 348 |
| Half/Full Time | 0 |

## 6. Gap Findings

1. **Handicap 3/1/0 — g7_no_leakage** (score=0.30): beidan_live.db snapshots are captured live (source='zqdc', 'live500'). No post-event terminal SP substitution detected — snapshot_ts always precedes or is near kickoff_ts for the captured data. Howeve
2. **Handicap 3/1/0 — g4_immutable_provenance** (score=0.30): beidan_live.db is append-only by convention but lacks per-snapshot SHA-256 hashes or file-level bundle verification. No SHA256SUMS exist for raw capture. The Freeze Protocol v1 would need to hash the 
3. **Total Goals — g7_no_leakage** (score=0.00): 121,584 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_complete_open. 136 forward_complete_open rows lack independent cutoff-clock proo
4. **Correct Score — g1_outcome_vectors** (score=0.49): 276,650 rows classified as forward_complete_open. 11,066/45,408 capture-vectors have the exact 25-outcome set priced (24.4%). 181/349 match-markets have at least one complete capture-vector (51.9%).
5. **Correct Score — g7_no_leakage** (score=0.00): 447,425 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_complete_open. 425 forward_complete_open rows lack independent cutoff-clock proo
6. **Half/Full Time — g3_pre_cutoff_evidence** (score=0.10): All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. No sale_status, sale_cutoff, or capture_classification beyond raw source_attribute values. Cannot confirm pre-
7. **Half/Full Time — g4_immutable_provenance** (score=0.10): No market_sp_capture_batches for playid=51. No SHA256SUMS, no immutable bundles, no batch provenance. Data exists as raw rows in live_market_sp_snapshots without hash verification.
8. **Half/Full Time — g5_asof_freeze** (score=0.00): No freeze package exists for playid=51. Freeze Protocol v1 requires capture batches which don't exist. Data is available but not in a freezable form.
9. **Half/Full Time — g6_settlement_mapping** (score=0.00): No settlement truth rows for Half/Full Time. Half/full-time settlement mapping is not available until separately sourced p51 settlement rows are built and audited.

## 7. Reproducibility

This audit was generated by:

```bash
.venv/bin/python scripts/run_mm_data_audit.py --output-dir results/research/mm_data_audit
```

The audit can be regenerated with the command above; local `results/` outputs are runtime artifacts.
Machine-readable results are at `results/research/mm_data_audit/audit_result.json`.

## 8. Follow-Up Issues

Gap findings above must be addressed as separate issues before SP-CONSISTENCY-001:

1. **Handicap 3/1/0 Freeze Protocol v1**: Create freeze package from beidan_live.db snapshots with SHA-256 verification.
2. **Half/Full Time Settlement Truth**: Build independently sourced half-time plus full-time truth for p51, including audited cancellation/postponement/SP=1 mapping.

## 9. Gates Definitions

| Gate | Description |
| --- | --- |
| G1 | Complete and correctly mapped outcome vectors |
| G2 | Explicit source and capture timestamps |
| G3 | Evidence that selected snapshot existed before declared decision cutoff |
| G4 | Immutable or append-only raw provenance with verifiable hashes |
| G5 | Deterministic as-of selection and Freeze Protocol v1 support |
| G6 | Complete, separately sourced settlement mapping including cancellation/postponement/SP=1 handling |
| G7 | No terminal/final SP or post-event page used as a pre-event feature |

## 10. Engineering Validation Checklist

- [ ] Clean-checkout command reproduces the audit from the frozen snapshot.
- [ ] Hash verification succeeds and tampering fails closed.
- [ ] Tests cover vector completeness, cutoff rejection, terminal-data rejection and settlement special states.
- [ ] Existing strategy, ticket, API, frontend and release-manifest behavior is unchanged.
- [ ] Outputs remain `execution_enabled=false`, `frontend_selectable=false`, `roi_authorized=false`.
