# Binary EV pool N sweep

- Source outcome table: `results/n3_outcome_ev_depth_coverage_20260628/n3_outcome_ev_depth_option_depth.csv`
- Source calibrated arm: `n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev`
- Selector premise: collapse pre-match EV into only `high` and `low`; high outcomes are investable, low outcomes only protect selected tickets.
- `absolute` high means `q_cal >= cut`; `local` high means issue-local top share by `q_cal`.
- Tickets are unique N=3/4/5 combinations with distinct matches. Same-budget replay uses 256 units per active issue with fractional scaling/ranking by predicted EV.
- This directly tests whether increasing N to absorb more high-EV matches uses capital better than deepening N3 coverage.

## Summary

| strategy | pool_n_legs | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | pool_avg_high_options | pool_avg_high_matches | pool_avg_raw_tickets | mix_raw_roi | mix_raw_hit_rate | mix_pattern_mix | hq_captured_hq_missed_winners |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| binary_n5_absq20_t120_high100__budget256_fractional | 5 | 668 | 21676.3448 | 0.1268 | 0.1737 | 0.2680 | -14011.9175 | 15 | 0.0428 | -6785.7123 | -0.2055 | 66.3937 | 66.3638 | 117.8967 | 0.1404 | 0.0226 | HHHHH:78755 | 0 |
| binary_n5_local60_t180_high100__budget256_fractional | 5 | 671 | 21420.6428 | 0.1247 | 0.1848 | 0.2951 | -13217.4839 | 13 | 0.0502 | -3363.4283 | -0.1018 | 55.8584 | 55.8122 | 177.7288 | 0.1378 | 0.0225 | HHHHH:119256 | 0 |
| binary_n5_absq20_t80_high100__budget256_fractional | 5 | 668 | 20031.5863 | 0.1171 | 0.1647 | 0.2186 | -16500.4306 | 22 | 0.0257 | -8884.8588 | -0.2690 | 66.3937 | 66.3638 | 78.7949 | 0.1306 | 0.0225 | HHHHH:52635 | 0 |
| binary_n5_local60_t120_high100__budget256_fractional | 5 | 671 | 19661.8064 | 0.1145 | 0.1744 | 0.2668 | -13081.1732 | 13 | 0.0309 | -3606.8561 | -0.1092 | 55.8584 | 55.8122 | 118.6945 | 0.1258 | 0.0226 | HHHHH:79644 | 0 |
| binary_n5_local60_t120_high90_low1_10__budget256_fractional | 5 | 671 | 19661.8064 | 0.1145 | 0.1744 | 0.2668 | -13081.1732 | 13 | 0.0309 | -3606.8561 | -0.1092 | 55.8584 | 55.8122 | 118.6945 | 0.1258 | 0.0226 | HHHHH:71700;HHHHH_backfill:7944 | 0 |
| binary_n5_local60_t80_high100__budget256_fractional | 5 | 671 | 18831.6028 | 0.1096 | 0.1639 | 0.2176 | -12843.5944 | 22 | 0.0186 | -5904.1107 | -0.1788 | 55.8584 | 55.8122 | 79.2310 | 0.1199 | 0.0226 | HHHHH:53164 | 0 |
| binary_n4_local60_t240_high100__budget256_fractional | 4 | 672 | 831.2645 | 0.0048 | 0.2634 | 0.6146 | -9699.1934 | 6 | -0.0231 | -5181.1247 | -0.1569 | 55.7798 | 55.7336 | 236.2485 | 0.0169 | 0.0442 | HHHH:158759 | 0 |
| binary_n4_absq20_t180_high100__budget256_fractional | 4 | 669 | -1415.8910 | -0.0083 | 0.2511 | 0.5590 | -10794.0898 | 7 | -0.0395 | -7322.5000 | -0.2217 | 66.3004 | 66.2706 | 176.2915 | 0.0017 | 0.0439 | HHHH:117939 | 0 |
| binary_n4_local60_t180_high100__budget256_fractional | 4 | 672 | -1948.2065 | -0.0113 | 0.2440 | 0.5506 | -10213.4738 | 7 | -0.0424 | -6357.7041 | -0.1925 | 55.7798 | 55.7336 | 177.5878 | 0.0002 | 0.0441 | HHHH:119339 | 0 |
| binary_n4_local60_t180_high85_low1_15__budget256_fractional | 4 | 672 | -1948.2065 | -0.0113 | 0.2440 | 0.5506 | -10213.4738 | 7 | -0.0424 | -6357.7041 | -0.1925 | 55.7798 | 55.7336 | 177.5878 | 0.0002 | 0.0441 | HHHH:101519;HHHH_backfill:17820 | 0 |
| binary_n4_absq20_t120_high100__budget256_fractional | 4 | 669 | -2702.5623 | -0.0158 | 0.2362 | 0.4858 | -12390.1618 | 9 | -0.0492 | -7959.2561 | -0.2410 | 66.3004 | 66.2706 | 117.9686 | -0.0057 | 0.0438 | HHHH:78921 | 0 |
| binary_n4_local60_t120_high100__budget256_fractional | 4 | 672 | -2992.9148 | -0.0174 | 0.2336 | 0.4836 | -11655.4712 | 9 | -0.0507 | -6563.5653 | -0.1988 | 55.7798 | 55.7336 | 118.6414 | -0.0074 | 0.0440 | HHHH:79727 | 0 |
| binary_n3_absq20_t180_high100__budget256_fractional | 3 | 670 | -12005.2433 | -0.0700 | 0.3343 | 0.8746 | -12552.4961 | 3 | -0.0799 | -7863.2387 | -0.2381 | 66.2060 | 66.1761 | 175.1627 | -0.0729 | 0.0937 | HHH:117359 | 64 |
| binary_n3_absq20_t360_high80_low1_20__budget256_fractional | 3 | 671 | -13379.3630 | -0.0779 | 0.3413 | 0.9016 | -13482.5689 | 3 | -0.0871 | -7761.1074 | -0.2350 | 66.1103 | 66.0805 | 349.3905 | -0.0689 | 0.0929 | HHH:186371;HHL:42094;HHH_backfill:5976 | 86 |
| binary_n3_absq20_t240_high80_low1_20__budget256_fractional | 3 | 671 | -13443.4640 | -0.0783 | 0.3323 | 0.8882 | -14034.3276 | 3 | -0.0887 | -7562.2151 | -0.2290 | 66.1103 | 66.0805 | 234.1788 | -0.0769 | 0.0919 | HHH:125051;HHL:28099;HHH_backfill:3984 | 77 |
| binary_n3_local60_t360_high80_low1_20__budget256_fractional | 3 | 672 | -13919.5959 | -0.0809 | 0.3438 | 0.8988 | -14302.4109 | 3 | -0.0901 | -7652.6842 | -0.2317 | 55.7783 | 55.7321 | 352.9598 | -0.0782 | 0.0912 | HHH:189095;HHL:48094 | 85 |
| binary_n3_local60_t240_high80_low1_20__budget256_fractional | 3 | 672 | -14067.9397 | -0.0818 | 0.3274 | 0.8735 | -14682.5279 | 3 | -0.0934 | -7264.1770 | -0.2200 | 55.7783 | 55.7321 | 236.3170 | -0.0793 | 0.0909 | HHH:126697;HHL:32108 | 77 |
| binary_n3_absq20_t180_high80_low1_20__budget256_fractional | 3 | 671 | -14247.0764 | -0.0829 | 0.3145 | 0.8510 | -15560.7976 | 3 | -0.0927 | -7400.4285 | -0.2241 | 66.1103 | 66.0805 | 176.3025 | -0.0804 | 0.0917 | HHH:94220;HHL:21091;HHH_backfill:2988 | 57 |
| binary_n3_local60_t180_high70_low1_25_low2_5__budget256_fractional | 3 | 672 | -14451.3773 | -0.0840 | 0.3408 | 0.8363 | -15955.9706 | 4 | -0.0965 | -6362.4782 | -0.1927 | 55.7783 | 55.7321 | 178.1190 | -0.0825 | 0.0893 | HHH:83560;HHL:30107;HLL:6029 | 50 |
| binary_n3_local60_t180_high100__budget256_fractional | 3 | 672 | -14624.9182 | -0.0850 | 0.3199 | 0.8676 | -14624.9182 | 3 | -0.0948 | -7817.1405 | -0.2367 | 55.7783 | 55.7321 | 176.8765 | -0.0793 | 0.0938 | HHH:118861 | 62 |
| binary_n3_local60_t180_high80_low1_20__budget256_fractional | 3 | 672 | -15401.9731 | -0.0895 | 0.3051 | 0.8438 | -16367.9244 | 3 | -0.1008 | -6888.3104 | -0.2086 | 55.7783 | 55.7321 | 177.7321 | -0.0868 | 0.0904 | HHH:95332;HHL:24104 | 54 |


