# Issue #336 — QEU support-depth attribution

## Five-minute conclusion

- Verdict: **QEU_TAIL_ONLY**.
- Development selected `R=3`; 2023 matched lift is CNY 61344.22 and 2024 transfer lift is CNY 66812.19.
- R3 is a credible **forward challenger**, but not a historically stable promotion: after removing the largest 2023 issue only 0.66% of raw lift remains. The 2024 transfer is broader (44.15% remains).
- This is a single-variable test: all arms use the same seven matches, N7, 128 distinct tickets, 512 funded units and CNY 1,024 per issue. Only how many match supports switch from probability Top-2 to QEU Top-2 changes.
- The 0.65 Beijing payout factor is applied once, after multiplying all seven winning SPs. It is not applied per leg.
- 2024 is a historical transfer year, not a fresh sealed holdout.
- Exact #319 match-selection parity passes on all 105 globally common settled issues. Fourteen additional #319 active issues are excluded because the QEU matched experiment requires trusted settlement for all seven selected legs.

## Method

For each match, the incumbent support retains the two largest calibrated European probabilities (`q_eu`). The challenger ranks outcomes by `log(q_eu/q_line)`, where `q_line` is the normalized Beijing-handicap implied distribution. `support_pressure` is the QEU score of the gained outcome minus that of the displaced incumbent outcome. Within the seven incumbent-selected matches, `R` activates QEU support on the top-R pressure ranks.

## Development choice

| arm | r | issue_year | issues | stake_cny | gross_cny | pnl_cny | capital_return | stake_roi | hit_issues | hit_rate | miss_by_1_issues | miss_by_2_issues | largest_payout_share | matched_lift_cny | ex_largest_lift_cny | mean_miss_count | mean_changed_matches | mean_baseline_overlap_fraction | max_drawdown_fraction | positive_ex_largest | selected_on_2023 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R3 | 3.0000 | 2023.0000 | 47.0000 | 48128.0000 | 95942.5959 | 47814.5959 | 0.4781 | 0.9935 | 9.0000 | 0.1915 | 16.0000 | 12.0000 | 0.6352 | 61344.2211 | 405.8390 | 1.5319 | 1.9574 | 0.3351 | 0.1312 | True | True |
| R1 | 1.0000 | 2023.0000 | 47.0000 | 48128.0000 | 33168.5642 | -14959.4358 | -0.1496 | -0.3108 | 9.0000 | 0.1915 | 18.0000 | 13.0000 | 0.2122 | -1429.8105 | 7628.3893 | 1.3830 | 0.9149 | 0.5426 | 0.2145 | True | False |
| R2 | 2.0000 | 2023.0000 | 47.0000 | 48128.0000 | 25858.9178 | -22269.0822 | -0.2227 | -0.4627 | 7.0000 | 0.1489 | 18.0000 | 13.0000 | 0.2521 | -8739.4570 | 318.7428 | 1.5319 | 1.5319 | 0.3883 | 0.2849 | True | False |
| R4 | 4.0000 | 2023.0000 | 47.0000 | 48128.0000 | 85320.8959 | 37192.8959 | 0.3719 | 0.7728 | 7.0000 | 0.1489 | 17.0000 | 12.0000 | 0.7142 | 50722.5211 | -10215.8610 | 1.6170 | 2.2128 | 0.3205 | 0.1601 | False | False |
| R7 | 7.0000 | 2023.0000 | 47.0000 | 48128.0000 | 85320.8959 | 37192.8959 | 0.3719 | 0.7728 | 7.0000 | 0.1489 | 17.0000 | 12.0000 | 0.7142 | 50722.5211 | -10215.8610 | 1.6170 | 2.3191 | 0.3191 | 0.1601 | False | False |

## Complete R curve

