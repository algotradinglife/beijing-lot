# N7 384 Drawdown Diagnostics And Dynamic Allocator

## Scope

- Base profile: `b384_dd32_smooth80_convex19`.
- MaxDD window: peak issue `23012` to trough issue `25012`, segment issues `113`, drawdown `-15077.2` units.
- Dynamic allocator uses current-issue pre-bet features and rolling thresholds from prior issues only.

## Baseline

| portfolio | issues | stake_units | profit_units | profit_per_256 | roi | issue_win_rate | non_full_loss_rate | full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_loss_streak | max_dead_streak | best_issue_profit_units | roi_ex_best_issue | recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| b384_dd32_smooth80_convex19 | 669 | 256896.0000 | 361873.9050 | 241249.2700 | 1.4086 | 0.1779 | 0.5157 | 0.4843 | -15077.1643 | -10051.4429 | 30 | 7 | 121287.2383 | 0.9379 | 77894.0415 |


## Component Attribution

| component | segment | issues | stake_units | profit_units | roi | win_issues | full_loss_issues | avg_profit_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current | maxdd_window | 113 | 28928.0000 | -17101.6084 | -0.5912 | 8 | 67 | -151.3417 |
| current | outside_window | 556 | 142336.0000 | 221601.3164 | 1.5569 | 63 | 308 | 398.5635 |
| current | all | 669 | 171264.0000 | 204499.7081 | 1.1941 | 71 | 375 | 305.6797 |
| n7prot_same_ticket2_alt_risk__budget256_fractional | maxdd_window | 113 | 3616.0000 | 3311.8177 | 0.9159 | 2 | 111 | 29.3081 |
| n7prot_same_ticket2_alt_risk__budget256_fractional | outside_window | 556 | 17792.0000 | 20730.2445 | 1.1651 | 14 | 539 | 37.2846 |
| n7prot_same_ticket2_alt_risk__budget256_fractional | all | 669 | 21408.0000 | 24042.0621 | 1.1230 | 16 | 650 | 35.9373 |
| n7prot_same_ticket2_draw_risk__budget256_fractional | maxdd_window | 113 | 2169.6000 | -2169.6000 | -1.0000 | 0 | 113 | -19.2000 |
| n7prot_same_ticket2_draw_risk__budget256_fractional | outside_window | 556 | 10675.2000 | 118320.9892 | 11.0837 | 13 | 540 | 212.8075 |
| n7prot_same_ticket2_draw_risk__budget256_fractional | all | 669 | 12844.8000 | 116151.3892 | 9.0427 | 13 | 653 | 173.6194 |
| n7prot_same_ticket4_full_risk__budget256_fractional | maxdd_window | 113 | 8678.4000 | 882.2264 | 0.1017 | 12 | 101 | 7.8073 |
| n7prot_same_ticket4_full_risk__budget256_fractional | outside_window | 556 | 42700.8000 | 16298.5193 | 0.3817 | 82 | 469 | 29.3139 |
| n7prot_same_ticket4_full_risk__budget256_fractional | all | 669 | 51379.2000 | 17180.7456 | 0.3344 | 94 | 570 | 25.6812 |


## Same-Budget 384 Portfolios Inside MaxDD Window

| portfolio | window_profit_units | window_roi | window_win_rate | window_full_loss_rate | full_profit_per_256 | full_maxdd_units | full_recent_profit_per_256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| b384_dd64_smooth100 | -9742.7844 | -0.2245 | 0.1593 | 0.4956 | 177934.0803 | -15243.0899 | 86188.1755 |
| b384_dd64_smooth80_convex19 | -11336.2221 | -0.2613 | 0.1504 | 0.4956 | 227647.9482 | -15965.0676 | 89863.7645 |
| b384_dd32_smooth100 | -12687.0077 | -0.2924 | 0.1681 | 0.4956 | 166678.4682 | -13202.9307 | 72380.6582 |
| b384_dd32_safe80_convex19 | -14915.2713 | -0.3437 | 0.1770 | 0.5044 | 241980.2951 | -15477.7035 | 78001.9702 |
| b384_dd32_smooth80_convex19 | -15077.1643 | -0.3475 | 0.1593 | 0.4956 | 241249.2700 | -15077.1643 | 77894.0415 |
| b384_dd32_smooth50_convex50 | -18662.3992 | -0.4301 | 0.1416 | 0.4956 | 353105.4728 | -18662.3992 | 86164.1166 |
| b384_dd32_safe35_convex65 | -20384.1884 | -0.4698 | 0.1150 | 0.5044 | 409353.3977 | -20384.1884 | 90346.3729 |
| b384_dd32_smooth35_convex65 | -20455.0167 | -0.4714 | 0.1150 | 0.4956 | 409033.5742 | -20455.0167 | 90299.1541 |


