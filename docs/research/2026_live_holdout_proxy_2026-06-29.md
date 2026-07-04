# 2026 Live Holdout Proxy

Date: 2026-06-29

## Scope

- This is a 2026-only live-data proxy, not the full production 384 replay.
- Training is frozen on pre-2026 historical rows; 2026 results are not used to train q.
- Historical DB: `../../data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- Live DB: `../../data/beidan_live.db`
- Snapshot used for selection: `1h`
- Training mode: `last_n` from `24112` to `25042`.
- Full issue settlement required: `True`.

## Data Inventory

| issue | matches | settled_matches | usable_settled_matches | full_issue_settled | pre_kick_eu_snapshot_matches | snapshot_1h_eu_matches | snapshot_10h_eu_matches | issue_start_ts | issue_close_ts | first_snapshot_ts | last_snapshot_ts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26051 | 393 | 393 | 393 | 1 | 335 | 331 | 307 | 2026-05-01T00:00:00 | 2026-05-05T08:30:00 | 2026-05-02T00:57:41Z | 2026-05-05T02:11:32Z |
| 26052 | 393 | 61 | 61 | 0 | 70 | 64 | 60 | 2026-04-30T19:30:00 | 2026-05-08T10:00:00 | 2026-05-05T02:16:53Z | 2026-05-08T02:46:43Z |
| 26053 | 334 | 334 | 334 | 1 | 325 | 325 | 325 | 2026-05-08T00:00:00 | 2026-05-12T03:15:00 | 2026-05-08T02:55:35Z | 2026-05-12T02:25:53Z |
| 26054 | 334 | 109 | 109 | 0 | 111 | 101 | 101 | 2026-05-09T21:55:00 | 2026-05-15T09:00:00 | 2026-05-12T02:41:19Z | 2026-05-15T02:45:42Z |
| 26055 | 297 | 297 | 297 | 1 | 294 | 294 | 294 | 2026-05-15T00:00:00 | 2026-05-19T06:00:00 | 2026-05-15T03:04:43Z | 2026-05-19T02:56:53Z |
| 26056 | 297 | 75 | 75 | 0 | 206 | 206 | 205 | 2026-05-17T20:55:00 | 2026-05-26T05:55:00 | 2026-05-19T03:03:40Z | 2026-05-22T03:39:24Z |
| 26057 | 205 | 205 | 205 | 1 | 203 | 203 | 203 | 2026-05-22T00:00:00 | 2026-05-26T06:00:00 | 2026-05-22T03:41:59Z | 2026-05-26T02:25:30Z |
| 26058 | 205 | 42 | 42 | 0 | 47 | 43 | 42 | 2026-05-23T19:55:00 | 2026-05-29T08:30:00 | 2026-05-26T02:29:56Z | 2026-05-29T02:51:16Z |
| 26061 | 132 | 132 | 132 | 1 | 131 | 131 | 131 | 2026-05-29T00:00:00 | 2026-06-02T07:00:00 | 2026-05-29T03:08:54Z | 2026-06-02T03:33:46Z |
| 26062 | 12 | 12 | 12 | 1 | 11 | 11 | 11 | 2026-06-02T00:00:00 | 2026-06-05T10:00:00 | 2026-06-02T03:53:31Z | 2026-06-05T02:37:56Z |
| 26063 | 51 | 51 | 51 | 1 | 50 | 50 | 50 | 2026-06-05T00:00:00 | 2026-06-09T07:00:00 | 2026-06-05T02:58:52Z | 2026-06-09T01:46:02Z |
| 26064 | 70 | 25 | 25 | 0 | 69 | 69 | 69 | 2026-06-09T00:00:00 | 2026-06-16T06:00:00 | 2026-06-09T02:00:36Z | 2026-06-12T03:10:08Z |
| 26065 | 70 | 70 | 70 | 1 | 70 | 70 | 70 | 2026-06-12T23:30:00 | 2026-06-16T09:00:00 | 2026-06-12T03:25:10Z | 2026-06-16T02:26:19Z |
| 26066 | 70 | 26 | 26 | 0 | 63 | 62 | 58 | 2026-06-15T06:55:00 | 2026-06-23T06:00:00 | 2026-06-16T02:47:59Z | 2026-06-19T06:01:37Z |
| 26067 | 58 | 58 | 58 | 1 | 58 | 58 | 58 | 2026-06-20T01:00:00 | 2026-06-23T11:00:00 | 2026-06-19T06:20:26Z | 2026-06-23T03:08:22Z |
| 26068 | 65 | 24 | 24 | 0 | 63 | 63 | 63 | 2026-06-23T00:00:00 | 2026-06-30T03:10:00 | 2026-06-23T03:31:06Z | 2026-06-26T03:35:15Z |
| 26069 | 67 | 63 | 63 | 0 | 65 | 65 | 65 | 2026-06-26T00:00:00 | 2026-06-30T09:00:00 | 2026-06-26T03:51:51Z | 2026-06-29T03:07:16Z |


## Tested Issues

| issue | matches | settled_matches | usable_settled_matches | full_issue_settled | pre_kick_eu_snapshot_matches | snapshot_1h_eu_matches | snapshot_10h_eu_matches | issue_start_ts | issue_close_ts | first_snapshot_ts | last_snapshot_ts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26051 | 393 | 393 | 393 | 1 | 335 | 331 | 307 | 2026-05-01T00:00:00 | 2026-05-05T08:30:00 | 2026-05-02T00:57:41Z | 2026-05-05T02:11:32Z |
| 26053 | 334 | 334 | 334 | 1 | 325 | 325 | 325 | 2026-05-08T00:00:00 | 2026-05-12T03:15:00 | 2026-05-08T02:55:35Z | 2026-05-12T02:25:53Z |
| 26055 | 297 | 297 | 297 | 1 | 294 | 294 | 294 | 2026-05-15T00:00:00 | 2026-05-19T06:00:00 | 2026-05-15T03:04:43Z | 2026-05-19T02:56:53Z |
| 26057 | 205 | 205 | 205 | 1 | 203 | 203 | 203 | 2026-05-22T00:00:00 | 2026-05-26T06:00:00 | 2026-05-22T03:41:59Z | 2026-05-26T02:25:30Z |
| 26061 | 132 | 132 | 132 | 1 | 131 | 131 | 131 | 2026-05-29T00:00:00 | 2026-06-02T07:00:00 | 2026-05-29T03:08:54Z | 2026-06-02T03:33:46Z |
| 26062 | 12 | 12 | 12 | 1 | 11 | 11 | 11 | 2026-06-02T00:00:00 | 2026-06-05T10:00:00 | 2026-06-02T03:53:31Z | 2026-06-05T02:37:56Z |
| 26063 | 51 | 51 | 51 | 1 | 50 | 50 | 50 | 2026-06-05T00:00:00 | 2026-06-09T07:00:00 | 2026-06-05T02:58:52Z | 2026-06-09T01:46:02Z |
| 26065 | 70 | 70 | 70 | 1 | 70 | 70 | 70 | 2026-06-12T23:30:00 | 2026-06-16T09:00:00 | 2026-06-12T03:25:10Z | 2026-06-16T02:26:19Z |
| 26067 | 58 | 58 | 58 | 1 | 58 | 58 | 58 | 2026-06-20T01:00:00 | 2026-06-23T11:00:00 | 2026-06-19T06:20:26Z | 2026-06-23T03:08:22Z |


## Excluded Issues

| issue | matches | settled_matches | usable_settled_matches | full_issue_settled | pre_kick_eu_snapshot_matches | snapshot_1h_eu_matches | snapshot_10h_eu_matches | issue_start_ts | issue_close_ts | first_snapshot_ts | last_snapshot_ts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26052 | 393 | 61 | 61 | 0 | 70 | 64 | 60 | 2026-04-30T19:30:00 | 2026-05-08T10:00:00 | 2026-05-05T02:16:53Z | 2026-05-08T02:46:43Z |
| 26054 | 334 | 109 | 109 | 0 | 111 | 101 | 101 | 2026-05-09T21:55:00 | 2026-05-15T09:00:00 | 2026-05-12T02:41:19Z | 2026-05-15T02:45:42Z |
| 26056 | 297 | 75 | 75 | 0 | 206 | 206 | 205 | 2026-05-17T20:55:00 | 2026-05-26T05:55:00 | 2026-05-19T03:03:40Z | 2026-05-22T03:39:24Z |
| 26058 | 205 | 42 | 42 | 0 | 47 | 43 | 42 | 2026-05-23T19:55:00 | 2026-05-29T08:30:00 | 2026-05-26T02:29:56Z | 2026-05-29T02:51:16Z |
| 26064 | 70 | 25 | 25 | 0 | 69 | 69 | 69 | 2026-06-09T00:00:00 | 2026-06-16T06:00:00 | 2026-06-09T02:00:36Z | 2026-06-12T03:10:08Z |
| 26066 | 70 | 26 | 26 | 0 | 63 | 62 | 58 | 2026-06-15T06:55:00 | 2026-06-23T06:00:00 | 2026-06-16T02:47:59Z | 2026-06-19T06:01:37Z |
| 26068 | 65 | 24 | 24 | 0 | 63 | 63 | 63 | 2026-06-23T00:00:00 | 2026-06-30T03:10:00 | 2026-06-23T03:31:06Z | 2026-06-26T03:35:15Z |
| 26069 | 67 | 63 | 63 | 0 | 65 | 65 | 65 | 2026-06-26T00:00:00 | 2026-06-30T09:00:00 | 2026-06-26T03:51:51Z | 2026-06-29T03:07:16Z |


## Budgeted Strategy Summary

| strategy | n_tickets | n_issues | hit_rate | issue_win_rate | profitable_issues | total_stake_units | total_profit_units | roi | best_issue_profit_share | avg_issue_stake_units | max_drawdown_pct_on_10000 | avg_full_cover_per_ticket | avg_double_cover_per_ticket | avg_pred_ev_per_stake | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_q_high_sp__budget256_fractional | 145 | 8 | 0.0000 | 0.0000 | 0 | 2048.0000 | -2048.0000 | -1.0000 |  | 256.0000 | -0.2048 | 0.0000 | 0.0000 | 376.3893 | insufficient_volume |
| ev_m0p95_p0p8_full_opt__budget256_fractional | 155 | 8 | 0.0000 | 0.0000 | 0 | 2048.0000 | -2048.0000 | -1.0000 |  | 256.0000 | -0.2048 | 0.0000 | 0.7032 | 5058.8492 | insufficient_volume |


## High-N Selector Summary

| period | source_strategy | selector | issues | tickets | hit_rate | issue_win_rate | stake_units | profit_units | roi | profit_per_issue | max_drawdown_units | max_loss_streak | best_issue_profit_units | best_issue_profit_share | ex_top1_roi | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | all | 8 | 155 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 19.3750 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | draw_free | 8 | 113 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 14.1250 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 8 | 67 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 8.3750 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 8 | 71 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 8.8750 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 8 | 71 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 8.8750 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 8 | 76 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 9.5000 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v1_topology_priority | 8 | 29 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 3.6250 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 8 | 29 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 3.6250 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | topology_neg0_ge5_pos3_ge1_d0 | 8 | 46 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 5.7500 |
| 2026_holdout | ev_m0p95_p0p8_full_opt__budget256_fractional | topology_neg0_ge6_d0 | 8 | 82 | 0.0000 | 0.0000 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -2048.0000 | 8 | -256.0000 |  | -1.0000 | 10.2500 |


## Ex-Best Issue

| strategy | n_issues | stake_units | profit_units | roi | best_issue_profit_units | profit_ex_best_issue | roi_ex_best_issue | best_issue_profit_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_q_high_sp__budget256_fractional | 8 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -1792.0000 | -0.8750 |  |
| ev_m0p95_p0p8_full_opt__budget256_fractional | 8 | 2048.0000 | -2048.0000 | -1.0000 | -256.0000 | -1792.0000 | -0.8750 |  |


## Decision Chain

| strategy | stage | n_base_matches | n_rows | pass_rate_vs_base | avg_best_single_ev_n7 | avg_match_ev_n7 | avg_chosen_ev_n7 | n_cover1 | n_cover2 | n_cover3 | n_protected_candidates | protected_candidate_rate | n_tickets | budget_profit_units | budget_roi | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt | outcome_estimation | 1473 | 4419 | 1.0000 |  |  |  |  |  |  |  |  |  |  |  |  |
| ev_m0p95_p0p8_full_opt | match_ev_filter | 1473 | 585 | 0.3971 | 1.0173 | 1.0223 |  |  |  |  |  |  |  |  |  |  |
| ev_m0p95_p0p8_full_opt | coverage_choice | 1473 | 585 | 0.3971 | 1.0173 | 1.0223 | 0.9536 | 405 | 180 | 0 | 180 | 0.3077 |  |  |  |  |
| ev_m0p95_p0p8_full_opt | ticket_construction | 1473 | 155 |  |  |  |  |  | 109 | 0 |  |  | 155 |  |  |  |
| ev_m0p95_p0p8_full_opt | portfolio_result | 1473 | 155 |  |  |  |  |  |  |  |  |  | 155 | -2048.0000 | -1.0000 | insufficient_volume |


## Interpretation Notes

- The no-leakage guard uses only snapshots at or before the 1h target before kickoff.
- Partially settled issues are excluded by default to avoid selecting from a biased subset of matches.
- `26011-26050` are not used in this strict 1h live-snapshot replay because
  they lack timestamped live snapshots locally. They do have average euro odds
  in `beidan_history.db`, so they should be tested separately as an avg-euro
  proxy holdout.
- The full production 384 sleeve replay still requires extending the standard modeling DB and ticket-generation chain into 2026.

## Files

- `results/2026_live_holdout_proxy_20260629/live_holdout_inventory.csv`
- `results/2026_live_holdout_proxy_20260629/live_holdout_summary.csv`
- `results/2026_live_holdout_proxy_20260629/live_holdout_issue_profit.csv`
- `results/2026_live_holdout_proxy_20260629/high_n_selector_summary.csv`
- `results/2026_live_holdout_proxy_20260629/high_n_selector_issue_profit.csv`