| arm | r | issue_year | issues | stake_cny | gross_cny | pnl_cny | capital_return | stake_roi | hit_issues | hit_rate | miss_by_1_issues | miss_by_2_issues | largest_payout_share | matched_lift_cny | ex_largest_lift_cny | mean_miss_count | mean_changed_matches | mean_baseline_overlap_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 | 0.0000 | 2023.0000 | 47.0000 | 48128.0000 | 34598.3748 | -13529.6252 | -0.1353 | -0.2811 | 11.0000 | 0.2340 | 17.0000 | 15.0000 | 0.2618 | 0.0000 | 0.0000 | 1.2766 | 0.0000 | 1.0000 |
| R0 | 0.0000 | 2024.0000 | 58.0000 | 59392.0000 | 73661.1876 | 14269.1876 | 0.1427 | 0.2403 | 20.0000 | 0.3448 | 18.0000 | 16.0000 | 0.1607 | 0.0000 | 0.0000 | 1.0690 | 0.0000 | 1.0000 |
| R1 | 1.0000 | 2023.0000 | 47.0000 | 48128.0000 | 33168.5642 | -14959.4358 | -0.1496 | -0.3108 | 9.0000 | 0.1915 | 18.0000 | 13.0000 | 0.2122 | -1429.8105 | 7628.3893 | 1.3830 | 0.9149 | 0.5426 |
| R1 | 1.0000 | 2024.0000 | 58.0000 | 59392.0000 | 61261.0673 | 1869.0673 | 0.0187 | 0.0315 | 15.0000 | 0.2586 | 26.0000 | 13.0000 | 0.1995 | -12400.1203 | -24619.3047 | 1.1379 | 0.9828 | 0.5086 |
| R2 | 2.0000 | 2023.0000 | 47.0000 | 48128.0000 | 25858.9178 | -22269.0822 | -0.2227 | -0.4627 | 7.0000 | 0.1489 | 18.0000 | 13.0000 | 0.2521 | -8739.4570 | 318.7428 | 1.5319 | 1.5319 | 0.3883 |
| R2 | 2.0000 | 2024.0000 | 58.0000 | 59392.0000 | 107056.2096 | 47664.2096 | 0.4766 | 0.8025 | 14.0000 | 0.2414 | 23.0000 | 15.0000 | 0.3486 | 33395.0219 | -3919.5036 | 1.2586 | 1.7931 | 0.3060 |
| R3 | 3.0000 | 2023.0000 | 47.0000 | 48128.0000 | 95942.5959 | 47814.5959 | 0.4781 | 0.9935 | 9.0000 | 0.1915 | 16.0000 | 12.0000 | 0.6352 | 61344.2211 | 405.8390 | 1.5319 | 1.9574 | 0.3351 |
| R3 | 3.0000 | 2024.0000 | 58.0000 | 59392.0000 | 140473.3738 | 81081.3738 | 0.8108 | 1.3652 | 14.0000 | 0.2414 | 19.0000 | 18.0000 | 0.2656 | 66812.1862 | 29497.6606 | 1.3276 | 2.4138 | 0.2306 |
| R4 | 4.0000 | 2023.0000 | 47.0000 | 48128.0000 | 85320.8959 | 37192.8959 | 0.3719 | 0.7728 | 7.0000 | 0.1489 | 17.0000 | 12.0000 | 0.7142 | 50722.5211 | -10215.8610 | 1.6170 | 2.2128 | 0.3205 |
| R4 | 4.0000 | 2024.0000 | 58.0000 | 59392.0000 | 125968.9563 | 66576.9563 | 0.6658 | 1.1210 | 14.0000 | 0.2414 | 19.0000 | 12.0000 | 0.2962 | 52307.7687 | 14993.2431 | 1.4655 | 2.8103 | 0.2069 |
| R7 | 7.0000 | 2023.0000 | 47.0000 | 48128.0000 | 85320.8959 | 37192.8959 | 0.3719 | 0.7728 | 7.0000 | 0.1489 | 17.0000 | 12.0000 | 0.7142 | 50722.5211 | -10215.8610 | 1.6170 | 2.3191 | 0.3191 |
| R7 | 7.0000 | 2024.0000 | 58.0000 | 59392.0000 | 123054.6359 | 63662.6359 | 0.6366 | 1.0719 | 13.0000 | 0.2241 | 19.0000 | 13.0000 | 0.3032 | 49393.4483 | 12078.9227 | 1.5690 | 3.2759 | 0.1996 |

## Path risk

| arm | r | issue_year | max_drawdown_fraction | max_consecutive_losing_issues | worst_rolling_5_cny | worst_rolling_10_cny | worst_rolling_20_cny | max_completed_recovery_issues | terminal_underwater_issues |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R0 | 0.0000 | 2023.0000 | 0.2596 | 12.0000 | -5120.0000 | -10240.0000 | -17626.0748 | 0.0000 | 43.0000 |
| R0 | 0.0000 | 2024.0000 | 0.1164 | 7.0000 | -5120.0000 | -8853.6068 | -13180.1757 | 16.0000 | 29.0000 |
| R1 | 1.0000 | 2023.0000 | 0.2145 | 13.0000 | -5120.0000 | -10240.0000 | -13025.4130 | 0.0000 | 45.0000 |
| R1 | 1.0000 | 2024.0000 | 0.1765 | 10.0000 | -5120.0000 | -10240.0000 | -16258.1832 | 24.0000 | 29.0000 |
| R2 | 2.0000 | 2023.0000 | 0.2849 | 25.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 0.0000 | 45.0000 |
| R2 | 2.0000 | 2024.0000 | 0.1863 | 8.0000 | -5120.0000 | -9201.2605 | -11491.9683 | 41.0000 | 0.0000 |
| R3 | 3.0000 | 2023.0000 | 0.1312 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 4.0000 | 41.0000 |
| R3 | 3.0000 | 2024.0000 | 0.1980 | 10.0000 | -5120.0000 | -10240.0000 | -11491.9683 | 38.0000 | 1.0000 |
| R4 | 4.0000 | 2023.0000 | 0.1601 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 5.0000 | 41.0000 |
| R4 | 4.0000 | 2024.0000 | 0.1369 | 9.0000 | -5120.0000 | -9201.2605 | -8462.7102 | 38.0000 | 1.0000 |
| R7 | 7.0000 | 2023.0000 | 0.1601 | 21.0000 | -5120.0000 | -10240.0000 | -20064.3854 | 5.0000 | 41.0000 |
| R7 | 7.0000 | 2024.0000 | 0.1661 | 10.0000 | -5120.0000 | -10240.0000 | -11377.0306 | 38.0000 | 1.0000 |

