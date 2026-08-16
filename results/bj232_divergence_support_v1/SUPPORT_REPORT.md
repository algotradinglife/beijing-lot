# Issue #232 — causal SP-backed divergence support

Contract: BJ-UNIFIED-DIVERGENCE-SUPPORT-001/v1 (candidate).
Disposition: **UNRECOVERABLE_WITH_CURRENT_SOURCES**

## Census
- bj214_selected_market_observations: present, rows=16496, issue 26051..26083, clock=snapshot_ts_utc
- full_3sp_official: ABSENT, rows=0, issue nan..nan, clock=last_update_ts
- beidan_live_snapshots: ABSENT, rows=0, issue nan..nan, clock=snapshot_ts
- sp_drift_panel: ABSENT, rows=0, issue nan..nan, clock=snapshot_ts
- 500_bjdc_live_sp_snapshots: ABSENT, rows=0, issue nan..nan, clock=fetched_at
- bj203_devig_euro_probability: present, rows=332718, issue 190101..26069, clock=euro_1h_available_ts_utc
- bj204_avg_eu: present, rows=357705, issue 190101..26049, clock=euro_1h_available_ts_utc
- bj180_match_probability_freeze: present, rows=1558, issue 20012..25042, clock=feature_cutoff_ts

## Zero-overlap diagnosis
- Q_BJ_x_SP: GENUINELY_UNAVAILABLE_HISTORICAL_DATA — #214 SP observations cover issues 26051..26083 (2026-05-02+ only); the Q_BJ anchor causal axis ends at 26049, so SP and anchor windows are disjoint; no pre-2026 timestamped SP observation exists in any committed or recoverable asset (#203 DATA_CARD: historical official 3SP is label-only with no trustworthy observation timestamp)
- Q_BJ_x_EU_x_SP: GENUINELY_UNAVAILABLE_HISTORICAL_DATA — EU: EU de-vig causal support exists on historical issues (#229: 2,976 cells on 190101+); Q_EU_BJLINE translation is 0 (no score/goal-difference distribution support); Q_BJ anchor causal cells are 2026-only and no historical pre-event SP observation exists -> Q_BJ x EU x SP triple intersection empty; SP: #214 SP observations cover issues 26051..26083 (2026-05-02+ only); the Q_BJ anchor causal axis ends at 26049, so SP and anchor windows are disjoint; no pre-2026 timestamped SP observation exists in any committed or recoverable asset (#203 DATA_CARD: historical official 3SP is label-only with no trustworthy observation timestamp)
- Q_BJ_x_POWER_x_SP: GENUINELY_UNAVAILABLE_HISTORICAL_DATA — POWER: P_POWER_BJLINE causal cells exist on historical issues (#229: 234 cells on 20062-24105) but never overlap the Q_BJ anchor (causal cells 2026-only); SP is absent for all historical issues; SP: #214 SP observations cover issues 26051..26083 (2026-05-02+ only); the Q_BJ anchor causal axis ends at 26049, so SP and anchor windows are disjoint; no pre-2026 timestamped SP observation exists in any committed or recoverable asset (#203 DATA_CARD: historical official 3SP is label-only with no trustworthy observation timestamp)

## Recovery
- decision-epoch SP triplets recovered: 741 matches / 17 issues; SP prices separate from de-vig columns.
- receipt: Q_BJ_SP_DEVIG RECOVERED

## Reconciliation
- Q_BJ_x_POWER_BJLINE: reconciled cells=0
- Q_BJ_x_EU_BJLINE: reconciled cells=0

## Modelability (REQ-S08)
        interface  fit_issues  fit_matches  tune_issues  tune_matches  calibration_issues  calibration_matches  2024_plus_issues  2024_plus_matches
        Q_BJ_x_SP           0            0            0             0                   0                    0                 0                  0
   Q_BJ_x_EU_x_SP           0            0            0             0                   0                    0                 0                  0
Q_BJ_x_POWER_x_SP           0            0            0             0                   0                    0                 0                  0

## #229 debt E1-E4
{
  "all_closed": true,
  "e1_binding": {
    "audited_sha": "0000000000000000000000000000000000000000",
    "binding_mode": "external_ev_review",
    "status": "BOUND"
  },
  "e2_schema_problems": [],
  "e3_crash_restart_probe": true,
  "e3_journal_consistent": true,
  "e4_protocol_problems": []
}
