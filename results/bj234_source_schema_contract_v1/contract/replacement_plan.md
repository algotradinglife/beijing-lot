# Migration-Free Replacement Plan (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1)

Obsolete ambiguous schemas are **removed from the accepted interface** rather than wrapped in compatibility layers (repository principle 1: no backward-compat tax).  Every legacy table is adjudicated:

- **REMOVE** — subsumed by the canonical schema; dropped from the accepted interface.
- **REDIRECT** — consumers switch to the canonical table; the legacy asset remains only as an ingestion source until a cleanup milestone.
- **KEEP_AS_SOURCE** — raw capture/source asset; registry receipt, not part of the accepted research interface.

| legacy_database | legacy_table | verdict | replacement | rationale |
|---|---|---|---|---|
| beidan_xlsm.sqlite | market_snapshots | REDIRECT | market_observation + market_quote (long Mx3, snapshot_kind label) | Legacy wide Mx3 rows with label snapshots map onto canonical market_observation/market_quote; labels stay LABEL_RELATIVE (RETROSPECTIVE_PROXY). |
| beidan_xlsm.sqlite | market_consensus | REMOVE | computed view over market_quote; never a stored table | Aggregated consensus is derivable; storing it invites drift with the raw quotes (REQ-DS04). |
| beidan_xlsm.sqlite | exotic_odds | REMOVE | out of accepted scope; market_type domain is 3/1/0 1X2 + hcap | Exotic (goals/half_full/score) markets are not in the frozen market_type domain; removed from the accepted interface. |
| beidan_xlsm.sqlite | matches | REDIRECT | fixture + team + team_alias + competition + competition_alias | Identity columns (issue, match_idx) carry 1 duplicate pair and 2,560 null kickoffs in legacy; canonical fixture enforces UNIQUE and NOT NULL. |
| beidan_xlsm.sqlite | action_candidates | REMOVE | derived selection views (not a source table) | Selection candidates are downstream derived artifacts, not source registry assets. |
| beidan_xlsm.sqlite | outcome_features | REMOVE | probability_estimate + derived feature views | Feature-engineered columns (kelly_*, euro_* moves) are derivable from market_quote/probability_estimate; removing the denormalized legacy table eliminates drift. |
| beidan_xlsm.sqlite | official_500_settlements | REDIRECT | settlement (physically separate namespace) | Settlement rows carry result + winning_sp + fetched_at; canonical settlement keeps result_code/winning_sp/settled_at_utc/source_id only. |
| beidan_xlsm.sqlite | official_3sp_settlements | REDIRECT | settlement (via raw export import) | Official 3SP export is a settlement source; #203 DATA_CARD adjudicates historical 3SP as label-only (no trustworthy observation time). |
| beidan_features.db | matches | REDIRECT | fixture + probability_estimate (EU p_close/p_open triplets) | EU probability features map onto canonical probability_estimate with estimator_id='eu_features_v1'; kickoff is SCHEDULE_ONLY. |
| beidan_history.db | historical_matches | REDIRECT | settlement + market_quote (avg closing odds as SETTLEMENT_ONLY proxy) | Settlement/history rows and average closing odds are not inference-time observations (REQ-DS03); REDIRECT to settlement namespace. |
| beidan_history.db | scrape_log | REDIRECT | ingestion_batch (batch receipt) | The scrape log's fetched_at/n_matches/status maps onto ingestion_batch.requested_at/received_at/row_count/status. |
| beidan_live.db | snapshots | REDIRECT | market_observation + market_quote (sp_1x2 + euro_1x2) | Live snapshots with snapshot_ts (TIMESTAMPED_UTC) are the primary prospective causal source; REDIRECT to canonical observation tables. |
| beidan_live.db | matches | REDIRECT | fixture + team_alias (fid alias) | Live matches carry fid; canonical fixture keeps source_match_key and resolves fid via alias crosswalk. |
| beidan_live.db | settlements | REDIRECT | settlement (source='live_collector') | Live settlements are after-event truth; canonical settlement namespace is physically separate (REQ-DS05). |
| 500_bjdc.sqlite | live_sp_snapshots | REDIRECT | market_observation + market_quote (sp_1x2) | 500.bjdc live SP captures with fetched_at are prospective timestamped captures; REDIRECT to canonical observation tables. |

## Contract checklist

- bj234_source_schema_contract_v1
- BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 / v1
