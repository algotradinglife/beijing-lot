# High-N directional cluster and q/conf ML feature audit

## Scope

- Directional gate: existing N7 EV-framework budget tickets.
- ML feature audit: `joint_leg_rows.csv`, train 2014-2022, test 2023-2025.
- Model features are pre-match only. `hit`, `winning_sp`, and realized multipliers are labels/reporting only.

## Recent Directional Gates

| strategy | gate | active_issues | active_issue_share | scaled_profit_units | scaled_roi_active | scaled_profit_per_all_issue | scaled_issue_win_rate | hit_stake_rate | median_hit_unit_payout | best_scaled_issue_profit_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_ge6 | 129 | 1.0000 | 51651.8753 | 1.5641 | 400.4021 | 0.0465 | 0.0033 | 232.0736 | 1.1802 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_ge6_draw_free | 129 | 1.0000 | 51651.8753 | 1.5641 | 400.4021 | 0.0465 | 0.0035 | 232.0736 | 1.1802 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | mixed_neg0_ge4_pos3_ge1_draw_le1 | 124 | 0.9612 | 40402.2266 | 1.2728 | 313.1956 | 0.0161 | 0.0054 | 92.6114 | 1.5088 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | mixed_neg0_ge4_pos3_ge1 | 125 | 0.9690 | 40146.2266 | 1.2546 | 311.2111 | 0.0160 | 0.0052 | 92.6114 | 1.5184 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_ge5 | 129 | 1.0000 | 34246.4460 | 1.0370 | 265.4763 | 0.0465 | 0.0034 | 189.7245 | 1.2693 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_ge5_draw_free | 129 | 1.0000 | 34246.4460 | 1.0370 | 265.4763 | 0.0465 | 0.0036 | 189.7245 | 1.2693 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 129 | 1.0000 | 21047.6423 | 0.6373 | 163.1600 | 0.0543 | 0.0044 | 136.9078 | 1.4420 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | directional_ge6 | 129 | 1.0000 | 21047.6423 | 0.6373 | 163.1600 | 0.0543 | 0.0044 | 136.9078 | 1.4420 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | directional_ge7 | 129 | 1.0000 | 21047.6423 | 0.6373 | 163.1600 | 0.0543 | 0.0044 | 136.9078 | 1.4420 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | draw_free | 129 | 1.0000 | 17945.2577 | 0.5434 | 139.1105 | 0.0465 | 0.0033 | 163.3162 | 1.6913 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | directional_ge6_draw_le1 | 129 | 1.0000 | 17945.2577 | 0.5434 | 139.1105 | 0.0465 | 0.0032 | 163.3162 | 1.6913 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_ge7 | 127 | 0.9845 | -7016.5482 | -0.2158 | -54.3918 | 0.0315 | 0.0028 | 232.0736 |  |
| ev_m0p95_p0p85_full_opt__budget256_fractional | pos3_ge2_neg0_ge3 | 117 | 0.9070 | -18097.7411 | -0.6042 | -140.2926 | 0.0085 | 0.0037 | 92.6114 |  |
| ev_m0p95_p0p8_full_opt__budget256_fractional | mixed_neg0_ge4_pos3_ge1_draw_le1 | 123 | 0.9535 | 101873.5166 | 3.2353 | 789.7172 | 0.0163 | 0.0069 | 92.6114 | 1.1993 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_ge6_draw_free | 129 | 1.0000 | 46436.4844 | 1.4061 | 359.9727 | 0.0465 | 0.0039 | 232.0736 | 1.0930 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_ge5_draw_free | 129 | 1.0000 | 44365.9517 | 1.3434 | 343.9221 | 0.0465 | 0.0041 | 189.7245 | 1.1440 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_ge6 | 129 | 1.0000 | 39148.9499 | 1.1855 | 303.4802 | 0.0465 | 0.0032 | 232.0736 | 1.1104 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_ge5 | 129 | 1.0000 | 37078.4172 | 1.1228 | 287.4296 | 0.0465 | 0.0033 | 189.7245 | 1.1724 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | draw_free | 129 | 1.0000 | 27254.0211 | 0.8253 | 211.2715 | 0.0465 | 0.0040 | 163.3162 | 1.3944 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | mixed_neg0_ge4_pos3_ge1 | 125 | 0.9690 | 26019.6212 | 0.8131 | 201.7025 | 0.0160 | 0.0048 | 92.6114 | 1.7999 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | directional_ge6_draw_le1 | 129 | 1.0000 | 20899.0200 | 0.6328 | 162.0079 | 0.0465 | 0.0038 | 163.3162 | 1.6150 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 129 | 1.0000 | 533.1251 | 0.0161 | 4.1328 | 0.0465 | 0.0028 | 163.3162 | 29.7365 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | directional_ge6 | 129 | 1.0000 | 533.1251 | 0.0161 | 4.1328 | 0.0465 | 0.0028 | 163.3162 | 29.7365 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | directional_ge7 | 129 | 1.0000 | 533.1251 | 0.0161 | 4.1328 | 0.0465 | 0.0028 | 163.3162 | 29.7365 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_ge7 | 127 | 0.9845 | -3839.3049 | -0.1181 | -29.7621 | 0.0315 | 0.0028 | 232.0736 |  |
| ev_m0p95_p0p8_full_opt__budget256_fractional | pos3_ge2_neg0_ge3 | 118 | 0.9147 | -18353.7411 | -0.6076 | -142.2771 | 0.0085 | 0.0035 | 92.6114 |  |


