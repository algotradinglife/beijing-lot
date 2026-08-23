# Issue #355 — low-N fixed-Top2 match selection

## Decision

- Selected family from 2019–2021 expanding OOF calibration: **S2_LOGISTIC**.
- Verdict: **NO_PROMOTION**.
- Outcome support stays q_eu Top-2/R0; only match selection changes.
- 2022/2023/2024 are exposed transfer evidence, not a holdout.

## OOF model comparison

| family | rows | issues | issue_weighted_log_loss | issue_weighted_brier | mean_prediction | actual_rate |
| --- | --- | --- | --- | --- | --- | --- |
| S2_LOGISTIC | 47788 | 157 | 0.569284 | 0.190784 | 0.745245 | 0.742159 |
| S3_HGB | 47788 | 157 | 0.569543 | 0.190881 | 0.743389 | 0.742159 |
| S1_CALIBRATED_MASS | 47788 | 157 | 0.569559 | 0.190824 | 0.74441 | 0.742159 |
| S0_RAW_MASS | 47788 | 157 | 0.569599 | 0.190797 | 0.739771 | 0.742159 |

## Development selection evidence

| arm | n | period | issues | match_top2_hit_rate | issue_hit_rate | mean_predicted_joint_hit |
| --- | --- | --- | --- | --- | --- | --- |
| S0_RAW_MASS | 3 | 2019 | 53 | 0.842767 | 0.660377 | 0.644662 |
| S0_RAW_MASS | 3 | 2020 | 30 | 0.722222 | 0.333333 | 0.574406 |
| S0_RAW_MASS | 3 | 2021 | 48 | 0.770833 | 0.520833 | 0.569368 |
| S0_RAW_MASS | 4 | 2019 | 53 | 0.830189 | 0.509434 | 0.536961 |
| S0_RAW_MASS | 4 | 2020 | 29 | 0.732759 | 0.241379 | 0.46 |
| S0_RAW_MASS | 4 | 2021 | 46 | 0.76087 | 0.413043 | 0.454774 |
| S0_RAW_MASS | 5 | 2019 | 53 | 0.815094 | 0.433962 | 0.443201 |
| S0_RAW_MASS | 5 | 2020 | 28 | 0.728571 | 0.25 | 0.370686 |
| S0_RAW_MASS | 5 | 2021 | 44 | 0.768182 | 0.340909 | 0.365379 |
| SELECTED_MODEL | 3 | 2019 | 52 | 0.839744 | 0.596154 | 0.598543 |
| SELECTED_MODEL | 3 | 2020 | 37 | 0.792793 | 0.540541 | 0.552721 |
| SELECTED_MODEL | 3 | 2021 | 49 | 0.809524 | 0.55102 | 0.552544 |
| SELECTED_MODEL | 4 | 2019 | 52 | 0.802885 | 0.403846 | 0.494158 |
| SELECTED_MODEL | 4 | 2020 | 34 | 0.794118 | 0.5 | 0.443108 |
| SELECTED_MODEL | 4 | 2021 | 49 | 0.780612 | 0.408163 | 0.447261 |
| SELECTED_MODEL | 5 | 2019 | 52 | 0.807692 | 0.365385 | 0.405808 |
| SELECTED_MODEL | 5 | 2020 | 33 | 0.781818 | 0.393939 | 0.355574 |
| SELECTED_MODEL | 5 | 2021 | 49 | 0.795918 | 0.367347 | 0.360659 |

## Matched Top-2 issue-hit evidence

| n | period | common_issues | s0_issue_hit_rate | candidate_issue_hit_rate | paired_issue_hit_rate_lift |
| --- | --- | --- | --- | --- | --- |
| 3 | 2022 | 52 | 0.576923 | 0.557692 | -0.0192308 |
| 3 | 2023 | 47 | 0.553191 | 0.617021 | 0.0638298 |
| 3 | 2024 | 54 | 0.666667 | 0.685185 | 0.0185185 |
| 3 | ALL_2019_2021 | 128 | 0.53125 | 0.5625 | 0.03125 |
| 3 | ALL_2022_2024 | 153 | 0.601307 | 0.620915 | 0.0196078 |
| 4 | 2022 | 51 | 0.470588 | 0.45098 | -0.0196078 |
| 4 | 2023 | 46 | 0.413043 | 0.478261 | 0.0652174 |
| 4 | 2024 | 54 | 0.574074 | 0.574074 | 0 |
| 4 | ALL_2019_2021 | 124 | 0.41129 | 0.419355 | 0.00806452 |
| 4 | ALL_2022_2024 | 151 | 0.490066 | 0.503311 | 0.013245 |
| 5 | 2022 | 50 | 0.4 | 0.32 | -0.08 |
| 5 | 2023 | 46 | 0.304348 | 0.326087 | 0.0217391 |
| 5 | 2024 | 54 | 0.462963 | 0.444444 | -0.0185185 |
| 5 | ALL_2019_2021 | 121 | 0.363636 | 0.363636 | 0 |
| 5 | ALL_2022_2024 | 150 | 0.393333 | 0.366667 | -0.0266667 |

