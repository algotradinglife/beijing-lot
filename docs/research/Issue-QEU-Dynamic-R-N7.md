# Issue #340 — within-issue QEU dynamic support depth R on fixed N7

## Five-minute conclusion

- Verdict: **FIXED_R3_REMAINS_BEST**.
- N remained fixed at **7**; all arms used the exact #319 matches, 128 distinct tickets and CNY1,024 per issue.
- Dynamic R lift versus R3: CNY -15394.62 in 2023 and CNY -39024.23 in 2024.
- Ex-largest lift versus R3: CNY -6249.33 in 2023 and CNY -4372.79 in 2024.
- The learner made 89 learned decisions after 16 R3 cold-start issues; mean learned R was 1.449438202247191.
- The 2023 full-policy lift versus R0 is not learning evidence: R3 cold start contributes CNY 48029.58, while learned decisions contribute CNY -2079.99. The all-learned 2024 lift versus R0 is CNY 27787.96.
- Coverage is 105/119; 2024 was previously exposed. `promotable_to_210` is **false by contract**.

## What was tested

The fixed curve includes every R0–R7 support depth. The dynamic policy observes only each issue's pre-outcome QEU rank landscape: within-issue percentiles, adjacent pressure gaps, cutoff cliffs, dispersion, prefix pressure and strictly-prior expanding robust-z context. Eleven shallow random-forest action-value models are refit before each issue from strictly earlier settled issues. Their median prediction chooses R; no seed is selected after outcomes.

The issue is the statistical unit. Eight candidate-R counterfactual rows per issue have total training weight one and do not increase the sample size.

## Complete fixed-R and dynamic performance

| arm | issue_year | issues | pnl_cny | ending_capital_cny | capital_return | hit_rate | matched_lift_r0_cny | matched_lift_r3_cny | ex_largest_lift_r0_cny | ex_largest_lift_r3_cny | largest_payout_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DYN_R_PRIOR_MEAN | 2023.0000 | 47.0000 | 47814.5959 | 147814.5959 | 0.4781 | 0.1915 | 61344.2211 | 0.0000 | 405.8390 | 0.0000 | 0.6352 |
| DYN_R_PRIOR_MEAN | 2024.0000 | 58.0000 | 81081.3738 | 181081.3738 | 0.8108 | 0.2414 | 66812.1862 | 0.0000 | 29497.6606 | 0.0000 | 0.2656 |
| DYN_R_RF_ENSEMBLE | 2023.0000 | 47.0000 | 32419.9714 | 132419.9714 | 0.3242 | 0.1702 | 45949.5967 | -15394.6245 | -14988.7854 | -6249.3285 | 0.7565 |
| DYN_R_RF_ENSEMBLE | 2024.0000 | 58.0000 | 42057.1433 | 142057.1433 | 0.4206 | 0.3276 | 27787.9557 | -39024.2305 | -9526.5699 | -4372.7871 | 0.3678 |
| R0 | 2023.0000 | 47.0000 | -13529.6252 | 86470.3748 | -0.1353 | 0.2340 | 0.0000 | -61344.2211 | 0.0000 | -405.8390 | 0.2618 |
| R0 | 2024.0000 | 58.0000 | 14269.1876 | 114269.1876 | 0.1427 | 0.3448 | 0.0000 | -66812.1862 | 0.0000 | -29497.6606 | 0.1607 |
| R1 | 2023.0000 | 47.0000 | -14959.4358 | 85040.5642 | -0.1496 | 0.1915 | -1429.8105 | -62774.0317 | 7628.3893 | -1835.6495 | 0.2122 |
| R1 | 2024.0000 | 58.0000 | 1869.0673 | 101869.0673 | 0.0187 | 0.2586 | -12400.1203 | -79212.3065 | -24619.3047 | -41897.7809 | 0.1995 |
| R2 | 2023.0000 | 47.0000 | -22269.0822 | 77730.9178 | -0.2227 | 0.1489 | -8739.4570 | -70083.6781 | 318.7428 | -9145.2960 | 0.2521 |
| R2 | 2024.0000 | 58.0000 | 47664.2096 | 147664.2096 | 0.4766 | 0.2414 | 33395.0219 | -33417.1643 | -3919.5036 | 1234.2791 | 0.3486 |
| R3_CORRECTED | 2023.0000 | 47.0000 | 47814.5959 | 147814.5959 | 0.4781 | 0.1915 | 61344.2211 | 0.0000 | 405.8390 | 0.0000 | 0.6352 |
| R3_CORRECTED | 2024.0000 | 58.0000 | 81081.3738 | 181081.3738 | 0.8108 | 0.2414 | 66812.1862 | 0.0000 | 29497.6606 | 0.0000 | 0.2656 |
| R4 | 2023.0000 | 47.0000 | 37192.8959 | 137192.8959 | 0.3719 | 0.1489 | 50722.5211 | -10621.7000 | -10215.8610 | -1476.4040 | 0.7142 |
| R4 | 2024.0000 | 58.0000 | 66576.9563 | 166576.9563 | 0.6658 | 0.2414 | 52307.7687 | -14504.4175 | 14993.2431 | 3977.8995 | 0.2962 |
| R5 | 2023.0000 | 47.0000 | 37192.8959 | 137192.8959 | 0.3719 | 0.1489 | 50722.5211 | -10621.7000 | -10215.8610 | -1476.4040 | 0.7142 |
| R5 | 2024.0000 | 58.0000 | 66576.9563 | 166576.9563 | 0.6658 | 0.2414 | 52307.7687 | -14504.4175 | 14993.2431 | 3977.8995 | 0.2962 |
| R6 | 2023.0000 | 47.0000 | 37192.8959 | 137192.8959 | 0.3719 | 0.1489 | 50722.5211 | -10621.7000 | -10215.8610 | -1476.4040 | 0.7142 |
| R6 | 2024.0000 | 58.0000 | 63662.6359 | 163662.6359 | 0.6366 | 0.2241 | 49393.4483 | -17418.7379 | 12078.9227 | 1063.5791 | 0.3032 |
| R7 | 2023.0000 | 47.0000 | 37192.8959 | 137192.8959 | 0.3719 | 0.1489 | 50722.5211 | -10621.7000 | -10215.8610 | -1476.4040 | 0.7142 |
| R7 | 2024.0000 | 58.0000 | 63662.6359 | 163662.6359 | 0.6366 | 0.2241 | 49393.4483 | -17418.7379 | 12078.9227 | 1063.5791 | 0.3032 |

