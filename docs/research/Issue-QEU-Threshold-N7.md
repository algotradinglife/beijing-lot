# Issue #338 — causal QEU threshold activation on fixed N7

## Five-minute conclusion

- Verdict: **FIXED_R3_REMAINS_BEST**.
- N remained fixed at **7**. Every arm used the exact #319 matches, 128 distinct tickets, 512 CNY2 units and CNY1,024 per issue.
- 2023 selected `RAW_Q80`. Its lift vs R0 is CNY -12899.40; 2024 transfer lift is CNY -24916.29.
- Relative to fixed R3, the selected threshold changes 2023 capital by CNY -74243.62 and 2024 by CNY -91728.47.
- 2023 ex-largest retention is N/A (raw lift <= 0); 2024 is N/A (raw lift <= 0). Promotion to #210 is `False`.
- `0.65` is applied once to a complete winning N7 ticket, never per leg or cell.
- 2024 is historical transfer evidence, not a fresh sealed holdout.

## What was tested

The QEU action replaces probability Top-2 support with the two outcomes having the largest `log(q_eu/q_line)`. `support_pressure` measures the QEU-score gain of the newly included outcome over the displaced one. The experiment compares the incumbent R0, fixed top-three R3, six raw cutoffs, five robust-z cutoffs and three predeclared dual cutoffs.

Raw cutoffs were frozen from 2020–2022: `{"Q50": 0.13072608078841338, "Q60": 0.15568754219540268, "Q70": 0.18769768930359537, "Q75": 0.2044369529815513, "Q80": 0.22306941036379507, "Q85": 0.245111822114056, "Q90": 0.2697853182317174, "Q95": 0.3075980331873884}`. Robust z uses the same strictly prior panel with `(lost outcome, gained outcome)` strata and a global fallback.

## Key matched performance

| arm | kind | issue_year | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_issues | hit_rate | miss_by_1_issues | miss_by_2_issues | matched_lift_r0_cny | matched_lift_r3_cny | ex_largest_lift_r0_cny | ex_largest_lift_r3_cny | largest_payout_share | mean_activated_changes | mean_baseline_overlap_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 | control | 2023.0000 | 47.0000 | 48128.0000 | 34598.3748 | -13529.6252 | 86470.3748 | -0.1353 | -0.2811 | 11.0000 | 0.2340 | 17.0000 | 15.0000 | 0.0000 | -61344.2211 | 0.0000 | -405.8390 | 0.2618 | 0.0000 | 1.0000 |
| R0 | control | 2024.0000 | 58.0000 | 59392.0000 | 73661.1876 | 14269.1876 | 114269.1876 | 0.1427 | 0.2403 | 20.0000 | 0.3448 | 18.0000 | 16.0000 | 0.0000 | -66812.1862 | 0.0000 | -29497.6606 | 0.1607 | 0.0000 | 1.0000 |
| R3_CORRECTED | fixed_rank | 2023.0000 | 47.0000 | 48128.0000 | 95942.5959 | 47814.5959 | 147814.5959 | 0.4781 | 0.9935 | 9.0000 | 0.1915 | 16.0000 | 12.0000 | 61344.2211 | 0.0000 | 405.8390 | 0.0000 | 0.6352 | 1.9574 | 0.3351 |
| R3_CORRECTED | fixed_rank | 2024.0000 | 58.0000 | 59392.0000 | 140473.3738 | 81081.3738 | 181081.3738 | 0.8108 | 1.3652 | 14.0000 | 0.2414 | 19.0000 | 18.0000 | 66812.1862 | 0.0000 | 29497.6606 | 0.0000 | 0.2656 | 2.3966 | 0.2306 |
| RAW_Q80 | raw | 2023.0000 | 47.0000 | 48128.0000 | 21698.9720 | -26429.0280 | 73570.9720 | -0.2643 | -0.5491 | 8.0000 | 0.1702 | 21.0000 | 11.0000 | -12899.4028 | -74243.6239 | -3841.2030 | -13305.2418 | 0.3005 | 0.8511 | 0.6489 |
| RAW_Q80 | raw | 2024.0000 | 58.0000 | 59392.0000 | 48744.9021 | -10647.0979 | 89352.9021 | -0.1065 | -0.1793 | 15.0000 | 0.2586 | 24.0000 | 17.0000 | -24916.2855 | -91728.4717 | -13076.0850 | -54413.9462 | 0.1761 | 1.0862 | 0.6051 |

