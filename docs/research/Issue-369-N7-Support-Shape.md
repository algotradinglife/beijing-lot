# Issue #369 — corrected-N7 support-shape contraction x expansion factorial

Contract: `BJ-UNIFIED-N7-SUPPORT-SHAPE-001/v1`

## Decision

`NON_PROMOTABLE_HISTORICAL_EVIDENCE`. Exposed historical chronology-synchronization factorial;
2022-2024 are exposed evidence, not a holdout. OOF 2017-2021 development
diagnostic: **FAIL**
(limitation `DEV_DIAGNOSTIC_FAIL_REPORTED_NOT_REPAIRED`).
Upstream corrected-R3 (#366) all-period PnL: 32689.13 CNY.
Exact-common control denominator: 151 issues.

## Scientific findings (corrected = final)

- The corrected CONTROL arm reproduces #366 exactly (R0 -15993.94, R3 32689.13 CNY), so all contrasts are measured against the canonical corrected-N7 expert interface.
- R0 base: contraction main effect positive and robust (+32,677; median +33,335); expansion main effect negative (-11,933); contraction x expansion interaction negative (-24,234) — adding third-outcome expansion destroys R0's contraction gain.
- R3 base: contraction main effect negative (-16,698); expansion flat (-1,622); interaction strongly positive (+56,517, bootstrap p05 +6,291) — BOTH is the standout absolute arm (+70,886).
- Mechanism: contraction coverage loss is modest (34 R0 / 29 R3 issues) but stakes are doubled, so R3's pressure-leg insurance loss costs 102,006 gross CNY; R3 BOTH rescues 51 e-fixture third-outcome issues worth 108,705 gross CNY (concentrated stake pays more when the retained c hits). Integer-vs-fractional deltas are small — integer allocation is not the driver.
- OOF 2017-2021: contraction scores calibrate and rank monotonically on both bases; expansion scores FAIL both checks and are systematically under-predictive of the third-outcome rate. Expansion-arm results carry this disclosed limitation.
- R3 BOTH's matched lift is sensitive to one large negative paired delta (bootstrap p05 = -108,149). No treatment shape clears every pre-registered admission criterion → NON_PROMOTABLE.

## OOF 2017-2021 score diagnostic (before evaluation labels)

102 dev issues, 714 fixtures. Checks:

| base | score | n_observations | n_bins | bin_min_n | spearman_monotonicity | max_bin_calibration_err | global_calibration_err | observed_rate | predicted_mean | monotone_pass | calibration_pass | pass | reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0_CORRECTED | contraction_score | 519 | 8 | 64 | 0.8095 | 0.0732 | 0.0056 | 0.6724 | 0.6668 | True | True | True |  |
| R0_CORRECTED | expansion_score | 675 | 8 | 84 | -0.0238 | 0.1958 | 0.0421 | 0.2311 | 0.1890 | False | False | False |  |
| R3_CORRECTED | contraction_score | 515 | 8 | 64 | 0.8810 | 0.0593 | 0.0146 | 0.6757 | 0.6903 | True | True | True |  |
| R3_CORRECTED | expansion_score | 675 | 8 | 84 | 0.2515 | 0.1703 | 0.0182 | 0.2370 | 0.2188 | False | False | False |  |

## 8-arm absolute performance (ALL, exact-common settled issues)

| base | shape | issues | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | hit_rate | payout_cond_hit |
|---|---|---|---|---|---|---|---|---|---|---|
| R0_CORRECTED | CONTROL | 151 | 154624.0000 | 138630.0588 | -15993.9412 | 84006.0588 | -0.1599 | -0.1034 | 0.2583 | 3554.6169 |
| R0_CORRECTED | CONTRACTION_ONLY | 151 | 154624.0000 | 171307.3288 | 16683.3288 | 116683.3288 | 0.1668 | 0.1079 | 0.1987 | 5710.2443 |
| R0_CORRECTED | EXPANSION_ONLY | 151 | 154624.0000 | 126696.7662 | -27927.2338 | 72072.7662 | -0.2793 | -0.1806 | 0.2980 | 2815.4837 |
| R0_CORRECTED | BOTH | 151 | 154624.0000 | 135140.4854 | -19483.5146 | 80516.4854 | -0.1948 | -0.1260 | 0.2119 | 4223.1402 |
| R3_CORRECTED | CONTROL | 151 | 154624.0000 | 187313.1262 | 32689.1262 | 132689.1262 | 0.3269 | 0.2114 | 0.1722 | 7204.3510 |
| R3_CORRECTED | CONTRACTION_ONLY | 151 | 154624.0000 | 170614.6383 | 15990.6383 | 115990.6383 | 0.1599 | 0.1034 | 0.1258 | 8979.7178 |
| R3_CORRECTED | EXPANSION_ONLY | 151 | 154624.0000 | 185691.2214 | 31067.2214 | 131067.2214 | 0.3107 | 0.2009 | 0.2583 | 4761.3134 |
| R3_CORRECTED | BOTH | 151 | 154624.0000 | 225509.7219 | 70885.7219 | 170885.7219 | 0.7089 | 0.4584 | 0.1987 | 7516.9907 |

## Matched contrasts (exact-common denominator, per-issue matched)

| contrast | issues | lift_cny | ex_largest_lift_cny | bootstrap_p05_cny | bootstrap_median_cny | bootstrap_p95_cny |
|---|---|---|---|---|---|---|
| BASE=R0_CORRECTED|EFFECT=contraction | 151 | 32677.2700 | 45883.0103 | -14562.6061 | 33334.8254 | 78101.0668 |
| BASE=R0_CORRECTED|EFFECT=expansion | 151 | -11933.2926 | -19246.9824 | -38334.8397 | -11612.4045 | 14987.4251 |
| BASE=R0_CORRECTED|EFFECT=interaction | 151 | -24233.5508 | -16919.8610 | -51010.6834 | -24583.7557 | 175.3136 |
| BASE=R3_CORRECTED|EFFECT=contraction | 151 | -16698.4879 | 44239.8942 | -144432.2091 | -8736.4569 | 80396.6692 |
| BASE=R3_CORRECTED|EFFECT=expansion | 151 | -1621.9048 | -26761.2752 | -52517.3437 | -4672.4235 | 58958.1249 |
| BASE=R3_CORRECTED|EFFECT=interaction | 151 | 56516.9883 | 31377.6179 | 6290.8164 | 52719.7276 | 118395.6935 |
| SHAPE=CONTROL|LIFT=R3-R0 | 151 | 48683.0675 | -12255.3147 | -57704.6241 | 37917.8488 | 171000.3027 |
| SHAPE=CONTRACTION_ONLY|LIFT=R3-R0 | 151 | -692.6905 | -37657.3245 | -94303.3020 | -1734.0663 | 103202.6251 |
| SHAPE=EXPANSION_ONLY|LIFT=R3-R0 | 151 | 58994.4553 | 13290.6687 | -26085.6593 | 53690.5850 | 167840.5013 |
| SHAPE=BOTH|LIFT=R3-R0 | 151 | 90369.2365 | 40090.4957 | -13798.0749 | 86658.1909 | 212117.0987 |

## Capital-path risk (annual + ALL)

| scope | base | shape | max_drawdown_fraction | longest_losing_run | open_underwater_issues | largest_payout_share | payout_hhi |
|---|---|---|---|---|---|---|---|
| 2022 | R0_CORRECTED | BOTH | 0.3650 | 16 | 46 | 0.3491 | 0.2235 |
| 2022 | R0_CORRECTED | CONTRACTION_ONLY | 0.3056 | 16 | 46 | 0.3491 | 0.2235 |
| 2022 | R0_CORRECTED | CONTROL | 0.2394 | 11 | 51 | 0.2778 | 0.1544 |
| 2022 | R0_CORRECTED | EXPANSION_ONLY | 0.2502 | 12 | 51 | 0.1992 | 0.1269 |
| 2022 | R3_CORRECTED | BOTH | 0.2746 | 18 | 46 | 0.4865 | 0.3188 |
| 2022 | R3_CORRECTED | CONTRACTION_ONLY | 0.3298 | 21 | 46 | 0.4580 | 0.3650 |
| 2022 | R3_CORRECTED | CONTROL | 0.3317 | 19 | 51 | 0.2860 | 0.2159 |
| 2022 | R3_CORRECTED | EXPANSION_ONLY | 0.2536 | 17 | 51 | 0.3325 | 0.1772 |
| 2023 | R0_CORRECTED | BOTH | 0.2827 | 14 | 46 | 0.3505 | 0.2699 |
| 2023 | R0_CORRECTED | CONTRACTION_ONLY | 0.2296 | 10 | 46 | 0.3835 | 0.2721 |
| 2023 | R0_CORRECTED | CONTROL | 0.2658 | 14 | 44 | 0.2161 | 0.1521 |
| 2023 | R0_CORRECTED | EXPANSION_ONLY | 0.2943 | 14 | 46 | 0.2810 | 0.1641 |
| 2023 | R3_CORRECTED | BOTH | 0.1853 | 15 | 44 | 0.3727 | 0.2274 |
| 2023 | R3_CORRECTED | CONTRACTION_ONLY | 0.2579 | 26 | 12 | 0.4688 | 0.3541 |
| 2023 | R3_CORRECTED | CONTROL | 0.1248 | 18 | 38 | 0.7076 | 0.5231 |
| 2023 | R3_CORRECTED | EXPANSION_ONLY | 0.1844 | 14 | 38 | 0.7022 | 0.5077 |
| 2024 | R0_CORRECTED | BOTH | 0.0869 | 10 | 0 | 0.1856 | 0.0818 |
| 2024 | R0_CORRECTED | CONTRACTION_ONLY | 0.0695 | 10 | 0 | 0.2131 | 0.0902 |
| 2024 | R0_CORRECTED | CONTROL | 0.1068 | 6 | 29 | 0.1859 | 0.0849 |
| 2024 | R0_CORRECTED | EXPANSION_ONLY | 0.0817 | 6 | 8 | 0.1334 | 0.0667 |
| 2024 | R3_CORRECTED | BOTH | 0.1024 | 10 | 0 | 0.3397 | 0.1740 |
| 2024 | R3_CORRECTED | CONTRACTION_ONLY | 0.1563 | 11 | 1 | 0.3656 | 0.1924 |
| 2024 | R3_CORRECTED | CONTROL | 0.1750 | 7 | 1 | 0.2407 | 0.1343 |
| 2024 | R3_CORRECTED | EXPANSION_ONLY | 0.1521 | 7 | 1 | 0.2768 | 0.1332 |
| ALL | R0_CORRECTED | BOTH | 0.6265 | 16 | 146 | 0.1314 | 0.0517 |
| ALL | R0_CORRECTED | CONTRACTION_ONLY | 0.4850 | 16 | 0 | 0.1382 | 0.0533 |
| ALL | R0_CORRECTED | CONTROL | 0.3023 | 14 | 151 | 0.0953 | 0.0420 |
| ALL | R0_CORRECTED | EXPANSION_ONLY | 0.4755 | 14 | 151 | 0.0701 | 0.0345 |
| ALL | R3_CORRECTED | BOTH | 0.3291 | 22 | 0 | 0.2230 | 0.0914 |
| ALL | R3_CORRECTED | CONTRACTION_ONLY | 0.5008 | 31 | 1 | 0.2167 | 0.0977 |
| ALL | R3_CORRECTED | CONTROL | 0.3317 | 19 | 1 | 0.3253 | 0.1368 |
| ALL | R3_CORRECTED | EXPANSION_ONLY | 0.3426 | 17 | 1 | 0.2461 | 0.0988 |

## Mechanism attribution

Causal events counted only on the shapes that perform the operation.
`contracts_c_coverage_loss_issues` = CONTRACTION_ONLY / BOTH only: issues where
the realized outcome of fixture `c` equals its dropped (non-retained) support
outcome; PnL = control gross minus shape gross on those issues. The third
already-omitted outcome is not a contraction loss (neither arm covered it).
`expands_e_rescue_issues` = EXPANSION_ONLY / BOTH only: issues where the
realized outcome of fixture `e` equals its omitted third outcome; PnL = shape
gross minus control gross.

| base | shape | contracts_c | contracts_c_coverage_loss_issues | contracts_c_coverage_loss_pnl_cny | expands_e | expands_e_rescue_issues | expands_e_rescue_pnl_cny | pnl_shift_int_cny | pnl_shift_frac_cny | integer_vs_fractional_delta_cny |
|---|---|---|---|---|---|---|---|---|---|---|
| R0_CORRECTED | CONTRACTION_ONLY | True | 34 | 52976.3944 | False | 0 | 0.0000 | 32677.2700 | 32677.2700 | 0.0000 |
| R0_CORRECTED | EXPANSION_ONLY | False | 0 | 0.0000 | True | 29 | 31056.3111 | -11933.2926 | -14005.7086 | 2072.4160 |
| R0_CORRECTED | BOTH | True | 34 | 52976.3944 | True | 29 | 16800.3101 | -3489.5734 | -6504.8421 | 3015.2687 |
| R3_CORRECTED | CONTRACTION_ONLY | True | 29 | 102005.8071 | False | 0 | 0.0000 | -16698.4879 | -16698.4879 | 0.0000 |
| R3_CORRECTED | EXPANSION_ONLY | False | 0 | 0.0000 | True | 51 | 54085.5689 | -1621.9048 | -9199.0160 | 7577.1112 |
| R3_CORRECTED | BOTH | True | 29 | 102005.8071 | True | 51 | 108704.9556 | 38196.5956 | 24644.3927 | 13552.2029 |

## Expert admission gate

`standalone_ex_largest` removes the single largest-|PnL| issue's signed value
(#366 largest-absolute-delta semantics; tie: smallest index). Not disclosed
otherwise: REMOVE_LARGEST_ABS_PNL_ROW_SIGNED_VALUE.

| base | shape | standalone_pnl_cny | standalone_ex_largest_pnl_cny | matched_lift_cny | ex_largest_matched_lift_cny | bootstrap_p05_cny | annual_positive_lifts | annual_denominators | promotable | reason |
|---|---|---|---|---|---|---|---|---|---|---|
| R0_CORRECTED | CONTROL | -15993.9412 | -28175.6815 | nan | nan | nan | nan | nan | False | CONTROL is the corrected baseline; not an expert candidate |
| R0_CORRECTED | CONTRACTION_ONLY | 16683.3288 | -5973.0724 | 32677.2700 | 45883.0103 | -16717.3816 | 2.0000 | [51, 46, 54] | False | non-promotable historical evidence |
| R0_CORRECTED | EXPANSION_ONLY | -27927.2338 | -35783.3843 | -11933.2926 | -19246.9824 | -38224.0919 | 1.0000 | [51, 46, 54] | False | non-promotable historical evidence |
| R0_CORRECTED | BOTH | -19483.5146 | -36219.8155 | -3489.5734 | 9716.1669 | -47569.3652 | 1.0000 | [51, 46, 54] | False | non-promotable historical evidence |
| R3_CORRECTED | CONTROL | 32689.1262 | -27225.2559 | nan | nan | nan | nan | nan | False | CONTROL is the corrected baseline; not an expert candidate |
| R3_CORRECTED | CONTRACTION_ONLY | 15990.6383 | -19949.9957 | -16698.4879 | 44239.8942 | -143626.3604 | 2.0000 | [51, 46, 54] | False | non-promotable historical evidence |
| R3_CORRECTED | EXPANSION_ONLY | 31067.2214 | -13612.5651 | -1621.9048 | -26761.2752 | -52545.0687 | 2.0000 | [51, 46, 54] | False | non-promotable historical evidence |
| R3_CORRECTED | BOTH | 70885.7219 | 21630.9810 | 38196.5956 | 99134.9778 | -108149.0005 | 2.0000 | [51, 46, 54] | False | non-promotable historical evidence |

## Artifacts

- Package: `results/n7_support_shape/`
- Notebook: `notebooks/research/n7-support-shape/n7_support_shape.ipynb`
- Verifier: `scripts/verify_n7_support_shape.py` (replays #366, rebuilds frames, tamper tests in `tests/`)