## Pool Shape

| strategy | n_legs | active_issues | avg_high_options | avg_low_options | avg_high_matches | avg_high_cut | avg_raw_tickets |
| --- | --- | --- | --- | --- | --- | --- | --- |
| binary_n3_absq20_t180_high100 | 3 | 670 | 66.2060 | 26.6776 | 66.1761 | 2.0000 | 175.1627 |
| binary_n3_absq20_t180_high80_low1_20 | 3 | 671 | 66.1103 | 26.6408 | 66.0805 | 2.0000 | 176.3025 |
| binary_n3_absq20_t240_high80_low1_20 | 3 | 671 | 66.1103 | 26.6408 | 66.0805 | 2.0000 | 234.1788 |
| binary_n3_absq20_t360_high80_low1_20 | 3 | 671 | 66.1103 | 26.6408 | 66.0805 | 2.0000 | 349.3905 |
| binary_n3_local60_t180_high100 | 3 | 672 | 55.7783 | 36.8452 | 55.7321 | 2.0352 | 176.8765 |
| binary_n3_local60_t180_high70_low1_25_low2_5 | 3 | 672 | 55.7783 | 36.8452 | 55.7321 | 2.0352 | 178.1190 |
| binary_n3_local60_t180_high80_low1_20 | 3 | 672 | 55.7783 | 36.8452 | 55.7321 | 2.0352 | 177.7321 |
| binary_n3_local60_t240_high80_low1_20 | 3 | 672 | 55.7783 | 36.8452 | 55.7321 | 2.0352 | 236.3170 |
| binary_n3_local60_t360_high80_low1_20 | 3 | 672 | 55.7783 | 36.8452 | 55.7321 | 2.0352 | 352.9598 |
| binary_n4_absq20_t120_high100 | 4 | 669 | 66.3004 | 26.7130 | 66.2706 | 2.0000 | 117.9686 |
| binary_n4_absq20_t180_high100 | 4 | 669 | 66.3004 | 26.7130 | 66.2706 | 2.0000 | 176.2915 |
| binary_n4_local60_t120_high100 | 4 | 672 | 55.7798 | 36.8438 | 55.7336 | 2.0352 | 118.6414 |
| binary_n4_local60_t180_high100 | 4 | 672 | 55.7798 | 36.8438 | 55.7336 | 2.0352 | 177.5878 |
| binary_n4_local60_t180_high85_low1_15 | 4 | 672 | 55.7798 | 36.8438 | 55.7336 | 2.0352 | 177.5878 |
| binary_n4_local60_t240_high100 | 4 | 672 | 55.7798 | 36.8438 | 55.7336 | 2.0352 | 236.2485 |
| binary_n5_absq20_t120_high100 | 5 | 668 | 66.3937 | 26.7290 | 66.3638 | 2.0000 | 117.8967 |
| binary_n5_absq20_t80_high100 | 5 | 668 | 66.3937 | 26.7290 | 66.3638 | 2.0000 | 78.7949 |
| binary_n5_local60_t120_high100 | 5 | 671 | 55.8584 | 36.8972 | 55.8122 | 2.0352 | 118.6945 |
| binary_n5_local60_t120_high90_low1_10 | 5 | 671 | 55.8584 | 36.8972 | 55.8122 | 2.0352 | 118.6945 |
| binary_n5_local60_t180_high100 | 5 | 671 | 55.8584 | 36.8972 | 55.8122 | 2.0352 | 177.7288 |
| binary_n5_local60_t80_high100 | 5 | 671 | 55.8584 | 36.8972 | 55.8122 | 2.0352 | 79.2310 |


