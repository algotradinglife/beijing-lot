# Issue #381 — corrected N6 fixed R0..R6 complete surface

Contract: `BJ-UNIFIED-N6-CORRECTED-ALL-R-001/v1`

## Decision

`FIXED_R_GRID_EXPOSED_DIAGNOSTIC_COMPLETE`. This is an exposed historical fixed-R diagnostic matrix,
not an R-selection exercise. `promotable_to_210=false`; **no exposed winner
replaces fixed R3**, #210/#218 stay unchanged, and a non-R3 positive standalone
point estimate may enter #378 only as an exposed diagnostic comparator.

Corrected R0/R3 exact parity with #376: **True**.
Legacy #352 common issue-arm rows changed in PnL: **79 / 1064**.

## Corrected per-arm performance (ALL scope)

| scope | arm | issues | ticket_count_per_issue | total_tickets | ticket_hit_rate | issue_hit_rate | issue_gross_positive_rate | issue_profitable_rate | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | ex_largest_pnl_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | R0 | 152 | 64 | 9728 | 0.0047 | 0.3026 | 0.3026 | 0.2697 | 155648.0000 | 122136.9084 | -33511.0916 | 66488.9084 | -0.3351 | -0.2153 | -40777.5442 |
| ALL | R1 | 152 | 64 | 9728 | 0.0042 | 0.2697 | 0.2697 | 0.2434 | 155648.0000 | 150201.1391 | -5446.8609 | 94553.1391 | -0.0545 | -0.0350 | -21976.8882 |
| ALL | R2 | 152 | 64 | 9728 | 0.0037 | 0.2368 | 0.2368 | 0.2171 | 155648.0000 | 133951.9803 | -21696.0197 | 78303.9803 | -0.2170 | -0.1394 | -38226.0470 |
| ALL | R3 | 152 | 64 | 9728 | 0.0037 | 0.2368 | 0.2368 | 0.2171 | 155648.0000 | 143348.0104 | -12299.9896 | 87700.0104 | -0.1230 | -0.0790 | -35959.6963 |
| ALL | R4 | 152 | 64 | 9728 | 0.0036 | 0.2303 | 0.2303 | 0.2105 | 155648.0000 | 141967.8346 | -13680.1654 | 86319.8346 | -0.1368 | -0.0879 | -37339.8720 |
| ALL | R5 | 152 | 64 | 9728 | 0.0034 | 0.2171 | 0.2171 | 0.1974 | 155648.0000 | 138518.3717 | -17129.6283 | 82870.3717 | -0.1713 | -0.1101 | -40789.3350 |
| ALL | R6 | 152 | 64 | 9728 | 0.0034 | 0.2171 | 0.2171 | 0.1974 | 155648.0000 | 138518.3717 | -17129.6283 | 82870.3717 | -0.1713 | -0.1101 | -40789.3350 |

## Path risk (ALL scope)

| scope | arm | max_drawdown_fraction | longest_profitable_issue_losing_run | open_underwater_issues | longest_losing_run | largest_payout_share | payout_hhi |
|---|---|---|---|---|---|---|---|
| ALL | R0 | 0.4932 | 12 | 152 | 12 | 0.0679 | 0.0309 |
| ALL | R1 | 0.4774 | 17 | 152 | 17 | 0.1169 | 0.0455 |
| ALL | R2 | 0.6441 | 19 | 152 | 19 | 0.1310 | 0.0508 |
| ALL | R3 | 0.4689 | 19 | 152 | 19 | 0.1722 | 0.0675 |
| ALL | R4 | 0.4827 | 19 | 152 | 19 | 0.1739 | 0.0688 |
| ALL | R5 | 0.5013 | 19 | 152 | 19 | 0.1782 | 0.0719 |
| ALL | R6 | 0.5013 | 19 | 152 | 19 | 0.1782 | 0.0719 |

## Matched lift versus corrected R0 and bootstrap stability

