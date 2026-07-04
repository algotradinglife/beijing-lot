# High-N Capital Performance Comparison

## Scope

- Source strategy: `ev_m0p95_p0p8_full_opt__budget256_fractional`
- Issue stake: `256.0` units per active issue.
- Calendar-budget ROI treats every issue in the comparison calendar as if 256 units of capital were reserved, even when a narrow selector has no bet.
- Equity figure: `docs/research/figures/high_n_capital_performance_2026-06-28.svg`

## Overall

| label | calendar_issues | active_issues | deployment_rate | profit_units | roi_on_deployed | roi_on_calendar_budget | profit_per_year | issue_win_rate | max_drawdown_units | longest_underwater_issues | ex_best_roi_on_deployed | bankroll_for_25pct_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 70 core / 30 exact | 669 | 666 | 0.9955 | 243883.7883 | 1.4304 | 1.4240 | 20323.6490 | 0.0511 | -26071.0573 | 239 | 0.4914 | 104284.2294 |
| 80 core / 20 exact | 669 | 666 | 0.9955 | 237744.6066 | 1.3944 | 1.3882 | 19812.0506 | 0.0511 | -23891.0473 | 239 | 0.4553 | 95564.1890 |
| 90 core / 10 exact | 669 | 666 | 0.9955 | 231605.4249 | 1.3584 | 1.3523 | 19300.4521 | 0.0511 | -24679.9176 | 239 | 0.4193 | 98719.6705 |
| core neg0>=6 d0 | 669 | 666 | 0.9955 | 225466.2432 | 1.3224 | 1.3165 | 18788.8536 | 0.0511 | -25474.7932 | 239 | 0.3832 | 101899.1727 |
| exact 6n0+1p3 | 669 | 480 | 0.7175 | 127996.8846 | 1.0416 | 0.7474 | 10666.4071 | 0.0125 | -60562.3739 | 539 | -0.6181 | 242249.4957 |
| p0.8 all | 669 | 669 | 1.0000 | 111291.2322 | 0.6498 | 0.6498 | 9274.2693 | 0.0717 | -23640.2992 | 250 | 0.0977 | 94561.1969 |


## Recent 2023-2025

| label | calendar_issues | active_issues | profit_units | roi_on_deployed | issue_win_rate | window_max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- |
| exact 6n0+1p3 | 129 | 96 | 188559.2585 | 7.6725 | 0.0208 | -15235.7082 |
| 70 core / 30 exact | 129 | 129 | 92278.5972 | 2.7943 | 0.0465 | -23090.1666 |
| 80 core / 20 exact | 129 | 129 | 76997.8929 | 2.3316 | 0.0465 | -23885.0421 |
| 90 core / 10 exact | 129 | 129 | 61717.1887 | 1.8689 | 0.0465 | -24679.9176 |
| core neg0>=6 d0 | 129 | 129 | 46436.4844 | 1.4061 | 0.0465 | -25474.7932 |
| p0.8 all | 129 | 129 | 533.1251 | 0.0161 | 0.0465 | -23640.2992 |


## Annual Focus