## Pre-Bet Feature Differences In MaxDD Window

| feature | window_mean | outside_mean | diff | std_diff | window_median | outside_median | window_n | outside_n |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_avg_line_gap_net | 0.3066 | 1.3643 | -1.0577 | -1.0449 | 0.2308 | 1.3333 | 113 | 553 |
| all_avg_line_gap_net | 0.4528 | 1.4697 | -1.0170 | -1.0323 | 0.4091 | 1.4442 | 113 | 556 |
| all_avg_abs_line_gap | 0.2601 | 0.3321 | -0.0720 | -0.9958 | 0.2565 | 0.3243 | 113 | 556 |
| core_linegap_x_tickets | 4.1858 | 19.4029 | -15.2170 | -0.9832 | 3.0000 | 18.0000 | 113 | 556 |
| core_avg_abs_line_gap | 0.2497 | 0.3175 | -0.0678 | -0.9209 | 0.2502 | 0.3066 | 113 | 553 |
| core_avg_conf | 1.3302 | 1.3768 | -0.0467 | -0.7701 | 1.3266 | 1.3753 | 111 | 550 |
| all_avg_conf | 1.3399 | 1.3816 | -0.0417 | -0.7317 | 1.3372 | 1.3792 | 112 | 552 |
| exact_avg_line_gap_net | 0.5503 | 1.6993 | -1.1489 | -0.7104 | 0.5000 | 1.3333 | 84 | 396 |
| c4_k2_full_risk_avg_source_line_gap | 0.3673 | 1.4828 | -1.1156 | -0.6891 | 0.0000 | 1.0000 | 113 | 553 |
| exact_avg_abs_line_gap | 0.2714 | 0.3500 | -0.0786 | -0.6782 | 0.2597 | 0.3432 | 84 | 396 |
| same_ticket2_alt_risk_avg_source_line_gap | 0.1947 | 1.2821 | -1.0874 | -0.6752 | 0.0000 | 1.0000 | 113 | 553 |
| same_ticket2_draw_risk_avg_source_line_gap | 0.1947 | 1.2821 | -1.0874 | -0.6752 | 0.0000 | 1.0000 | 113 | 553 |
| same_ticket4_full_risk_avg_source_line_gap | 0.1947 | 1.2821 | -1.0874 | -0.6752 | 0.0000 | 1.0000 | 113 | 553 |
| core_avg_q | 2.1838 | 2.5730 | -0.3891 | -0.6095 | 2.0985 | 2.4168 | 111 | 550 |
| all_avg_q | 2.1738 | 2.5430 | -0.3692 | -0.5873 | 2.0930 | 2.3992 | 112 | 552 |
| exact_avg_conf | 1.3377 | 1.3866 | -0.0489 | -0.5585 | 1.3250 | 1.3816 | 81 | 372 |
| core_avg_pred_hit | 0.0009 | 0.0017 | -0.0007 | -0.5542 | 0.0008 | 0.0013 | 113 | 553 |
| all_avg_pred_ev | 4393.1663 | 7991.2774 | -3598.1111 | -0.4973 | 3316.0435 | 5867.1640 | 113 | 556 |
| all_avg_selector_score | 93.5330 | 165.0991 | -71.5660 | -0.4966 | 73.2101 | 121.5590 | 113 | 556 |
| core_avg_pred_ev | 4859.8133 | 8773.2470 | -3913.4336 | -0.4867 | 3933.5085 | 6242.8272 | 113 | 553 |
| core_avg_selector_score | 101.9944 | 179.7198 | -77.7254 | -0.4847 | 85.1678 | 128.6755 | 113 | 553 |
| exact_avg_selector_score | 92.2638 | 164.3157 | -72.0520 | -0.4714 | 65.9349 | 96.8114 | 84 | 396 |
| all_avg_pred_hit | 0.0010 | 0.0017 | -0.0006 | -0.4705 | 0.0009 | 0.0013 | 113 | 556 |
| exact_avg_pred_ev | 3803.9027 | 7395.5109 | -3591.6082 | -0.4701 | 2491.1217 | 4031.6521 | 84 | 396 |


## Dynamic Allocator: Balanced Candidates

