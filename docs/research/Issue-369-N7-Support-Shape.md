# Issue #369 — corrected N7 support-shape factorial

Contract: `BJ-UNIFIED-N7-SUPPORT-SHAPE-001/v1`

## Decision

`NO_PROMOTION`. This is exposed historical evidence; it does not modify #210/#218 and it does not infer deployment readiness.

## Strictly OOF 2017–2021 score diagnostics

| base | diagnostic | conditioning | rows | mean_score | observed_rate | bin_spearman | nonnegative_monotonicity |
|---|---|---|---|---|---|---|---|
| R0_CORRECTED | contraction_score | SUPPORTED_REALIZED | 1427 | 0.7073 | 0.7106 | 0.7052 | True |
| R0_CORRECTED | expansion_score | ALL | 1781 | 0.1663 | 0.1988 | 0.9119 | True |
| R3_CORRECTED | contraction_score | SUPPORTED_REALIZED | 1410 | 0.7219 | 0.7184 | 0.8268 | True |
| R3_CORRECTED | expansion_score | ALL | 1781 | 0.1859 | 0.2083 | 0.8667 | True |

The diagnostic checks the frozen probability-mass scores before 2022–2024 evaluation. It is descriptive calibration/monotonicity evidence, not a search over exposed outcomes.

## Eight-cell absolute performance

| scope | base | shape | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_rate | conditional_gross_on_hit_cny | ex_largest_pnl_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | R0_CORRECTED | BOTH | 151 | 154624.0000 | 135140.4854 | -19483.5146 | 80516.4854 | -0.1948 | -0.1260 | 0.2119 | 4223.1402 | -36219.8155 |
| ALL | R0_CORRECTED | CONTRACTION_ONLY | 151 | 154624.0000 | 171307.3288 | 16683.3288 | 116683.3288 | 0.1668 | 0.1079 | 0.1987 | 5710.2443 | -5973.0724 |
| ALL | R0_CORRECTED | CONTROL | 151 | 154624.0000 | 138630.0588 | -15993.9412 | 84006.0588 | -0.1599 | -0.1034 | 0.2583 | 3554.6169 | -28175.6815 |
| ALL | R0_CORRECTED | EXPANSION_ONLY | 151 | 154624.0000 | 126696.7662 | -27927.2338 | 72072.7662 | -0.2793 | -0.1806 | 0.2980 | 2815.4837 | -35783.3843 |
| ALL | R3_CORRECTED | BOTH | 151 | 154624.0000 | 225509.7219 | 70885.7219 | 170885.7219 | 0.7089 | 0.4584 | 0.1987 | 7516.9907 | 21630.9810 |
| ALL | R3_CORRECTED | CONTRACTION_ONLY | 151 | 154624.0000 | 170614.6383 | 15990.6383 | 115990.6383 | 0.1599 | 0.1034 | 0.1258 | 8979.7178 | -19949.9957 |
| ALL | R3_CORRECTED | CONTROL | 151 | 154624.0000 | 187313.1262 | 32689.1262 | 132689.1262 | 0.3269 | 0.2114 | 0.1722 | 7204.3510 | -27225.2559 |
| ALL | R3_CORRECTED | EXPANSION_ONLY | 151 | 154624.0000 | 185691.2214 | 31067.2214 | 131067.2214 | 0.3107 | 0.2009 | 0.2583 | 4761.3134 | -13612.5651 |

## Key findings

1. **The strongest point estimate is R3 + BOTH.** Ending capital is CNY170,886, versus CNY132,689 for R3 CONTROL. The actual matched lift is CNY38,197; under ideal fractional units it remains CNY24,644. Thus the signal is not purely integer allocation luck, although integer placement contributes CNY13,552.
2. **The R3 interaction is the clearest but still borderline mechanism result.** The factorial interaction is CNY56,517, with actual-unit paired-bootstrap p05 CNY6,576. Under ideal fractional units its lift remains CNY50,542, but p05 is only CNY141, effectively on the zero boundary at bootstrap Monte Carlo resolution. Contraction or expansion alone does not improve R3; the joint capacity transfer signal is real enough to retain as a hypothesis, but its apparent robustness is integer-allocation-sensitive.
3. **The candidate still fails expert admission.** R3 BOTH has positive standalone and ex-largest PnL, but its lift bootstrap p05 is CNY-115,247. Its matched lift is positive in 2022 and 2024 but sharply negative in 2023. Maximum drawdown is slightly lower than R3 CONTROL (32.91% versus 33.17%), while the longest losing run is worse (22 versus 19 issues). This is a historical synergy candidate, not stable Edge.
4. **R0 contraction is informative but fragile.** It turns R0 from negative to CNY16,683 PnL and adds CNY32,677, yet standalone ex-largest PnL and bootstrap p05 remain negative. Concentrating stake can amplify the right tail without creating robust expectancy.
5. **Expansion alone trades precision for coverage without an aggregate lift.** Hit rates rise for both bases, but stake per ticket falls; neither base gains versus its own control on aggregate PnL.