## Raw Mix

| strategy | n_legs | raw_tickets | raw_hit_rate | raw_roi | avg_pred_ev_per_stake | avg_pred_hit_prob | avg_q_product | pattern_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| binary_n3_absq20_t180_high100 | 3 | 117359 | 0.0937 | -0.0729 | 53.7440 | 0.0696 | 84.2215 | HHH:117359 |
| binary_n3_absq20_t180_high80_low1_20 | 3 | 118299 | 0.0917 | -0.0804 | 50.6975 | 0.0685 | 79.5347 | HHH:94220;HHL:21091;HHH_backfill:2988 |
| binary_n3_absq20_t240_high80_low1_20 | 3 | 157134 | 0.0919 | -0.0769 | 49.1417 | 0.0688 | 77.1410 | HHH:125051;HHL:28099;HHH_backfill:3984 |
| binary_n3_absq20_t360_high80_low1_20 | 3 | 234441 | 0.0929 | -0.0689 | 46.8624 | 0.0695 | 73.6345 | HHH:186371;HHL:42094;HHH_backfill:5976 |
| binary_n3_local60_t180_high100 | 3 | 118861 | 0.0938 | -0.0793 | 53.3137 | 0.0697 | 83.5595 | HHH:118861 |
| binary_n3_local60_t180_high70_low1_25_low2_5 | 3 | 119696 | 0.0893 | -0.0825 | 46.7456 | 0.0673 | 73.4547 | HHH:83560;HHL:30107;HLL:6029 |
| binary_n3_local60_t180_high80_low1_20 | 3 | 119436 | 0.0904 | -0.0868 | 49.6318 | 0.0681 | 77.8951 | HHH:95332;HHL:24104 |
| binary_n3_local60_t240_high80_low1_20 | 3 | 158805 | 0.0909 | -0.0793 | 48.1033 | 0.0683 | 75.5435 | HHH:126697;HHL:32108 |
| binary_n3_local60_t360_high80_low1_20 | 3 | 237189 | 0.0912 | -0.0782 | 45.8845 | 0.0688 | 72.1300 | HHH:189095;HHL:48094 |
| binary_n4_absq20_t120_high100 | 4 | 78921 | 0.0438 | -0.0057 | 280.9779 | 0.0287 | 433.8122 | HHHH:78921 |
| binary_n4_absq20_t180_high100 | 4 | 117939 | 0.0439 | 0.0017 | 271.3640 | 0.0288 | 419.0215 | HHHH:117939 |
| binary_n4_local60_t120_high100 | 4 | 79727 | 0.0440 | -0.0074 | 278.8179 | 0.0287 | 430.4890 | HHHH:79727 |
| binary_n4_local60_t180_high100 | 4 | 119339 | 0.0441 | 0.0002 | 268.9712 | 0.0289 | 415.3403 | HHHH:119339 |
| binary_n4_local60_t180_high85_low1_15 | 4 | 119339 | 0.0441 | 0.0002 | 268.9712 | 0.0289 | 415.3403 | HHHH:101519;HHHH_backfill:17820 |
| binary_n4_local60_t240_high100 | 4 | 158759 | 0.0442 | 0.0169 | 261.9059 | 0.0290 | 404.4706 | HHHH:158759 |
| binary_n5_absq20_t120_high100 | 5 | 78755 | 0.0226 | 0.1404 | 1345.9968 | 0.0121 | 2072.3028 | HHHHH:78755 |
| binary_n5_absq20_t80_high100 | 5 | 52635 | 0.0225 | 0.1306 | 1382.1557 | 0.0119 | 2127.9319 | HHHHH:52635 |
| binary_n5_local60_t120_high100 | 5 | 79644 | 0.0226 | 0.1258 | 1333.2094 | 0.0121 | 2052.6299 | HHHHH:79644 |
| binary_n5_local60_t120_high90_low1_10 | 5 | 79644 | 0.0226 | 0.1258 | 1333.2094 | 0.0121 | 2052.6299 | HHHHH:71700;HHHHH_backfill:7944 |
| binary_n5_local60_t180_high100 | 5 | 119256 | 0.0225 | 0.1378 | 1294.0629 | 0.0121 | 1992.4045 | HHHHH:119256 |
| binary_n5_local60_t80_high100 | 5 | 53164 | 0.0226 | 0.1199 | 1370.4513 | 0.0119 | 2109.9250 | HHHHH:53164 |