## Complete threshold atlas

| arm | kind | issue_year | pnl_cny | capital_return | hit_rate | matched_lift_r0_cny | matched_lift_r3_cny | ex_largest_lift_r0_cny | mean_activated_changes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DUAL_Q75_Z1P0 | dual | 2023.0000 | -27905.4321 | -0.2791 | 0.1489 | -14375.8068 | -75720.0279 | -5317.6070 | 0.8936 |
| DUAL_Q75_Z1P0 | dual | 2024.0000 | -10647.0979 | -0.1065 | 0.2586 | -24916.2855 | -91728.4717 | -13076.0850 | 1.0690 |
| DUAL_Q75_Z1P5 | dual | 2023.0000 | -17370.8282 | -0.1737 | 0.1915 | -3841.2030 | -65185.4241 | -10361.2055 | 0.6383 |
| DUAL_Q75_Z1P5 | dual | 2024.0000 | 18403.2412 | 0.1840 | 0.3103 | 4134.0536 | -62678.1326 | -14348.2634 | 0.7759 |
| DUAL_Q85_Z1P0 | dual | 2023.0000 | -26429.0280 | -0.2643 | 0.1702 | -12899.4028 | -74243.6239 | -3841.2030 | 0.7660 |
| DUAL_Q85_Z1P0 | dual | 2024.0000 | -8521.4098 | -0.0852 | 0.2759 | -22790.5974 | -89602.7836 | -10950.3969 | 0.9655 |
| R0 | control | 2023.0000 | -13529.6252 | -0.1353 | 0.2340 | 0.0000 | -61344.2211 | 0.0000 | 0.0000 |
| R0 | control | 2024.0000 | 14269.1876 | 0.1427 | 0.3448 | 0.0000 | -66812.1862 | 0.0000 | 0.0000 |
| R3_CORRECTED | fixed_rank | 2023.0000 | 47814.5959 | 0.4781 | 0.1915 | 61344.2211 | 0.0000 | 405.8390 | 1.9574 |
| R3_CORRECTED | fixed_rank | 2024.0000 | 81081.3738 | 0.8108 | 0.2414 | 66812.1862 | 0.0000 | 29497.6606 | 2.3966 |
| RAW_Q50 | raw | 2023.0000 | -20007.6036 | -0.2001 | 0.1489 | -6477.9784 | -67822.1995 | -15623.2744 | 1.4468 |
| RAW_Q50 | raw | 2024.0000 | -4420.2413 | -0.0442 | 0.2414 | -18689.4290 | -85501.6152 | -30908.6134 | 1.7586 |
| RAW_Q60 | raw | 2023.0000 | -20007.6036 | -0.2001 | 0.1489 | -6477.9784 | -67822.1995 | -15623.2744 | 1.3191 |
| RAW_Q60 | raw | 2024.0000 | -16639.4258 | -0.1664 | 0.2241 | -30908.6134 | -97720.7996 | -19068.4128 | 1.5172 |
| RAW_Q70 | raw | 2023.0000 | -18760.1361 | -0.1876 | 0.1702 | -5230.5108 | -66574.7319 | -14375.8068 | 1.0638 |
| RAW_Q70 | raw | 2024.0000 | -10647.0979 | -0.1065 | 0.2586 | -24916.2855 | -91728.4717 | -13076.0850 | 1.2759 |
| RAW_Q80 | raw | 2023.0000 | -26429.0280 | -0.2643 | 0.1702 | -12899.4028 | -74243.6239 | -3841.2030 | 0.8511 |
| RAW_Q80 | raw | 2024.0000 | -10647.0979 | -0.1065 | 0.2586 | -24916.2855 | -91728.4717 | -13076.0850 | 1.0862 |
| RAW_Q90 | raw | 2023.0000 | -26429.0280 | -0.2643 | 0.1702 | -12899.4028 | -74243.6239 | -3841.2030 | 0.7021 |
| RAW_Q90 | raw | 2024.0000 | 27856.5058 | 0.2786 | 0.3448 | 13587.3182 | -53224.8680 | -4894.9988 | 0.7586 |
| RAW_Q95 | raw | 2023.0000 | -14767.6963 | -0.1477 | 0.2128 | -1238.0711 | -62582.2922 | -7758.0737 | 0.5745 |
| RAW_Q95 | raw | 2024.0000 | 8697.0676 | 0.0870 | 0.3276 | -5572.1200 | -72384.3062 | 6268.0806 | 0.5172 |
| Z_GE_0P0 | z | 2023.0000 | -20007.6036 | -0.2001 | 0.1489 | -6477.9784 | -67822.1995 | -15623.2744 | 1.3830 |
| Z_GE_0P0 | z | 2024.0000 | -4420.2413 | -0.0442 | 0.2414 | -18689.4290 | -85501.6152 | -30908.6134 | 1.7586 |
| Z_GE_0P5 | z | 2023.0000 | -18760.1361 | -0.1876 | 0.1702 | -5230.5108 | -66574.7319 | -14375.8068 | 1.1064 |
| Z_GE_0P5 | z | 2024.0000 | -13561.4183 | -0.1356 | 0.2414 | -27830.6059 | -94642.7921 | -15990.4053 | 1.3276 |
| Z_GE_1P0 | z | 2023.0000 | -27905.4321 | -0.2791 | 0.1489 | -14375.8068 | -75720.0279 | -5317.6070 | 0.8936 |
| Z_GE_1P0 | z | 2024.0000 | -10647.0979 | -0.1065 | 0.2586 | -24916.2855 | -91728.4717 | -13076.0850 | 1.0690 |
| Z_GE_1P5 | z | 2023.0000 | -17370.8282 | -0.1737 | 0.1915 | -3841.2030 | -65185.4241 | -10361.2055 | 0.6383 |
| Z_GE_1P5 | z | 2024.0000 | 18403.2412 | 0.1840 | 0.3103 | 4134.0536 | -62678.1326 | -14348.2634 | 0.7759 |
| Z_GE_2P0 | z | 2023.0000 | -17370.8282 | -0.1737 | 0.1915 | -3841.2030 | -65185.4241 | -10361.2055 | 0.5532 |
| Z_GE_2P0 | z | 2024.0000 | 8697.0676 | 0.0870 | 0.3276 | -5572.1200 | -72384.3062 | 6268.0806 | 0.4483 |

