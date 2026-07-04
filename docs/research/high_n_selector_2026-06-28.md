# High-N selector replay

## Scope

- Ticket pool: `results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_budget_fractional_tickets.csv`
- q/conf LL source: `results/n7_q_conf_drift_joint_2014_10h_trusted/joint_leg_rows.csv` / spec `keyed_pockets`
- DB: `../../data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- Line gap: `-beidan_handicap - asian_handicap_1h`.
- Line gap threshold: `0.5`. Draw-only legs are treated as neutral.
- Same-budget active issue stake: `256.0`.

## Main Comparison

| source_strategy | selector | issues | profit_units | roi | issue_win_rate | max_drawdown_units | ex_top1_roi | recent_issues | recent_profit_units | recent_roi | recent_issue_win_rate | recent_max_drawdown_units | recent_ex_top1_roi | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 480 | 127996.8846 | 1.0416 | 0.0125 | -60562.3739 | -0.6181 | 96 | 188559.2585 | 7.6725 | 0.0208 | -15235.7082 | -0.6265 | 2.4521 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | topology_neg0_ge5_pos3_ge1_d0 | 578 | 181365.4135 | 1.2257 | 0.0190 | -41903.6791 | -0.1518 | 112 | 184906.0504 | 6.4490 | 0.0179 | -18888.9163 | -0.6647 | 3.5536 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v1_topology_priority | 669 | 323937.7521 | 1.8915 | 0.0194 | -53331.1405 | 0.7026 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 3.9253 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 669 | 323937.7521 | 1.8915 | 0.0194 | -53331.1405 | 0.7026 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 3.9253 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v4_linegap_supported_priority | 669 | 182269.7937 | 1.0643 | 0.0179 | -50866.5660 | -0.1259 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 2.7578 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 669 | 177087.5756 | 1.0340 | 0.0164 | -52110.1732 | -0.1562 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 2.8804 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 495 | 100318.2237 | 0.7917 | 0.0121 | -45999.6791 | -0.4149 | 101 | 136266.5169 | 5.2702 | 0.0198 | -16515.7082 | -0.6451 | 2.6283 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 669 | 294630.5526 | 1.7203 | 0.0179 | -58799.6791 | 0.7859 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 3.8670 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 669 | 294630.5526 | 1.7203 | 0.0179 | -58799.6791 | 0.7859 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 3.8670 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v4_linegap_supported_priority | 669 | 186393.2625 | 1.0883 | 0.0164 | -57246.5277 | 0.1965 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 2.7549 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 669 | 182122.4675 | 1.0634 | 0.0149 | -57578.7117 | 0.1716 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 2.8640 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 666 | 243883.7883 | 1.4304 | 0.0511 | -26071.0573 | 0.4914 | 129 | 92278.5972 | 2.7943 | 0.0465 | -23090.1666 | -0.1340 | 11.2808 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 666 | 237744.6066 | 1.3944 | 0.0511 | -23891.0473 | 0.4553 | 129 | 76997.8929 | 2.3316 | 0.0465 | -23885.0421 | -0.1333 | 12.0631 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 666 | 231602.2503 | 1.3584 | 0.0495 | -28361.8443 | 0.4192 | 129 | 75504.3689 | 2.2863 | 0.0465 | -23090.1666 | -0.3968 | 11.4805 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 669 | 244546.1450 | 1.4279 | 0.0538 | -24297.3762 | 0.4931 | 129 | 73171.4393 | 2.2157 | 0.0465 | -24297.3762 | -0.2500 | 11.6891 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 666 | 229121.5738 | 1.3439 | 0.0495 | -26509.0895 | 0.4047 | 129 | 67553.5377 | 2.0456 | 0.0465 | -23885.0421 | -0.3592 | 12.3168 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 669 | 237639.8871 | 1.3876 | 0.0523 | -24297.3762 | 0.4527 | 129 | 67141.2036 | 2.0331 | 0.0465 | -24297.3762 | -0.3718 | 11.9312 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 666 | 231605.4249 | 1.3584 | 0.0511 | -24679.9176 | 0.4193 | 129 | 61717.1887 | 1.8689 | 0.0465 | -24679.9176 | -0.1325 | 12.9054 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 666 | 226640.8973 | 1.3293 | 0.0495 | -24679.9176 | 0.3901 | 129 | 59602.7065 | 1.8048 | 0.0465 | -24679.9176 | -0.3216 | 13.1757 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_neg0_ge5_pos3_ge1_d0 | 596 | 89317.0203 | 0.5854 | 0.0201 | -40111.6791 | 0.0857 | 118 | 55838.1962 | 1.8485 | 0.0169 | -20424.9163 | -0.6819 | 3.8138 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_neg0_ge6_d0 | 666 | 224160.2208 | 1.3148 | 0.0495 | -25474.7932 | 0.3755 | 129 | 51651.8753 | 1.5641 | 0.0465 | -25474.7932 | -0.2840 | 13.9775 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | topology_neg0_ge6_d0 | 666 | 225466.2432 | 1.3224 | 0.0511 | -25474.7932 | 0.3832 | 129 | 46436.4844 | 1.4061 | 0.0465 | -25474.7932 | -0.1318 | 13.6832 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | draw_free | 667 | 188024.5551 | 1.1012 | 0.0660 | -23640.2992 | 0.4245 | 129 | 27254.0211 | 0.8253 | 0.0465 | -23640.2992 | -0.3280 | 17.7136 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 669 | 141089.3330 | 0.8238 | 0.0673 | -20537.9146 | 0.2720 | 129 | 21047.6423 | 0.6373 | 0.0543 | -20537.9146 | -0.2839 | 19.3483 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | draw_free | 668 | 174422.8819 | 1.0200 | 0.0644 | -23640.2992 | 0.3442 | 129 | 17945.2577 | 0.5434 | 0.0465 | -23640.2992 | -0.3786 | 18.5165 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 669 | 111291.2322 | 0.6498 | 0.0717 | -23640.2992 | 0.0977 | 129 | 533.1251 | 0.0161 | 0.0465 | -23640.2992 | -0.4675 | 19.3901 |


## Current Read

- Preferred source for the next iteration: `ev_m0p95_p0p8_full_opt__budget256_fractional`.
- Main high-N core: `topology_neg0_ge6_d0`, profit `225466.2`, ROI `132.24%`, recent profit `46436.5`, recent ROI `140.61%`.
- Convex sleeve candidate: `topology_exact_6n0_1p3_d0`, profit `127996.9`, but max drawdown `-60562.4` and ex-top1 ROI `-61.81%`; do not run it as full-stake standalone.
- Current practical arm: `portfolio_realloc_80_core_neg0ge6_20_exact`, profit `237744.6`, ROI `139.44%`, recent profit `76997.9`, recent ROI `233.16%`, max drawdown `-23891.0`.
- Line-gap is useful as a diagnostic/niche descriptor, but the first hard/soft gates did not outperform the topology portfolio. Recent exact-topology winners were mostly `line_gap_support_net = 0`, not strongly positive.

## Annual Detail

| source_strategy | selector | year | issues | profit_units | roi | issue_win_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2014 | 116 | 17068.2965 | 0.5748 | 0.0862 | -11445.0048 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2015 | 58 | 1959.5948 | 0.1320 | 0.0690 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2016 | 53 | 7022.0578 | 0.5175 | 0.0566 | -10391.8663 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2017 | 47 | -6080.1968 | -0.5053 | 0.1064 | -6080.1968 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2018 | 54 | 111032.2884 | 8.0318 | 0.1111 | -4405.6112 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2019 | 55 | -7277.2547 | -0.5169 | 0.0545 | -10542.4786 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2020 | 42 | -60.5802 | -0.0056 | 0.0714 | -5495.9586 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2021 | 58 | 10969.4848 | 0.7388 | 0.0690 | -7168.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2022 | 57 | -14592.0000 | -1.0000 | 0.0000 | -14592.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2023 | 55 | 18956.1192 | 1.3463 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2024 | 59 | -6969.9146 | -0.4615 | 0.0508 | -9441.6154 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2025 | 15 | 9061.4377 | 2.3597 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2014 | 116 | 7881.3572 | 0.2654 | 0.0690 | -10754.3182 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2015 | 58 | 371.0246 | 0.0250 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2018 | 54 | 191506.5951 | 13.8532 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2019 | 55 | -7607.6562 | -0.5403 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2020 | 41 | 2238.5338 | 0.2133 | 0.0488 | -4352.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2021 | 57 | -2955.3311 | -0.2025 | 0.0351 | -11776.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2022 | 56 | -14336.0000 | -1.0000 | 0.0000 | -14336.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2023 | 55 | 68737.8426 | 4.8819 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2024 | 59 | -10317.0421 | -0.6831 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2025 | 15 | 9132.7372 | 2.3783 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2014 | 116 | 6184.0126 | 0.2082 | 0.0690 | -10754.3182 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2015 | 58 | 371.0246 | 0.0250 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2018 | 54 | 192196.4492 | 13.9031 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2019 | 55 | -5672.7666 | -0.4029 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2020 | 42 | 3010.9272 | 0.2800 | 0.0714 | -4352.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2021 | 58 | 4531.5238 | 0.3052 | 0.0517 | -7168.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2022 | 57 | -14592.0000 | -1.0000 | 0.0000 | -14592.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2023 | 55 | 68737.8426 | 4.8819 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2024 | 59 | -10729.3762 | -0.7104 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2025 | 15 | 9132.7372 | 2.3783 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2014 | 116 | -27370.7117 | -0.9217 | 0.0086 | -27370.7117 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2015 | 58 | -14848.0000 | -1.0000 | 0.0000 | -14848.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2016 | 53 | -13568.0000 | -1.0000 | 0.0000 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2017 | 47 | -2500.9674 | -0.2079 | 0.0213 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2018 | 54 | 208539.5172 | 15.0853 | 0.0741 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2019 | 55 | 66.6719 | 0.0047 | 0.0182 | -12800.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2020 | 42 | 5939.2513 | 0.5524 | 0.0476 | -4608.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2021 | 58 | 23866.2746 | 1.6074 | 0.0172 | -9216.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2022 | 57 | -14592.0000 | -1.0000 | 0.0000 | -14592.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2023 | 55 | 138958.2251 | 9.8692 | 0.0182 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2024 | 59 | -6019.7082 | -0.3986 | 0.0169 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2025 | 15 | -3840.0000 | -1.0000 | 0.0000 | -3840.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2014 | 116 | -27370.7117 | -0.9217 | 0.0086 | -27370.7117 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2015 | 58 | -14848.0000 | -1.0000 | 0.0000 | -14848.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2016 | 53 | -13568.0000 | -1.0000 | 0.0000 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2017 | 47 | -2500.9674 | -0.2079 | 0.0213 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2018 | 54 | 208539.5172 | 15.0853 | 0.0741 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2019 | 55 | 66.6719 | 0.0047 | 0.0182 | -12800.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2020 | 42 | 5939.2513 | 0.5524 | 0.0476 | -4608.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2021 | 58 | 23866.2746 | 1.6074 | 0.0172 | -9216.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2022 | 57 | -14592.0000 | -1.0000 | 0.0000 | -14592.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2023 | 55 | 138958.2251 | 9.8692 | 0.0182 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2024 | 59 | -6019.7082 | -0.3986 | 0.0169 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2025 | 15 | -3840.0000 | -1.0000 | 0.0000 | -3840.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2014 | 116 | -27370.7117 | -0.9217 | 0.0086 | -27370.7117 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2015 | 58 | -14848.0000 | -1.0000 | 0.0000 | -14848.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2016 | 53 | -13568.0000 | -1.0000 | 0.0000 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2017 | 47 | 7030.0652 | 0.5843 | 0.0213 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2018 | 54 | 86500.3994 | 6.2573 | 0.0370 | -6912.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2019 | 55 | 66.6719 | 0.0047 | 0.0182 | -12800.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2020 | 42 | 5939.2513 | 0.5524 | 0.0476 | -4608.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2021 | 58 | 23866.2746 | 1.6074 | 0.0172 | -9216.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2022 | 57 | -14592.0000 | -1.0000 | 0.0000 | -14592.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2023 | 55 | 138958.2251 | 9.8692 | 0.0182 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2024 | 59 | -6019.7082 | -0.3986 | 0.0169 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2025 | 15 | -3840.0000 | -1.0000 | 0.0000 | -3840.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2014 | 100 | -23274.7117 | -0.9092 | 0.0100 | -23274.7117 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2015 | 38 | -9728.0000 | -1.0000 | 0.0000 | -9728.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2016 | 41 | -10496.0000 | -1.0000 | 0.0000 | -10496.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2017 | 29 | 2107.0326 | 0.2838 | 0.0345 | -5888.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2018 | 38 | 31782.1019 | 3.2671 | 0.0263 | -4864.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2019 | 38 | -9728.0000 | -1.0000 | 0.0000 | -9728.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2020 | 33 | 3101.2841 | 0.3671 | 0.0303 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2021 | 40 | -10240.0000 | -1.0000 | 0.0000 | -10240.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2022 | 37 | -9472.0000 | -1.0000 | 0.0000 | -9472.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2023 | 47 | 141006.2251 | 11.7193 | 0.0213 | -11776.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2024 | 43 | -1923.7082 | -0.1748 | 0.0233 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2025 | 11 | -2816.0000 | -1.0000 | 0.0000 | -2816.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2014 | 116 | 6508.0885 | 0.2192 | 0.1034 | -9889.1815 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2015 | 58 | 1959.5948 | 0.1320 | 0.0690 | -6144.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2016 | 53 | 7022.0578 | 0.5175 | 0.0566 | -10391.8663 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2017 | 47 | -6080.1968 | -0.5053 | 0.1064 | -6080.1968 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2018 | 54 | 108474.1695 | 7.8468 | 0.1111 | -5628.7200 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2019 | 55 | -7277.2547 | -0.5169 | 0.0545 | -10542.4786 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2020 | 42 | 279.0423 | 0.0260 | 0.0714 | -5495.9586 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2021 | 58 | 10969.4848 | 0.7388 | 0.0690 | -7168.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2022 | 57 | -11096.8792 | -0.7605 | 0.0351 | -12392.0270 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2023 | 55 | 4457.7610 | 0.3166 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2024 | 59 | -10072.2992 | -0.6669 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2025 | 15 | 6147.6633 | 1.6010 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2014 | 116 | 13815.7374 | 0.4652 | 0.0690 | -10754.3182 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2015 | 58 | 371.0246 | 0.0250 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2018 | 54 | 182132.8503 | 13.1751 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2019 | 55 | -7607.6562 | -0.5403 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2020 | 41 | 3317.9349 | 0.3161 | 0.0488 | -4352.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2021 | 57 | -2955.3311 | -0.2025 | 0.0351 | -11776.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2022 | 56 | -12797.3589 | -0.8927 | 0.0179 | -12797.3589 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2023 | 55 | 70778.3522 | 5.0269 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2024 | 59 | -10317.0421 | -0.6831 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2025 | 15 | 16536.5828 | 4.3064 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2014 | 116 | 13815.7374 | 0.4652 | 0.0690 | -10754.3182 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2015 | 58 | 371.0246 | 0.0250 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2018 | 54 | 182822.7044 | 13.2250 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2019 | 55 | -5672.7666 | -0.4029 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2020 | 42 | 4090.3283 | 0.3804 | 0.0714 | -4352.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2021 | 58 | 4531.5238 | 0.3052 | 0.0517 | -7168.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2022 | 57 | -13053.3589 | -0.8946 | 0.0175 | -13053.3589 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2023 | 55 | 70778.3522 | 5.0269 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2024 | 59 | -10729.3762 | -0.7104 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2025 | 15 | 13122.4632 | 3.4173 | 0.1333 | -2048.0000 |


## Recent Topology x Line Gap

| strategy | topology | linegap_net_bucket | tickets | issues | hit_rate | profit_units | roi_raw_ticket_stake | avg_ll_bad_count | avg_ll_good_count | avg_abs_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 0 | 125 | 65 | 0.0080 | 29007.2521 | 18.1251 | 0.0000 | 0.4160 | 0.2135 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 0 | 673 | 124 | 0.0030 | 3292.4050 | 0.3862 | 0.0000 | 0.1738 | 0.2029 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 1:2 | 361 | 105 | 0.0055 | 801.6353 | 0.1796 | 0.0000 | 0.1330 | 0.3103 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 1:2 | 57 | 43 | 0.0175 | 642.1024 | 0.8775 | 0.0000 | 0.4912 | 0.3131 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_0_pos3_7_draw_0 | 0 | 47 | 39 | 0.0000 | -583.0531 | -1.0000 | 0.0000 | 1.2979 | 0.1721 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | -2:-1 | 64 | 40 | 0.0000 | -787.7850 | -1.0000 | 0.0000 | 0.2969 | 0.2603 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 0 | 68 | 48 | 0.0000 | -897.9310 | -1.0000 | 0.0000 | 0.9559 | 0.2276 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | >=3 | 76 | 36 | 0.0000 | -943.9454 | -1.0000 | 0.0000 | 0.0000 | 0.4171 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 1:2 | 77 | 49 | 0.0000 | -967.9254 | -1.0000 | 0.0000 | 0.2078 | 0.3141 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 1:2 | 99 | 62 | 0.0000 | -1261.8571 | -1.0000 | 0.0000 | 0.2525 | 0.3086 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 0 | 91 | 53 | 0.0000 | -1300.9931 | -1.0000 | 0.0000 | 0.5385 | 0.2145 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | -2:-1 | 336 | 110 | 0.0000 | -4284.5641 | -1.0000 | 0.0000 | 0.1458 | 0.2615 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 0 | 101 | 57 | 0.0099 | 15136.7417 | 15.5641 | 0.0000 | 0.3960 | 0.2054 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 0 | 710 | 122 | 0.0028 | 1840.0866 | 0.2605 | 0.0000 | 0.1662 | 0.1934 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 1:2 | 379 | 107 | 0.0053 | 1330.2342 | 0.3381 | 0.0000 | 0.1504 | 0.3090 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 1:2 | 47 | 37 | 0.0213 | 858.0286 | 1.6634 | 0.0000 | 0.1702 | 0.3178 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_0_pos3_7_draw_0 | 0 | 45 | 33 | 0.0000 | -483.2535 | -1.0000 | 0.0000 | 1.3333 | 0.1666 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 0 | 51 | 39 | 0.0000 | -493.6750 | -1.0000 | 0.0000 | 0.7451 | 0.2154 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | -2:-1 | 52 | 33 | 0.0000 | -510.0961 | -1.0000 | 0.0000 | 0.2692 | 0.2459 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 1:2 | 79 | 48 | 0.0000 | -770.2446 | -1.0000 | 0.0000 | 0.2405 | 0.3070 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 0 | 70 | 41 | 0.0000 | -792.5592 | -1.0000 | 0.0000 | 0.3571 | 0.1988 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 1:2 | 98 | 61 | 0.0000 | -891.0691 | -1.0000 | 0.0000 | 0.1939 | 0.3095 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | >=3 | 79 | 36 | 0.0000 | -940.5214 | -1.0000 | 0.0000 | 0.0253 | 0.4158 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | -2:-1 | 270 | 86 | 0.0000 | -2687.1044 | -1.0000 | 0.0000 | 0.1481 | 0.2661 |


## Interpretation

- The selector is evaluated as a ticket-pool selector. It does not yet regenerate better combinations from leg primitives.
- `topology_exact_6n0_1p3_d0` tests the niche directly: six negative-handicap `0` legs plus one positive-handicap `3` leg, with no draw cover.
- `selector_v1_topology_priority` uses exact topology first, then mixed negative-0/positive-3 draw-free tickets, then negative-0-heavy draw-free tickets.
- `selector_v2_topology_ll_guard` adds an LL-risk guard; it keeps useful LL pockets but avoids bad LL pockets where possible.
- `selector_v3_topology_ll_linegap_topk` adds a soft line-gap preference and keeps only the top-k tickets per active issue.
- `selector_v4_linegap_supported_priority` checks whether the Beidan-vs-Asian handicap mismatch can act as a niche filter.
- `portfolio_realloc_*` arms keep `neg0>=6, draw=0` as the broad high-N core and allocate a smaller sleeve to the convex topology; if the sleeve is unavailable in an issue, its stake is reallocated to the core.

## Files

- `results/high_n_selector_20260628/high_n_selector_summary.csv`
- `results/high_n_selector_20260628/high_n_selector_recent_2023_2025_summary.csv`
- `results/high_n_selector_20260628/high_n_selector_annual_summary.csv`
- `results/high_n_selector_20260628/high_n_selector_issue_profit.csv`
- `results/high_n_selector_20260628/high_n_selector_portfolio_issue_profit.csv`
- `results/high_n_selector_20260628/high_n_selector_selected_tickets.csv`
- `results/high_n_selector_20260628/high_n_selector_enriched_source_tickets.csv`
- `results/high_n_selector_20260628/high_n_selector_topology_linegap_recent.csv`