## High-Quality Missed Winner Capture

| strategy | captured_hq_missed_winners | captured_hq_share | captured_hq_payout_sum |
| --- | --- | --- | --- |
| binary_n3_absq20_t180_high100__budget256_fractional | 64 | 0.2909 | 2749.7422 |
| binary_n3_absq20_t180_high80_low1_20__budget256_fractional | 57 | 0.2591 | 2505.7943 |
| binary_n3_absq20_t240_high80_low1_20__budget256_fractional | 77 | 0.3500 | 3319.3557 |
| binary_n3_absq20_t360_high80_low1_20__budget256_fractional | 86 | 0.3909 | 3635.5472 |
| binary_n3_local60_t180_high100__budget256_fractional | 62 | 0.2818 | 2676.8950 |
| binary_n3_local60_t180_high70_low1_25_low2_5__budget256_fractional | 50 | 0.2273 | 2097.5196 |
| binary_n3_local60_t180_high80_low1_20__budget256_fractional | 54 | 0.2455 | 2288.4888 |
| binary_n3_local60_t240_high80_low1_20__budget256_fractional | 77 | 0.3500 | 3244.6803 |
| binary_n3_local60_t360_high80_low1_20__budget256_fractional | 85 | 0.3864 | 3584.9640 |
| binary_n4_absq20_t120_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n4_absq20_t180_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n4_local60_t120_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n4_local60_t180_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n4_local60_t180_high85_low1_15__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n4_local60_t240_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n5_absq20_t120_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n5_absq20_t80_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n5_local60_t120_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n5_local60_t120_high90_low1_10__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n5_local60_t180_high100__budget256_fractional | 0 | 0.0000 | 0 |
| binary_n5_local60_t80_high100__budget256_fractional | 0 | 0.0000 | 0 |


