# High-N selector replay

## Scope

- Ticket pool: `results/n7_ev_framework_selector_2014_1h_minodds4_optional_plus2026/ev_framework_budget_fractional_tickets.csv`
- q/conf LL source: `results/n7_q_conf_drift_joint_2014_10h_trusted_plus2026_linefill_20260630/joint_leg_rows.csv` / spec `keyed_pockets`
- DB: `data/derived/beidan_xlsm/beidan_modeling_plus_2026.sqlite`
- Line gap: `-beidan_handicap - asian_handicap_1h`.
- Line gap threshold: `0.5`. Draw-only legs are treated as neutral.
- Same-budget active issue stake: `256.0`.

## Main Comparison

| source_strategy | selector | issues | profit_units | roi | issue_win_rate | max_drawdown_units | ex_top1_roi | recent_issues | recent_profit_units | recent_roi | recent_issue_win_rate | recent_max_drawdown_units | recent_ex_top1_roi | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 504 | 125086.9411 | 0.9695 | 0.0139 | -57584.3174 | -0.6112 | 95 | 188815.2585 | 7.7638 | 0.0211 | -14979.7082 | -0.6225 | 2.3829 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | topology_neg0_ge5_pos3_ge1_d0 | 610 | 160370.5961 | 1.0270 | 0.0180 | -49894.3749 | -0.2785 | 113 | 184650.0504 | 6.3831 | 0.0177 | -19144.9163 | -0.6677 | 3.3951 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v1_topology_priority | 702 | 321381.0207 | 1.7883 | 0.0228 | -49275.7069 | 0.6552 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 3.8177 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 702 | 321381.0207 | 1.7883 | 0.0228 | -49275.7069 | 0.6552 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 3.8148 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v4_linegap_supported_priority | 702 | 183854.7209 | 1.0231 | 0.0214 | -45352.6170 | -0.1111 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 2.6667 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 702 | 173874.6934 | 0.9675 | 0.0185 | -48740.0305 | -0.1667 | 129 | 180111.2585 | 5.4540 | 0.0155 | -23683.7082 | -0.7228 | 2.8063 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 528 | 107306.3102 | 0.7939 | 0.0152 | -42253.6227 | -0.3371 | 101 | 136266.5169 | 5.2702 | 0.0198 | -16515.7082 | -0.6451 | 2.5019 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 702 | 303123.5836 | 1.6867 | 0.0214 | -54060.6781 | 0.7963 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 3.6980 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 702 | 303123.5836 | 1.6867 | 0.0214 | -54060.6781 | 0.7963 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 3.6952 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v4_linegap_supported_priority | 702 | 200640.0079 | 1.1165 | 0.0199 | -50821.1556 | 0.2667 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 2.5869 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 702 | 189930.2074 | 1.0569 | 0.0171 | -53525.0018 | 0.2070 | 129 | 129098.5169 | 3.9092 | 0.0155 | -23683.7082 | -0.7228 | 2.7450 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 695 | 242720.7692 | 1.3642 | 0.0532 | -22834.1666 | 0.4643 | 129 | 96244.9386 | 2.9144 | 0.0543 | -22834.1666 | 0.0709 | 11.1655 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_neg0_ge5_pos3_ge1_d0 | 631 | 87777.9848 | 0.5434 | 0.0206 | -38630.3749 | -0.0868 | 117 | 81600.5671 | 2.7244 | 0.0171 | -20168.9163 | -0.6792 | 3.6894 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 695 | 236896.6657 | 1.3315 | 0.0532 | -23629.0421 | 0.4315 | 129 | 81530.8545 | 2.4688 | 0.0543 | -23629.0421 | 0.1009 | 11.9554 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 702 | 244510.0390 | 1.3606 | 0.0570 | -24041.3762 | 0.4696 | 129 | 77704.4009 | 2.3530 | 0.0543 | -24041.3762 | -0.0159 | 11.5470 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 698 | 225754.1974 | 1.2634 | 0.0530 | -23401.0996 | 0.3672 | 129 | 73179.1790 | 2.2159 | 0.0465 | -23090.1666 | -0.3489 | 11.3252 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 695 | 231072.5622 | 1.2987 | 0.0532 | -24423.9176 | 0.3987 | 129 | 66816.7705 | 2.0233 | 0.0543 | -24423.9176 | 0.1309 | 12.7986 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 698 | 221468.0053 | 1.2394 | 0.0530 | -23885.0421 | 0.3432 | 129 | 64896.1778 | 1.9651 | 0.0465 | -23885.0421 | -0.3044 | 12.1547 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 702 | 230122.0135 | 1.2805 | 0.0556 | -24297.3762 | 0.3895 | 129 | 64483.8437 | 1.9526 | 0.0465 | -24297.3762 | -0.3170 | 11.7607 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 698 | 217181.8132 | 1.2154 | 0.0530 | -24679.9176 | 0.3192 | 129 | 56613.1766 | 1.7143 | 0.0465 | -24679.9176 | -0.2600 | 13.0372 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | topology_neg0_ge6_d0 | 695 | 225248.4587 | 1.2660 | 0.0532 | -25218.7932 | 0.3660 | 129 | 52102.6864 | 1.5777 | 0.0543 | -25218.7932 | 0.1608 | 13.5842 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_neg0_ge6_d0 | 698 | 212895.6210 | 1.1914 | 0.0530 | -25474.7932 | 0.2952 | 129 | 48330.1754 | 1.4635 | 0.0465 | -25474.7932 | -0.2156 | 13.8481 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | draw_free | 699 | 205187.5331 | 1.1467 | 0.0715 | -23384.2992 | 0.5011 | 129 | 36608.2778 | 1.1085 | 0.0543 | -23384.2992 | -0.0426 | 17.4492 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 702 | 133525.5796 | 0.7430 | 0.0755 | -20824.2992 | 0.2170 | 129 | 25830.5096 | 0.7822 | 0.0543 | -20824.2992 | -0.1380 | 19.7051 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | draw_free | 701 | 174796.1530 | 0.9740 | 0.0699 | -23640.2992 | 0.3301 | 129 | 17945.2577 | 0.5434 | 0.0465 | -23640.2992 | -0.3786 | 18.3595 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 702 | 125463.9233 | 0.6981 | 0.0897 | -15723.8815 | 0.1721 | 129 | 14837.6850 | 0.4493 | 0.0775 | -13915.0572 | -0.0310 | 19.6439 |