## Transfer capital performance

| arm | n | period | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_rate | largest_payout_share | payout_hhi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0_RAW_MASS | 3 | 2022 | 52 | 53248 | 43391.6 | -9856.38 | 90143.6 | -0.0985638 | -0.185103 | 0.576923 | 0.105738 | 0.0498484 |
| S0_RAW_MASS | 3 | 2023 | 48 | 49152 | 41018.3 | -8133.71 | 91866.3 | -0.0813371 | -0.165481 | 0.5625 | 0.162297 | 0.0606331 |
| S0_RAW_MASS | 3 | 2024 | 54 | 55296 | 53964 | -1331.95 | 98668 | -0.0133195 | -0.0240877 | 0.666667 | 0.140393 | 0.046796 |
| S0_RAW_MASS | 3 | ALL_2022_2024 | 154 | 157696 | 138374 | -19322 | 80678 | -0.19322 | -0.122527 | 0.603896 | 0.0547514 | 0.0173469 |
| S0_RAW_MASS | 4 | 2022 | 51 | 52224 | 44927.6 | -7296.4 | 92703.6 | -0.072964 | -0.139713 | 0.470588 | 0.115544 | 0.0623011 |
| S0_RAW_MASS | 4 | 2023 | 48 | 49152 | 35656.2 | -13495.8 | 86504.2 | -0.134958 | -0.274572 | 0.4375 | 0.132959 | 0.0647747 |
| S0_RAW_MASS | 4 | 2024 | 54 | 55296 | 61338.7 | 6042.68 | 106043 | 0.0604268 | 0.109279 | 0.574074 | 0.11387 | 0.0506841 |
| S0_RAW_MASS | 4 | ALL_2022_2024 | 153 | 156672 | 141923 | -14749.5 | 85250.5 | -0.147495 | -0.0941425 | 0.496732 | 0.0492144 | 0.0197995 |
| S0_RAW_MASS | 5 | 2022 | 51 | 52224 | 55103.4 | 2879.4 | 102879 | 0.028794 | 0.0551356 | 0.392157 | 0.171131 | 0.0867701 |
| S0_RAW_MASS | 5 | 2023 | 48 | 49152 | 30277.8 | -18874.2 | 81125.8 | -0.188742 | -0.383997 | 0.333333 | 0.23908 | 0.105691 |
| S0_RAW_MASS | 5 | 2024 | 54 | 55296 | 56876.2 | 1580.22 | 101580 | 0.0158022 | 0.0285774 | 0.462963 | 0.109614 | 0.0585297 |
| S0_RAW_MASS | 5 | ALL_2022_2024 | 153 | 156672 | 142257 | -14414.6 | 85585.4 | -0.144146 | -0.092005 | 0.398693 | 0.0662877 | 0.0271627 |
| SELECTED_MODEL | 3 | 2022 | 53 | 54272 | 45675.6 | -8596.38 | 91403.6 | -0.0859638 | -0.158394 | 0.566038 | 0.100451 | 0.0475618 |
| SELECTED_MODEL | 3 | 2023 | 50 | 51200 | 38302.5 | -12897.5 | 87102.5 | -0.128975 | -0.251903 | 0.6 | 0.0711294 | 0.0422078 |
| SELECTED_MODEL | 3 | 2024 | 58 | 59392 | 57195.6 | -2196.37 | 97803.6 | -0.0219637 | -0.036981 | 0.689655 | 0.0627415 | 0.0307391 |
| SELECTED_MODEL | 3 | ALL_2022_2024 | 161 | 164864 | 141174 | -23690.2 | 76309.8 | -0.236902 | -0.143695 | 0.621118 | 0.0325001 | 0.0131313 |
| SELECTED_MODEL | 4 | 2022 | 53 | 54272 | 51217.7 | -3054.27 | 96945.7 | -0.0305427 | -0.056277 | 0.471698 | 0.108602 | 0.0622927 |
| SELECTED_MODEL | 4 | 2023 | 48 | 49152 | 39187.9 | -9964.08 | 90035.9 | -0.0996408 | -0.20272 | 0.479167 | 0.123836 | 0.0662452 |
| SELECTED_MODEL | 4 | 2024 | 56 | 57344 | 54774.2 | -2569.79 | 97430.2 | -0.0256979 | -0.0448137 | 0.571429 | 0.115366 | 0.0462888 |
| SELECTED_MODEL | 4 | ALL_2022_2024 | 157 | 160768 | 145180 | -15588.1 | 84411.9 | -0.155881 | -0.0969605 | 0.509554 | 0.0435259 | 0.0191685 |
| SELECTED_MODEL | 5 | 2022 | 52 | 53248 | 47378.9 | -5869.12 | 94130.9 | -0.0586912 | -0.110222 | 0.326923 | 0.173317 | 0.100215 |
| SELECTED_MODEL | 5 | 2023 | 48 | 49152 | 34089.2 | -15062.8 | 84937.2 | -0.150628 | -0.306453 | 0.333333 | 0.194541 | 0.100073 |
| SELECTED_MODEL | 5 | 2024 | 56 | 57344 | 53517.6 | -3826.38 | 96173.6 | -0.0382638 | -0.0667268 | 0.428571 | 0.22404 | 0.0829967 |
| SELECTED_MODEL | 5 | ALL_2022_2024 | 156 | 159744 | 134986 | -24758.3 | 75241.7 | -0.247583 | -0.154987 | 0.365385 | 0.0888249 | 0.0317743 |

