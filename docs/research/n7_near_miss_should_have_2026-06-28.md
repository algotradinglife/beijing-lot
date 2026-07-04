# N7 Near-Miss Should-Have Analysis

## Scope

- Raw ticket path: `results/n7_core_ticket_protection_20260628/n7_core_ticket_protection_raw_tickets.csv`.
- Strategies: `core_base,core_tp_only_draw_top_ev_k1`.
- Snapshot for diagnostic market features: `1h`.
- This is an oracle diagnostic: it uses realized result to measure distance to hit. Rules found here must be validated by prospective replay before entering strategy.

## Headline

- One-miss tickets total: `295` across `173` issues.
- If every one-miss ticket had been protected exactly on the missed leg, oracle delta is `1,796,716.1` for incremental stake `3,747.0`.
- Oracle delta per incremental stake: `479.50`. This is not tradable directly; it is the upper bound for protection mining.

## Distance Distribution: Core

| strategy | miss_count | tickets | ticket_share | profit_units | oracle_coverable | oracle_delta_profit_units | oracle_incremental_stake_units | oracle_delta_per_incremental_stake |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_base | 0 | 44 | 0.0048 | 210777.5568 | 0 | 0.0000 | 0.0000 |  |
| core_base | 1 | 256 | 0.0281 | -2896.9687 | 256 | 1549407.2835 | 2896.9687 | 534.8374 |
| core_base | 2 | 952 | 0.1045 | -10732.2509 | 952 | 9766160.5005 | 32196.7527 | 303.3275 |
| core_base | 3 | 1944 | 0.2133 | -21503.5033 | 0 | 0.0000 | 0.0000 |  |
| core_base | 4 | 2508 | 0.2752 | -28163.2086 | 0 | 0.0000 | 0.0000 |  |
| core_base | 5 | 2143 | 0.2352 | -24273.3249 | 0 | 0.0000 | 0.0000 |  |
| core_base | 6 | 1063 | 0.1166 | -12012.8762 | 0 | 0.0000 | 0.0000 |  |
| core_base | 7 | 203 | 0.0223 | -2247.6789 | 0 | 0.0000 | 0.0000 |  |


## Distance Distribution: Protected Top-EV

| strategy | miss_count | tickets | ticket_share | profit_units | oracle_coverable | oracle_delta_profit_units | oracle_incremental_stake_units | oracle_delta_per_incremental_stake |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_tp_only_draw_top_ev_k1 | 0 | 7 | 0.0105 | 40581.9427 | 0 | 0.0000 | 0.0000 |  |
| core_tp_only_draw_top_ev_k1 | 1 | 39 | 0.0586 | -877.9263 | 39 | 247308.8056 | 850.0675 | 290.9284 |
| core_tp_only_draw_top_ev_k1 | 2 | 89 | 0.1336 | -1967.3435 | 89 | 1087306.4778 | 5749.3065 | 189.1196 |
| core_tp_only_draw_top_ev_k1 | 3 | 168 | 0.2523 | -3573.3589 | 0 | 0.0000 | 0.0000 |  |
| core_tp_only_draw_top_ev_k1 | 4 | 194 | 0.2913 | -4895.6040 | 0 | 0.0000 | 0.0000 |  |
| core_tp_only_draw_top_ev_k1 | 5 | 121 | 0.1817 | -2690.9376 | 0 | 0.0000 | 0.0000 |  |
| core_tp_only_draw_top_ev_k1 | 6 | 42 | 0.0631 | -995.4918 | 0 | 0.0000 | 0.0000 |  |
| core_tp_only_draw_top_ev_k1 | 7 | 6 | 0.0090 | -105.3175 | 0 | 0.0000 | 0.0000 |  |


## One-Miss Oracle Rules