## Issue-cluster bootstrap

| arm | r | issue_year | draws | lift_p05_cny | lift_p50_cny | lift_p95_cny | positive_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R0 | 0.0000 | 2023.0000 | 2000.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| R0 | 0.0000 | 2024.0000 | 2000.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| R1 | 1.0000 | 2023.0000 | 2000.0000 | -27174.4094 | -1523.6847 | 24410.1131 | 0.4655 |
| R1 | 1.0000 | 2024.0000 | 2000.0000 | -45314.9686 | -12692.4239 | 21884.1190 | 0.2555 |
| R2 | 2.0000 | 2023.0000 | 2000.0000 | -32536.7330 | -8928.1907 | 13455.2600 | 0.2470 |
| R2 | 2.0000 | 2024.0000 | 2000.0000 | -37397.2366 | 30231.7271 | 117687.8034 | 0.7550 |
| R3 | 3.0000 | 2023.0000 | 2000.0000 | -18879.4008 | 54812.0021 | 184430.2635 | 0.8150 |
| R3 | 3.0000 | 2024.0000 | 2000.0000 | -20916.7905 | 64951.9990 | 173149.6604 | 0.8855 |
| R4 | 4.0000 | 2023.0000 | 2000.0000 | -24868.2909 | 47758.2334 | 173716.9211 | 0.7250 |
| R4 | 4.0000 | 2024.0000 | 2000.0000 | -38438.3359 | 48318.2670 | 155831.0603 | 0.8020 |
| R7 | 7.0000 | 2023.0000 | 2000.0000 | -24925.4262 | 47856.5983 | 175126.8831 | 0.7400 |
| R7 | 7.0000 | 2024.0000 | 2000.0000 | -35995.9019 | 45818.3918 | 151948.1876 | 0.7950 |

## Z100/K1 diagnostic

| diagnostic | policies | action_rows | issues | actions_in_qeu_issue_support | actions_in_incumbent_n7 | exact_r1_action_overlaps | median_support_pressure_on_join | median_abs_delta_on_join | denominator_warning |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| other Z100/K1 policies | 42.0000 | 547.0000 | 34.0000 | 547.0000 | 176.0000 | 43.0000 | 0.0421 | 0.0313 | #190 selects different matches/issues; overlap is diagnostic, not policy replication |
| #190 positive representatives | 6.0000 | 153.0000 | 34.0000 | 153.0000 | 56.0000 | 13.0000 | 0.0538 | 0.0313 | #190 selects different matches/issues; overlap is diagnostic, not policy replication |

The zero/low exact overlap is not a contradiction: #190 selects a different N7 match identity and deletes one code only on its strongest signal, whereas this experiment preserves #319 matches and changes Top-2 support on R pressure-ranked matches. They share the divergence hypothesis, not an execution identity.

## PI adversarial review

### Strengths

- Exact matched design removes exposure, match-selection and allocation as explanations for lift.
- R3 is an interior point; R1/R2 underperform and R4/R7 do not add improvement. That shape is more informative than an unconstrained all-QEU result.
- The 2024 transfer survives removal of its largest issue and has 88.55% positive issue-bootstrap draws.

### Material limitations

- **Development concentration:** issue 23021 contributes CNY60,938 of the CNY61,344 development lift. The remaining CNY406 is not enough to call the development evidence stable.
- **Historical reuse:** 2024 has been inspected in prior Issues, so its positive result is corroboration, not a confirmatory holdout.
- **Multiplicity:** R is selected from five challenger depths. The fixed lexicographic rule limits discretion, but it does not erase selection optimism.
- **Path risk:** on 2024 R3 max drawdown is 19.80% versus R0's 11.64%, and the longest losing run is 10 versus 7 issues. Higher ending capital does not make the holding path uniformly safer.
- **Sparse settlement denominator:** 105/119 #319 active issues form exact common support. This is transparent matched evidence, not a claim about all historical issues.

### Challenger's rebuttal

If challenged, the strongest objection is: “R3 was selected because one 2023 jackpot made it look best; 2024 was already visible, so the apparent replication may be another historical selection artifact.” That objection is valid. The proportionate answer is a frozen R3-vs-R0 prospective comparison, not more historical tuning.

## Decision discipline

Promotion requires positive raw and ex-largest matched lift in both 2023 and 2024, plus at least 80% positive 2024 issue-bootstrap draws. A tail-only or negative result remains useful attribution evidence but does not unblock #210.

The PI disposition is therefore to freeze `R3` as the single #210 forward challenger while retaining probability Top-2 `R0` as incumbent. This is not a deployable-policy claim and does not override #210's other native blocker.

## Artifacts

- Notebook: `notebooks/research/qeu-support-depth/qeu_support_depth.ipynb`
- Package: `results/qeu_support_depth/`
- Figures: `docs/research/figures/issue_336_qeu_support_depth_curve.png`, `issue_336_qeu_selected_capital.png`