## Matched lift versus N-specific S0

| n | period | common_issues | s0_pnl_cny | candidate_pnl_cny | s0_stake_roi | candidate_stake_roi | pnl_lift_cny | mean_pnl_lift_cny | hit_rate_lift | armwise_ex_largest_pnl_lift_cny | ex_largest_abs_delta_pnl_lift_cny | largest_abs_paired_delta_cny | s0_max_drawdown_fraction | candidate_max_drawdown_fraction | s0_longest_losing_run | candidate_longest_losing_run | s0_recovery_issues | candidate_recovery_issues | bootstrap_mean_lift_p05_cny | bootstrap_mean_lift_p50_cny | bootstrap_mean_lift_p95_cny |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 2022 | 52 | -9856.38 | -8531.89 | -0.185103 | -0.160229 | 1324.48 | 25.4708 | -0.0192308 | 1324.48 | -1653.98 | 2978.46 | 0.110142 | 0.11402 | 5 | 12 | 41 | 47 | -141.934 | 19.3693 | 205.731 |
| 3 | 2023 | 47 | -8767.22 | -10375.4 | -0.182165 | -0.215578 | -1608.14 | -34.2157 | 0.0638298 | 2324.55 | 2474.08 | 4082.22 | 0.123439 | 0.118665 | 17 | 12 | 45 | 46 | -244.632 | -31.6609 | 156.798 |
| 3 | 2024 | 54 | -1331.95 | -1500.2 | -0.0240877 | -0.0271303 | -168.245 | -3.11564 | 0.0185185 | 3819.38 | 6392.79 | 6561.04 | 0.100543 | 0.105308 | 8 | 8 | 51 | 49 | -313.983 | 8.56098 | 273.305 |
| 3 | ALL_2022_2024 | 153 | -19955.6 | -20407.4 | -0.127372 | -0.130256 | -451.9 | -2.95359 | 0.0196078 | 2536.1 | 6109.14 | 6561.04 | 0.289494 | 0.295292 | 17 | 12 | 142 | 148 | -142.277 | -2.86368 | 128.504 |
| 4 | 2022 | 51 | -7296.4 | -3326.86 | -0.139713 | -0.0637036 | 3969.54 | 77.8342 | -0.0196078 | 3598.34 | -1592.79 | 5562.33 | 0.0801488 | 0.107715 | 5 | 13 | 40 | 41 | -219.111 | 77.6223 | 400.908 |
| 4 | 2023 | 46 | -14346.1 | -8324.57 | -0.304562 | -0.176728 | 6021.5 | 130.902 | 0.0652174 | 5909.43 | 1673.75 | 4347.75 | 0.195009 | 0.138946 | 8 | 7 | 45 | 44 | -101.749 | 120.456 | 393.061 |
| 4 | 2024 | 54 | 6042.68 | -1639.98 | 0.109279 | -0.0296582 | -7682.66 | -142.271 | 0 | -7017.1 | -698.019 | 6984.64 | 0.0928098 | 0.122683 | 5 | 8 | 32 | 49 | -500.012 | -137.553 | 198.322 |
| 4 | ALL_2022_2024 | 151 | -15599.8 | -13291.4 | -0.100889 | -0.0859596 | 2308.38 | 15.2873 | 0.013245 | 2973.94 | 9293.02 | 6984.64 | 0.273499 | 0.276875 | 8 | 13 | 140 | 141 | -164.79 | 14.5346 | 194.78 |
| 5 | 2022 | 50 | 3903.4 | -4481.86 | 0.0762383 | -0.0875364 | -8385.26 | -167.705 | -0.08 | -7166.89 | -1837.42 | 6547.85 | 0.0814664 | 0.137206 | 7 | 16 | 22 | 46 | -617.99 | -170.782 | 288.248 |
| 5 | 2023 | 46 | -19710.4 | -13880.3 | -0.418444 | -0.294674 | 5830.04 | 126.74 | 0.0217391 | 6437.11 | 998.793 | 4831.24 | 0.249333 | 0.165754 | 7 | 14 | 45 | 44 | -207.381 | 124.069 | 473.436 |
| 5 | 2024 | 54 | 1580.22 | -1778.38 | 0.0285774 | -0.0321611 | -3358.6 | -62.1963 | -0.0185185 | -9114.28 | -15348.7 | 11990.1 | 0.0775369 | 0.148071 | 6 | 6 | 32 | 49 | -577.554 | -75.9195 | 511.262 |
| 5 | ALL_2022_2024 | 150 | -14226.8 | -20140.6 | -0.0926221 | -0.131124 | -5913.83 | -39.4255 | -0.0266667 | -8474 | -17903.9 | 11990.1 | 0.263556 | 0.357925 | 7 | 16 | 122 | 146 | -299.882 | -45.2493 | 225.781 |

