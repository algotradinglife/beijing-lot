# N7 384 Switch Gate Discrimination

## Goal

The frozen dynamic rule switches to the defensive sleeve when prior-only `core_avg_pred_ev` falls into the rolling bottom 15%.
This report asks whether a second pre-bet gate can keep the rare convex rescues while removing unproductive switches.

## Candidate Results

| portfolio | gate_desc | profit_per_256 | roi | profit_delta_vs_base_units | max_drawdown_units | maxdd_delta_vs_base_units | max_dead_streak | switch_count | switch_delta_units | helped_count | hurt_count | flat_count | pre2023_switch_delta_units | recent_switch_delta_units | recent_profit_per_256 | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_dd32_smooth80_convex19 |  | 241249.2700 | 1.4086 |  | -15077.1643 |  | 7 |  |  |  |  |  |  |  | 77894.0415 | 0.9379 |
| frozen_original | low core predEV only | 253315.5103 | 1.4791 | 18099.3605 | -14751.6792 | 325.4851 | 7 | 93 | 18099.3605 | 2 | 6 | 85 | -1403.0483 | 19502.4087 | 90895.6473 | 0.9518 |
| core_count_ge12 | low predEV + core_ticket_count >= 12 | 253830.8204 | 1.4821 | 18872.3256 | -14751.6792 | 325.4851 | 7 | 43 | 18872.3256 | 2 | 3 | 38 | -630.0831 | 19502.4087 | 90895.6473 | 0.9548 |
| source_linegap_le0 | low predEV + same_ticket4_full_risk_avg_source_line_gap <= 0 | 253801.6136 | 1.4819 | 18828.5154 | -14751.6792 | 325.4851 | 7 | 42 | 18828.5154 | 2 | 2 | 38 | -673.8933 | 19502.4087 | 90895.6473 | 0.9546 |
| core_count_ge12_source_linegap_le0 | low predEV + core_ticket_count >= 12 + same_ticket4_full_risk_avg_source_line_gap <= 0 | 254250.8758 | 1.4846 | 19502.4087 | -14751.6792 | 325.4851 | 7 | 15 | 19502.4087 | 2 | 0 | 13 | -0.0000 | 19502.4087 | 90895.6473 | 0.9572 |
| core_count_ge12_core_linegap_le01 | low predEV + core_ticket_count >= 12 + core_avg_line_gap_net <= 0.1 | 254250.8758 | 1.4846 | 19502.4087 | -14751.6792 | 325.4851 | 7 | 12 | 19502.4087 | 2 | 0 | 10 | 0.0000 | 19502.4087 | 90895.6473 | 0.9572 |
| core_count_ge12_source_linegap_le0_exact_ratio_le25 | low predEV + core_ticket_count >= 12 + same_ticket4_full_risk_avg_source_line_gap <= 0 + core_exact_ticket_ratio <= 0.25 | 254250.8758 | 1.4846 | 19502.4087 | -14751.6792 | 325.4851 | 7 | 12 | 19502.4087 | 2 | 0 | 10 | -0.0000 | 19502.4087 | 90895.6473 | 0.9572 |
| core_count_ge12_source_linegap_le0_llgood_le40 | low predEV + core_ticket_count >= 12 + same_ticket4_full_risk_avg_source_line_gap <= 0 + core_avg_ll_good <= 0.4 | 254250.8758 | 1.4846 | 19502.4087 | -14751.6792 | 325.4851 | 7 | 9 | 19502.4087 | 2 | 0 | 7 | -0.0000 | 19502.4087 | 90895.6473 | 0.9572 |


## Switched-Issue Feature Diagnostics

| group | n | core_ticket_count_median | core_avg_pred_ev_median | core_avg_line_gap_net_median | core_avg_ll_good_median | all_ticket_count_median | core_exact_ticket_ratio_median | same_ticket4_full_risk_avg_source_line_gap_median |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| flat | 85 | 11.0000 | 562.6784 | 0.2222 | 0.2500 | 62.0000 | 0.1000 | 1.0000 |
| helped | 2 | 15.0000 | 943.6381 | -0.1389 | 0.2639 | 85.0000 | 0.1250 | -0.5000 |
| hurt | 6 | 12.0000 | 721.1510 | 0.6821 | 0.5778 | 66.5000 | 0.2158 | 1.5000 |


## Nonzero Switch Cases

| issue | calendar_year | group | delta_vs_base_units | core_ticket_count | core_avg_line_gap_net | core_avg_ll_good | core_exact_ticket_ratio | same_ticket4_full_risk_avg_source_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 140909 | 2014 | hurt | -182.2888 | 13.0000 | 0.2308 | 0.6923 | 0.1538 | 1.0000 |
| 160603 | 2016 | hurt | -399.4092 | 18.0000 | 1.1667 | 0.5556 | 0.2778 | 3.0000 |
| 180701 | 2018 | hurt | -366.1673 | 10.0000 | 0.1000 | 0.6000 | 0.3000 | 0.0000 |
| 191205 | 2019 | hurt | -48.3851 | 15.0000 | 1.1333 | 0.4000 | 0.1333 | 3.0000 |
| 20054 | 2020 | hurt | -307.7260 | 1.0000 | 0.0000 | 1.0000 | 1.0000 | 0.0000 |
| 20062 | 2020 | hurt | -99.0718 | 11.0000 | 1.6364 | 0.0909 | 0.0909 | 2.0000 |
| 23011 | 2023 | helped | 14548.0782 | 12.0000 | -0.3333 | 0.2500 | 0.2500 | 0.0000 |
| 24095 | 2024 | helped | 4954.3305 | 18.0000 | 0.0556 | 0.2778 | 0.0000 | -1.0000 |