## Key path risk

| arm | issue_year | max_drawdown_fraction | max_consecutive_losing_issues | worst_rolling_5_cny | worst_rolling_10_cny | worst_rolling_20_cny | max_completed_recovery_issues | terminal_underwater_issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 | 2023.0000 | 0.2596 | 12.0000 | -5120.0000 | -10240.0000 | -17626.0748 | 0.0000 | 43.0000 |
| R0 | 2024.0000 | 0.1164 | 7.0000 | -5120.0000 | -8853.6068 | -13180.1757 | 16.0000 | 29.0000 |
| R3_CORRECTED | 2023.0000 | 0.1312 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 4.0000 | 41.0000 |
| R3_CORRECTED | 2024.0000 | 0.1980 | 10.0000 | -5120.0000 | -10240.0000 | -11491.9683 | 38.0000 | 1.0000 |
| RAW_Q80 | 2023.0000 | 0.3264 | 26.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 0.0000 | 44.0000 |
| RAW_Q80 | 2024.0000 | 0.1843 | 8.0000 | -5120.0000 | -9201.2605 | -14008.0533 | 0.0000 | 58.0000 |

## Key bootstrap evidence

| arm | issue_year | draws | r0_p05_cny | r0_p50_cny | r0_p95_cny | r0_positive_fraction | r3_p05_cny | r3_p50_cny | r3_p95_cny | r3_positive_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R3_CORRECTED | 2023.0000 | 2000.0000 | -20111.1674 | 55088.6586 | 183170.2117 | 0.8225 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| R3_CORRECTED | 2024.0000 | 2000.0000 | -21064.6380 | 64477.5799 | 173317.9698 | 0.8890 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| RAW_Q80 | 2023.0000 | 2000.0000 | -35155.0523 | -12393.3367 | 7166.6711 | 0.1565 | -193914.1808 | -68836.2106 | -2912.4782 | 0.0365 |
| RAW_Q80 | 2024.0000 | 2000.0000 | -57989.0971 | -24201.2226 | 5569.7783 | 0.0885 | -196457.7236 | -87224.7348 | -9230.4449 | 0.0270 |