## All-transfer holding risk

| arm | n | period | max_drawdown_cny | max_drawdown_fraction | longest_losing_run | recovery_issues |
| --- | --- | --- | --- | --- | --- | --- |
| S0_RAW_MASS | 3 | ALL_2022_2024 | 28692.5 | 0.28324 | 15 | 143 |
| S0_RAW_MASS | 4 | ALL_2022_2024 | 26627.9 | 0.265036 | 8 | 142 |
| S0_RAW_MASS | 5 | ALL_2022_2024 | 29214.5 | 0.265262 | 8 | 125 |
| SELECTED_MODEL | 3 | ALL_2022_2024 | 33407.6 | 0.326978 | 13 | 155 |
| SELECTED_MODEL | 4 | ALL_2022_2024 | 31785.9 | 0.297026 | 13 | 146 |
| SELECTED_MODEL | 5 | ALL_2022_2024 | 41993.5 | 0.399326 | 16 | 151 |

## Selection change

Mean overlap fraction by N:

| n | overlap_fraction |
| --- | --- |
| 3 | 0.568389 |
| 4 | 0.588906 |
| 5 | 0.620669 |

## Interpretation

Calibration is the model-selection criterion; capital is downstream evidence.
S2_LOGISTIC changes development log-loss by -0.000315 and
Brier by -0.000013 versus raw Top-2 mass.  Both improvements
are numerically tiny, so the learned coverage model is not a strong calibration
advance even though it wins the frozen lexicographic selection rule.

The chronology-corrected N4 result is only a weak clue, not the former apparent
near-break-even result. On 151 matched 2022–2024
issues, the candidate lift is CNY+2,308.38; annual lifts
are 2022: CNY+3,969.54, 2023: CNY+6,021.50, 2024: CNY-7,682.66.  Armwise ex-largest lift is
CNY+2,973.94, but the issue-bootstrap
mean-lift p05 remains CNY-164.79.  Full
path maximum drawdown/longest losing run worsen from
27.35%/
8 to
27.69%/
13 on the exact common issue path.
N3 and N5 have
negative all-transfer matched lift.

This is not evidence that coverage-only selection is useless. It says the
coverage target alone is insufficient for promotion.  The small, unstable N4
payoff clue still motivates a separately preregistered
coverage × expected-return experiment. That experiment is #358 → #359 and
must call European prices `EUROPEAN_AVERAGE_ODDS_PROXY`, not official Beijing
SP. Every comparison here uses the same issue and fixed CNY1,024 stake
semantics, with 0.65 applied once at winning N-fold settlement. The result does
not unlock #210 or alter #218.  It uses fixture-relative 10h snapshots as a
historical proxy and does not claim simultaneous issue-time deployability.

## Artifacts

- Package: `results/low_n_match_selector/`
- Notebook: `notebooks/research/low-n-match-selector/low_n_match_selector.ipynb`
- Figures: `docs/research/figures/issue_355_selector_models.png`, `docs/research/figures/issue_355_low_n_capital.png`