| label | year | active_issues | profit_units | roi_on_deployed | issue_win_rate | window_max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- |
| 80 core / 20 exact | 2014 | 116 | 13815.7374 | 0.4652 | 0.0690 | -10754.3182 |
| 80 core / 20 exact | 2015 | 58 | 371.0246 | 0.0250 | 0.0517 | -6144.0000 |
| 80 core / 20 exact | 2016 | 53 | -8479.9982 | -0.6250 | 0.0377 | -10899.5278 |
| 80 core / 20 exact | 2017 | 47 | -7050.4891 | -0.5860 | 0.0426 | -7925.3391 |
| 80 core / 20 exact | 2018 | 54 | 182132.8503 | 13.1751 | 0.1111 | -3848.6359 |
| 80 core / 20 exact | 2019 | 55 | -7607.6562 | -0.5403 | 0.0364 | -10799.8800 |
| 80 core / 20 exact | 2020 | 41 | 3317.9349 | 0.3161 | 0.0488 | -4352.0000 |
| 80 core / 20 exact | 2021 | 57 | -2955.3311 | -0.2025 | 0.0351 | -11776.0000 |
| 80 core / 20 exact | 2022 | 56 | -12797.3589 | -0.8927 | 0.0179 | -12797.3589 |
| 80 core / 20 exact | 2023 | 55 | 70778.3522 | 5.0269 | 0.0364 | -13568.0000 |
| 80 core / 20 exact | 2024 | 59 | -10317.0421 | -0.6831 | 0.0339 | -12544.0000 |
| 80 core / 20 exact | 2025 | 15 | 16536.5828 | 4.3064 | 0.1333 | -2048.0000 |
| core neg0>=6 d0 | 2014 | 116 | 22745.2150 | 0.7659 | 0.0690 | -10376.2199 |
| core neg0>=6 d0 | 2015 | 58 | 4175.7808 | 0.2812 | 0.0517 | -6144.0000 |
| core neg0>=6 d0 | 2016 | 53 | -7207.9977 | -0.5312 | 0.0377 | -10552.4098 |
| core neg0>=6 d0 | 2017 | 47 | -8187.8696 | -0.6805 | 0.0426 | -8187.8696 |
| core neg0>=6 d0 | 2018 | 54 | 183187.0214 | 13.2514 | 0.1111 | -3848.6359 |
| core neg0>=6 d0 | 2019 | 55 | -7107.6262 | -0.5048 | 0.0364 | -10299.8501 |
| core neg0>=6 d0 | 2020 | 41 | 3884.0975 | 0.3701 | 0.0488 | -4352.0000 |
| core neg0>=6 d0 | 2021 | 57 | -46.1639 | -0.0032 | 0.0351 | -11776.0000 |
| core neg0>=6 d0 | 2022 | 56 | -12412.6986 | -0.8658 | 0.0179 | -12412.6986 |
| core neg0>=6 d0 | 2023 | 55 | 40980.1986 | 2.9105 | 0.0364 | -13568.0000 |
| core neg0>=6 d0 | 2024 | 59 | -11906.7932 | -0.7883 | 0.0339 | -12544.0000 |
| core neg0>=6 d0 | 2025 | 15 | 17363.0790 | 4.5216 | 0.1333 | -2048.0000 |
| p0.8 all | 2014 | 116 | 6508.0885 | 0.2192 | 0.1034 | -9889.1815 |
| p0.8 all | 2015 | 58 | 1959.5948 | 0.1320 | 0.0690 | -6144.0000 |
| p0.8 all | 2016 | 53 | 7022.0578 | 0.5175 | 0.0566 | -10391.8663 |
| p0.8 all | 2017 | 47 | -6080.1968 | -0.5053 | 0.1064 | -6080.1968 |
| p0.8 all | 2018 | 54 | 108474.1695 | 7.8468 | 0.1111 | -5628.7200 |
| p0.8 all | 2019 | 55 | -7277.2547 | -0.5169 | 0.0545 | -10542.4786 |
| p0.8 all | 2020 | 42 | 279.0423 | 0.0260 | 0.0714 | -5495.9586 |
| p0.8 all | 2021 | 58 | 10969.4848 | 0.7388 | 0.0690 | -7168.0000 |
| p0.8 all | 2022 | 57 | -11096.8792 | -0.7605 | 0.0351 | -12392.0270 |
| p0.8 all | 2023 | 55 | 4457.7610 | 0.3166 | 0.0364 | -13568.0000 |
| p0.8 all | 2024 | 59 | -10072.2992 | -0.6669 | 0.0339 | -12544.0000 |
| p0.8 all | 2025 | 15 | 6147.6633 | 1.6010 | 0.1333 | -2048.0000 |


## Read

- The pure exact topology has the highest recent convexity, but its full-history capital curve is too jagged for a main allocation.
- The broad `core neg0>=6 d0` arm is the more reliable high-N core.
- The 80/20 core/exact portfolio improves recent upside while keeping drawdown close to the broad core.
- `all` has the smoothest deployment and higher issue win rate, but materially weaker profit density in 2023-2025.

## Files

- `results/high_n_capital_performance_20260628/high_n_capital_summary.csv`
- `results/high_n_capital_performance_20260628/high_n_capital_recent_2023_2025.csv`
- `results/high_n_capital_performance_20260628/high_n_capital_annual.csv`
- `results/high_n_capital_performance_20260628/high_n_capital_equity_curve.csv`
- `docs/research/figures/high_n_capital_performance_2026-06-28.svg`
