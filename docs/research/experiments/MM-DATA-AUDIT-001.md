# Research Phase 1: Multi-Market Data Audit (MM-DATA-AUDIT-001)

**Audit Cutoff (UTC):** 2026-07-22T15:13:50+00:00
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
| Handicap 3/1/0 | `READY_STRICT` | `PARTIAL` | `READY_STRICT` |
| Total Goals | `READY_STRICT` | `READY_STRICT` | `READY_STRICT` |
| Correct Score | `READY_STRICT` | `READY_STRICT` | `READY_STRICT` |
| Half/Full Time | `PARTIAL` | `UNAVAILABLE` | `SETTLEMENT_ONLY` |

### Readiness Legend

- `READY_STRICT`: every gate passes for a clearly stated forward scope.
- `PARTIAL`: timestamped data exists, but one or more strict gates fail or coverage is insufficient.
- `SETTLEMENT_ONLY`: usable for outcome verification but prohibited as a pre-event input.
- `UNAVAILABLE`: no auditable asset for the required purpose.

## 4. Per-Market Audit Details

### 4.34 Handicap 3/1/0 — Pre Event Input

**Classification:** `READY_STRICT`

Handicap 3/1/0 pre_event_input: READY_STRICT. 4/4 relevant gates passed, avg score=0.89

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 0.58 | 554,607/960,078 snapshots (57.8%) have complete 3/1/0 SP vectors across 3,519 matches. Outcome mapping is hard-coded in ... |
| g2_source_timestamps | ✓ | 1.00 | 960,078/960,078 snapshots (100.0%) have snapshot_ts. Sources: ['merged']. No dual-clock (fetched_at + source_updated_at)... |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 3519/3519 matches (100.0%) have kickoff_ts. 528,993 snapshots are pre-kickoff. Segment decision windows from 500_bjdc pr... |
| g7_no_leakage | ✓ | 1.00 | beidan_live.db snapshots are captured live (source='zqdc', 'live500'). No post-event terminal SP substitution detected —... |

#### Key Metrics