| rule | tickets | issues | base_profit_units | oracle_profit_units | oracle_delta_profit_units | oracle_incremental_stake_units | oracle_delta_per_incremental_stake | avg_actual_1h_p | avg_draw_1h_p | avg_line_gap | avg_source_pred_ev |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| oracle_one_miss_any | 295 | 173 | -3774.8950 | 1792941.1941 | 1796716.0891 | 3747.0362 | 479.5033 | 0.4879 | 0.1813 | 0.2079 | 13009.4787 |
| draw_any | 126 | 87 | -1498.5127 | 816104.8440 | 817603.3567 | 1498.5127 | 545.6099 | 0.1844 | 0.1844 | 0.2637 | 13197.9419 |
| draw_0to10 | 124 | 85 | -1472.9127 | 796752.3403 | 798225.2530 | 1472.9127 | 541.9366 | 0.1853 | 0.1853 | 0.2726 | 13341.5853 |
| cold_actual_p_lt24 | 104 | 70 | -1261.9539 | 571173.0279 | 572434.9818 | 1261.9539 | 453.6101 | 0.1687 | 0.1687 | 0.2601 | 15867.5881 |
| draw_0to10_hcp-2 | 82 | 51 | -1011.5560 | 409911.2836 | 410922.8396 | 1011.5560 | 406.2285 | 0.1615 | 0.1615 | 0.2900 | 19172.4702 |
| draw_0to10_hcp-2_drawp_lt24 | 82 | 51 | -1011.5560 | 409911.2836 | 410922.8396 | 1011.5560 | 406.2285 | 0.1615 | 0.1615 | 0.2900 | 19172.4702 |
| cold_hcp-2_actual_p_lt24 | 82 | 51 | -1011.5560 | 409911.2836 | 410922.8396 | 1011.5560 | 406.2285 | 0.1615 | 0.1615 | 0.2900 | 19172.4702 |
| cold_actual_p_lt20 | 70 | 42 | -937.8719 | 355366.2841 | 356304.1560 | 937.8719 | 379.9071 | 0.1453 | 0.1453 | 0.1811 | 20303.3001 |
| draw_0to10_hcp-2_posgap | 63 | 40 | -730.6025 | 296228.8892 | 296959.4916 | 730.6025 | 406.4584 | 0.1758 | 0.1758 | 0.4682 | 18840.7262 |
| draw_0to10_hcp-2_drawp_lt24_posgap | 63 | 40 | -730.6025 | 296228.8892 | 296959.4916 | 730.6025 | 406.4584 | 0.1758 | 0.1758 | 0.4682 | 18840.7262 |


## One-Miss By Transition

| strategy | transition | hcp_bucket | tickets | issues | oracle_delta_profit_units | oracle_incremental_stake_units | oracle_delta_per_incremental_stake | avg_actual_1h_p | avg_draw_1h_p | avg_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_base | 0->30 | -1 | 49 | 39 | 440548.0217 | 544.1335 | 809.6322 | 0.6116 | 0.2287 | -0.0060 |
| core_base | 0->10 | -1 | 37 | 35 | 370144.0132 | 384.8689 | 961.7405 | 0.2453 | 0.2453 | 0.1755 |
| core_base | 0->10 | -2 | 68 | 49 | 352174.1009 | 734.1828 | 479.6818 | 0.1622 | 0.1622 | 0.2944 |
| core_base | 0->30 | -2 | 92 | 66 | 342961.5614 | 1112.0007 | 308.4185 | 0.7517 | 0.1614 | 0.2599 |
| core_tp_only_draw_top_ev_k1 | 0->30 | -2 | 19 | 19 | 162750.8857 | 452.7032 | 359.5091 | 0.7668 | 0.1537 | 0.1719 |
| core_tp_only_draw_top_ev_k1 | 0->10 | -2 | 14 | 14 | 58748.7387 | 277.3732 | 211.8039 | 0.1582 | 0.1582 | 0.2686 |
| core_base | 3->31 | >=2 | 2 | 2 | 19378.1037 | 25.6000 | 756.9572 | 0.1283 | 0.1283 | -0.2885 |
| core_base | 0->10 | <=-3 | 3 | 2 | 9587.8163 | 38.4000 | 249.6827 | 0.1083 | 0.1083 | 0.8643 |
| core_tp_only_draw_top_ev_k1 | 10->310 | -2 | 1 | 1 | 8996.8275 | 12.8000 | 702.8771 | 0.7029 | 0.1793 | 0.5192 |
| core_base | 0->30 | <=-3 | 4 | 4 | 8534.9273 | 47.5429 | 179.5207 | 0.8808 | 0.0834 | 0.1838 |
| core_base | 3->30 | >=2 | 1 | 1 | 6078.7390 | 10.2400 | 593.6269 | 0.7175 | 0.1923 | -0.5000 |
| core_tp_only_draw_top_ev_k1 | 0->30 | -1 | 1 | 1 | 5349.5014 | 28.4444 | 188.0684 | 0.5651 | 0.2411 | 0.2143 |
| core_tp_only_draw_top_ev_k1 | 0->10 | <=-3 | 1 | 1 | 4184.0288 | 25.6000 | 163.4386 | 0.1109 | 0.1109 | 0.9423 |
| core_tp_only_draw_top_ev_k1 | 0->10 | -1 | 1 | 1 | 3386.5551 | 12.4878 | 271.1890 | 0.2199 | 0.2199 | 0.0000 |
| core_tp_only_draw_top_ev_k1 | 0->30 | <=-3 | 1 | 1 | 2253.2370 | 25.6000 | 88.0171 | 0.8734 | 0.0888 | 0.2500 |
| core_tp_only_draw_top_ev_k1 | 10->310 | -1 | 1 | 1 | 1639.0313 | 15.0588 | 108.8419 | 0.6249 | 0.2223 | 0.0000 |


