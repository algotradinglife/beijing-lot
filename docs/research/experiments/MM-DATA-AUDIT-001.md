# Research Phase 1: Multi-Market Data Audit (MM-DATA-AUDIT-001)

**Audit Cutoff (UTC):** 2026-07-23T16:03:12+00:00
**Status:** `reviewed`

**PI decision:** `no_market_end_to_end_ready` (PR #13). The readiness matrix
below is the frozen audit baseline; this status correction adds no new evidence.

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
| Total Goals | `READY_STRICT` | `SETTLEMENT_ONLY` | `READY_STRICT` |
| Correct Score | `READY_STRICT` | `SETTLEMENT_ONLY` | `READY_STRICT` |
| Half/Full Time | `PARTIAL` | `UNAVAILABLE` | `UNAVAILABLE` |

### Readiness Legend

- `READY_STRICT`: every gate passes for a clearly stated forward scope.
- `PARTIAL`: timestamped data exists, but one or more strict gates fail or coverage is insufficient.
- `SETTLEMENT_ONLY`: usable for outcome verification but prohibited as a pre-event input.
- `UNAVAILABLE`: no auditable asset for the required purpose.

## 4. Per-Market Audit Details

### 4.34 Handicap 3/1/0 — Pre Event Input

**Classification:** `PARTIAL`

Handicap 3/1/0 pre_event_input: PARTIAL. 3/4 relevant gates passed, avg score=0.78

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g1_outcome_vectors | ✓ | 0.81 | 28,019/34,649 snapshots (80.9%) have complete 3/1/0 SP vectors across 100 matches. Outcome mapping is hard-coded in beid... |
| g2_source_timestamps | ✓ | 1.00 | 34,649/34,649 snapshots (100.0%) have snapshot_ts. Sources: ['merged']. No dual-clock (fetched_at + source_updated_at) —... |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 100/100 matches (100.0%) have kickoff_ts. 25,351 snapshots are pre-kickoff. 86/100 matches (86.0%) have a complete 3/1/0... |
| g7_no_leakage | ✗ | 0.30 | beidan_live.db snapshots are captured live (source='zqdc', 'live500'). No post-event terminal SP substitution detected —... |

#### Key Metrics

```json
{
  "total_snapshots": 34649,
  "total_matches": 100,
  "complete_vector_snapshots": 28019,
  "complete_vector_pct": 80.87,
  "has_source_column": true,
  "sources": [
    "merged"
  ],
  "has_snapshot_ts": true,
  "timestamped_snapshots": 34649,
  "timestamped_pct": 100.0,
  "matches_with_kickoff": 100,
  "kickoff_coverage_pct": 100.0,
  "pre_kickoff_snapshots": 25351,
  "complete_pre_kickoff_matches": 86,
  "complete_pre_kickoff_match_pct": 86.0,
  "discovered_match_markets": 100
}
```

### 4.34 Handicap 3/1/0 — Freeze Support

**Classification:** `PARTIAL`

Handicap 3/1/0 freeze_support: PARTIAL. 1/2 relevant gates passed, avg score=0.50

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✗ | 0.30 | beidan_live.db is append-only by convention but lacks per-snapshot SHA-256 hashes or file-level bundle verification. No... |
| g5_asof_freeze | ✓ | 0.70 | 3 segment_decision_windows in 500_bjdc provide freeze_at timestamps. beidan_live.db snapshots have snapshot_ts which can... |

#### Key Metrics

```json
{
  "immutable_append_only": true,
  "has_bundle_hashes": false,
  "segment_decision_windows": 3,
  "freeze_protocol_v1_capable": true
}
```

### 4.34 Handicap 3/1/0 — Settlement Support

**Classification:** `READY_STRICT`

Handicap 3/1/0 settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=0.65

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 0.65 | 65 settlement rows cover 65/100 matches (65.0% of DB matches). 65 have final scores. 0 cancellations/postponements, 0 SP... |

#### Key Metrics

```json
{
  "total_settlements": 65,
  "total_settlement_rows": 65,
  "settled_matches": 65,
  "total_match_rows": 100,
  "settled_with_score": 65,
  "cancelled_or_postponed": 0,
  "sp1_void": 0,
  "settlement_coverage_pct": 65.0,
  "result_codes": {
    "0": 27,
    "1": 15,
    "3": 23
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
| g1_outcome_vectors | ✓ | 1.00 | 16 rows classified as forward_complete_open. 2/2 capture-vectors have the exact 8-outcome set priced (100.0%). 2/2 match... |
| g2_source_timestamps | ✓ | 1.00 | Dual-clock (fetched_at_utc + source_updated_at_hkt): 16/16 rows (100.0%) have both timestamps. |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 2 capture-vectors with both sale_status=open and forward_complete_open classification (100.0%). 2/2 match-markets have e... |
| g7_no_leakage | ✓ | 1.00 | 0 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_comple... |

#### Key Metrics

```json
{
  "total_rows": 16,
  "total_match_markets": 2,
  "forward_complete_open_rows": 16,
  "total_capture_vectors": 2,
  "complete_capture_vectors": 2,
  "complete_match_markets": 2,
  "complete_match_vectors": 2,
  "complete_vector_pct": 100.0,
  "complete_match_market_pct": 100.0,
  "has_dual_clock": true,
  "dual_clock_complete_rows": 16,
  "dual_clock_pct": 100.0,
  "pre_cutoff_eligible_capture_vectors": 2,
  "pre_cutoff_eligible_match_markets": 2,
  "pre_cutoff_eligible_match_vectors": 2,
  "pre_cutoff_eligible_pct": 100.0,
  "pre_cutoff_eligible_match_market_pct": 100.0,
  "pre_cutoff_rejection_reasons": {
    "non_open_sale": 0,
    "missing_cutoff_clock": 0,
    "missing_dual_clock": 0,
    "fetched_at_or_after_cutoff": 0,
    "source_updated_at_or_after_cutoff": 0
  },
  "discovered_match_markets": 2
}
```

### 4.40 Total Goals — Freeze Support

**Classification:** `SETTLEMENT_ONLY`

Total Goals freeze_support: SETTLEMENT_ONLY. 0/2 relevant gates passed, avg score=0.25

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✗ | 0.30 | 0 capture batches for Total Goals. 0 bundle directories on disk. 0 bundles verified by recomputing SHA256SUMS entries an... |
| g5_asof_freeze | ✗ | 0.20 | No verified compatible 10h freeze package for this market. |

#### Key Metrics

```json
{
  "capture_batches": 0,
  "bundle_dirs": 0,
  "sha256_verified_bundle_dirs": 0,
  "sha256_failed_bundle_dirs": 0,
  "sha256_failure_samples": [],
  "all_sha256_verifiable": false,
  "has_existing_freeze": false,
  "freeze_manifest": null,
  "freeze_verification": {},
  "freeze_verification_failures": []
}
```

### 4.40 Total Goals — Settlement Support

**Classification:** `READY_STRICT`

Total Goals settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 2 match-markets in settlement truth: 2 settled (100.0%), 0 pending, 0 cancelled, 0 SP=1 voids. Score source is separatel... |

#### Key Metrics

```json
{
  "total_settlement_rows": 2,
  "settled": 2,
  "pending_or_unknown": 0,
  "cancelled": 0,
  "void_sp1": 0,
  "settlement_coverage_pct": 100.0,
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
| g1_outcome_vectors | ✓ | 1.00 | 50 rows classified as forward_complete_open. 2/2 capture-vectors have the exact 25-outcome set priced (100.0%). 2/2 matc... |
| g2_source_timestamps | ✓ | 1.00 | Dual-clock (fetched_at_utc + source_updated_at_hkt): 50/50 rows (100.0%) have both timestamps. |
| g3_pre_cutoff_evidence | ✓ | 1.00 | 2 capture-vectors with both sale_status=open and forward_complete_open classification (100.0%). 2/2 match-markets have e... |
| g7_no_leakage | ✓ | 1.00 | 0 terminal-backfill rows exist but are classified as terminal_backfill_exploratory_only and excluded from forward_comple... |

#### Key Metrics

```json
{
  "total_rows": 50,
  "total_match_markets": 2,
  "forward_complete_open_rows": 50,
  "total_capture_vectors": 2,
  "complete_capture_vectors": 2,
  "complete_match_markets": 2,
  "complete_match_vectors": 2,
  "complete_vector_pct": 100.0,
  "complete_match_market_pct": 100.0,
  "has_dual_clock": true,
  "dual_clock_complete_rows": 50,
  "dual_clock_pct": 100.0,
  "pre_cutoff_eligible_capture_vectors": 2,
  "pre_cutoff_eligible_match_markets": 2,
  "pre_cutoff_eligible_match_vectors": 2,
  "pre_cutoff_eligible_pct": 100.0,
  "pre_cutoff_eligible_match_market_pct": 100.0,
  "pre_cutoff_rejection_reasons": {
    "non_open_sale": 0,
    "missing_cutoff_clock": 0,
    "missing_dual_clock": 0,
    "fetched_at_or_after_cutoff": 0,
    "source_updated_at_or_after_cutoff": 0
  },
  "discovered_match_markets": 2
}
```

### 4.42 Correct Score — Freeze Support

**Classification:** `SETTLEMENT_ONLY`

Correct Score freeze_support: SETTLEMENT_ONLY. 0/2 relevant gates passed, avg score=0.25

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g4_immutable_provenance | ✗ | 0.30 | 0 capture batches for Correct Score. 0 bundle directories on disk. 0 bundles verified by recomputing SHA256SUMS entries... |
| g5_asof_freeze | ✗ | 0.20 | No verified compatible 10h freeze package for this market. |

#### Key Metrics

```json
{
  "capture_batches": 0,
  "bundle_dirs": 0,
  "sha256_verified_bundle_dirs": 0,
  "sha256_failed_bundle_dirs": 0,
  "sha256_failure_samples": [],
  "all_sha256_verifiable": false,
  "has_existing_freeze": false,
  "freeze_manifest": null,
  "freeze_verification": {},
  "freeze_verification_failures": []
}
```

### 4.42 Correct Score — Settlement Support

**Classification:** `READY_STRICT`

Correct Score settlement_support: READY_STRICT. 1/1 relevant gates passed, avg score=1.00

#### Gates

| Gate | Passed | Score | Evidence |
| --- | ---: | ---: | --- |
| g6_settlement_mapping | ✓ | 1.00 | 2 match-markets in settlement truth: 2 settled (100.0%), 0 pending, 0 cancelled, 0 SP=1 voids. Score source is separatel... |

#### Key Metrics

```json
{
  "total_settlement_rows": 2,
  "settled": 2,
  "pending_or_unknown": 0,
  "cancelled": 0,
  "void_sp1": 0,
  "settlement_coverage_pct": 100.0,
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
| g1_outcome_vectors | ✓ | 0.60 | 18 rows across 2 match-markets. Outcome codes: ['0-0', '0-1', '0-3', '1-0', '1-1', '1-3', '3-0', '3-1', '3-3']. All 9 ex... |
| g2_source_timestamps | ✓ | 0.80 | 18/18 rows (100.0%) have fetched_at. Dual-clock (fetched_at_utc + source_updated_at_hkt): present. No batch_id or source... |
| g3_pre_cutoff_evidence | ✗ | 0.10 | All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. No sale_status, sale_cutoff, o... |
| g7_no_leakage | ✗ | 0.50 | No terminal classification exists; all data is non_target_market_unclassified. Risk unknown — data may contain post-even... |

#### Key Metrics

```json
{
  "total_rows": 18,
  "total_match_markets": 2,
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
  "timestamped_rows": 18,
  "timestamped_pct": 100.0,
  "has_dual_clock": true,
  "discovered_match_markets": 2
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
| Handicap 3/1/0 | 100 | 3 |
| Total Goals | 2 | 8 |
| Correct Score | 2 | 25 |
| Half/Full Time | 2 | 9 |

### 5.2 Settlement Coverage

| Market | Settlement Rows |
| --- | ---: |
| Handicap 3/1/0 | 65 |
| Total Goals | 2 |
| Correct Score | 2 |
| Half/Full Time | 0 |

## 6. Gap Findings

1. **Handicap 3/1/0 — g7_no_leakage** (score=0.30): beidan_live.db snapshots are captured live (source='zqdc', 'live500'). No post-event terminal SP substitution detected — snapshot_ts always precedes or is near kickoff_ts for the captured data. Howeve...
2. **Handicap 3/1/0 — g4_immutable_provenance** (score=0.30): beidan_live.db is append-only by convention but lacks per-snapshot SHA-256 hashes or file-level bundle verification. No SHA256SUMS exist for raw capture. The Freeze Protocol v1 would need to hash the...
3. **Total Goals — g4_immutable_provenance** (score=0.30): 0 capture batches for Total Goals. 0 bundle directories on disk. 0 bundles verified by recomputing SHA256SUMS entries and matching the recorded SHA256SUMS digest. 0 bundle checks failed.
4. **Total Goals — g5_asof_freeze** (score=0.20): No verified compatible 10h freeze package for this market.
5. **Correct Score — g4_immutable_provenance** (score=0.30): 0 capture batches for Correct Score. 0 bundle directories on disk. 0 bundles verified by recomputing SHA256SUMS entries and matching the recorded SHA256SUMS digest. 0 bundle checks failed.
6. **Correct Score — g5_asof_freeze** (score=0.20): No verified compatible 10h freeze package for this market.
7. **Half/Full Time — g3_pre_cutoff_evidence** (score=0.10): All rows are non_target_market_unclassified — never validated for pre-cutoff eligibility. No sale_status, sale_cutoff, or capture_classification beyond raw source_attribute values. Cannot confirm pre-...
8. **Half/Full Time — g4_immutable_provenance** (score=0.10): No market_sp_capture_batches for playid=51. No SHA256SUMS, no immutable bundles, no batch provenance. Data exists as raw rows in live_market_sp_snapshots without hash verification.
9. **Half/Full Time — g5_asof_freeze** (score=0.00): No freeze package exists for playid=51. Freeze Protocol v1 requires capture batches which don't exist. Data is available but not in a freezable form.
10. **Half/Full Time — g6_settlement_mapping** (score=0.00): No settlement truth rows for Half/Full Time. Half/full-time settlement mapping is not available until separately sourced p51 settlement rows are built and audited.

## 7. Reproducibility

This audit was generated by:

```bash
.venv/bin/python scripts/run_mm_data_audit.py --fixtures-dir tests/fixtures --output-dir results/research/mm_data_audit
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
