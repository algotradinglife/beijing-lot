# High-N selector replay

## Scope

- Ticket pool: `results/n7_ev_framework_selector_cap80_budget1024_20260628/ev_framework_budget_fractional_tickets.csv`
- q/conf LL source: `results/n7_q_conf_drift_joint_2014_10h_trusted/joint_leg_rows.csv` / spec `keyed_pockets`
- DB: `../../data/derived/beidan_xlsm/beidan_xlsm.sqlite`
- Line gap: `-beidan_handicap - asian_handicap_1h`.
- Line gap threshold: `0.5`. Draw-only legs are treated as neutral.
- Same-budget active issue stake: `1024.0`.

## Main Comparison

| source_strategy | selector | issues | profit_units | roi | issue_win_rate | max_drawdown_units | ex_top1_roi | recent_issues | recent_profit_units | recent_roi | recent_issue_win_rate | recent_max_drawdown_units | recent_ex_top1_roi | avg_tickets_per_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 610 | 620104.2962 | 0.9927 | 0.0180 | -310964.2252 | -0.3128 | 119 | 730685.0342 | 5.9963 | 0.0168 | -84494.8328 | -0.6993 | 5.3820 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v4_linegap_supported_priority | 669 | 680631.3090 | 0.9935 | 0.0194 | -277685.9219 | -0.1967 | 129 | 720445.0342 | 5.4540 | 0.0155 | -94734.8328 | -0.7228 | 3.8984 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 669 | 602293.9210 | 0.8792 | 0.0149 | -285892.8264 | -0.3112 | 129 | 720445.0342 | 5.4540 | 0.0155 | -94734.8328 | -0.7228 | 4.1824 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 669 | 580644.1294 | 0.8476 | 0.0194 | -328920.3920 | -0.3429 | 129 | 720445.0342 | 5.4540 | 0.0155 | -94734.8328 | -0.7228 | 5.8714 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 669 | 580644.1294 | 0.8476 | 0.0194 | -328920.3920 | -0.3429 | 129 | 720445.0342 | 5.4540 | 0.0155 | -94734.8328 | -0.7228 | 5.8595 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_neg0_ge5_pos3_ge1_d0 | 643 | 331688.0896 | 0.5038 | 0.0233 | -300852.7853 | -0.4251 | 124 | 523285.2350 | 4.1211 | 0.0161 | -87843.6652 | -0.6974 | 8.6827 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_70_core_neg0ge6_30_exact | 665 | 779997.6089 | 1.1454 | 0.0917 | -93024.1353 | 0.6625 | 129 | 315457.6591 | 2.3881 | 0.0853 | -93024.1353 | -0.1074 | 27.3774 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 665 | 798554.9815 | 1.1727 | 0.0917 | -95266.6070 | 0.6887 | 129 | 249937.9697 | 1.8921 | 0.0853 | -95266.6070 | -0.0780 | 30.2872 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 669 | 781387.8072 | 1.1406 | 0.0912 | -95266.6070 | 0.6595 | 129 | 239207.8796 | 1.8109 | 0.0853 | -95266.6070 | -0.1599 | 29.8670 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_90_core_neg0ge6_10_exact | 665 | 817112.3540 | 1.1999 | 0.0917 | -97509.0788 | 0.6551 | 129 | 184418.2803 | 1.3961 | 0.0853 | -97509.0788 | -0.0486 | 33.1564 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_neg0_ge6_d0 | 665 | 835669.7266 | 1.2272 | 0.0932 | -99751.5506 | 0.6215 | 129 | 118898.5910 | 0.9001 | 0.0853 | -99751.5506 | -0.0191 | 36.0316 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | draw_free | 667 | 640623.8512 | 0.9379 | 0.1229 | -98341.9697 | 0.5512 | 129 | 57359.3692 | 0.4342 | 0.0853 | -97277.9695 | -0.2218 | 49.7616 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 669 | 263100.4927 | 0.3841 | 0.1973 | -76962.5260 | 0.1284 | 129 | 18076.3375 | 0.1368 | 0.2326 | -43737.8393 | -0.0949 | 68.1629 |


## Current Read

