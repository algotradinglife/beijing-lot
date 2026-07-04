# Beidan Nowscore 2026 Update And N7 Core Replay

## Data Chain

- update DB: `data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite`
- issues: `26011` to `26051` across `34` issues
- matches: `6001`
- trusted settlements: `5641`
- missing settlements: `360`
- market rows: `720120`
- market scope: euro 1x2 and Kelly snapshots only; Asian handicap / over-under are intentionally deferred because full 2026 line fetch is 200k+ HTTP calls.

## 2025 Updater Validation

Validation issue `25042`:

## Match Alignment

- rows: `476`
- provider match id exact: `474`
- kickoff within 60s: `476`
- handicap exact: `0`
- old xlsm non-empty home names: `0`
- new parser non-empty home names: `476`

## Euro/Kelly Snapshot Comparison

- compared grouped rows: `57120`
- values filled by new parser where old was NULL: `2848`
- values missing in new parser where old had value: `2372`
- value differences where both non-null: `0`

Differences are expected where the old macro had shifted/partial cells; field-level CSVs are in the same result directory.

## N7 Core Walk-Forward Summary

| snapshot | period | strategy | n_tickets | n_issues | hit_rate | issue_win_rate | total_profit_units | roi | max_drawdown_units | max_issue_loss_streak | ex_best_profit_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10h | 2023_2026 | baseline_q_high_sp | 5068 | 114 | 0.34% | 7.89% | 4666.6 | 92.08% | -1987.3 | 30 | -393.5 |
| 10h | 2023_2026 | fixed_handicap_edges | 4845 | 114 | 0.25% | 7.02% | -790.5 | -10.54% | -4551.3 | 30 | -4551.3 |
| 10h | 2023_2026 | local_best_action_hcp | 5004 | 114 | 0.16% | 5.26% | 198.4 | 3.97% | -3549.5 | 39 | -3549.5 |
| 10h | 2023_2026 | local_best_plus_1_full | 4650 | 114 | 0.30% | 7.02% | -3032.5 | -21.74% | -8081.7 | 33 | -7807.3 |
| 1h | 2023_2026 | baseline_q_high_sp | 5023 | 114 | 0.24% | 7.89% | 8894.5 | 177.08% | -1667.3 | 33 | -3114.6 |
| 1h | 2023_2026 | fixed_handicap_edges | 4845 | 114 | 0.25% | 7.02% | -790.5 | -10.54% | -4551.3 | 30 | -4551.3 |
| 1h | 2023_2026 | local_best_action_hcp | 5004 | 114 | 0.16% | 5.26% | 198.4 | 3.97% | -3549.5 | 39 | -3549.5 |
| 1h | 2023_2026 | local_best_plus_1_full | 4650 | 114 | 0.30% | 7.02% | -3032.5 | -21.74% | -8081.7 | 33 | -7807.3 |
| 10h | 2026 | baseline_q_high_sp | 1214 | 33 | 0.16% | 6.06% | -712.8 | -58.71% | -786.8 | 16 | -1063.8 |
| 10h | 2026 | fixed_handicap_edges | 1178 | 33 | 0.17% | 3.03% | -3220.6 | -84.07% | -3756.0 | 30 | -3811.0 |
| 10h | 2026 | local_best_action_hcp | 1183 | 33 | 0.08% | 3.03% | -999.7 | -84.51% | -999.7 | 28 | -1133.0 |
| 10h | 2026 | local_best_plus_1_full | 941 | 33 | 0.11% | 3.03% | -2313.4 | -81.95% | -2313.4 | 28 | -2673.0 |
| 1h | 2026 | baseline_q_high_sp | 1242 | 33 | 0.00% | 0.00% | -1242.0 | -100.00% | -1242.0 | 33 | -1231.0 |
| 1h | 2026 | fixed_handicap_edges | 1178 | 33 | 0.17% | 3.03% | -3220.6 | -84.07% | -3756.0 | 30 | -3811.0 |
| 1h | 2026 | local_best_action_hcp | 1183 | 33 | 0.08% | 3.03% | -999.7 | -84.51% | -999.7 | 28 | -1133.0 |
| 1h | 2026 | local_best_plus_1_full | 941 | 33 | 0.11% | 3.03% | -2313.4 | -81.95% | -2313.4 | 28 | -2673.0 |

## Readout

- The Python updater reproduces old xlsm euro/Kelly values exactly where both have data, while filling many old NULL cells and restoring home-team names.
- 2026 coverage is now usable for euro/Kelly-based strategy evaluation through issue `26051`; settlement join is limited to rows present in `beidan_full_3sp.csv`.
- This replay is a core N=7 comparison, not the full 384 sleeve production replay. The full sleeve replay still needs its ticket-generation chain pointed at the combined modeling DB.

## Files

- `results/beidan_nowscore_update_20260629/walkforward_period_summary.csv`
- `results/beidan_walkforward_plus_2026_1h_n7_20260629`
- `results/beidan_walkforward_plus_2026_10h_n7_20260629`
- `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`