## Path risk

| scope | base | shape | max_drawdown_fraction | longest_losing_run | open_underwater_issues | largest_payout_share | payout_hhi |
|---|---|---|---|---|---|---|---|
| ALL | R0_CORRECTED | BOTH | 0.6265 | 16 | 146 | 0.1314 | 0.0517 |
| ALL | R0_CORRECTED | CONTRACTION_ONLY | 0.4850 | 16 | 0 | 0.1382 | 0.0533 |
| ALL | R0_CORRECTED | CONTROL | 0.3023 | 14 | 151 | 0.0953 | 0.0420 |
| ALL | R0_CORRECTED | EXPANSION_ONLY | 0.4755 | 14 | 151 | 0.0701 | 0.0345 |
| ALL | R3_CORRECTED | BOTH | 0.3291 | 22 | 0 | 0.2230 | 0.0914 |
| ALL | R3_CORRECTED | CONTRACTION_ONLY | 0.5008 | 31 | 1 | 0.2167 | 0.0977 |
| ALL | R3_CORRECTED | CONTROL | 0.3317 | 19 | 1 | 0.3253 | 0.1368 |
| ALL | R3_CORRECTED | EXPANSION_ONLY | 0.3426 | 17 | 1 | 0.2461 | 0.0988 |

## Matched effects and stability

| scope | contrast | issues | matched_lift_cny | ideal_fractional_matched_lift_cny | integer_contribution_to_lift_cny | largest_abs_delta_issue | largest_abs_delta_cny | ex_largest_lift_cny | bootstrap_p05_cny | bootstrap_median_cny | bootstrap_p95_cny | ideal_bootstrap_p05_cny | ideal_bootstrap_median_cny | ideal_bootstrap_p95_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | R0_CORRECTED:CONTRACTION_MAIN | 151 | 32677.2700 | 32677.2700 | 0.0000 | 22095 | -13205.7403 | 45883.0103 | -14889.2942 | 33361.2375 | 78059.8485 | -14889.2942 | 33361.2375 | 78059.8485 |
| ALL | R0_CORRECTED:EXPANSION_MAIN | 151 | -11933.2926 | -14005.7086 | 2072.4160 | 23104 | 7313.6898 | -19246.9824 | -37766.5778 | -12415.7312 | 15846.2696 | -39982.4489 | -14723.0732 | 14563.9568 |
| ALL | R0_CORRECTED:BOTH_V_CONTROL | 151 | -3489.5734 | -6504.8421 | 3015.2687 | 22095 | -13205.7403 | 9716.1669 | -45934.3679 | -3076.3813 | 36351.9421 | -49063.1965 | -5842.9034 | 33700.8193 |
| ALL | R0_CORRECTED:FACTORIAL_INTERACTION | 151 | -24233.5508 | -25176.4035 | 942.8527 | 23104 | -7313.6898 | -16919.8610 | -50376.1682 | -23905.6003 | 1592.7176 | -53362.8852 | -24679.4892 | 1744.7037 |
| ALL | R3_CORRECTED:CONTRACTION_MAIN | 151 | -16698.4879 | -16698.4879 | 0.0000 | 23021 | -60938.3821 | 44239.8942 | -140073.0061 | -9881.8081 | 79355.8607 | -140073.0061 | -9881.8081 | 79355.8607 |
| ALL | R3_CORRECTED:EXPANSION_MAIN | 151 | -1621.9048 | -9199.0160 | 7577.1112 | 24104 | 25139.3704 | -26761.2752 | -52134.3948 | -2984.0153 | 56594.8715 | -63461.1136 | -9042.2624 | 48292.0526 |
| ALL | R3_CORRECTED:BOTH_V_CONTROL | 151 | 38196.5956 | 24644.3927 | 13552.2029 | 23021 | -60938.3821 | 99134.9778 | -115247.2866 | 40407.1328 | 173511.7730 | -124458.3351 | 27851.4175 | 150121.2982 |
| ALL | R3_CORRECTED:FACTORIAL_INTERACTION | 151 | 56516.9883 | 50541.8966 | 5975.0917 | 24104 | 25139.3704 | 31377.6179 | 6575.5367 | 54205.5467 | 117151.4222 | 141.0891 | 48309.7283 | 111032.5392 |
| ALL | R3_MINUS_R0:CONTROL | 151 | 48683.0675 | 48683.0675 | 0.0000 | 23021 | 60938.3821 | -12255.3147 | -58206.8631 | 40407.3854 | 177357.1722 | -58206.8631 | 40407.3854 | 177357.1722 |
| ALL | R3_MINUS_R0:CONTRACTION_ONLY | 151 | -692.6905 | -692.6905 | 0.0000 | 24081 | 36964.6340 | -37657.3245 | -95824.9988 | -1680.0167 | 103473.6263 | -95824.9988 | -1680.0167 | 103473.6263 |
| ALL | R3_MINUS_R0:EXPANSION_ONLY | 151 | 58994.4553 | 53489.7601 | 5504.6952 | 23021 | 45703.7866 | 13290.6687 | -26483.4074 | 53251.9726 | 162107.1657 | -22529.3052 | 48273.6186 | 146002.6306 |
| ALL | R3_MINUS_R0:BOTH | 151 | 90369.2365 | 79832.3023 | 10536.9342 | 24104 | 50278.7408 | 40090.4957 | -16303.0066 | 85792.8069 | 212494.9217 | -16868.2456 | 75460.5742 | 189990.0962 |