## Best Candidate Period Check

| portfolio | period | n_issues | switch_count | switch_delta_units | base_profit_units | dynamic_profit_units | dynamic_delta_vs_base | base_roi | dynamic_roi | base_maxdd_units | dynamic_maxdd_units | maxdd_delta_vs_base |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| frozen_original | all | 669 | 93 | 18099.3605 | 361873.9050 | 379973.2655 | 18099.3605 | 1.4086 | 1.4791 | -15077.1643 | -14751.6792 | 325.4851 |
| frozen_original | train_like_2014_2022 | 540 | 75 | -1403.0483 | 245032.8427 | 243629.7945 | -1403.0483 | 1.1817 | 1.1749 | -12890.6740 | -12890.6740 | 0.0000 |
| frozen_original | recent_2023_2025 | 129 | 18 | 19502.4087 | 116841.0623 | 136343.4710 | 19502.4087 | 2.3587 | 2.7524 | -15077.1643 | -14751.6792 | 325.4851 |
| frozen_original | weak_recent_2024_2025 | 74 | 12 | 4954.3305 | 553.3278 | 5507.6583 | 4954.3305 | 0.0195 | 0.1938 | -8008.4025 | -7682.9174 | 325.4851 |
| core_count_ge12_source_linegap_le0 | all | 669 | 15 | 19502.4087 | 361873.9050 | 381376.3138 | 19502.4087 | 1.4086 | 1.4846 | -15077.1643 | -14751.6792 | 325.4851 |
| core_count_ge12_source_linegap_le0 | train_like_2014_2022 | 540 | 11 | 0.0000 | 245032.8427 | 245032.8427 | 0.0000 | 1.1817 | 1.1817 | -12890.6740 | -12890.6740 | 0.0000 |
| core_count_ge12_source_linegap_le0 | recent_2023_2025 | 129 | 4 | 19502.4087 | 116841.0623 | 136343.4710 | 19502.4087 | 2.3587 | 2.7524 | -15077.1643 | -14751.6792 | 325.4851 |
| core_count_ge12_source_linegap_le0 | weak_recent_2024_2025 | 74 | 3 | 4954.3305 | 553.3278 | 5507.6583 | 4954.3305 | 0.0195 | 0.1938 | -8008.4025 | -7682.9174 | 325.4851 |


## Best Candidate Rolling Check

| portfolio | window | n_windows | positive_delta_rate | positive_maxdd_delta_rate | avg_delta_units | median_delta_units | worst_delta_units | best_delta_units | avg_maxdd_delta_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| frozen_original | 40 | 630 | 0.1286 | 0.0095 | 1086.2536 | 0.0000 | -455.1829 | 14548.0782 | -53.2150 |
| frozen_original | 80 | 590 | 0.2153 | 0.0475 | 2051.3954 | -182.2888 | -455.1829 | 14548.0782 | -53.1256 |
| frozen_original | 120 | 550 | 0.2527 | 0.0545 | 3169.8473 | -366.1673 | -821.3502 | 19502.4087 | -78.8118 |
| core_count_ge12_source_linegap_le0 | 40 | 630 | 0.1143 | 0.0048 | 1175.3360 | 0.0000 | -0.0000 | 14548.0782 | -0.0000 |
| core_count_ge12_source_linegap_le0 | 80 | 590 | 0.1898 | 0.0322 | 2241.3302 | 0.0000 | -0.0000 | 14548.0782 | 8.2750 |
| core_count_ge12_source_linegap_le0 | 120 | 550 | 0.2345 | 0.0364 | 3462.3781 | 0.0000 | -0.0000 | 19502.4087 | 8.8769 |


## Drawdown Attribution For Best Candidate

| period | n_issues | switch_count | switch_delta_units | base_profit_units | dynamic_profit_units | dynamic_delta_vs_base | base_roi | dynamic_roi | base_maxdd_units | dynamic_maxdd_units | maxdd_delta_vs_base | peak_issue | trough_issue | window_issues | source_maxdd_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base_maxdd_window | 113 | 3 | 4954.3305 | -15077.1643 | -10122.8338 | 4954.3305 | -0.3475 | -0.2333 | -15077.1643 | -14751.6792 | 325.4851 | 23012 | 25012 | 113 | -15077.1643 |
| dynamic_maxdd_window | 95 | 2 | 0.0000 | -14751.6792 | -14751.6792 | 0.0000 | -0.4044 | -0.4044 | -14751.6792 | -14751.6792 | 0.0000 | 23012 | 24091 | 95 | -14751.6792 |


## Interpretation

- Best exploratory candidate: `core_count_ge12_source_linegap_le0`.
- The useful pattern is not simply weak quality. It is weak quality plus enough core breadth plus a defensive source that is not riding a positive line-gap signal.
- This keeps the two nonzero positive switches in 2023/2024 and removes the six nonzero negative switches in 2014-2020.
- This is still a research selector, not a production replacement: the positive sample has only two cases, so the rule is fragile until monitored on fresh issues.

## Files

- `results/n7_384_switch_gate_discrimination_20260629/switch_feature_rows.csv`
- `results/n7_384_switch_gate_discrimination_20260629/switch_feature_group_summary.csv`
- `results/n7_384_switch_gate_discrimination_20260629/gate_candidate_summary.csv`
- `results/n7_384_switch_gate_discrimination_20260629/gate_candidate_period_summary.csv`
- `results/n7_384_switch_gate_discrimination_20260629/gate_candidate_rolling_summary.csv`
- `results/n7_384_switch_gate_discrimination_20260629/best_gate_issue_profit.csv`
- `docs/research/figures/n7_384_switch_gate_discrimination_2026-06-29.svg`