| portfolio | feature | bad_side | low_q | high_q | defensive_portfolio | aggressive_portfolio | profit_per_256 | roi | non_full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_core_ticket_count_low_l20_h60__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_ticket_count | low | 0.2000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 239761.5822 | 1.4000 | 0.5157 | -14656.0763 | -9770.7175 | 7 | 78174.7669 | defensive:140;neutral:529 |
| dyn_core_ticket_count_low_l20_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_ticket_count | low | 0.2000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 239761.5822 | 1.4000 | 0.5157 | -14656.0763 | -9770.7175 | 7 | 78174.7669 | defensive:140;neutral:529 |
| dyn_core_ticket_count_low_l20_h80__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_ticket_count | low | 0.2000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 239761.5822 | 1.4000 | 0.5157 | -14656.0763 | -9770.7175 | 7 | 78174.7669 | defensive:140;neutral:529 |
| dyn_core_avg_pred_ev_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248834.7579 | 1.4529 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:121;neutral:548 |
| dyn_core_avg_pred_ev_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248834.7579 | 1.4529 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:121;neutral:548 |
| dyn_core_avg_pred_ev_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248834.7579 | 1.4529 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:121;neutral:548 |
| dyn_core_avg_selector_score_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248681.5299 | 1.4520 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:126;neutral:543 |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248681.5299 | 1.4520 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:126;neutral:543 |
| dyn_core_avg_selector_score_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248681.5299 | 1.4520 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:126;neutral:543 |
| dyn_core_ticket_count_low_l20_h60__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | core_ticket_count | low | 0.2000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 239572.9084 | 1.3989 | 0.5157 | -14909.9730 | -9939.9820 | 7 | 78439.0444 | aggressive:285;defensive:140;neutral:244 |
| dyn_core_avg_selector_score_low_l20_h60__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 235258.9878 | 1.3737 | 0.5157 | -14924.3315 | -9949.5543 | 7 | 70721.8910 | defensive:126;neutral:543 |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 235258.9878 | 1.3737 | 0.5157 | -14924.3315 | -9949.5543 | 7 | 70721.8910 | defensive:126;neutral:543 |
| dyn_core_avg_selector_score_low_l20_h80__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 235258.9878 | 1.3737 | 0.5157 | -14924.3315 | -9949.5543 | 7 | 70721.8910 | defensive:126;neutral:543 |
| dyn_core_avg_pred_ev_low_l20_h60__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 235029.1459 | 1.3723 | 0.5157 | -14924.3315 | -9949.5543 | 7 | 70721.8910 | defensive:121;neutral:548 |
| dyn_core_avg_pred_ev_low_l20_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 235029.1459 | 1.3723 | 0.5157 | -14924.3315 | -9949.5543 | 7 | 70721.8910 | defensive:121;neutral:548 |
| dyn_core_avg_pred_ev_low_l20_h80__def_b384_dd32_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_smooth80_convex19 | 235029.1459 | 1.3723 | 0.5157 | -14924.3315 | -9949.5543 | 7 | 70721.8910 | defensive:121;neutral:548 |


## Dynamic Allocator: Profit And MaxDD Both Improve

| portfolio | feature | bad_side | low_q | high_q | defensive_portfolio | aggressive_portfolio | profit_per_256 | roi | non_full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_core_avg_pred_ev_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248834.7579 | 1.4529 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:121;neutral:548 |
| dyn_core_avg_pred_ev_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248834.7579 | 1.4529 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:121;neutral:548 |
| dyn_core_avg_pred_ev_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_pred_ev | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248834.7579 | 1.4529 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:121;neutral:548 |
| dyn_core_avg_selector_score_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248681.5299 | 1.4520 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:126;neutral:543 |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248681.5299 | 1.4520 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:126;neutral:543 |
| dyn_core_avg_selector_score_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth80_convex19 | core_avg_selector_score | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth80_convex19 | 248681.5299 | 1.4520 | 0.5157 | -14751.6792 | -9834.4528 | 7 | 86114.2136 | defensive:126;neutral:543 |


## Dynamic Allocator: Best MaxDD Improvement