## Annual For Top Strategies

| strategy | year | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| binary_n5_absq20_t120_high100__budget256_fractional | 2014 | 116 | 2931.9834 | 0.0987 | 0.2328 | 0.3448 | -5435.3100 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2015 | 56 | -1696.8801 | -0.1184 | 0.0893 | 0.2143 | -5248.0068 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2016 | 52 | -5713.3864 | -0.4292 | 0.1538 | 0.2308 | -6960.4371 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2017 | 46 | 16655.7043 | 1.4144 | 0.2391 | 0.3043 | -2965.4924 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2018 | 58 | 3090.8415 | 0.2082 | 0.1724 | 0.2931 | -4003.0766 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2019 | 55 | -2730.1223 | -0.1939 | 0.1273 | 0.2000 | -6671.5960 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2020 | 42 | 10698.8960 | 0.9951 | 0.1905 | 0.2381 | -2816.0000 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2021 | 58 | 8148.4802 | 0.5488 | 0.2241 | 0.2931 | -5180.4647 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2022 | 56 | -2923.4596 | -0.2039 | 0.1607 | 0.2143 | -3730.8820 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2023 | 55 | -3821.2402 | -0.2714 | 0.1273 | 0.2727 | -7369.2503 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2024 | 59 | -3862.4382 | -0.2557 | 0.1186 | 0.2034 | -6382.3392 |
| binary_n5_absq20_t120_high100__budget256_fractional | 2025 | 15 | 897.9660 | 0.2338 | 0.2667 | 0.4667 | -817.1030 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2014 | 116 | 2142.4994 | 0.0721 | 0.2328 | 0.3276 | -6129.6865 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2015 | 56 | 1136.5670 | 0.0793 | 0.0893 | 0.1071 | -5632.0000 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2016 | 52 | -6538.3813 | -0.4912 | 0.1346 | 0.1731 | -6920.0403 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2017 | 46 | 17293.3758 | 1.4685 | 0.1957 | 0.2391 | -3995.6739 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2018 | 58 | 1105.4226 | 0.0744 | 0.1552 | 0.2241 | -4196.2995 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2019 | 55 | -2882.1406 | -0.2047 | 0.1273 | 0.1636 | -6884.5305 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2020 | 42 | 12605.9496 | 1.1724 | 0.1667 | 0.1905 | -2816.0000 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2021 | 58 | 7772.6514 | 0.5235 | 0.1897 | 0.2586 | -5707.1908 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2022 | 56 | -3719.4988 | -0.2595 | 0.1250 | 0.1429 | -4230.8346 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2023 | 55 | -5716.2070 | -0.4060 | 0.1455 | 0.2364 | -8068.2755 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2024 | 59 | -3630.4164 | -0.2404 | 0.1356 | 0.1695 | -6325.5911 |
| binary_n5_absq20_t80_high100__budget256_fractional | 2025 | 15 | 461.7646 | 0.1203 | 0.3333 | 0.4000 | -928.0854 |
| binary_n5_local60_t120_high100__budget256_fractional | 2014 | 116 | 2441.0159 | 0.0822 | 0.2328 | 0.3362 | -5730.0907 |
| binary_n5_local60_t120_high100__budget256_fractional | 2015 | 56 | -3628.0540 | -0.2531 | 0.0893 | 0.2143 | -5248.0068 |
| binary_n5_local60_t120_high100__budget256_fractional | 2016 | 52 | -5713.3864 | -0.4292 | 0.1538 | 0.2308 | -6960.4371 |
| binary_n5_local60_t120_high100__budget256_fractional | 2017 | 46 | 16655.7043 | 1.4144 | 0.2391 | 0.3043 | -2965.4924 |
| binary_n5_local60_t120_high100__budget256_fractional | 2018 | 58 | 3090.8415 | 0.2082 | 0.1724 | 0.2931 | -4003.0766 |
| binary_n5_local60_t120_high100__budget256_fractional | 2019 | 55 | -2730.1223 | -0.1939 | 0.1273 | 0.2000 | -6671.5960 |
| binary_n5_local60_t120_high100__budget256_fractional | 2020 | 43 | 10101.2177 | 0.9176 | 0.2093 | 0.2558 | -2873.1442 |
| binary_n5_local60_t120_high100__budget256_fractional | 2021 | 58 | 6585.7789 | 0.4435 | 0.2069 | 0.2759 | -5180.4647 |
| binary_n5_local60_t120_high100__budget256_fractional | 2022 | 58 | -3534.3332 | -0.2380 | 0.1552 | 0.2241 | -3756.4425 |
| binary_n5_local60_t120_high100__budget256_fractional | 2023 | 55 | -3821.2402 | -0.2714 | 0.1273 | 0.2727 | -7369.2503 |
| binary_n5_local60_t120_high100__budget256_fractional | 2024 | 59 | -683.5820 | -0.0453 | 0.1356 | 0.2034 | -5120.4835 |
| binary_n5_local60_t120_high100__budget256_fractional | 2025 | 15 | 897.9660 | 0.2338 | 0.2667 | 0.4667 | -817.1030 |
| binary_n5_local60_t180_high100__budget256_fractional | 2014 | 116 | 610.7549 | 0.0206 | 0.2241 | 0.3448 | -5715.1160 |
| binary_n5_local60_t180_high100__budget256_fractional | 2015 | 56 | -3916.6559 | -0.2732 | 0.1071 | 0.2321 | -5034.4041 |
| binary_n5_local60_t180_high100__budget256_fractional | 2016 | 52 | -4699.2268 | -0.3530 | 0.1731 | 0.2885 | -6330.1925 |
| binary_n5_local60_t180_high100__budget256_fractional | 2017 | 46 | 16716.8540 | 1.4196 | 0.2609 | 0.3696 | -2369.8544 |
| binary_n5_local60_t180_high100__budget256_fractional | 2018 | 58 | 3985.6587 | 0.2684 | 0.2069 | 0.3621 | -3617.3575 |
| binary_n5_local60_t180_high100__budget256_fractional | 2019 | 55 | -3927.7022 | -0.2790 | 0.1091 | 0.2000 | -7096.6791 |
| binary_n5_local60_t180_high100__budget256_fractional | 2020 | 43 | 10571.8214 | 0.9604 | 0.2093 | 0.2558 | -2816.0000 |
| binary_n5_local60_t180_high100__budget256_fractional | 2021 | 58 | 7084.4225 | 0.4771 | 0.2414 | 0.3276 | -4471.5977 |
| binary_n5_local60_t180_high100__budget256_fractional | 2022 | 58 | -1641.8554 | -0.1106 | 0.1724 | 0.2414 | -3500.8300 |
| binary_n5_local60_t180_high100__budget256_fractional | 2023 | 55 | -2233.0339 | -0.1586 | 0.1455 | 0.2909 | -7699.8663 |
| binary_n5_local60_t180_high100__budget256_fractional | 2024 | 59 | -1657.6054 | -0.1097 | 0.1356 | 0.2373 | -5113.4217 |
| binary_n5_local60_t180_high100__budget256_fractional | 2025 | 15 | 527.2109 | 0.1373 | 0.2667 | 0.4667 | -974.0827 |


## Interpretation

- This is a selector test, not a final staking policy. If higher N improves capital efficiency, it should be considered a separate sleeve from N3 high-win coverage.
- The high-quality missed-winner capture section is N3-based only; use the summary/annual rows for N4/N5 evaluation.
- If absolute high activates fewer issues, compare both deployed ROI and unit-time profit before treating it as better.

Equity curve SVG: `docs/research/figures/binary_ev_pool_n_sweep_equity_2026-06-28.svg`

## Files

- Summary: `results/binary_ev_pool_n_sweep_20260628/binary_ev_pool_n_sweep_summary.csv`
- Annual: `results/binary_ev_pool_n_sweep_20260628/binary_ev_pool_n_sweep_annual.csv`
- Budget tickets: `results/binary_ev_pool_n_sweep_20260628/binary_ev_pool_n_sweep_budget_tickets.csv`
- Pool summary: `results/binary_ev_pool_n_sweep_20260628/binary_ev_pool_n_sweep_pool_summary.csv`