```json
{
  "total_snapshots": 960078,
  "total_matches": 3519,
  "complete_vector_snapshots": 554607,
  "complete_vector_pct": 57.77,
  "has_source_column": true,
  "sources": [
    "merged"
  ],
  "has_snapshot_ts": true,
  "timestamped_snapshots": 960078,
  "timestamped_pct": 100.0,
  "matches_with_kickoff": 3519,
  "kickoff_coverage_pct": 100.0,
  "pre_kickoff_snapshots": 528993,
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

Handicap 3/1/0 settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 2278 settlements across 2278 matches (100.0% of DB). 2278 have final scores. 0 cancellations/postponements, 1 SP=1 voids... |

#### Key Metrics

```json
{
  "total_settlements": 2278,
  "settled_matches": 2278,
  "settled_with_score": 2278,
  "cancelled_or_postponed": 0,
  "sp1_void": 1,
  "settlement_coverage_pct": 100.0,
  "result_codes": {
    "0": 792,
    "1": 622,
    "3": 864
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

**Classification:** `READY_STRICT`

Total Goals pre_event_input: READY_STRICT. 4/4 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 1.00 | 136,088 rows classified as forward_complete_open → ~17,011 complete match-vectors of 8 outcomes each (4874.2% of 349 tot... |
| g2_source_timestamps | ✓ | 0.99 | Dual-clock (fetched_at_utc + source_updated_at_hkt): 287,400/290,600 rows (98.9%) have both timestamps. |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 17,011 match-vectors with both sale_status=open and forward_complete_open classification (4874.2%). Dual-clock confirms ... |
| g7_no_leakage | ✓ | 1.00 | 101,064 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_... |

#### Key Metrics

```json
{
  "total_rows": 290600,
  "total_match_markets": 349,
  "forward_complete_open_rows": 136088,
  "complete_match_vectors": 17011,
  "complete_vector_pct": 4874.21,
  "has_dual_clock": true,
  "dual_clock_complete_rows": 287400,
  "dual_clock_pct": 98.9,
  "pre_cutoff_eligible_match_vectors": 17011,
  "pre_cutoff_eligible_pct": 4874.21,
  "discovered_match_markets": 349
}
```

### 4.40 Total Goals — Freeze Support

**Classification:** `READY_STRICT`

Total Goals freeze_support: READY_STRICT. 2/2 relevant gates passed, avg score=0.90

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✓ | 1.00 | 465 capture batches for Total Goals. 465 bundle directories on disk. All bundles have SHA256SUMS with verifiable checksu... |
| g5_asof_freeze | ✓ | 0.80 | Existing 10h freeze package found: multimarket_asof_freeze_v1 with 231 frozen rows for this market. |

#### Key Metrics

```json
{
  "capture_batches": 465,
  "bundle_dirs": 465,
  "all_sha256_verifiable": true,
  "has_existing_freeze": true,
  "freeze_manifest": "multimarket_asof_freeze_v1"
}
```

### 4.40 Total Goals — Settlement Support

**Classification:** `READY_STRICT`

Total Goals settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 348 match-markets in settlement truth: 295 settled (84.8%), 52 pending, 1 cancelled, 0 SP=1 voids. Score source is separ... |

#### Key Metrics

```json
{
  "total_settlement_rows": 348,
  "settled": 295,
  "pending_or_unknown": 52,
  "cancelled": 1,
  "void_sp1": 0,
  "settlement_coverage_pct": 84.77,
  "has_separate_score_source": true,
  "settlement_sourced_separately": true
}
```

### 4.42 Correct Score — Pre Event Input

**Classification:** `READY_STRICT`

Correct Score pre_event_input: READY_STRICT. 4/4 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 1.00 | 228,600 rows classified as forward_complete_open → ~9,144 complete match-vectors of 25 outcomes each (2620.1% of 349 tot... |
| g2_source_timestamps | ✓ | 0.99 | Dual-clock (fetched_at_utc + source_updated_at_hkt): 986,450/996,450 rows (99.0%) have both timestamps. |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 9,144 match-vectors with both sale_status=open and forward_complete_open classification (2620.1%). Dual-clock confirms b... |
| g7_no_leakage | ✓ | 1.00 | 385,600 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_... |

#### Key Metrics

```json
{
  "total_rows": 996450,
  "total_match_markets": 349,
  "forward_complete_open_rows": 228600,
  "complete_match_vectors": 9144,
  "complete_vector_pct": 2620.06,
  "has_dual_clock": true,
  "dual_clock_complete_rows": 986450,
  "dual_clock_pct": 99.0,
  "pre_cutoff_eligible_match_vectors": 9144,
  "pre_cutoff_eligible_pct": 2620.06,
  "discovered_match_markets": 349
}
```

### 4.42 Correct Score — Freeze Support

**Classification:** `READY_STRICT`

Correct Score freeze_support: READY_STRICT. 2/2 relevant gates passed, avg score=0.90

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✓ | 1.00 | 504 capture batches for Correct Score. 504 bundle directories on disk. All bundles have SHA256SUMS with verifiable check... |
| g5_asof_freeze | ✓ | 0.80 | Existing 10h freeze package found: multimarket_asof_freeze_v1 with 231 frozen rows for this market. |

#### Key Metrics

```json
{
  "capture_batches": 504,
  "bundle_dirs": 504,
  "all_sha256_verifiable": true,
  "has_existing_freeze": true,
  "freeze_manifest": "multimarket_asof_freeze_v1"
}
```

### 4.42 Correct Score — Settlement Support

**Classification:** `READY_STRICT`

Correct Score settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 348 match-markets in settlement truth: 295 settled (84.8%), 52 pending, 1 cancelled, 0 SP=1 voids. Score source is separ... |

#### Key Metrics

```json
{
  "total_settlement_rows": 348,
  "settled": 295,
  "pending_or_unknown": 52,
  "cancelled": 1,
  "void_sp1": 0,
  "settlement_coverage_pct": 84.77,
  "has_separate_score_source": true,
  "settlement_sourced_separately": true
}
```

### 4.51 Half/Full Time — Pre Event Input

**Classification:** `PARTIAL`

Half/Full Time pre_event_input: PARTIAL. 3/4 relevant gates passed, avg score=0.50

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 0.60 | 399,744 rows across 349 match-markets. Outcome codes: ['0-0', '0-1', '0-3', '1-0', '1-1', '1-3', '3-0', '3-1', '3-3']. A... |
| g2_source_timestamps | ✓ | 0.80 | 399,744/399,744 rows (100.0%) have fetched_at. Dual-clock (fetched_at_utc + source_updated_at_hkt): present. No batch_id... |
| g3_pre_cutoff_evidence | ✗ | 0.10 | All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. No sale_status, sale_cutoff, o... |
| g7_no_leakage | ✓ | 0.50 | No terminal classification exists; all data is non_target_market_unclassified. Risk unknown — data may contain post-even... |

#### Key Metrics

```json
{
  "total_rows": 399744,
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
  "timestamped_rows": 399744,
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

**Classification:** `SETTLEMENT_ONLY`

Half/Full Time settlement_support: SETTLEMENT_ONLY. 0/1 relevant gates passed, avg score=0.20

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✗ | 0.20 | No settlement truth rows for Half/Full Time. However, matches table has scores (fthg/ftag) which can be mapped to half/f... |

#### Key Metrics

```json
{}
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
| Handicap 3/1/0 | 0 |
| Total Goals | 348 |
| Correct Score | 348 |
| Half/Full Time | 0 |

## 6. Gap Findings

1. **Handicap 3/1/0 — g4_immutable_provenance** (score=0.30): beidan_live.db is append-only by convention but lacks per-snapshot SHA-256 hashes or file-level bundle verification. No SHA256SUMS exist for raw capture. The Freeze Protocol v1 would need to hash the 
2. **Half/Full Time — g3_pre_cutoff_evidence** (score=0.10): All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. No sale_status, sale_cutoff, or capture_classification beyond raw source_attribute values. Cannot confirm pre-
3. **Half/Full Time — g4_immutable_provenance** (score=0.10): No market_sp_capture_batches for playid=51. No SHA256SUMS, no immutable bundles, no batch provenance. Data exists as raw rows in live_market_sp_snapshots without hash verification.
4. **Half/Full Time — g5_asof_freeze** (score=0.00): No freeze package exists for playid=51. Freeze Protocol v1 requires capture batches which don't exist. Data is available but not in a freezable form.
5. **Half/Full Time — g6_settlement_mapping** (score=0.20): No settlement truth rows for Half/Full Time. However, matches table has scores (fthg/ftag) which can be mapped to half/full-time outcomes using a deterministic mapping function. This would need to be 

## 7. Reproducibility

This audit was generated by:

```bash
.venv/bin/python scripts/run_mm_data_audit.py --output-dir results/research/mm_data_audit
```

The audit input snapshot is frozen under `results/freeze/MM-DATA-AUDIT-001/`.
Machine-readable results are at `results/research/mm_data_audit/audit_result.json`.

## 8. Follow-Up Issues

Gap findings above must be addressed as separate issues before SP-CONSISTENCY-001:

1. **Handicap 3/1/0 Freeze Protocol v1**: Create freeze package from beidan_live.db snapshots with SHA-256 verification.

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