## Recent Topologies

| strategy | topology | active_issues | scaled_profit_units | scaled_roi_active | scaled_issue_win_rate | median_hit_unit_payout |
| --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 101 | 136266.5169 | 5.2702 | 0.0198 | 1231.0966 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 127 | -7016.5482 | -0.2158 | 0.0315 | 232.0736 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 83 | -7509.3577 | -0.3534 | 0.0120 | 107.3331 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_1_pos3_6_draw_0 | 39 | -9984.0000 | -1.0000 | 0.0000 |  |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 88 | -12558.1244 | -0.5574 | 0.0114 | 77.8897 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_2_pos3_5_draw_0 | 51 | -13056.0000 | -1.0000 | 0.0000 |  |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_0_pos3_7_draw_0 | 53 | -13568.0000 | -1.0000 | 0.0000 |  |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_3_pos3_4_draw_0 | 58 | -14848.0000 | -1.0000 | 0.0000 |  |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 96 | 188559.2585 | 7.6725 | 0.0208 | 1231.0966 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 127 | -3839.3049 | -0.1181 | 0.0315 | 232.0736 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 72 | -4693.3577 | -0.2546 | 0.0139 | 107.3331 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 77 | -9742.1244 | -0.4942 | 0.0130 | 77.8897 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_2_pos3_5_draw_0 | 42 | -10752.0000 | -1.0000 | 0.0000 |  |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_0_pos3_7_draw_0 | 44 | -11264.0000 | -1.0000 | 0.0000 |  |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_3_pos3_4_draw_0 | 52 | -13312.0000 | -1.0000 | 0.0000 |  |


## ML Model Summary

| model | train_rows | test_rows | train_auc | test_auc | test_log_loss | test_brier |
| --- | --- | --- | --- | --- | --- | --- |
| logistic | 52475 | 12548 | 0.6035 | 0.5918 | 0.6764 | 0.2419 |
| random_forest | 52475 | 12548 | 0.6701 | 0.5912 | 0.6764 | 0.2419 |


## Random Forest Feature Importance

| feature | importance |
| --- | --- |
| snapshot_odds | 0.0847 |
| snapshot_p | 0.0825 |
| selected_market_p | 0.0811 |
| q_conf_product | 0.0701 |
| q_score | 0.0681 |
| selected_model_p | 0.0596 |
| q_minus_conf | 0.0529 |
| model_market_ratio | 0.0487 |
| q_conf_ratio | 0.0469 |
| pred_sp_multiplier | 0.0456 |
| margin | 0.0426 |
| action_code | 0.0417 |
| pocket | 0.0412 |
| ll_pocket | 0.0388 |
| top_p | 0.0383 |
| is_draw | 0.0353 |
| conf_weight | 0.0314 |
| hcp | 0.0149 |
| hcp_bucket | 0.0138 |
| quad2 | 0.0099 |
| q_bucket | 0.0097 |
| drift_bucket | 0.0094 |
| selected_prob_rank | 0.0088 |
| confidence_bucket | 0.0079 |
| top2_agree | 0.0054 |