| portfolio | feature | bad_side | low_q | high_q | defensive_portfolio | aggressive_portfolio | profit_per_256 | roi | non_full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l20_h60__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.2000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 170527.9864 | 0.9957 | 0.5202 | -12357.0867 | -8238.0578 | 7 | 73061.7312 | aggressive:309;defensive:247;neutral:113 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h60__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 171635.2974 | 1.0022 | 0.5187 | -12410.1575 | -8273.4383 | 7 | 72823.7780 | aggressive:275;defensive:337;neutral:57 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h70__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 171378.2822 | 1.0007 | 0.5187 | -12410.1575 | -8273.4383 | 7 | 72823.7780 | aggressive:227;defensive:337;neutral:105 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h70__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 171363.4942 | 1.0006 | 0.5187 | -12410.1575 | -8273.4383 | 7 | 72823.7780 | aggressive:227;defensive:362;neutral:80 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h60__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 170895.4514 | 0.9978 | 0.5172 | -12410.1575 | -8273.4383 | 7 | 72823.7780 | aggressive:261;defensive:362;neutral:46 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h80__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 170636.3211 | 0.9963 | 0.5157 | -12410.1575 | -8273.4383 | 7 | 72823.7780 | aggressive:167;defensive:337;neutral:165 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h80__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 170621.5331 | 0.9962 | 0.5157 | -12410.1575 | -8273.4383 | 7 | 72823.7780 | aggressive:167;defensive:362;neutral:140 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h70__def_b384_dd32_smooth100__agg_b384_dd32_safe35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_safe35_convex65 | 181933.2258 | 1.0623 | 0.5187 | -12614.0042 | -8409.3362 | 7 | 72574.5231 | aggressive:227;defensive:337;neutral:105 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h70__def_b384_dd32_smooth100__agg_b384_dd32_safe35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_safe35_convex65 | 181918.4378 | 1.0622 | 0.5187 | -12614.0042 | -8409.3362 | 7 | 72574.5231 | aggressive:227;defensive:362;neutral:80 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h60__def_b384_dd32_smooth100__agg_b384_dd32_safe35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_safe35_convex65 | 181615.5519 | 1.0604 | 0.5187 | -12614.0042 | -8409.3362 | 7 | 72574.5231 | aggressive:275;defensive:337;neutral:57 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h60__def_b384_dd32_smooth100__agg_b384_dd32_safe35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_safe35_convex65 | 180696.5797 | 1.0551 | 0.5172 | -12614.0042 | -8409.3362 | 7 | 72574.5231 | aggressive:261;defensive:362;neutral:46 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h80__def_b384_dd32_smooth100__agg_b384_dd32_safe35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_safe35_convex65 | 174184.1672 | 1.0171 | 0.5157 | -12614.0042 | -8409.3362 | 7 | 72574.5231 | aggressive:167;defensive:337;neutral:165 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h80__def_b384_dd32_smooth100__agg_b384_dd32_safe35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_safe35_convex65 | 174169.3791 | 1.0170 | 0.5157 | -12614.0042 | -8409.3362 | 7 | 72574.5231 | aggressive:167;defensive:362;neutral:140 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l20_h70__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.2000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 169733.6138 | 0.9911 | 0.5187 | -12672.9705 | -8448.6470 | 7 | 72589.9821 | aggressive:228;defensive:247;neutral:194 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l20_h80__def_b384_dd32_smooth100__agg_b384_dd32_safe80_convex19 | same_ticket4_full_risk_avg_source_line_gap | low | 0.2000 | 0.8000 | b384_dd32_smooth100 | b384_dd32_safe80_convex19 | 168991.6527 | 0.9867 | 0.5157 | -12672.9705 | -8448.6470 | 7 | 72589.9821 | aggressive:167;defensive:247;neutral:255 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth50_convex50 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth50_convex50 | 177891.3420 | 1.0387 | 0.5157 | -12904.8016 | -8603.2011 | 7 | 72380.6582 | aggressive:227;defensive:337;neutral:105 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth50_convex50 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth50_convex50 | 177876.5540 | 1.0386 | 0.5157 | -12904.8016 | -8603.2011 | 7 | 72380.6582 | aggressive:227;defensive:362;neutral:80 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h60__def_b384_dd32_smooth100__agg_b384_dd32_smooth50_convex50 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.6000 | b384_dd32_smooth100 | b384_dd32_smooth50_convex50 | 177604.5966 | 1.0370 | 0.5157 | -12904.8016 | -8603.2011 | 7 | 72380.6582 | aggressive:275;defensive:337;neutral:57 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l30_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.3000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth35_convex65 | 181566.7273 | 1.0602 | 0.5157 | -12904.8016 | -8603.2011 | 7 | 72380.6582 | aggressive:227;defensive:337;neutral:105 |
| dyn_same_ticket4_full_risk_avg_source_line_gap_low_l40_h70__def_b384_dd32_smooth100__agg_b384_dd32_smooth35_convex65 | same_ticket4_full_risk_avg_source_line_gap | low | 0.4000 | 0.7000 | b384_dd32_smooth100 | b384_dd32_smooth35_convex65 | 181551.9393 | 1.0601 | 0.5157 | -12904.8016 | -8603.2011 | 7 | 72380.6582 | aggressive:227;defensive:362;neutral:80 |