## Path risk

| arm | issue_year | max_drawdown_fraction | max_consecutive_losing_issues | worst_rolling_5_cny | worst_rolling_10_cny | worst_rolling_20_cny | max_completed_recovery_issues | terminal_underwater_issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DYN_R_RF_ENSEMBLE | 2023.0000 | 0.1975 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 4.0000 | 41.0000 |
| DYN_R_RF_ENSEMBLE | 2024.0000 | 0.0859 | 7.0000 | -5120.0000 | -8114.3119 | -3.4689 | 16.0000 | 14.0000 |
| R0 | 2023.0000 | 0.2596 | 12.0000 | -5120.0000 | -10240.0000 | -17626.0748 | 0.0000 | 43.0000 |
| R0 | 2024.0000 | 0.1164 | 7.0000 | -5120.0000 | -8853.6068 | -13180.1757 | 16.0000 | 29.0000 |
| R3_CORRECTED | 2023.0000 | 0.1312 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 4.0000 | 41.0000 |
| R3_CORRECTED | 2024.0000 | 0.1980 | 10.0000 | -5120.0000 | -10240.0000 | -11491.9683 | 38.0000 | 1.0000 |

## Bootstrap evidence

| arm | issue_year | r0_positive_fraction | r3_positive_fraction | r3_p05_cny | r3_p50_cny | r3_p95_cny |
| --- | --- | --- | --- | --- | --- | --- |
| DYN_R_RF_ENSEMBLE | 2023.0000 | 0.6700 | 0.0820 | -36604.0537 | -15123.9504 | 270.6741 |
| DYN_R_RF_ENSEMBLE | 2024.0000 | 0.7275 | 0.1810 | -115548.8776 | -35622.4653 | 24507.6451 |
| R0 | 2023.0000 | 0.0000 | 0.1735 | -180156.5979 | -57211.0485 | 17991.0395 |
| R0 | 2024.0000 | 0.0000 | 0.1345 | -169024.5147 | -62674.1779 | 24043.4073 |
| R3_CORRECTED | 2023.0000 | 0.8175 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| R3_CORRECTED | 2024.0000 | 0.8820 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

## Dynamic R distribution