- Preferred source for the next iteration: `ev_m0p95_p0p8_full_opt__budget256_fractional`.
- Main high-N core: `topology_neg0_ge6_d0`, profit `nan`, ROI `nan%`, recent profit `nan`, recent ROI `nan%`.
- Convex sleeve candidate: `topology_exact_6n0_1p3_d0`, profit `nan`, but max drawdown `nan` and ex-top1 ROI `nan%`; do not run it as full-stake standalone.
- Current practical arm: `portfolio_realloc_80_core_neg0ge6_20_exact`, profit `nan`, ROI `nan%`, recent profit `nan`, recent ROI `nan%`, max drawdown `nan`.
- Line-gap is useful as a diagnostic/niche descriptor, but the first hard/soft gates did not outperform the topology portfolio. Recent exact-topology winners were mostly `line_gap_support_net = 0`, not strongly positive.

## Annual Detail

| source_strategy | selector | year | issues | profit_units | roi | issue_win_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2014 | 116 | -19970.0611 | -0.1681 | 0.1983 | -35052.3733 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2015 | 58 | -8161.3104 | -0.1374 | 0.1724 | -23687.2245 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2016 | 53 | 25643.5250 | 0.4725 | 0.2264 | -15173.3681 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2017 | 47 | 108587.4076 | 2.2562 | 0.2979 | -8666.0799 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2018 | 54 | 182071.7754 | 3.2927 | 0.1852 | -22408.8531 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2019 | 55 | -29637.8294 | -0.5262 | 0.0909 | -37324.4551 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2020 | 42 | -15599.9634 | -0.3627 | 0.2619 | -19204.1352 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2021 | 58 | 33862.8991 | 0.5702 | 0.2069 | -12325.3386 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2022 | 57 | -31772.2874 | -0.5443 | 0.0877 | -35659.0838 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2023 | 55 | 41299.3265 | 0.7333 | 0.2364 | -20514.8503 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2024 | 59 | -15188.5051 | -0.2514 | 0.2542 | -25399.4946 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | all | 2025 | 15 | -8034.4838 | -0.5231 | 0.1333 | -8364.2154 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2014 | 116 | 26815.2567 | 0.2257 | 0.1034 | -37107.6882 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2015 | 58 | -6925.8557 | -0.1166 | 0.0862 | -20480.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2016 | 53 | 33845.1471 | 0.6236 | 0.0755 | -29000.9392 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2017 | 47 | 107624.6957 | 2.2362 | 0.1489 | -20940.4693 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2018 | 54 | 340417.6691 | 6.1563 | 0.1296 | -24380.4116 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2019 | 55 | -49396.2800 | -0.8771 | 0.0364 | -49396.2800 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2020 | 41 | 54738.1680 | 1.3038 | 0.0732 | -14353.2747 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2021 | 56 | 79479.7835 | 1.3860 | 0.1071 | -35840.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2022 | 56 | -37981.5727 | -0.6623 | 0.0714 | -37981.5727 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2023 | 55 | 210416.0355 | 3.7361 | 0.0364 | -54272.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2024 | 59 | -25589.2824 | -0.4236 | 0.0847 | -45017.5072 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_exact | 2025 | 15 | 65111.2166 | 4.2390 | 0.2667 | -8192.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2014 | 116 | 26815.2567 | 0.2257 | 0.1034 | -37107.6882 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2015 | 58 | -6925.8557 | -0.1166 | 0.0862 | -20480.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2016 | 53 | 31504.0629 | 0.5805 | 0.0755 | -29000.9392 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2017 | 47 | 107624.6957 | 2.2362 | 0.1489 | -20940.4693 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2018 | 54 | 340417.6691 | 6.1563 | 0.1296 | -24380.4116 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2019 | 55 | -49396.2800 | -0.8771 | 0.0364 | -49396.2800 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2020 | 42 | 53714.1680 | 1.2489 | 0.0714 | -14353.2747 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2021 | 58 | 77431.7835 | 1.3037 | 0.1034 | -36864.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2022 | 57 | -39005.5727 | -0.6683 | 0.0702 | -39005.5727 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2023 | 55 | 210416.0355 | 3.7361 | 0.0364 | -54272.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2024 | 59 | -25589.2824 | -0.4236 | 0.0847 | -45017.5072 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | portfolio_realloc_80_core_neg0ge6_20_priority | 2025 | 15 | 54381.1265 | 3.5404 | 0.2667 | -8192.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2014 | 116 | -92096.8329 | -0.7753 | 0.0259 | -92096.8329 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2015 | 58 | -53748.0749 | -0.9050 | 0.0172 | -56320.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2016 | 53 | -54272.0000 | -1.0000 | 0.0000 | -54272.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2017 | 47 | -29065.9348 | -0.6039 | 0.0213 | -39936.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2018 | 54 | -20889.5494 | -0.3778 | 0.0185 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2019 | 55 | -56320.0000 | -1.0000 | 0.0000 | -56320.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2020 | 42 | 238718.9386 | 5.5506 | 0.0476 | -22528.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2021 | 58 | -25609.7942 | -0.4312 | 0.0345 | -49152.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2022 | 57 | -46517.6571 | -0.7970 | 0.0175 | -46517.6571 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2023 | 55 | 759883.8670 | 13.4923 | 0.0182 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2024 | 59 | -24078.8328 | -0.3986 | 0.0169 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v1_topology_priority | 2025 | 15 | -15360.0000 | -1.0000 | 0.0000 | -15360.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2014 | 116 | -92096.8329 | -0.7753 | 0.0259 | -92096.8329 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2015 | 58 | -53748.0749 | -0.9050 | 0.0172 | -56320.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2016 | 53 | -54272.0000 | -1.0000 | 0.0000 | -54272.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2017 | 47 | -29065.9348 | -0.6039 | 0.0213 | -39936.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2018 | 54 | -20889.5494 | -0.3778 | 0.0185 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2019 | 55 | -56320.0000 | -1.0000 | 0.0000 | -56320.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2020 | 42 | 238718.9386 | 5.5506 | 0.0476 | -22528.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2021 | 58 | -25609.7942 | -0.4312 | 0.0345 | -49152.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2022 | 57 | -46517.6571 | -0.7970 | 0.0175 | -46517.6571 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2023 | 55 | 759883.8670 | 13.4923 | 0.0182 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2024 | 59 | -24078.8328 | -0.3986 | 0.0169 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v2_topology_ll_guard | 2025 | 15 | -15360.0000 | -1.0000 | 0.0000 | -15360.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2014 | 116 | -85425.0411 | -0.7192 | 0.0259 | -85425.0411 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2015 | 58 | -59392.0000 | -1.0000 | 0.0000 | -59392.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2016 | 53 | -54272.0000 | -1.0000 | 0.0000 | -54272.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2017 | 47 | -10003.8695 | -0.2079 | 0.0213 | -39936.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2018 | 54 | 2048.0843 | 0.0370 | 0.0185 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2019 | 55 | -56320.0000 | -1.0000 | 0.0000 | -56320.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2020 | 42 | 238718.9386 | 5.5506 | 0.0476 | -22528.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2021 | 58 | -35137.2253 | -0.5916 | 0.0172 | -49152.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2022 | 57 | -58368.0000 | -1.0000 | 0.0000 | -58368.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2023 | 55 | 759883.8670 | 13.4923 | 0.0182 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2024 | 59 | -24078.8328 | -0.3986 | 0.0169 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | selector_v3_topology_ll_linegap_topk | 2025 | 15 | -15360.0000 | -1.0000 | 0.0000 | -15360.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2014 | 105 | -96144.7410 | -0.8942 | 0.0190 | -96144.7410 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2015 | 49 | -50176.0000 | -1.0000 | 0.0000 | -50176.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2016 | 50 | -51200.0000 | -1.0000 | 0.0000 | -51200.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2017 | 45 | -27017.9348 | -0.5863 | 0.0222 | -37888.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2018 | 51 | -17817.5494 | -0.3412 | 0.0196 | -27648.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2019 | 50 | -51200.0000 | -1.0000 | 0.0000 | -51200.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2020 | 35 | 245886.9386 | 6.8607 | 0.0571 | -17408.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2021 | 53 | -20489.7942 | -0.3775 | 0.0377 | -45056.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2022 | 53 | -42421.6571 | -0.7816 | 0.0189 | -43008.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2023 | 55 | 759883.8670 | 13.4923 | 0.0182 | -55296.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2024 | 50 | -14862.8328 | -0.2903 | 0.0200 | -47104.0000 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | topology_exact_6n0_1p3_d0 | 2025 | 14 | -14336.0000 | -1.0000 | 0.0000 | -14336.0000 |