## Dynamic Allocator: Best Profit

| portfolio | feature | bad_side | low_q | high_q | defensive_portfolio | aggressive_portfolio | profit_per_256 | roi | non_full_loss_rate | max_drawdown_units | max_drawdown_per_256 | max_dead_streak | recent_profit_per_256 | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth35_convex65 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth35_convex65 | 252671.6084 | 1.4753 | 0.5157 | -17183.7908 | -11455.8605 | 7 | 84116.5655 | aggressive:224;defensive:126;neutral:319 |
| dyn_core_avg_pred_ev_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth35_convex65 | core_avg_pred_ev | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth35_convex65 | 252395.5933 | 1.4737 | 0.5157 | -17183.7908 | -11455.8605 | 7 | 84116.5655 | aggressive:223;defensive:121;neutral:325 |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_safe35_convex65 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_safe35_convex65 | 252288.7655 | 1.4731 | 0.5157 | -17347.5752 | -11565.0502 | 7 | 84007.3758 | aggressive:224;defensive:126;neutral:319 |
| dyn_core_avg_pred_ev_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth35_convex65 | core_avg_pred_ev | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth35_convex65 | 252135.4743 | 1.4722 | 0.5157 | -17933.5071 | -11955.6714 | 7 | 83616.7546 | aggressive:272;defensive:121;neutral:276 |
| dyn_core_avg_selector_score_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth35_convex65 | core_avg_selector_score | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth35_convex65 | 251982.2463 | 1.4713 | 0.5157 | -17933.5071 | -11955.6714 | 7 | 83616.7546 | aggressive:273;defensive:126;neutral:270 |
| dyn_core_avg_pred_ev_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_safe35_convex65 | core_avg_pred_ev | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_safe35_convex65 | 251947.0327 | 1.4711 | 0.5157 | -17347.5752 | -11565.0502 | 7 | 84007.3758 | aggressive:223;defensive:121;neutral:325 |
| dyn_core_avg_pred_ev_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_safe35_convex65 | core_avg_pred_ev | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_safe35_convex65 | 251601.8068 | 1.4691 | 0.5127 | -18097.2916 | -12064.8610 | 7 | 83507.5650 | aggressive:272;defensive:121;neutral:276 |
| dyn_core_avg_selector_score_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_safe35_convex65 | core_avg_selector_score | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_safe35_convex65 | 251448.5788 | 1.4682 | 0.5127 | -18097.2916 | -12064.8610 | 7 | 83507.5650 | aggressive:273;defensive:126;neutral:270 |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth50_convex50 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth50_convex50 | 251341.5823 | 1.4676 | 0.5157 | -16373.0869 | -10915.3913 | 7 | 84782.4482 | aggressive:224;defensive:126;neutral:319 |
| dyn_core_avg_pred_ev_low_l20_h70__def_b384_dd64_smooth100__agg_b384_dd32_smooth50_convex50 | core_avg_pred_ev | low | 0.2000 | 0.7000 | b384_dd64_smooth100 | b384_dd32_smooth50_convex50 | 251208.6482 | 1.4668 | 0.5157 | -16373.0869 | -10915.3913 | 7 | 84782.4482 | aggressive:223;defensive:121;neutral:325 |
| dyn_core_avg_pred_ev_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth50_convex50 | core_avg_pred_ev | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth50_convex50 | 251035.2355 | 1.4658 | 0.5157 | -16872.8978 | -11248.5985 | 7 | 84449.2410 | aggressive:272;defensive:121;neutral:276 |
| dyn_core_avg_selector_score_low_l20_h60__def_b384_dd64_smooth100__agg_b384_dd32_smooth50_convex50 | core_avg_selector_score | low | 0.2000 | 0.6000 | b384_dd64_smooth100 | b384_dd32_smooth50_convex50 | 250882.0075 | 1.4649 | 0.5157 | -16872.8978 | -11248.5985 | 7 | 84449.2410 | aggressive:273;defensive:126;neutral:270 |
| dyn_core_avg_pred_ev_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth35_convex65 | core_avg_pred_ev | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth35_convex65 | 249825.6565 | 1.4587 | 0.5157 | -16986.0590 | -11324.0393 | 7 | 84248.3866 | aggressive:174;defensive:121;neutral:374 |
| dyn_core_ticket_count_low_l20_h60__def_b384_dd32_smooth80_wideconvex19__agg_b384_dd32_smooth80_convex19 | core_ticket_count | low | 0.2000 | 0.6000 | b384_dd32_smooth80_wideconvex19 | b384_dd32_smooth80_convex19 | 249788.3941 | 1.4585 | 0.5172 | -15077.1643 | -10051.4429 | 7 | 77894.0415 | defensive:140;neutral:529 |
| dyn_core_ticket_count_low_l20_h70__def_b384_dd32_smooth80_wideconvex19__agg_b384_dd32_smooth80_convex19 | core_ticket_count | low | 0.2000 | 0.7000 | b384_dd32_smooth80_wideconvex19 | b384_dd32_smooth80_convex19 | 249788.3941 | 1.4585 | 0.5172 | -15077.1643 | -10051.4429 | 7 | 77894.0415 | defensive:140;neutral:529 |
| dyn_core_ticket_count_low_l20_h80__def_b384_dd32_smooth80_wideconvex19__agg_b384_dd32_smooth80_convex19 | core_ticket_count | low | 0.2000 | 0.8000 | b384_dd32_smooth80_wideconvex19 | b384_dd32_smooth80_convex19 | 249788.3941 | 1.4585 | 0.5172 | -15077.1643 | -10051.4429 | 7 | 77894.0415 | defensive:140;neutral:529 |
| dyn_core_avg_selector_score_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth35_convex65 | core_avg_selector_score | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth35_convex65 | 249672.4286 | 1.4578 | 0.5157 | -16986.0590 | -11324.0393 | 7 | 84248.3866 | aggressive:174;defensive:126;neutral:369 |
| dyn_core_avg_selector_score_low_l20_h70__def_b384_dd32_smooth80_wideconvex19__agg_b384_dd32_smooth35_convex65 | core_avg_selector_score | low | 0.2000 | 0.7000 | b384_dd32_smooth80_wideconvex19 | b384_dd32_smooth35_convex65 | 249639.0209 | 1.4576 | 0.5172 | -17509.2758 | -11672.8506 | 7 | 70795.1192 | aggressive:224;defensive:126;neutral:319 |
| dyn_core_ticket_count_low_l20_h60__def_b384_dd32_smooth80_wideconvex19__agg_b384_dd32_safe80_convex19 | core_ticket_count | low | 0.2000 | 0.6000 | b384_dd32_smooth80_wideconvex19 | b384_dd32_safe80_convex19 | 249599.7203 | 1.4574 | 0.5172 | -15243.1803 | -10162.1202 | 7 | 78158.3190 | aggressive:285;defensive:140;neutral:244 |
| dyn_core_avg_pred_ev_low_l20_h80__def_b384_dd64_smooth100__agg_b384_dd32_smooth50_convex50 | core_avg_pred_ev | low | 0.2000 | 0.8000 | b384_dd64_smooth100 | b384_dd32_smooth50_convex50 | 249495.3570 | 1.4568 | 0.5157 | -16241.2658 | -10827.5105 | 7 | 84870.3290 | aggressive:174;defensive:121;neutral:374 |


## Interpretation

- Best balanced dynamic candidate improves maxDD by `421.1` units while keeping profit/256 at `239761.6`.
- Best profit-positive candidate improves profit/256 by `7585.5` and maxDD by `325.5` units.
- The maxDD improvement is still modest; use this as a regime-signal lead, not an operating replacement yet.

## Files

- `results/n7_384_drawdown_dynamic_20260629/maxdd_window_issues.csv`
- `results/n7_384_drawdown_dynamic_20260629/component_attribution.csv`
- `results/n7_384_drawdown_dynamic_20260629/feature_window_diffs.csv`
- `results/n7_384_drawdown_dynamic_20260629/same_budget_window_portfolios.csv`
- `results/n7_384_drawdown_dynamic_20260629/dynamic_allocator_summary.csv`
- `results/n7_384_drawdown_dynamic_20260629/dynamic_allocator_selected_issue_profit.csv`
- `results/n7_384_drawdown_dynamic_20260629/n7_384_dynamic_allocator_equity.svg`