| scope | arm | issues | matched_lift_cny | largest_abs_delta_cny | largest_abs_delta_issue | ex_largest_lift_cny | issue_bootstrap_p05_cny | issue_bootstrap_median_cny | issue_bootstrap_p95_cny | moving_block_p05_cny | moving_block_median_cny | moving_block_p95_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2022 | R0 | 51 | 0.0000 | 0.0000 | nan | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2022 | R1 | 51 | -2903.9138 | 3500.9414 | 22073.0000 | -6404.8551 | -12051.0054 | -3058.0685 | 6685.4482 | -13546.6711 | -2963.3961 | 7912.3700 |
| 2022 | R2 | 51 | -5290.2807 | 3500.9414 | 22073.0000 | -8791.2221 | -14739.6977 | -5275.0517 | 4315.6363 | -16108.0077 | -5464.3809 | 6531.7011 |
| 2022 | R3 | 51 | -6133.2205 | -4798.6550 | 22095.0000 | -1334.5655 | -20551.5661 | -6138.2733 | 7743.4480 | -20174.0958 | -5994.2717 | 6821.0833 |
| 2022 | R4 | 51 | -7513.3962 | -4798.6550 | 22095.0000 | -2714.7412 | -22254.8093 | -7436.6909 | 6079.7304 | -22435.2783 | -7042.8069 | 6421.9581 |
| 2022 | R5 | 51 | -7513.3962 | -4798.6550 | 22095.0000 | -2714.7412 | -21772.4375 | -7410.7487 | 6434.3264 | -22730.9537 | -7430.9960 | 6231.7661 |
| 2022 | R6 | 51 | -7513.3962 | -4798.6550 | 22095.0000 | -2714.7412 | -22252.1701 | -7308.9193 | 7398.1285 | -22440.1096 | -7159.1766 | 6722.2802 |
| 2023 | R0 | 47 | 0.0000 | 0.0000 | nan | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2023 | R1 | 47 | 9706.4085 | 8753.2539 | 23103.0000 | 953.1546 | -11367.1780 | 9305.5457 | 33693.7936 | -10275.5858 | 9908.5891 | 28689.1025 |
| 2023 | R2 | 47 | -3714.3660 | 5846.7757 | 23024.0000 | -9561.1417 | -24990.7023 | -3500.7402 | 17817.0439 | -29713.7840 | -4369.9857 | 22303.6970 |
| 2023 | R3 | 47 | 17026.2334 | 24683.7066 | 23021.0000 | -7657.4732 | -20844.7740 | 13910.4192 | 65094.2540 | -24180.5296 | 14784.0124 | 61738.4558 |
| 2023 | R4 | 47 | 17026.2334 | 24683.7066 | 23021.0000 | -7657.4732 | -20667.0044 | 14118.9612 | 68148.7912 | -23408.5621 | 16345.2018 | 64090.3994 |
| 2023 | R5 | 47 | 17026.2334 | 24683.7066 | 23021.0000 | -7657.4732 | -21551.1012 | 14228.8602 | 68389.6223 | -24096.0361 | 14581.7075 | 62322.3335 |
| 2023 | R6 | 47 | 17026.2334 | 24683.7066 | 23021.0000 | -7657.4732 | -21290.9316 | 14138.1872 | 64625.1974 | -23632.2800 | 15241.1732 | 62352.6108 |
| 2024 | R0 | 54 | 0.0000 | 0.0000 | nan | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 2024 | R1 | 54 | 21261.7360 | 17554.0273 | 24104.0000 | 3707.7087 | -16835.9661 | 19389.2925 | 67274.8565 | -18903.3432 | 20407.2412 | 63172.5034 |
| 2024 | R2 | 54 | 20819.7186 | 17554.0273 | 24104.0000 | 3265.6913 | -21018.9928 | 19340.4469 | 67091.2178 | -19706.9521 | 19299.2892 | 65243.3409 |
| 2024 | R3 | 54 | 10318.0891 | 17554.0273 | 24104.0000 | -7235.9382 | -28509.2003 | 9074.9274 | 54891.8852 | -27471.4211 | 8846.2066 | 54379.4348 |
| 2024 | R4 | 54 | 10318.0891 | 17554.0273 | 24104.0000 | -7235.9382 | -29148.6282 | 8500.3950 | 54996.0036 | -27745.6283 | 9030.6629 | 56579.1572 |
| 2024 | R5 | 54 | 6868.6261 | 17554.0273 | 24104.0000 | -10685.4012 | -32117.3708 | 6185.9655 | 52337.6101 | -32350.7593 | 4885.7553 | 52300.9832 |
| 2024 | R6 | 54 | 6868.6261 | 17554.0273 | 24104.0000 | -10685.4012 | -32168.7080 | 5296.2822 | 51432.1831 | -32337.5755 | 5622.4388 | 51982.5195 |
| ALL | R0 | 152 | 0.0000 | 0.0000 | nan | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| ALL | R1 | 152 | 28064.2307 | 17554.0273 | 24104.0000 | 10510.2034 | -18913.0266 | 27188.8331 | 80323.9859 | -20256.0890 | 27547.1260 | 79556.7646 |
| ALL | R2 | 152 | 11815.0720 | 17554.0273 | 24104.0000 | -5738.9553 | -35958.5234 | 10373.0787 | 65078.4297 | -38795.9146 | 10694.0931 | 69495.0760 |
| ALL | R3 | 152 | 21211.1020 | 24683.7066 | 23021.0000 | -3472.6047 | -38789.5827 | 18464.1055 | 86591.7939 | -40515.4680 | 18872.6943 | 88669.2300 |
| ALL | R4 | 152 | 19830.9263 | 24683.7066 | 23021.0000 | -4852.7804 | -40593.4756 | 17084.9388 | 87286.8651 | -43873.3382 | 16774.0921 | 89749.7722 |
| ALL | R5 | 152 | 16381.4633 | 24683.7066 | 23021.0000 | -8302.2434 | -42216.9484 | 13909.5997 | 82323.1863 | -46629.3121 | 15616.6298 | 86049.3791 |
| ALL | R6 | 152 | 16381.4633 | 24683.7066 | 23021.0000 | -8302.2434 | -43059.2936 | 14301.6492 | 83095.4541 | -48050.7872 | 14197.6442 | 84751.0324 |