| issue_year | cold_start | selected_r | issues |
| --- | --- | --- | --- |
| 2023.0000 | False | 0.0000 | 8.0000 |
| 2023.0000 | False | 1.0000 | 12.0000 |
| 2023.0000 | False | 2.0000 | 2.0000 |
| 2023.0000 | False | 3.0000 | 4.0000 |
| 2023.0000 | False | 4.0000 | 1.0000 |
| 2023.0000 | False | 5.0000 | 2.0000 |
| 2023.0000 | False | 6.0000 | 2.0000 |
| 2023.0000 | True | 3.0000 | 16.0000 |
| 2024.0000 | False | 0.0000 | 25.0000 |
| 2024.0000 | False | 1.0000 | 16.0000 |
| 2024.0000 | False | 2.0000 | 3.0000 |
| 2024.0000 | False | 3.0000 | 5.0000 |
| 2024.0000 | False | 4.0000 | 7.0000 |
| 2024.0000 | False | 5.0000 | 2.0000 |

## Seed stability

| issue_year | seeds | positive_raw_vs_r3 | positive_ex_largest_vs_r3 | mean_action_agreement |
| --- | --- | --- | --- | --- |
| 2023.0000 | 11.0000 | 0.0000 | 4.0000 | 0.7950 |
| 2024.0000 | 11.0000 | 0.0000 | 6.0000 | 0.8339 |

## Leading model features

| feature | mean_importance | median_importance | fits |
| --- | --- | --- | --- |
| prefix_z_mean | 0.3886 | 0.3702 | 968.0000 |
| prefix_pressure_min | 0.1192 | 0.0735 | 968.0000 |
| top_to_median | 0.0628 | 0.0088 | 968.0000 |
| largest_gap_rank | 0.0622 | 0.0111 | 968.0000 |
| largest_gap | 0.0551 | 0.0271 | 968.0000 |
| prefix_pressure_mean | 0.0539 | 0.0552 | 968.0000 |
| reference_actions_min | 0.0462 | 0.0357 | 968.0000 |
| pressure_std | 0.0315 | 0.0070 | 968.0000 |
| reference_actions_mean | 0.0301 | 0.0275 | 968.0000 |
| prefix_pressure_sum | 0.0298 | 0.0266 | 968.0000 |
| top_pressure | 0.0243 | 0.0153 | 968.0000 |
| pressure_range | 0.0232 | 0.0132 | 968.0000 |
| top_two_gap | 0.0181 | 0.0158 | 968.0000 |
| pressure_iqr | 0.0123 | 0.0084 | 968.0000 |
| pressure_mean | 0.0078 | 0.0054 | 968.0000 |

## Coverage boundary

The experiment settles exactly the 105 common issues already bounded by #338. The following 14 issues are excluded because the complete trusted seven-leg settlement is unavailable; no result generalizes across them.

## PI adversarial review

### Strengths

- Match identity, N, support width, ticket count and CNY exposure are matched, so lift isolates outcome-support depth.
- Every prediction is prequential: training anchors and expanding reference cutoffs are strictly earlier than the decision issue.
- R0–R7 are all observed controls, and the simple prior-mean policy tests whether issue features add anything beyond historical average-by-R.
- Capital, ex-largest, bootstrap, path risk and all eleven seed policies are reported; raw jackpot lift alone cannot pass the stable signal rule.

### Material limitations

- Only 105 issues have complete settlement and 2024 has already been inspected in earlier research.
- The first 16 issues inherit R3, so dynamic performance is decomposed rather than credited wholly to learning.
- Counterfactual R labels are correlated within an issue. They are useful for action-value supervision but remain one statistical unit.
- Random forests can reuse fingerprints of earlier jackpots. Ex-largest and transfer evidence bound but cannot eliminate that risk.

### Challenger's rebuttal

A challenger should ask whether the model merely learns which R won after a rare historical payout. The answer is decisive only if dynamic R beats fixed R3 after the largest issue is removed, across bootstrap draws and across seeds. Otherwise the learner is diagnostic rather than an edge.

## #338 corrections carried forward

- Robust references expand strictly through earlier anchors; static 2020–2022 z is not reused as a global action cutoff.
- Probability normalization uses `atol=1e-6, rtol=0`.
- Semantic verification accepts actual boolean columns only and rejects string values such as `FORGED_FALSE`.

## Decision boundary

This is historical exploration. It does not unlock/rebind #210 and does not change #218.

## Artifacts

- Notebook: `notebooks/research/qeu-dynamic-r-n7/qeu_dynamic_r_n7.ipynb`
- Package: `results/qeu_dynamic_r_n7/`
- Figures: `docs/research/figures/issue_340_dynamic_r_curve.png`, `issue_340_dynamic_r_capital.png`