## 2023 threshold selection table

| arm | kind | issue_year | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_issues | hit_rate | miss_by_1_issues | miss_by_2_issues | matched_lift_r0_cny | matched_lift_r3_cny | ex_largest_lift_r0_cny | ex_largest_lift_r3_cny | largest_payout_share | mean_activated_changes | mean_baseline_overlap_fraction | max_drawdown_fraction | r0_positive_fraction | positive_ex_largest | selected_on_2023 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RAW_Q80 | raw | 2023.0000 | 47.0000 | 48128.0000 | 21698.9720 | -26429.0280 | 73570.9720 | -0.2643 | -0.5491 | 8.0000 | 0.1702 | 21.0000 | 11.0000 | -12899.4028 | -74243.6239 | -3841.2030 | -13305.2418 | 0.3005 | 0.8511 | 0.6489 | 0.3264 | 0.1565 | False | True |
| DUAL_Q85_Z1P0 | dual | 2023.0000 | 47.0000 | 48128.0000 | 21698.9720 | -26429.0280 | 73570.9720 | -0.2643 | -0.5491 | 8.0000 | 0.1702 | 21.0000 | 11.0000 | -12899.4028 | -74243.6239 | -3841.2030 | -13305.2418 | 0.3005 | 0.7660 | 0.6702 | 0.3264 | 0.1415 | False | False |
| RAW_Q90 | raw | 2023.0000 | 47.0000 | 48128.0000 | 21698.9720 | -26429.0280 | 73570.9720 | -0.2643 | -0.5491 | 8.0000 | 0.1702 | 21.0000 | 10.0000 | -12899.4028 | -74243.6239 | -3841.2030 | -13305.2418 | 0.3005 | 0.7021 | 0.6915 | 0.3264 | 0.1300 | False | False |
| Z_GE_1P0 | z | 2023.0000 | 47.0000 | 48128.0000 | 20222.5679 | -27905.4321 | 72094.5679 | -0.2791 | -0.5798 | 7.0000 | 0.1489 | 23.0000 | 9.0000 | -14375.8068 | -75720.0279 | -5317.6070 | -14781.6458 | 0.3224 | 0.8936 | 0.6476 | 0.3363 | 0.1235 | False | False |
| DUAL_Q75_Z1P0 | dual | 2023.0000 | 47.0000 | 48128.0000 | 20222.5679 | -27905.4321 | 72094.5679 | -0.2791 | -0.5798 | 7.0000 | 0.1489 | 23.0000 | 9.0000 | -14375.8068 | -75720.0279 | -5317.6070 | -14781.6458 | 0.3224 | 0.8936 | 0.6476 | 0.3363 | 0.1150 | False | False |
| RAW_Q95 | raw | 2023.0000 | 47.0000 | 48128.0000 | 33360.3037 | -14767.6963 | 85232.3037 | -0.1477 | -0.3068 | 10.0000 | 0.2128 | 19.0000 | 13.0000 | -1238.0711 | -62582.2922 | -7758.0737 | -1643.9101 | 0.2715 | 0.5745 | 0.7500 | 0.2707 | 0.3790 | False | False |
| Z_GE_2P0 | z | 2023.0000 | 47.0000 | 48128.0000 | 30757.1718 | -17370.8282 | 82629.1718 | -0.1737 | -0.3609 | 9.0000 | 0.1915 | 20.0000 | 13.0000 | -3841.2030 | -65185.4241 | -10361.2055 | -4247.0420 | 0.2945 | 0.5532 | 0.7606 | 0.2939 | 0.3155 | False | False |
| DUAL_Q75_Z1P5 | dual | 2023.0000 | 47.0000 | 48128.0000 | 30757.1718 | -17370.8282 | 82629.1718 | -0.1737 | -0.3609 | 9.0000 | 0.1915 | 20.0000 | 11.0000 | -3841.2030 | -65185.4241 | -10361.2055 | -4247.0420 | 0.2945 | 0.6383 | 0.7181 | 0.2939 | 0.3135 | False | False |
| Z_GE_1P5 | z | 2023.0000 | 47.0000 | 48128.0000 | 30757.1718 | -17370.8282 | 82629.1718 | -0.1737 | -0.3609 | 9.0000 | 0.1915 | 20.0000 | 11.0000 | -3841.2030 | -65185.4241 | -10361.2055 | -4247.0420 | 0.2945 | 0.6383 | 0.7181 | 0.2939 | 0.3060 | False | False |
| RAW_Q70 | raw | 2023.0000 | 47.0000 | 48128.0000 | 29367.8639 | -18760.1361 | 81239.8639 | -0.1876 | -0.3898 | 8.0000 | 0.1702 | 20.0000 | 13.0000 | -5230.5108 | -66574.7319 | -14375.8068 | -5636.3498 | 0.3114 | 1.0638 | 0.6144 | 0.2612 | 0.3655 | False | False |
| Z_GE_0P5 | z | 2023.0000 | 47.0000 | 48128.0000 | 29367.8639 | -18760.1361 | 81239.8639 | -0.1876 | -0.3898 | 8.0000 | 0.1702 | 18.0000 | 15.0000 | -5230.5108 | -66574.7319 | -14375.8068 | -5636.3498 | 0.3114 | 1.1064 | 0.6104 | 0.2612 | 0.3430 | False | False |
| RAW_Q60 | raw | 2023.0000 | 47.0000 | 48128.0000 | 28120.3964 | -20007.6036 | 79992.3964 | -0.2001 | -0.4157 | 7.0000 | 0.1489 | 19.0000 | 15.0000 | -6477.9784 | -67822.1995 | -15623.2744 | -6883.8174 | 0.3252 | 1.3191 | 0.5372 | 0.2733 | 0.3445 | False | False |
| RAW_Q50 | raw | 2023.0000 | 47.0000 | 48128.0000 | 28120.3964 | -20007.6036 | 79992.3964 | -0.2001 | -0.4157 | 7.0000 | 0.1489 | 17.0000 | 17.0000 | -6477.9784 | -67822.1995 | -15623.2744 | -6883.8174 | 0.3252 | 1.4468 | 0.4920 | 0.2733 | 0.3280 | False | False |
| Z_GE_0P0 | z | 2023.0000 | 47.0000 | 48128.0000 | 28120.3964 | -20007.6036 | 79992.3964 | -0.2001 | -0.4157 | 7.0000 | 0.1489 | 17.0000 | 17.0000 | -6477.9784 | -67822.1995 | -15623.2744 | -6883.8174 | 0.3252 | 1.3830 | 0.5106 | 0.2733 | 0.3200 | False | False |