The issue bootstrap and the chronology-preserving moving-block bootstrap
(block length 10, 5000 draws) both remain
negative at their p05 bounds for most arms, consistent with the historical
long-tail challenge established for corrected R3 in #376.

## Rolling 20/30/50-issue windows (ALL scope)

| arm | window_issues | windows | worst_window_pnl_cny | p10_window_pnl_cny | median_window_pnl_cny | positive_window_rate |
|---|---|---|---|---|---|---|
| R0 | 20 | 133 | -18647.4536 | -13723.2143 | -4500.0797 | 0.3233 |
| R0 | 30 | 123 | -23362.1536 | -18904.3420 | -7820.6347 | 0.3659 |
| R0 | 50 | 103 | -26045.6521 | -23120.3904 | -16078.2423 | 0.2233 |
| R1 | 20 | 133 | -16835.0669 | -12368.4418 | -8381.1080 | 0.3233 |
| R1 | 30 | 123 | -20331.8015 | -16612.6301 | -10619.2765 | 0.2927 |
| R1 | 50 | 103 | -28898.6619 | -25076.4267 | -12463.5219 | 0.2330 |
| R2 | 20 | 133 | -18941.9440 | -14179.0036 | -9265.1336 | 0.1579 |
| R2 | 30 | 123 | -24419.0036 | -19505.1336 | -12657.9420 | 0.1382 |
| R2 | 50 | 103 | -33805.4020 | -29559.7366 | -24170.9969 | 0.1165 |
| R3 | 20 | 133 | -18941.9440 | -14087.1552 | -8516.5138 | 0.2632 |
| R3 | 30 | 123 | -20971.7746 | -19591.5988 | -9852.8556 | 0.3415 |
| R3 | 50 | 103 | -32127.9686 | -27239.9302 | -5770.8902 | 0.1456 |
| R4 | 20 | 133 | -18941.9440 | -14087.1552 | -8516.5138 | 0.2632 |
| R4 | 30 | 123 | -21395.2932 | -20810.6737 | -9852.8556 | 0.3415 |
| R4 | 50 | 103 | -33508.1444 | -27815.7760 | -7099.1455 | 0.1456 |
| R5 | 20 | 133 | -18941.9440 | -14633.2243 | -10203.8520 | 0.2406 |
| R5 | 30 | 123 | -21395.2932 | -20810.6737 | -11710.6199 | 0.3415 |
| R5 | 50 | 103 | -33508.1444 | -28810.7517 | -7099.1455 | 0.1262 |
| R6 | 20 | 133 | -18941.9440 | -14633.2243 | -10203.8520 | 0.2406 |
| R6 | 30 | 123 | -21395.2932 | -20810.6737 | -11710.6199 | 0.3415 |
| R6 | 50 | 103 | -33508.1444 | -28810.7517 | -7099.1455 | 0.1262 |

## Action-depth saturation and set-based replacement attribution