## Permutation Importance

| feature | importance_mean | importance_std |
| --- | --- | --- |
| snapshot_odds | 0.0055 | 0.0018 |
| snapshot_p | 0.0029 | 0.0011 |
| selected_market_p | 0.0025 | 0.0010 |
| pocket | 0.0016 | 0.0011 |
| q_score | 0.0011 | 0.0004 |
| is_draw | 0.0011 | 0.0009 |
| action_code | 0.0010 | 0.0009 |
| ll_pocket | 0.0010 | 0.0008 |
| q_minus_conf | 0.0010 | 0.0003 |
| hcp | 0.0007 | 0.0001 |
| hcp_bucket | 0.0007 | 0.0001 |
| q_conf_ratio | 0.0004 | 0.0002 |
| is_pos3 | 0.0001 | 0.0000 |
| drift_bucket | 0.0000 | 0.0002 |
| is_neg0 | 0.0000 | 0.0000 |
| is_LL | -0.0000 | 0.0000 |
| top2_agree | -0.0000 | 0.0000 |
| top1_agree | -0.0001 | 0.0001 |
| pred_sp_multiplier | -0.0001 | 0.0003 |
| selected_prob_rank | -0.0001 | 0.0001 |
| conf_weight | -0.0001 | 0.0003 |
| margin | -0.0002 | 0.0003 |
| q_conf_product | -0.0003 | 0.0005 |
| confidence_bucket | -0.0003 | 0.0003 |
| quad2 | -0.0003 | 0.0002 |


## Univariate AUC

| feature | auc | auc_inverse | mean_hit | mean_miss |
| --- | --- | --- | --- | --- |
| selected_market_p | 0.5681 | 0.4319 | 0.1869 | 0.1784 |
| snapshot_p | 0.5681 | 0.4319 | 0.1869 | 0.1784 |
| selected_model_p | 0.5615 | 0.4385 | 0.3996 | 0.3776 |
| conf_weight | 0.5550 | 0.4450 | 1.3179 | 1.2915 |
| top1_agree | 0.5527 | 0.4473 | 0.6037 | 0.4982 |
| hcp | 0.5371 | 0.4629 | -0.5506 | -0.6760 |
| top2_agree | 0.5329 | 0.4671 | 0.8644 | 0.7985 |
| q_conf_product | 0.5288 | 0.4712 | 2.3417 | 2.2579 |
| is_neg0 | 0.5231 | 0.4769 | 0.6691 | 0.6228 |
| is_pos3 | 0.5139 | 0.4861 | 0.2628 | 0.2350 |
| model_market_ratio | 0.5131 | 0.4869 | 2.1785 | 2.1468 |
| margin | 0.5118 | 0.4882 | 0.1411 | 0.1365 |
| q_score | 0.5100 | 0.4900 | 1.7680 | 1.7353 |
| top_p | 0.5093 | 0.4907 | 0.4534 | 0.4508 |
| q_minus_conf | 0.4917 | 0.5083 | 0.4502 | 0.4438 |
| q_conf_ratio | 0.4871 | 0.5129 | 1.3515 | 1.3519 |
| pred_sp_multiplier | 0.4847 | 0.5153 | 0.7396 | 0.7469 |
| is_LL | 0.4744 | 0.5256 | 0.1951 | 0.2463 |
| is_draw | 0.4630 | 0.5370 | 0.0681 | 0.1422 |
| selected_prob_rank | 0.4414 | 0.5586 | 1.5319 | 1.7032 |
| snapshot_odds | 0.4322 | 0.5678 | 5.1511 | 5.3983 |


## q/conf Period Quadrants