## Recent Topology x Line Gap

| strategy | topology | linegap_net_bucket | tickets | issues | hit_rate | profit_units | roi_raw_ticket_stake | avg_ll_bad_count | avg_ll_good_count | avg_abs_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_1_draw_0 | 0 | 280 | 88 | 0.0036 | 29828.3155 | 38.2743 | 0.0000 | 0.4714 | 0.2052 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_7_pos3_0_draw_7 | 1:2 | 47 | 16 | 0.2340 | 2524.2043 | 0.4298 | 0.0000 | 1.6383 | 0.3792 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_0_draw_2 | 1:2 | 47 | 28 | 0.0638 | 1074.0895 | 4.4471 | 0.0000 | 0.2128 | 0.2574 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_7_pos3_0_draw_0 | >=3 | 176 | 56 | 0.0170 | 811.8874 | 2.1822 | 0.0000 | 0.4602 | 0.4168 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_1 | 1:2 | 52 | 31 | 0.0192 | 445.1660 | 2.1997 | 0.0000 | 0.9808 | 0.2986 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_0_draw_1 | 0 | 73 | 37 | 0.0137 | 316.4669 | 1.0418 | 0.0000 | 0.2603 | 0.1948 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_7_pos3_0_draw_1 | 1:2 | 55 | 31 | 0.0182 | -19.1307 | -0.0861 | 0.0000 | 0.7818 | 0.3468 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_1_draw_0 | >=3 | 51 | 31 | 0.0196 | -21.5488 | -0.2329 | 0.0000 | 0.6078 | 0.4255 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_4_pos3_3_draw_0 | >=3 | 47 | 30 | 0.0000 | -67.9392 | -1.0000 | 0.0000 | 0.4468 | 0.4295 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_0 | >=3 | 41 | 31 | 0.0244 | -84.2089 | -0.5195 | 0.0000 | 0.3415 | 0.4261 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_2_pos3_5_draw_0 | 1:2 | 51 | 38 | 0.0000 | -92.4930 | -1.0000 | 0.0000 | 0.6863 | 0.2938 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_0_draw_1 | -2:-1 | 41 | 17 | 0.0000 | -137.2181 | -1.0000 | 0.0000 | 0.0976 | 0.2796 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_3_pos3_4_draw_0 | 1:2 | 83 | 55 | 0.0000 | -179.7120 | -1.0000 | 0.0000 | 0.6506 | 0.3072 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_1_pos3_6_draw_0 | 0 | 51 | 35 | 0.0000 | -198.7007 | -1.0000 | 0.0000 | 1.4118 | 0.1765 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_0_pos3_7_draw_0 | 1:2 | 63 | 34 | 0.0000 | -199.0725 | -1.0000 | 0.0000 | 0.9524 | 0.3088 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_2_pos3_5_draw_0 | 0 | 64 | 39 | 0.0000 | -204.0927 | -1.0000 | 0.0000 | 1.2031 | 0.1921 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_3_pos3_4_draw_0 | 0 | 76 | 46 | 0.0000 | -223.1973 | -1.0000 | 0.0000 | 1.1842 | 0.1952 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_0 | -2:-1 | 69 | 28 | 0.0000 | -244.4711 | -1.0000 | 0.0000 | 0.4783 | 0.2468 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_4_pos3_3_draw_0 | 1:2 | 141 | 64 | 0.0071 | -249.0968 | -0.6989 | 0.0000 | 0.5745 | 0.3044 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_4_pos3_3_draw_0 | 0 | 111 | 55 | 0.0000 | -291.6078 | -1.0000 | 0.0000 | 0.9550 | 0.1920 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_3_pos3_4_draw_4 | 1:2 | 42 | 26 | 0.0238 | -299.6561 | -0.2860 | 0.0000 | 1.0714 | 0.3192 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_2 | 0 | 54 | 30 | 0.0000 | -353.4598 | -1.0000 | 0.0000 | 0.9444 | 0.2467 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_0_pos3_7_draw_0 | 0 | 123 | 42 | 0.0000 | -362.8916 | -1.0000 | 0.0000 | 2.0488 | 0.1690 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_1_draw_0 | -2:-1 | 128 | 41 | 0.0000 | -419.0045 | -1.0000 | 0.0000 | 0.3281 | 0.2530 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_0 | 1:2 | 175 | 81 | 0.0000 | -421.9519 | -1.0000 | 0.0000 | 0.4229 | 0.3141 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_1_draw_1 | 1:2 | 93 | 55 | 0.0000 | -494.5875 | -1.0000 | 0.0000 | 0.6774 | 0.3156 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_4_pos3_0_draw_3 | 0 | 47 | 28 | 0.0000 | -537.7822 | -1.0000 | 0.0000 | 0.1489 | 0.2230 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_0_draw_2 | 0 | 69 | 37 | 0.0000 | -540.9255 | -1.0000 | 0.0000 | 0.2319 | 0.2024 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_1_draw_0 | 1:2 | 240 | 91 | 0.0000 | -550.6346 | -1.0000 | 0.0000 | 0.4500 | 0.3099 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_2 | 1:2 | 76 | 45 | 0.0000 | -577.1169 | -1.0000 | 0.0000 | 0.7368 | 0.3294 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_6_pos3_1_draw_1 | 0 | 123 | 50 | 0.0000 | -583.5716 | -1.0000 | 0.0000 | 0.6179 | 0.2269 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_5_pos3_2_draw_0 | 0 | 198 | 76 | 0.0000 | -637.9850 | -1.0000 | 0.0000 | 0.6818 | 0.2033 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_4_pos3_3_draw_3 | 1:2 | 43 | 31 | 0.0000 | -647.6604 | -1.0000 | 0.0000 | 1.1628 | 0.3314 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_3_pos3_0_draw_4 | 1:2 | 40 | 24 | 0.0000 | -895.8648 | -1.0000 | 0.0000 | 0.1000 | 0.2986 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_7_pos3_0_draw_0 | 0 | 1554 | 125 | 0.0026 | -1182.1194 | -0.3328 | 0.0000 | 0.2091 | 0.1902 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_7_pos3_0_draw_0 | 1:2 | 830 | 113 | 0.0036 | -1203.1995 | -0.5335 | 0.0000 | 0.4795 | 0.3187 |
| ev_m0p95_p0p8_full_opt__budget1024_fractional | neg0_7_pos3_0_draw_0 | -2:-1 | 567 | 88 | 0.0000 | -1491.3536 | -1.0000 | 0.0000 | 0.1570 | 0.2604 |