## Action attribution

| arm | issue_year | selected_match_rows | eligible_changes | activated_changes | realized_gained | realized_lost | mean_pressure | median_pressure | mean_z | global_fallback_rows | gained_precision | lost_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 | 2023.0000 | 329.0000 | 105.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0665 | 0.0000 | 0.8308 | 0.0000 |  |  |
| R0 | 2024.0000 | 406.0000 | 177.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0772 | 0.0000 | 0.4732 | 0.0000 |  |  |
| R3_CORRECTED | 2023.0000 | 329.0000 | 105.0000 | 92.0000 | 21.0000 | 33.0000 | 0.0665 | 0.0000 | 0.8308 | 0.0000 | 0.2283 | 0.3587 |
| R3_CORRECTED | 2024.0000 | 406.0000 | 177.0000 | 139.0000 | 27.0000 | 42.0000 | 0.0772 | 0.0000 | 0.4732 | 0.0000 | 0.1942 | 0.3022 |
| RAW_Q80 | 2023.0000 | 329.0000 | 105.0000 | 40.0000 | 9.0000 | 13.0000 | 0.0665 | 0.0000 | 0.8308 | 0.0000 | 0.2250 | 0.3250 |
| RAW_Q80 | 2024.0000 | 406.0000 | 177.0000 | 63.0000 | 13.0000 | 16.0000 | 0.0772 | 0.0000 | 0.4732 | 0.0000 | 0.2063 | 0.2540 |