| period | quad2 | n_legs | n_issues | hit_rate | avg_snapshot_p | avg_snapshot_odds | avg_realized_sp_multiplier_on_hits | avg_winning_sp_on_hits | market_q_proxy | drift_adjusted_ev_proxy | baseline_ticket_uses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014-2022 | HH | 15770 | 548 | 0.4244 | 0.1707 | 5.5952 | 0.4850 | 2.6337 | 2.4866 | 1.2061 | 29427 |
| 2014-2022 | HL | 10599 | 546 | 0.3789 | 0.1593 | 5.9647 | 0.5184 | 3.0286 | 2.3787 | 1.2332 | 16601 |
| 2014-2022 | LH | 14442 | 548 | 0.4553 | 0.2144 | 4.3899 | 0.5557 | 2.3906 | 2.1238 | 1.1803 | 16131 |
| 2014-2022 | LL | 11664 | 547 | 0.3355 | 0.1790 | 5.3812 | 0.5993 | 3.0637 | 1.8740 | 1.1230 | 9920 |
| 2023-2025 | HH | 3925 | 128 | 0.3931 | 0.1705 | 5.5790 | 0.5179 | 2.8148 | 2.3061 | 1.1942 | 6836 |
| 2023-2025 | HL | 2378 | 126 | 0.3604 | 0.1600 | 5.9419 | 0.5316 | 3.0906 | 2.2523 | 1.1974 | 3777 |
| 2023-2025 | LH | 3404 | 128 | 0.4477 | 0.2122 | 4.4455 | 0.5743 | 2.5103 | 2.1098 | 1.2118 | 4186 |
| 2023-2025 | LL | 2841 | 128 | 0.3347 | 0.1789 | 5.4113 | 0.6077 | 3.1416 | 1.8706 | 1.1368 | 2533 |


## Recent q/conf Pocket Value

| quad2 | pocket | n_legs | n_issues | hit_rate | avg_snapshot_p | avg_snapshot_odds | avg_realized_sp_multiplier_on_hits | avg_winning_sp_on_hits | market_q_proxy | drift_adjusted_ev_proxy | baseline_ticket_uses |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HH | 0@<=-2 | 148 | 79 | 0.5743 | 0.1267 | 7.3141 | 0.2808 | 2.0345 | 4.5335 | 1.2730 | 617 |
| HL | 3@1 | 130 | 43 | 0.3462 | 0.1568 | 6.0929 | 0.5724 | 3.3818 | 2.2072 | 1.2634 | 233 |
| LL | 0@-1 | 611 | 116 | 0.4812 | 0.2215 | 4.2006 | 0.5646 | 2.3618 | 2.1722 | 1.2264 | 771 |
| LH | 0@-1 | 1633 | 124 | 0.4709 | 0.2206 | 4.2002 | 0.5722 | 2.3886 | 2.1346 | 1.2214 | 1933 |
| HH | 3@1 | 297 | 59 | 0.3737 | 0.1789 | 5.3313 | 0.5775 | 3.0153 | 2.0887 | 1.2062 | 602 |
| LH | 3@1 | 1686 | 126 | 0.4312 | 0.2071 | 4.5943 | 0.5742 | 2.5898 | 2.0824 | 1.1957 | 2179 |
| HL | 0@-1 | 2245 | 126 | 0.3608 | 0.1602 | 5.9310 | 0.5301 | 3.0777 | 2.2516 | 1.1935 | 3532 |
| HH | 0@-1 | 3401 | 127 | 0.3828 | 0.1726 | 5.4867 | 0.5363 | 2.8749 | 2.2179 | 1.1894 | 5411 |
| LL | 3@1 | 883 | 116 | 0.3930 | 0.1857 | 5.2143 | 0.5533 | 2.7888 | 2.1167 | 1.1712 | 1158 |
| LL | 1@<=-2 | 1347 | 122 | 0.2301 | 0.1552 | 6.0895 | 0.7095 | 4.2761 | 1.4825 | 1.0518 | 604 |


## Files

- Directional gates: `results/high_n_directional_ml_20260628/directional_gate_summary.csv`
- Directional topologies: `results/high_n_directional_ml_20260628/directional_topology_summary.csv`
- ML model summary: `results/high_n_directional_ml_20260628/ml_model_summary.csv`
- RF importance: `results/high_n_directional_ml_20260628/ml_rf_importance.csv`
- Permutation importance: `results/high_n_directional_ml_20260628/ml_permutation_importance.csv`
- q/conf quadrants: `results/high_n_directional_ml_20260628/q_conf_period_quad_value.csv`
- q/conf pockets: `results/high_n_directional_ml_20260628/q_conf_recent_pocket_value.csv`