## Current Read

- Preferred source for the next iteration: `ev_m0p95_p0p8_full_opt__budget256_fractional`.
- Main high-N core: `topology_neg0_ge6_d0`, profit `225248.5`, ROI `126.60%`, recent profit `52102.7`, recent ROI `157.77%`.
- Convex sleeve candidate: `topology_exact_6n0_1p3_d0`, profit `125086.9`, but max drawdown `-57584.3` and ex-top1 ROI `-61.12%`; do not run it as full-stake standalone.
- Current practical arm: `portfolio_realloc_80_core_neg0ge6_20_exact`, profit `236896.7`, ROI `133.15%`, recent profit `81530.9`, recent ROI `246.88%`, max drawdown `-23629.0`.
- Line-gap is useful as a diagnostic/niche descriptor, but the first hard/soft gates did not outperform the topology portfolio. Recent exact-topology winners were mostly `line_gap_support_net = 0`, not strongly positive.

## Annual Detail

| source_strategy | selector | year | issues | profit_units | roi | issue_win_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2014 | 116 | 1821.5866 | 0.0613 | 0.1121 | -8302.4997 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2015 | 58 | -747.6128 | -0.0504 | 0.0690 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2016 | 53 | 7022.0578 | 0.5175 | 0.0566 | -10391.8663 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2017 | 47 | 1310.8495 | 0.1089 | 0.1489 | -4993.3048 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2018 | 54 | 111032.2884 | 8.0318 | 0.1111 | -4405.6112 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2019 | 55 | -7277.2547 | -0.5169 | 0.0545 | -10542.4786 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2020 | 42 | 3834.6462 | 0.3566 | 0.0952 | -3447.9586 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2021 | 58 | 10969.4848 | 0.7388 | 0.0690 | -7168.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2022 | 57 | -12151.5940 | -0.8328 | 0.0175 | -12151.5940 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2023 | 55 | 26841.3711 | 1.9063 | 0.0545 | -10752.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2024 | 59 | -10072.2992 | -0.6669 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2025 | 15 | 9061.4377 | 2.3597 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | all | 2026 | 33 | -8119.3819 | -0.9611 | 0.0303 | -8119.3819 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2014 | 116 | 4977.4947 | 0.1676 | 0.0862 | -7426.5790 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2015 | 58 | -1946.7675 | -0.1311 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2018 | 54 | 190768.6377 | 13.7998 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2019 | 55 | -7607.6562 | -0.5403 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2020 | 41 | 7135.3899 | 0.6798 | 0.0732 | -3328.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2021 | 56 | -3050.4395 | -0.2128 | 0.0357 | -11776.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2022 | 56 | -9726.3442 | -0.6785 | 0.0179 | -9726.3442 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2023 | 55 | 65365.1433 | 4.6424 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2024 | 59 | -10317.0421 | -0.6831 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2025 | 15 | 9848.0766 | 2.5646 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2026 | 33 | -8448.0000 | -1.0000 | 0.0000 | -8448.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2014 | 116 | 3671.8449 | 0.1236 | 0.0862 | -7426.5790 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2015 | 58 | -1946.7675 | -0.1311 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2018 | 54 | 191458.4918 | 13.8497 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2019 | 55 | -5672.7666 | -0.4029 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2020 | 42 | 7907.7833 | 0.7355 | 0.0952 | -3328.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2021 | 58 | 4180.4154 | 0.2815 | 0.0517 | -7168.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2022 | 57 | -9982.3442 | -0.6841 | 0.0175 | -9982.3442 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2023 | 55 | 65365.1433 | 4.6424 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2024 | 59 | -10729.3762 | -0.7104 | 0.0339 | -12544.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2025 | 15 | 9848.0766 | 2.5646 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2026 | 33 | -8448.0000 | -1.0000 | 0.0000 | -8448.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2014 | 116 | -24136.6553 | -0.8128 | 0.0172 | -24136.6553 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2015 | 58 | -13343.0555 | -0.8986 | 0.0172 | -14080.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2016 | 53 | -13568.0000 | -1.0000 | 0.0000 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2017 | 47 | -2500.9674 | -0.2079 | 0.0213 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2018 | 54 | 208539.5172 | 15.0853 | 0.0741 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2019 | 55 | 66.6719 | 0.0047 | 0.0182 | -12800.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2020 | 42 | 5939.2513 | 0.5524 | 0.0476 | -4608.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2021 | 58 | 23866.2746 | 1.6074 | 0.0172 | -9216.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2022 | 57 | -2389.9700 | -0.1638 | 0.0175 | -8960.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2023 | 55 | 138958.2251 | 9.8692 | 0.0182 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2024 | 59 | -6019.7082 | -0.3986 | 0.0169 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2025 | 15 | -3840.0000 | -1.0000 | 0.0000 | -3840.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v1_topology_priority | 2026 | 33 | -8448.0000 | -1.0000 | 0.0000 | -8448.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2014 | 116 | -24136.6553 | -0.8128 | 0.0172 | -24136.6553 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2015 | 58 | -13343.0555 | -0.8986 | 0.0172 | -14080.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2016 | 53 | -13568.0000 | -1.0000 | 0.0000 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2017 | 47 | -2500.9674 | -0.2079 | 0.0213 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2018 | 54 | 208539.5172 | 15.0853 | 0.0741 | -3848.6359 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2019 | 55 | 66.6719 | 0.0047 | 0.0182 | -12800.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2020 | 42 | 5939.2513 | 0.5524 | 0.0476 | -4608.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2021 | 58 | 23866.2746 | 1.6074 | 0.0172 | -9216.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2022 | 57 | -2389.9700 | -0.1638 | 0.0175 | -8960.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2023 | 55 | 138958.2251 | 9.8692 | 0.0182 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2024 | 59 | -6019.7082 | -0.3986 | 0.0169 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2025 | 15 | -3840.0000 | -1.0000 | 0.0000 | -3840.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v2_topology_ll_guard | 2026 | 33 | -8448.0000 | -1.0000 | 0.0000 | -8448.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2014 | 116 | -23317.0018 | -0.7852 | 0.0172 | -23317.0018 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2015 | 58 | -14848.0000 | -1.0000 | 0.0000 | -14848.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2016 | 53 | -13568.0000 | -1.0000 | 0.0000 | -13568.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2017 | 47 | 7030.0652 | 0.5843 | 0.0213 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2018 | 54 | 86500.3994 | 6.2573 | 0.0370 | -6912.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2019 | 55 | 66.6719 | 0.0047 | 0.0182 | -12800.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2020 | 42 | 5939.2513 | 0.5524 | 0.0476 | -4608.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2021 | 58 | 23866.2746 | 1.6074 | 0.0172 | -9216.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2022 | 57 | -2389.9700 | -0.1638 | 0.0175 | -8960.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2023 | 55 | 138958.2251 | 9.8692 | 0.0182 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2024 | 59 | -6019.7082 | -0.3986 | 0.0169 | -13824.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2025 | 15 | -3840.0000 | -1.0000 | 0.0000 | -3840.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | selector_v3_topology_ll_linegap_topk | 2026 | 33 | -8448.0000 | -1.0000 | 0.0000 | -8448.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2014 | 99 | -19784.6553 | -0.7806 | 0.0202 | -19784.6553 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2015 | 37 | -9472.0000 | -1.0000 | 0.0000 | -9472.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2016 | 39 | -9984.0000 | -1.0000 | 0.0000 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2017 | 30 | 1851.0326 | 0.2410 | 0.0333 | -5888.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2018 | 39 | 31526.1019 | 3.1577 | 0.0256 | -4864.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2019 | 39 | -9984.0000 | -1.0000 | 0.0000 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2020 | 32 | 3357.2841 | 0.4098 | 0.0312 | -6144.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2021 | 41 | -10496.0000 | -1.0000 | 0.0000 | -10496.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2022 | 42 | 1450.0300 | 0.1349 | 0.0238 | -6656.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2023 | 47 | 141006.2251 | 11.7193 | 0.0213 | -11776.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2024 | 43 | -1923.7082 | -0.1748 | 0.0233 | -9984.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2025 | 11 | -2816.0000 | -1.0000 | 0.0000 | -2816.0000 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | topology_exact_6n0_1p3_d0 | 2026 | 29 | -7424.0000 | -1.0000 | 0.0000 | -7424.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2014 | 116 | -5144.4867 | -0.1732 | 0.1293 | -7928.8709 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2015 | 58 | 6599.1125 | 0.4444 | 0.0862 | -6144.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2016 | 53 | 7022.0578 | 0.5175 | 0.0566 | -10391.8663 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2017 | 47 | 1310.8495 | 0.1089 | 0.1489 | -4993.3048 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2018 | 54 | 108984.2626 | 7.8837 | 0.1296 | -5118.6268 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2019 | 55 | -7277.2547 | -0.5169 | 0.0545 | -10542.4786 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2020 | 42 | 4174.2688 | 0.3882 | 0.0952 | -3447.9586 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2021 | 58 | 10969.4848 | 0.7388 | 0.0690 | -7168.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2022 | 57 | -11649.2887 | -0.7983 | 0.0351 | -11649.2887 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2023 | 55 | 13330.3413 | 0.9468 | 0.0727 | -9764.6717 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2024 | 59 | -1518.4183 | -0.1005 | 0.0678 | -12288.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2025 | 15 | 3025.7620 | 0.7880 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | all | 2026 | 33 | -4362.7678 | -0.5164 | 0.0909 | -4362.7678 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2014 | 116 | 12616.9718 | 0.4249 | 0.0776 | -8834.5037 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2015 | 58 | -1946.7675 | -0.1311 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2018 | 54 | 182515.1442 | 13.2028 | 0.1111 | -3848.6359 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2019 | 55 | -7607.6562 | -0.5403 | 0.0364 | -10799.8800 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2020 | 41 | 8214.7910 | 0.7827 | 0.0732 | -3328.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2021 | 56 | -3050.4395 | -0.2128 | 0.0357 | -11776.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2022 | 56 | -12165.7452 | -0.8486 | 0.0179 | -12165.7452 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2023 | 55 | 67390.0323 | 4.7862 | 0.0364 | -13568.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2024 | 59 | -2395.7606 | -0.1586 | 0.0508 | -12288.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2025 | 15 | 16536.5828 | 4.3064 | 0.1333 | -2048.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2026 | 30 | -7680.0000 | -1.0000 | 0.0000 | -7680.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2014 | 116 | 12616.9718 | 0.4249 | 0.0776 | -8834.5037 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2015 | 58 | -1946.7675 | -0.1311 | 0.0517 | -6144.0000 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |


## Recent Topology x Line Gap

| strategy | topology | linegap_net_bucket | tickets | issues | hit_rate | profit_units | roi_raw_ticket_stake | avg_ll_bad_count | avg_ll_good_count | avg_abs_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 0 | 104 | 64 | 0.0096 | 29346.7515 | 23.2746 | 0.0000 | 0.4519 | 0.2147 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 0 | 640 | 122 | 0.0031 | 3969.7633 | 0.5059 | 0.0000 | 0.1547 | 0.2022 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 1:2 | 67 | 47 | 0.0149 | 606.1690 | 0.7896 | 0.0000 | 0.6119 | 0.3135 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 1:2 | 399 | 112 | 0.0050 | 367.1771 | 0.0750 | 0.0000 | 0.2130 | 0.3154 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_0_pos3_7_draw_0 | 0 | 42 | 34 | 0.0000 | -522.5556 | -1.0000 | 0.0000 | 1.4762 | 0.1792 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_3_pos3_4_draw_0 | 1:2 | 47 | 36 | 0.0000 | -546.1802 | -1.0000 | 0.0000 | 0.9149 | 0.3035 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 0 | 50 | 37 | 0.0000 | -595.5920 | -1.0000 | 0.0000 | 0.9600 | 0.2238 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | -2:-1 | 58 | 38 | 0.0000 | -707.4463 | -1.0000 | 0.0000 | 0.2759 | 0.2536 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 0 | 68 | 47 | 0.0000 | -805.9369 | -1.0000 | 0.0000 | 0.5588 | 0.2167 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 1:2 | 90 | 55 | 0.0000 | -1083.8543 | -1.0000 | 0.0000 | 0.2333 | 0.3195 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | >=3 | 91 | 45 | 0.0000 | -1123.8269 | -1.0000 | 0.0000 | 0.1758 | 0.4198 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 1:2 | 114 | 67 | 0.0000 | -1366.3613 | -1.0000 | 0.0000 | 0.3947 | 0.3174 |
| ev_m0p95_p0p85_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | -2:-1 | 318 | 106 | 0.0000 | -3870.9577 | -1.0000 | 0.0000 | 0.1258 | 0.2614 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 0 | 96 | 55 | 0.0104 | 15259.3334 | 17.9531 | 0.0000 | 0.4271 | 0.2061 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 1:2 | 410 | 109 | 0.0073 | 4023.0824 | 0.9741 | 0.0000 | 0.1976 | 0.3128 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 1:2 | 51 | 41 | 0.0196 | 906.8734 | 1.9420 | 0.0000 | 0.4118 | 0.3092 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_4_pos3_3_draw_0 | 0 | 41 | 31 | 0.0000 | -395.7207 | -1.0000 | 0.0000 | 0.7317 | 0.2036 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | -2:-1 | 51 | 31 | 0.0000 | -403.4040 | -1.0000 | 0.0000 | 0.2157 | 0.2480 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_0_pos3_7_draw_0 | 0 | 42 | 29 | 0.0000 | -456.5595 | -1.0000 | 0.0000 | 1.3810 | 0.1678 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 0 | 60 | 41 | 0.0000 | -528.4342 | -1.0000 | 0.0000 | 0.4167 | 0.2012 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_5_pos3_2_draw_0 | 1:2 | 75 | 49 | 0.0000 | -733.0631 | -1.0000 | 0.0000 | 0.2267 | 0.3137 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_6_pos3_1_draw_0 | 1:2 | 99 | 64 | 0.0000 | -843.7428 | -1.0000 | 0.0000 | 0.2020 | 0.3110 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | 0 | 679 | 123 | 0.0029 | -893.9902 | -0.1339 | 0.0000 | 0.1723 | 0.1937 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | >=3 | 91 | 44 | 0.0000 | -1083.8060 | -1.0000 | 0.0000 | 0.1538 | 0.4159 |
| ev_m0p95_p0p8_full_opt__budget256_fractional | neg0_7_pos3_0_draw_0 | -2:-1 | 261 | 86 | 0.0000 | -2513.2772 | -1.0000 | 0.0000 | 0.1188 | 0.2638 |