## Pressure/z yearly drift and fallback

| issue_year | action_rows | issues | pressure_mean | pressure_median | pressure_q10 | pressure_q90 | z_mean | z_median | z_q10 | z_q90 | global_fallback_rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023.0000 | 8937.0000 | 53.0000 | 0.1355 | 0.1195 | 0.0294 | 0.2633 | 0.0393 | -0.1239 | -1.1068 | 1.4125 | 0.0000 |
| 2024.0000 | 10914.0000 | 66.0000 | 0.1292 | 0.1143 | 0.0270 | 0.2531 | -0.0255 | -0.1705 | -1.1415 | 1.3105 | 1.0000 |

The selected arm is a raw-pressure rule, so robust-z fallback cannot alter its action identity. The drift ledger contains the complete eligible-action population; only one 2024 row uses the global fallback.

## Threshold tie sensitivity

| arm | exact_boundary_rows | exact_boundary_issues | inclusive_threshold_material |
| --- | --- | --- | --- |
| R0 | 0.0000 | 0.0000 | False |
| R3_CORRECTED | 0.0000 | 0.0000 | False |
| RAW_Q50 | 0.0000 | 0.0000 | False |
| RAW_Q60 | 0.0000 | 0.0000 | False |
| RAW_Q70 | 0.0000 | 0.0000 | False |
| RAW_Q80 | 0.0000 | 0.0000 | False |
| RAW_Q90 | 0.0000 | 0.0000 | False |
| RAW_Q95 | 0.0000 | 0.0000 | False |
| Z_GE_0P0 | 0.0000 | 0.0000 | False |
| Z_GE_0P5 | 0.0000 | 0.0000 | False |
| Z_GE_1P0 | 0.0000 | 0.0000 | False |
| Z_GE_1P5 | 0.0000 | 0.0000 | False |
| Z_GE_2P0 | 0.0000 | 0.0000 | False |
| DUAL_Q75_Z1P0 | 0.0000 | 0.0000 | False |
| DUAL_Q85_Z1P0 | 0.0000 | 0.0000 | False |
| DUAL_Q75_Z1P5 | 0.0000 | 0.0000 | False |

## Corrected R3 versus legacy #336 bridge

| scope | issue_year | rows | baseline_support_differences | qeu_support_differences | pressure_differences_gt_1e12 | max_pressure_abs_diff |
| --- | --- | --- | --- | --- | --- | --- |
| ALL_COMPLETE_ACTIONS | 2023.0000 | 14675.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| ALL_COMPLETE_ACTIONS | 2024.0000 | 18090.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| SETTLED_R3_BUNDLES | 2023.0000 | 47.0000 | 0.0000 | 0.0000 |  |  |
| SETTLED_R3_BUNDLES | 2024.0000 | 58.0000 | 0.0000 | 0.0000 |  |  |

The corrected `1e-4` formula reproduces the legacy settled R3 bundle only where the bridge reports zero support differences. The compact action ledger now retains all q_eu/q_line primitives needed to recompute the corrected rule. Coverage remains 105/119 issues; 13 excluded issues would have changed at least one R3 action, so no full-schedule promotion is allowed.

## Why the absolute threshold failed

