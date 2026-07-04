# N7 candidate pool constraint audit

- N7 PnL source: `results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv` filtered by `model=core512_none0`, `sleeve_label=none`.
- Candidate source: `results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_outcomes.csv` and `results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_decisions.csv`, `strategy=ev_m0p95_p0p8_full_opt`.
- `q20_matches` means distinct matches with at least one pre-match outcome `q >= 2.0`.
- Distinct match count matters more than raw outcome count for N=7, because one ticket needs seven different matches.

## Correlations

| metric | pearson_profit | spearman_profit | spearman_roi | spearman_issue_win |
| --- | --- | --- | --- | --- |
| total_matches | 0.0037 | 0.1653 | 0.1557 | 0.0320 |
| q15_matches | -0.0053 | 0.1751 | 0.1658 | 0.0341 |
| q20_matches | 0.0232 | 0.1626 | 0.1521 | 0.0401 |
| q23_matches | 0.0343 | 0.1614 | 0.1562 | 0.0307 |
| standalone_evpos_matches | -0.0029 | 0.1745 | 0.1648 | 0.0376 |
| n7_evpos_matches | -0.0091 | 0.1764 | 0.1672 | 0.0362 |
| decision_matches | -0.0023 | 0.1784 | 0.1690 | 0.0440 |
| decision_cover_slots | -0.0050 | 0.1785 | 0.1698 | 0.0411 |
| avg_decision_score | 0.0551 | 0.0826 | 0.0811 | 0.0298 |
| top_decision_score | 0.0163 | 0.0256 | 0.0278 | -0.0510 |
| avg_q20 | -0.0043 | 0.0874 | 0.0907 | 0.0230 |
| top_q | 0.0238 | 0.0126 | 0.0158 | -0.0564 |


## Annual Shape

| year | n_issues | profit_units | roi | issue_win_rate | avg_q20_matches | avg_decision_matches | avg_decision_score | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2014 | 116 | 21329.7891 | 0.3591 | 0.1379 | 35.2328 | 46.8793 | 2.2215 | -15175.6850 |
| 2015 | 56 | 1951.6512 | 0.0681 | 0.0893 | 91.5000 | 109.5893 | 2.5019 | -8764.1921 |
| 2016 | 52 | 59249.6916 | 2.2254 | 0.2115 | 93.6154 | 121.2885 | 2.4780 | -9850.1831 |
| 2017 | 46 | -7742.9339 | -0.3288 | 0.1739 | 99.9783 | 126.5435 | 2.6404 | -8812.6503 |
| 2018 | 58 | 145163.2174 | 4.8883 | 0.1207 | 111.1207 | 118.2241 | 2.5709 | -10893.3622 |
| 2019 | 55 | -758.1474 | -0.0269 | 0.1455 | 95.2364 | 118.9455 | 2.5167 | -9408.6645 |
| 2020 | 42 | 5684.6012 | 0.2644 | 0.1667 | 91.6667 | 97.5952 | 2.3735 | -4377.2691 |
| 2021 | 58 | 18630.1372 | 0.6274 | 0.2759 | 88.1552 | 110.1034 | 2.2662 | -6124.6380 |
| 2022 | 57 | -4450.4385 | -0.1525 | 0.0175 | 77.7895 | 97.0702 | 2.2432 | -21094.2284 |
| 2023 | 55 | 40088.3051 | 1.4236 | 0.1818 | 74.1636 | 94.1273 | 2.2507 | -12908.9304 |
| 2024 | 59 | -16009.8027 | -0.5300 | 0.1186 | 69.1525 | 95.0847 | 2.2478 | -17198.9354 |
| 2025 | 15 | 43652.0705 | 5.6839 | 0.2000 | 106.8000 | 110.2000 | 2.2879 | -2313.8816 |


## Buckets

| metric | bucket | n_issues | profit_units | roi | issue_win_rate | non_full_loss_rate | avg_metric | avg_decision_score |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q20_matches | 0-40 | 166 | 57180.3473 | 0.6728 | 0.1265 | 0.6205 | 24.8373 | 2.2911 |
| q20_matches | 40-70 | 143 | -556.0205 | -0.0076 | 0.1399 | 0.8112 | 52.5874 | 2.3582 |
| q20_matches | 70-110 | 176 | 140645.6993 | 1.5608 | 0.1534 | 0.8466 | 90.1023 | 2.3793 |
| q20_matches | 110-10000 | 184 | 109518.1147 | 1.1625 | 0.1685 | 0.8478 | 141.4022 | 2.4405 |
| decision_matches | 0-40 | 111 | 64539.4078 | 1.1356 | 0.1351 | 0.5766 | 25.4054 | 2.3163 |
| decision_matches | 40-70 | 148 | -4148.5871 | -0.0547 | 0.1081 | 0.7500 | 54.4054 | 2.3082 |
| decision_matches | 70-110 | 128 | 120956.4138 | 1.8456 | 0.1719 | 0.8594 | 89.2891 | 2.4200 |
| decision_matches | 110-150 | 133 | 123097.5962 | 1.8077 | 0.1579 | 0.8271 | 130.3008 | 2.3824 |
| decision_matches | 150-10000 | 149 | 2343.3101 | 0.0307 | 0.1678 | 0.8658 | 174.0201 | 2.4162 |


## Worst/Best Years By Profit

| year | profit_units | roi | avg_q20_matches | avg_decision_matches | avg_decision_score |
| --- | --- | --- | --- | --- | --- |
| 2024 | -16009.8027 | -0.5300 | 69.1525 | 95.0847 | 2.2478 |
| 2017 | -7742.9339 | -0.3288 | 99.9783 | 126.5435 | 2.6404 |
| 2022 | -4450.4385 | -0.1525 | 77.7895 | 97.0702 | 2.2432 |
| 2019 | -758.1474 | -0.0269 | 95.2364 | 118.9455 | 2.5167 |
| 2015 | 1951.6512 | 0.0681 | 91.5000 | 109.5893 | 2.5019 |
| 2020 | 5684.6012 | 0.2644 | 91.6667 | 97.5952 | 2.3735 |
| 2021 | 18630.1372 | 0.6274 | 88.1552 | 110.1034 | 2.2662 |
| 2014 | 21329.7891 | 0.3591 | 35.2328 | 46.8793 | 2.2215 |
| 2023 | 40088.3051 | 1.4236 | 74.1636 | 94.1273 | 2.2507 |
| 2025 | 43652.0705 | 5.6839 | 106.8000 | 110.2000 | 2.2879 |
| 2016 | 59249.6916 | 2.2254 | 93.6154 | 121.2885 | 2.4780 |
| 2018 | 145163.2174 | 4.8883 | 111.1207 | 118.2241 | 2.5709 |


## Read

- Candidate pool size is a real regime variable, but it is not a complete explanation of N7 PnL.
- Issue-level monotonic correlations are positive but modest; profit is still dominated by rare convex hits.
- Thin high-EV match pools should be treated as a sizing/selector warning, not as a hard no-bet rule.
- The practical use is likely dynamic N/depth: high candidate breadth can justify higher N or more diverse tickets; thin breadth should push toward lower-N/high-win sleeves or smaller core exposure.

## Files

- Issue join: `results/n7_candidate_pool_constraint_20260628/n7_candidate_pool_by_issue.csv`
- Annual: `results/n7_candidate_pool_constraint_20260628/n7_candidate_pool_annual.csv`
- Correlations: `results/n7_candidate_pool_constraint_20260628/n7_candidate_pool_correlations.csv`
- Buckets: `results/n7_candidate_pool_constraint_20260628/n7_candidate_pool_bins.csv`