## Interpretation

- The selector is evaluated as a ticket-pool selector. It does not yet regenerate better combinations from leg primitives.
- `topology_exact_6n0_1p3_d0` tests the niche directly: six negative-handicap `0` legs plus one positive-handicap `3` leg, with no draw cover.
- `selector_v1_topology_priority` uses exact topology first, then mixed negative-0/positive-3 draw-free tickets, then negative-0-heavy draw-free tickets.
- `selector_v2_topology_ll_guard` adds an LL-risk guard; it keeps useful LL pockets but avoids bad LL pockets where possible.
- `selector_v3_topology_ll_linegap_topk` adds a soft line-gap preference and keeps only the top-k tickets per active issue.
- `selector_v4_linegap_supported_priority` checks whether the Beidan-vs-Asian handicap mismatch can act as a niche filter.
- `portfolio_realloc_*` arms keep `neg0>=6, draw=0` as the broad high-N core and allocate a smaller sleeve to the convex topology; if the sleeve is unavailable in an issue, its stake is reallocated to the core.

## Files

- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_summary.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_recent_2023_2025_summary.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_annual_summary.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_issue_profit.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_portfolio_issue_profit.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_selected_tickets.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_enriched_source_tickets.csv`
- `results/high_n_selector_cap80_budget1024_20260628/high_n_selector_topology_linegap_recent.csv`