## Interpretation

- The selector is evaluated as a ticket-pool selector. It does not yet regenerate better combinations from leg primitives.
- `topology_exact_6n0_1p3_d0` tests the niche directly: six negative-handicap `0` legs plus one positive-handicap `3` leg, with no draw cover.
- `selector_v1_topology_priority` uses exact topology first, then mixed negative-0/positive-3 draw-free tickets, then negative-0-heavy draw-free tickets.
- `selector_v2_topology_ll_guard` adds an LL-risk guard; it keeps useful LL pockets but avoids bad LL pockets where possible.
- `selector_v3_topology_ll_linegap_topk` adds a soft line-gap preference and keeps only the top-k tickets per active issue.
- `selector_v4_linegap_supported_priority` checks whether the Beidan-vs-Asian handicap mismatch can act as a niche filter.
- `portfolio_realloc_*` arms keep `neg0>=6, draw=0` as the broad high-N core and allocate a smaller sleeve to the convex topology; if the sleeve is unavailable in an issue, its stake is reallocated to the core.

## Files

- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_summary.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_recent_2023_2025_summary.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_annual_summary.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_issue_profit.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_portfolio_issue_profit.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_selected_tickets.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_enriched_source_tickets.csv`
- `results/high_n_selector_plus2026_linefill_20260630/high_n_selector_topology_linegap_recent.csv`