## Integer allocation versus ideal fractional units

| scope | base | shape | issues | integer_pnl_cny | ideal_fractional_pnl_cny | integer_minus_ideal_cny |
|---|---|---|---|---|---|---|
| ALL | R0_CORRECTED | BOTH | 151 | -19483.5146 | -22498.7834 | 3015.2687 |
| ALL | R0_CORRECTED | CONTRACTION_ONLY | 151 | 16683.3288 | 16683.3288 | 0.0000 |
| ALL | R0_CORRECTED | CONTROL | 151 | -15993.9412 | -15993.9412 | 0.0000 |
| ALL | R0_CORRECTED | EXPANSION_ONLY | 151 | -27927.2338 | -29999.6499 | 2072.4160 |
| ALL | R3_CORRECTED | BOTH | 151 | 70885.7219 | 57333.5190 | 13552.2029 |
| ALL | R3_CORRECTED | CONTRACTION_ONLY | 151 | 15990.6383 | 15990.6383 | 0.0000 |
| ALL | R3_CORRECTED | CONTROL | 151 | 32689.1262 | 32689.1262 | 0.0000 |
| ALL | R3_CORRECTED | EXPANSION_ONLY | 151 | 31067.2214 | 23490.1102 | 7577.1112 |

## Expert admission

| base | shape | standalone_positive | standalone_ex_largest_positive | matched_lift_positive | matched_ex_largest_positive | bootstrap_p05_nonnegative | at_least_two_positive_annual_lifts | admitted |
|---|---|---|---|---|---|---|---|---|
| R0_CORRECTED | CONTRACTION_ONLY | True | False | True | True | False | True | False |
| R0_CORRECTED | EXPANSION_ONLY | False | False | False | False | False | False | False |
| R0_CORRECTED | BOTH | False | False | False | True | False | False | False |
| R3_CORRECTED | CONTRACTION_ONLY | True | False | False | True | False | True | False |
| R3_CORRECTED | EXPANSION_ONLY | True | False | False | False | False | True | False |
| R3_CORRECTED | BOTH | True | True | True | True | False | True | False |

Only a candidate with positive standalone and ex-largest PnL, positive matched and ex-largest lift, non-negative paired-bootstrap p05, and at least two positive annual lifts is admitted. Low correlation or diversification is not Edge.

## Mechanism interpretation

- Contraction concentrates the fixed CNY1,024 budget into 64 tickets but loses the second supported outcome on one fixture.
- Expansion buys the omitted outcome on the hardest two-outcome fixture, spreading the same budget across 192 tickets.
- BOTH reallocates support capacity into a 96-ticket compromise; its factorial interaction is reported explicitly rather than inferred from the raw arm result.
- Non-divisible allocations use the frozen SHA-256 ticket rule. The ideal-fractional counterfactual isolates any integer-unit luck.

## Coverage and evidence boundary

The corrected registry contributes **172** issues; **151** have complete trusted settlement and **21** are excluded exactly as in #366. R0/R3 fixture selection and fixed R3 remain unchanged. All 2022–2024 outcomes are exposed historical evidence.

## Artifacts

- Package: `results/n7_support_shape/`
- Notebook: `notebooks/research/n7-support-shape/n7_support_shape.ipynb`
- Figure: `docs/research/figures/issue_369_support_shape_capital.png`