## Top One-Miss Leagues

| strategy | league | transition | tickets | issues | oracle_delta_profit_units | oracle_delta_per_incremental_stake | avg_actual_1h_p | avg_line_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_base | 苏冠 | 0->30 | 1 | 1 | 73934.5044 | 5776.1332 | 0.6509 | -0.2083 |
| core_base | 西甲 | 0->10 | 8 | 8 | 68479.2531 | 781.3938 | 0.1729 | 0.2777 |
| core_base | 欧冠杯 | 0->30 | 10 | 7 | 64793.4284 | 515.5727 | 0.7124 | 0.3422 |
| core_base | 日联杯 | 0->30 | 3 | 1 | 59440.5078 | 2941.0668 | 0.7355 | -0.7500 |
| core_base | 葡联杯 | 0->10 | 1 | 1 | 50166.9393 | 4115.2567 | 0.2549 | 0.2292 |
| core_base | 阿甲 | 0->10 | 4 | 3 | 48679.4244 | 1465.7369 | 0.2652 | 0.1836 |
| core_base | 英超 | 0->10 | 7 | 6 | 48082.6765 | 550.9473 | 0.1416 | -0.0723 |
| core_base | 巴西杯 | 0->10 | 3 | 3 | 41336.9974 | 1242.0973 | 0.2132 | 0.1347 |
| core_base | 德乙 | 0->10 | 4 | 3 | 41081.6269 | 821.0354 | 0.2165 | 0.4417 |
| core_base | 欧洲杯 | 0->30 | 3 | 3 | 35183.9547 | 1367.6497 | 0.7855 | 0.0129 |
| core_tp_only_draw_top_ev_k1 | 日职联 | 0->30 | 2 | 2 | 32217.3412 | 629.2449 | 0.6897 | 0.6354 |
| core_base | 欧罗巴 | 0->30 | 8 | 8 | 32128.3271 | 340.3790 | 0.7296 | 0.3412 |
| core_tp_only_draw_top_ev_k1 | 意杯 | 0->30 | 1 | 1 | 30625.8848 | 1196.3236 | 0.8081 | -0.0179 |
| core_base | 意甲 | 0->30 | 7 | 6 | 30360.5177 | 413.3029 | 0.7165 | -0.0427 |
| core_base | 捷甲 | 0->30 | 3 | 2 | 29314.1606 | 1702.9460 | 0.7165 | 0.0641 |
| core_tp_only_draw_top_ev_k1 | 欧洲预选 | 0->30 | 2 | 2 | 29283.0954 | 585.8851 | 0.7843 | 0.3084 |


## Annual Distance