| issue_year | issue | r3_issue_lift_r0_cny | match_idx | support_pressure | pressure_z | r3_activated | selected_threshold_activated | gained_outcome | lost_outcome | result_code | realized_gained | realized_lost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2023.0000 | 23021 | 60938.3821 | 44.0000 | 0.1766 | 0.3524 | True | False | 1 | 3 | 1 | True | False |
| 2023.0000 | 23021 | 60938.3821 | 193.0000 | 0.1225 | -0.2400 | True | False | 1 | 3 | 0 | False | False |
| 2023.0000 | 23021 | 60938.3821 | 188.0000 | 0.1131 | -0.3438 | True | False | 1 | 3 | 1 | True | False |
| 2023.0000 | 23021 | 60938.3821 | 92.0000 | 0.0000 |  | False | False |  |  | 1 | False | False |
| 2023.0000 | 23021 | 60938.3821 | 212.0000 | 0.0000 |  | False | False |  |  | 3 | False | False |
| 2023.0000 | 23021 | 60938.3821 | 213.0000 | 0.0000 |  | False | False |  |  | 1 | False | False |
| 2023.0000 | 23021 | 60938.3821 | 249.0000 | 0.0000 |  | False | False |  |  | 1 | False | False |
| 2024.0000 | 24104 | 37314.5256 | 146.0000 | 0.1900 | 0.7691 | True | False | 1 | 0 | 1 | True | False |
| 2024.0000 | 24104 | 37314.5256 | 407.0000 | 0.0282 | -1.2735 | True | False | 1 | 3 | 1 | True | False |
| 2024.0000 | 24104 | 37314.5256 | 133.0000 | 0.0000 |  | False | False |  |  | 0 | False | False |
| 2024.0000 | 24104 | 37314.5256 | 148.0000 | 0.0000 |  | False | False |  |  | 0 | False | False |
| 2024.0000 | 24104 | 37314.5256 | 316.0000 | 0.0000 |  | False | False |  |  | 3 | False | False |
| 2024.0000 | 24104 | 37314.5256 | 337.0000 | 0.0000 |  | False | False |  |  | 1 | False | False |
| 2024.0000 | 24104 | 37314.5256 | 338.0000 | 0.0000 |  | False | False |  |  | 1 | False | False |

The 2023 R3 tail issue is the decisive counterexample to a universal absolute cutoff. R3 needed the issue-relative top actions even when their raw pressure or z score was modest. The selected absolute threshold did not preserve the complete winning support. This does not show that divergence is useless; it shows that **cross-issue pressure magnitude is not a stable action-value scale**. Fixed R3 currently works as a per-issue relative rule, not as evidence for a global raw/z boundary.

## PI adversarial review

### Strengths

- The experiment is a matched N7 ablation: match identity, exposure, ticket count and allocation cannot explain differences.
- Thresholds are numeric and causal; no result determines whether a match activates at inference time.
- R0 and fixed R3 are reproduced exactly from #319/#336 before interpreting any threshold result.

### Material limitations

- 2023 selects among fourteen threshold candidates, so the chosen rule is exploratory and selection-optimistic.
- 2024 has already been inspected in prior research and is corroboration only.
- N7 payouts are intrinsically heavy-tailed; raw capital lift is not persuasive without ex-largest, bootstrap and path evidence.
- The robust z reference is frozen on 2020–2022. It measures abnormality relative to that regime; it is not yet a learned online regime model.

### Challenger's rebuttal

The strongest challenge is that a threshold can merely re-label the same jackpot-driven R3 discovery after seeing the historical curve. The response is proportionate: only materially broader lift and no worse path risk can replace R3; otherwise the threshold remains a diagnostic clue and #210 stays unchanged.

## Decision boundary

This is historical exploration, not production or forward evidence. `#210` is only eligible for a separate contract rebind when `promotable_to_210=true`; otherwise its frozen R3 challenger remains unchanged.

## Artifacts

- Notebook: `notebooks/research/qeu-threshold-n7/qeu_threshold_n7.ipynb`
- Package: `results/qeu_threshold_n7/`
- Figures: `docs/research/figures/issue_338_qeu_threshold_atlas.png`, `issue_338_qeu_threshold_capital.png`