| arm | activated_legs | noop_legs | replaced_legs | saturated_legs |
|---|---|---|---|---|
| R0 | 0 | 0 | 0 | 0 |
| R1 | 172 | 29 | 143 | 0 |
| R2 | 344 | 105 | 239 | 0 |
| R3 | 516 | 221 | 295 | 0 |
| R4 | 688 | 370 | 318 | 0 |
| R5 | 860 | 536 | 324 | 0 |
| R6 | 1032 | 708 | 324 | 0 |

The Mx3 construction leaves exactly one omitted outcome per leg, so the
candidate replacement set is always a singleton; `saturated_legs == 0` is
structural and disclosed rather than assumed. `noop_legs` records activated
legs whose support is unchanged (pressure-zero). Per-leg replacement detail,
including replaced/replacement outcomes, activation depth and the
`dropped_is_probability_first` flag, is in `support_attribution.parquet`.

## Replacement-rule interpretation disclosure

1643 replaced legs in total, of which
**166** drop the probability-first
pair member under the accepted #376 QEU Top-2 transfer; activated no-op legs:
**1969**. Candidate set size max
1; saturation events
0. See
`docs/research/Issue-381-PROTOCOL-LOG.md` entry 001.

## Settlement coverage

| issue_year | settlement_complete | issues |
|---|---|---|
| 2022 | False | 7 |
| 2022 | True | 51 |
| 2023 | False | 8 |
| 2023 | True | 47 |
| 2024 | False | 5 |
| 2024 | True | 54 |

The corrected registry contains **172** issues. Exactly
**152** issues are settled on the
exact-common denominator across all seven arms.

## Exact R0/R3 parity with corrected #376

| check | result |
|---|---|
| decisions | True |
| tickets | True |
| issue bundles | True |
| support attribution | True |
| performance | True |
| risk diagnostics | True |
| capital paths | True |
| coverage ledger | True |
| #376 bootstrap reproduction | True |
| point matched lift | True |

## Corrected-versus-legacy #352 ledger (R0..R6)

| arm | legacy_rows | corrected_rows | common_issues | exact_rows | changed_pnl_rows | year_routing_changed_rows | legacy_only_issue_arm_rows | corrected_only_issue_arm_rows | attribution_common_legs | attribution_exact_legs | legacy_only_unique_issues | corrected_only_unique_issues |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R0 | 159 | 152 | 152 | 96 | 16 | 8 | 7 | 0 | 975 | 950 | nan | nan |
| R1 | 159 | 152 | 152 | 95 | 13 | 8 | 7 | 0 | 975 | 934 | nan | nan |
| R2 | 159 | 152 | 152 | 94 | 14 | 8 | 7 | 0 | 975 | 930 | nan | nan |
| R3 | 159 | 152 | 152 | 95 | 11 | 8 | 7 | 0 | 975 | 939 | nan | nan |
| R4 | 159 | 152 | 152 | 94 | 9 | 8 | 7 | 0 | 975 | 938 | nan | nan |
| R5 | 159 | 152 | 152 | 95 | 8 | 8 | 7 | 0 | 975 | 941 | nan | nan |
| R6 | 159 | 152 | 152 | 95 | 8 | 8 | 7 | 0 | 975 | 941 | nan | nan |
| ALL | 1113 | 1064 | 1064 | 664 | 79 | 56 | 49 | 0 | 6825 | 6573 | 7.0000 | 0.0000 |

## Evidence boundary

- Upstream is the verified corrected #376 package only; #352 is never a source surface.
- Registry year and fixture-relative 10h decision time come from the source-bound
  #360 contract; every training label is strictly earlier than its fixture decision.
- R grid is exactly 0..6. No dynamic R, thresholds, selector retuning, seed mining,
  allocator search, or post-outcome R selection is used.
- 2022–2024 are exposed historical evidence; no row is holdout or tuning data.
- #210 and #218 are unchanged. #378 may consume non-R3 arms only as exposed
  diagnostic comparators.

## Artifacts

- Package: `results/n6_all_r_diagnostic/`
- Notebook: `notebooks/research/n6-all-r-diagnostic/n6_all_r_diagnostic.ipynb`
- Figures: `docs/research/figures/issue_381_n6_all_r_capital.png`,
  `docs/research/figures/issue_381_n6_all_r_lift.png`
- Protocol log: `docs/research/Issue-381-PROTOCOL-LOG.md` (interpretation disclosure)
