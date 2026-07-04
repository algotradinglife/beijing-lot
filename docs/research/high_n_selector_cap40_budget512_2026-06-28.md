# High-N selector replay

## Scope

- Ticket pool: `results/n7_ev_framework_selector_cap40_budget512_20260628/ev_framework_budget_fractional_tickets.csv`
- q/conf LL source: `results/n7_q_conf_drift_joint_2014_10h_trusted/joint_leg_rows.csv` / spec `keyed_pockets`
- DB: `../../data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- Line gap: `-beidan_handicap - asian_handicap_1h`.
- Line gap threshold: `0.5`. Draw-only legs are treated as neutral.
- Same-budget active issue stake: `512.0`.

## Main Comparison

| source_strategy | selector | issues | profit_units | roi | issue_win_rate | max_drawdown_units | ex_top1_roi | recent_issues | recent_profit_units | recent_roi | recent_issue_win_rate | recent_max_drawdown_units | recent_ex_top1_roi | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 575 | 371369.0700 | 1.2614 | 0.0174 | -127846.4816 | -0.1232 | 115 | 367390.5171 | 6.2396 | 0.0174 | -40199.4164 | -0.6887 | 3.5287 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v4_linegap_supported_priority | 669 | 477498.7777 | 1.3940 | 0.0194 | -95872.2963 | 0.2044 | 129 | 360222.5171 | 5.4540 | 0.0155 | -47367.4164 | -0.7228 | 2.8072 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 669 | 419121.6983 | 1.2236 | 0.0179 | -102777.2405 | 0.0337 | 129 | 360222.5171 | 5.4540 | 0.0155 | -47367.4164 | -0.7228 | 3.1943 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 669 | 363329.2463 | 1.0607 | 0.0194 | -134995.6491 | -0.1294 | 129 | 360222.5171 | 5.4540 | 0.0155 | -47367.4164 | -0.7228 | 4.0643 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 669 | 363329.2463 | 1.0607 | 0.0194 | -134995.6491 | -0.1294 | 129 | 360222.5171 | 5.4540 | 0.0155 | -47367.4164 | -0.7228 | 4.0583 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_neg0_ge5_pos3_ge1_d0 | 637 | 232368.3342 | 0.7125 | 0.0220 | -138262.0176 | -0.2248 | 124 | 261642.6175 | 4.1211 | 0.0161 | -43921.8326 | -0.6974 | 5.4427 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 665 | 413596.5206 | 1.2147 | 0.0692 | -48803.7584 | 0.4542 | 129 | 166345.5137 | 2.5186 | 0.0620 | -48803.7584 | 0.0241 | 18.0421 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 665 | 419459.7272 | 1.2320 | 0.0707 | -50252.3787 | 0.3624 | 129 | 134177.9281 | 2.0315 | 0.0620 | -50252.3787 | 0.0625 | 19.7579 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 669 | 415976.3616 | 1.2144 | 0.0703 | -50252.3787 | 0.3500 | 129 | 127918.7088 | 1.9368 | 0.0620 | -50252.3787 | -0.0330 | 19.2691 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 665 | 425322.9338 | 1.2492 | 0.0707 | -51700.9990 | 0.2705 | 129 | 102010.3424 | 1.5445 | 0.0620 | -51700.9990 | 0.1010 | 21.4526 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_neg0_ge6_d0 | 665 | 431186.1404 | 1.2664 | 0.0707 | -53149.6193 | 0.1786 | 129 | 69842.7568 | 1.0575 | 0.0620 | -53149.6193 | 0.1395 | 23.1639 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | draw_free | 667 | 333472.4301 | 0.9765 | 0.0990 | -51435.9347 | 0.2542 | 129 | 36719.8674 | 0.5560 | 0.0620 | -51435.9347 | -0.0991 | 31.1634 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 669 | 180186.8630 | 0.5261 | 0.1510 | -38923.2394 | -0.0633 | 129 | 85.5550 | 0.0013 | 0.1705 | -33775.9533 | -0.2315 | 37.9387 |


## Current Read

- Preferred source for the next iteration: `ev_m0p95_p0p8_full_opt__budget256_fractional`.
- Main high-N core: `topology_neg0_ge6_d0`, profit `nan`, ROI `nan%`, recent profit `nan`, recent ROI `nan%`.
- Convex sleeve candidate: `topology_exact_6n0_1p3_d0`, profit `nan`, but max drawdown `nan` and ex-top1 ROI `nan%`; do not run it as full-stake standalone.
- Current practical arm: `portfolio_realloc_80_core_neg0ge6_20_exact`, profit `nan`, ROI `nan%`, recent profit `nan`, recent ROI `nan%`, max drawdown `nan`.
- Line-gap is useful as a diagnostic/niche descriptor, but the first hard/soft gates did not outperform the topology portfolio. Recent exact-topology winners were mostly `line_gap_support_net = 0`, not strongly positive.

## Annual Detail

| source_strategy | selector | year | issues | profit_units | roi | issue_win_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2014 | 116 | -13699.1589 | -0.2307 | 0.2155 | -16672.7069 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2015 | 58 | -9989.7455 | -0.3364 | 0.1207 | -11524.5855 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2016 | 53 | -13515.2808 | -0.4981 | 0.1321 | -15452.1142 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2017 | 47 | 14082.6939 | 0.5852 | 0.2128 | -5742.9662 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2018 | 54 | 204881.8976 | 7.4104 | 0.1296 | -13969.7403 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2019 | 55 | -11660.9883 | -0.4141 | 0.0909 | -21487.1534 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2020 | 42 | -1602.1473 | -0.0745 | 0.1190 | -6679.8069 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2021 | 58 | 31989.2871 | 1.0772 | 0.1552 | -9728.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2022 | 57 | -20385.2498 | -0.6985 | 0.0702 | -21599.1960 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2023 | 55 | 20913.0623 | 0.7427 | 0.2000 | -12948.4459 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2024 | 59 | -15990.2312 | -0.5293 | 0.1356 | -17286.3953 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | all | 2025 | 15 | -4837.2761 | -0.6299 | 0.2000 | -5058.7784 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2014 | 116 | 13599.9179 | 0.2290 | 0.0948 | -16415.1093 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2015 | 58 | -10146.7029 | -0.3417 | 0.0690 | -12749.5813 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2016 | 53 | -21948.5486 | -0.8088 | 0.0377 | -23372.6574 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2017 | 47 | 7833.2403 | 0.3255 | 0.1064 | -12193.7865 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2018 | 54 | 306309.6874 | 11.0789 | 0.1111 | -11150.5186 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2019 | 55 | -22167.6335 | -0.7872 | 0.0364 | -23781.7091 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2020 | 41 | 37938.6428 | 1.8073 | 0.0732 | -6656.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2021 | 56 | -6754.3196 | -0.2356 | 0.0536 | -22528.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2022 | 56 | -19382.4847 | -0.6760 | 0.0536 | -19382.4847 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2023 | 55 | 106749.9061 | 3.7908 | 0.0364 | -27136.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2024 | 59 | -11954.9112 | -0.3958 | 0.0508 | -25266.7522 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2025 | 15 | 39382.9331 | 5.1280 | 0.2000 | -4096.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2014 | 116 | 13599.9179 | 0.2290 | 0.0948 | -16415.1093 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2015 | 58 | -10146.7029 | -0.3417 | 0.0690 | -12749.5813 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2016 | 53 | -21948.5486 | -0.8088 | 0.0377 | -23372.6574 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2017 | 47 | 7833.2403 | 0.3255 | 0.1064 | -12193.7865 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2018 | 54 | 306309.6874 | 11.0789 | 0.1111 | -11150.5186 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2019 | 55 | -17343.7799 | -0.6159 | 0.0364 | -23781.7091 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2020 | 42 | 37426.6428 | 1.7405 | 0.0714 | -7168.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2021 | 58 | -7778.3196 | -0.2619 | 0.0517 | -23040.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2022 | 57 | -19894.4847 | -0.6817 | 0.0526 | -19894.4847 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2023 | 55 | 106749.9061 | 3.7908 | 0.0364 | -27136.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2024 | 59 | -11954.9112 | -0.3958 | 0.0508 | -25266.7522 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2025 | 15 | 33123.7139 | 4.3130 | 0.2000 | -4096.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2014 | 116 | -45556.6244 | -0.7670 | 0.0259 | -45556.6244 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2015 | 58 | -25557.1216 | -0.8606 | 0.0172 | -28160.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2016 | 53 | -27136.0000 | -1.0000 | 0.0000 | -27136.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2017 | 47 | -5001.9348 | -0.2079 | 0.0213 | -19968.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2018 | 54 | -6143.9684 | -0.2222 | 0.0185 | -13824.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2019 | 55 | 133.3438 | 0.0047 | 0.0182 | -25600.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2020 | 42 | 127058.9920 | 5.9086 | 0.0476 | -11264.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2021 | 58 | 2643.6996 | 0.0890 | 0.0172 | -24576.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2022 | 57 | -17333.6571 | -0.5939 | 0.0175 | -23040.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2023 | 55 | 379941.9335 | 13.4923 | 0.0182 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2024 | 59 | -12039.4164 | -0.3986 | 0.0169 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v1_topology_priority | 2025 | 15 | -7680.0000 | -1.0000 | 0.0000 | -7680.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2014 | 116 | -45556.6244 | -0.7670 | 0.0259 | -45556.6244 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2015 | 58 | -25557.1216 | -0.8606 | 0.0172 | -28160.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2016 | 53 | -27136.0000 | -1.0000 | 0.0000 | -27136.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2017 | 47 | -5001.9348 | -0.2079 | 0.0213 | -19968.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2018 | 54 | -6143.9684 | -0.2222 | 0.0185 | -13824.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2019 | 55 | 133.3438 | 0.0047 | 0.0182 | -25600.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2020 | 42 | 127058.9920 | 5.9086 | 0.0476 | -11264.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2021 | 58 | 2643.6996 | 0.0890 | 0.0172 | -24576.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2022 | 57 | -17333.6571 | -0.5939 | 0.0175 | -23040.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2023 | 55 | 379941.9335 | 13.4923 | 0.0182 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2024 | 59 | -12039.4164 | -0.3986 | 0.0169 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v2_topology_ll_guard | 2025 | 15 | -7680.0000 | -1.0000 | 0.0000 | -7680.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2014 | 116 | -42361.2405 | -0.7132 | 0.0259 | -42361.2405 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2015 | 58 | -29696.0000 | -1.0000 | 0.0000 | -29696.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2016 | 53 | -27136.0000 | -1.0000 | 0.0000 | -27136.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2017 | 47 | 14060.1305 | 0.5843 | 0.0213 | -19968.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2018 | 54 | 15360.0632 | 0.5556 | 0.0185 | -13824.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2019 | 55 | 133.3438 | 0.0047 | 0.0182 | -25600.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2020 | 42 | 127058.9920 | 5.9086 | 0.0476 | -11264.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2021 | 58 | 18813.5494 | 0.6335 | 0.0172 | -24576.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2022 | 57 | -17333.6571 | -0.5939 | 0.0175 | -23040.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2023 | 55 | 379941.9335 | 13.4923 | 0.0182 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2024 | 59 | -12039.4164 | -0.3986 | 0.0169 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | selector_v3_topology_ll_linegap_topk | 2025 | 15 | -7680.0000 | -1.0000 | 0.0000 | -7680.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2014 | 103 | -46556.5784 | -0.8828 | 0.0194 | -46556.5784 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2015 | 45 | -23040.0000 | -1.0000 | 0.0000 | -23040.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2016 | 48 | -24576.0000 | -1.0000 | 0.0000 | -24576.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2017 | 41 | -1929.9348 | -0.0919 | 0.0244 | -16896.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2018 | 45 | -1535.9684 | -0.0667 | 0.0222 | -11776.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2019 | 42 | -21504.0000 | -1.0000 | 0.0000 | -21504.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2020 | 35 | 130642.9920 | 7.2903 | 0.0571 | -8704.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2021 | 49 | 7251.6996 | 0.2891 | 0.0204 | -20480.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2022 | 52 | -14773.6571 | -0.5549 | 0.0192 | -20992.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2023 | 54 | 380453.9335 | 13.7606 | 0.0185 | -27136.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2024 | 48 | -6407.4164 | -0.2607 | 0.0208 | -22528.0000 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | topology_exact_6n0_1p3_d0 | 2025 | 13 | -6656.0000 | -1.0000 | 0.0000 | -6656.0000 |


## Recent Topology x Line Gap

| strategy | topology | linegap_net_bucket | tickets | issues | hit_rate | profit_units | roi_raw_ticket_stake | avg_ll_bad_count | avg_ll_good_count | avg_abs_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_6_pos3_1_draw_0 | 0 | 181 | 78 | 0.0055 | 14244.4202 | 13.4457 | 0.0000 | 0.4807 | 0.2109 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_7_pos3_0_draw_0 | 1:2 | 631 | 112 | 0.0048 | -52.0739 | -0.0155 | 0.0000 | 0.3772 | 0.3170 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_4_pos3_3_draw_0 | 1:2 | 89 | 54 | 0.0112 | -158.8090 | -0.3544 | 0.0000 | 0.4719 | 0.3058 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_0_pos3_7_draw_0 | 1:2 | 43 | 32 | 0.0000 | -193.9500 | -1.0000 | 0.0000 | 0.9302 | 0.3091 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_3_pos3_4_draw_0 | 0 | 46 | 34 | 0.0000 | -257.2034 | -1.0000 | 0.0000 | 1.1957 | 0.2033 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_2_pos3_5_draw_0 | 0 | 45 | 34 | 0.0000 | -260.1440 | -1.0000 | 0.0000 | 1.0444 | 0.1941 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_3_pos3_4_draw_0 | 1:2 | 59 | 47 | 0.0000 | -293.3832 | -1.0000 | 0.0000 | 0.7119 | 0.2999 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_6_pos3_1_draw_1 | 0 | 46 | 25 | 0.0000 | -368.1423 | -1.0000 | 0.0000 | 0.6304 | 0.2228 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_5_pos3_2_draw_0 | -2:-1 | 44 | 23 | 0.0000 | -368.3726 | -1.0000 | 0.0000 | 0.3636 | 0.2508 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_0_pos3_7_draw_0 | 0 | 74 | 37 | 0.0000 | -395.2123 | -1.0000 | 0.0000 | 1.6892 | 0.1702 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_4_pos3_3_draw_0 | 0 | 73 | 48 | 0.0000 | -443.6971 | -1.0000 | 0.0000 | 0.9178 | 0.1942 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_6_pos3_1_draw_0 | -2:-1 | 83 | 36 | 0.0000 | -489.2870 | -1.0000 | 0.0000 | 0.2771 | 0.2550 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_5_pos3_2_draw_0 | 1:2 | 122 | 73 | 0.0000 | -650.4533 | -1.0000 | 0.0000 | 0.4016 | 0.3143 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_5_pos3_2_draw_0 | 0 | 121 | 69 | 0.0000 | -682.8079 | -1.0000 | 0.0000 | 0.5455 | 0.2038 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_7_pos3_0_draw_0 | >=3 | 130 | 53 | 0.0000 | -771.2216 | -1.0000 | 0.0000 | 0.3692 | 0.4173 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_6_pos3_1_draw_0 | 1:2 | 164 | 81 | 0.0000 | -829.4293 | -1.0000 | 0.0000 | 0.3963 | 0.3159 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_7_pos3_0_draw_0 | -2:-1 | 412 | 87 | 0.0000 | -2548.2734 | -1.0000 | 0.0000 | 0.1481 | 0.2611 |
| ev_m0p95_p0p8_full_opt__budget512_fractional | neg0_7_pos3_0_draw_0 | 0 | 1118 | 124 | 0.0027 | -3231.2431 | -0.5574 | 0.0000 | 0.1932 | 0.1915 |


## Interpretation

- The selector is evaluated as a ticket-pool selector. It does not yet regenerate better combinations from leg primitives.
- `topology_exact_6n0_1p3_d0` tests the niche directly: six negative-handicap `0` legs plus one positive-handicap `3` leg, with no draw cover.
- `selector_v1_topology_priority` uses exact topology first, then mixed negative-0/positive-3 draw-free tickets, then negative-0-heavy draw-free tickets.
- `selector_v2_topology_ll_guard` adds an LL-risk guard; it keeps useful LL pockets but avoids bad LL pockets where possible.
- `selector_v3_topology_ll_linegap_topk` adds a soft line-gap preference and keeps only the top-k tickets per active issue.
- `selector_v4_linegap_supported_priority` checks whether the Beidan-vs-Asian handicap mismatch can act as a niche filter.
- `portfolio_realloc_*` arms keep `neg0>=6, draw=0` as the broad high-N core and allocate a smaller sleeve to the convex topology; if the sleeve is unavailable in an issue, its stake is reallocated to the core.

## Files

- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_summary.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_recent_2023_2025_summary.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_annual_summary.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_issue_profit.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_portfolio_issue_profit.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_selected_tickets.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_enriched_source_tickets.csv`
- `results/high_n_selector_cap40_budget512_20260628/high_n_selector_topology_linegap_recent.csv`