| strategy | calendar_year | tickets | hit_rate | one_miss_tickets | one_miss_rate | miss_le2_tickets | miss_le2_rate | profit_units | oracle_delta_miss1 | oracle_delta_miss_le2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core_base | 2014 | 1556 | 0.0064 | 50 | 0.0321 | 213 | 0.1369 | 287.6411 | 175090.1712 | 1239255.4011 |
| core_base | 2015 | 859 | 0.0035 | 35 | 0.0407 | 143 | 0.1665 | 4535.9441 | 193739.1211 | 1312607.7132 |
| core_base | 2016 | 773 | 0.0039 | 23 | 0.0298 | 103 | 0.1332 | -5063.8178 | 202808.1082 | 1352493.2594 |
| core_base | 2017 | 675 | 0.0030 | 27 | 0.0400 | 119 | 0.1763 | -5826.2838 | 192550.4661 | 1105567.5769 |
| core_base | 2018 | 838 | 0.0084 | 22 | 0.0263 | 124 | 0.1480 | 109882.7207 | 111068.4101 | 1092406.8684 |
| core_base | 2019 | 738 | 0.0041 | 27 | 0.0366 | 136 | 0.1843 | -3291.2996 | 149318.1052 | 870141.9695 |
| core_base | 2020 | 483 | 0.0124 | 12 | 0.0248 | 78 | 0.1615 | 3758.8961 | 59645.6107 | 824382.0520 |
| core_base | 2021 | 722 | 0.0042 | 13 | 0.0180 | 81 | 0.1122 | -1645.2295 | 144341.3579 | 1059583.0077 |
| core_base | 2022 | 760 | 0.0013 | 5 | 0.0066 | 62 | 0.0816 | -7679.4501 | 17353.0127 | 585963.7253 |
| core_base | 2023 | 644 | 0.0031 | 12 | 0.0186 | 56 | 0.0870 | 11713.6299 | 149081.7102 | 775446.9250 |
| core_base | 2024 | 851 | 0.0024 | 20 | 0.0235 | 107 | 0.1257 | -5487.8877 | 95452.3760 | 913988.2810 |
| core_base | 2025 | 214 | 0.0093 | 10 | 0.0467 | 30 | 0.1402 | 7762.8819 | 58958.8341 | 183731.0044 |
| core_tp_only_draw_top_ev_k1 | 2014 | 116 | 0.0086 | 7 | 0.0603 | 29 | 0.2500 | -1220.7362 | 21370.8270 | 160813.9610 |
| core_tp_only_draw_top_ev_k1 | 2015 | 56 | 0.0000 | 7 | 0.1250 | 16 | 0.2857 | -1414.8005 | 43523.7745 | 158980.6092 |
| core_tp_only_draw_top_ev_k1 | 2016 | 52 | 0.0192 | 4 | 0.0769 | 10 | 0.1923 | 1930.8762 | 44347.7109 | 111548.9982 |
| core_tp_only_draw_top_ev_k1 | 2017 | 46 | 0.0000 | 2 | 0.0435 | 7 | 0.1522 | -1096.4546 | 8041.6634 | 61561.8670 |
| core_tp_only_draw_top_ev_k1 | 2018 | 58 | 0.0172 | 2 | 0.0345 | 10 | 0.1724 | 4551.9214 | 8266.8030 | 162288.6139 |
| core_tp_only_draw_top_ev_k1 | 2019 | 55 | 0.0364 | 3 | 0.0545 | 16 | 0.2909 | 8607.9586 | 12318.4176 | 185573.7695 |
| core_tp_only_draw_top_ev_k1 | 2020 | 41 | 0.0000 | 4 | 0.0976 | 8 | 0.1951 | -1432.2654 | 40171.3057 | 92102.9575 |
| core_tp_only_draw_top_ev_k1 | 2021 | 57 | 0.0000 | 4 | 0.0702 | 11 | 0.1930 | -1356.6092 | 39601.4752 | 195602.8151 |
| core_tp_only_draw_top_ev_k1 | 2022 | 56 | 0.0179 | 0 | 0.0000 | 11 | 0.1964 | 3293.4912 | 0.0000 | 111376.0641 |
| core_tp_only_draw_top_ev_k1 | 2023 | 55 | 0.0182 | 2 | 0.0364 | 8 | 0.1455 | 14971.0087 | 8419.3856 | 39562.2985 |
| core_tp_only_draw_top_ev_k1 | 2024 | 59 | 0.0000 | 2 | 0.0339 | 7 | 0.1186 | -1064.0504 | 3505.0138 | 37460.9005 |
| core_tp_only_draw_top_ev_k1 | 2025 | 15 | 0.0000 | 2 | 0.1333 | 2 | 0.1333 | -294.3769 | 17742.4289 | 17742.4289 |


## Interpretation

- `miss_count=1` is the most actionable bucket: one added result on one leg would have converted the ticket.
- `transition` tells what protection would have been needed, for example `0->10` means add draw to an original away/lower-side leg.
- High oracle delta with low incremental stake marks a protection mining target, but it can be a mirage if the trigger uses realized result. The next step is to replay the same trigger using only pre-match features.
