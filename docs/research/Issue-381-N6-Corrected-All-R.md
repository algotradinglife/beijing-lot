# Issue #381 — corrected N6 fixed-R0–R6 diagnostic

Contract: `BJ-UNIFIED-N6-CORRECTED-ALL-R-001/v2`

## Shared cutoff-learning lineage

This diagnostic is a downstream client of `BJ-UNIFIED-CUTOFF-LEARNING-001/v2` rather
than a local chronology implementation.  It passes the explicit
`EVALUATION_YEAR_2022` boundary at `2021-12-31T11:00:00+00:00`; the latest
admitted training label is `2021-12-31T09:00:00+00:00`.
The source-bound replay reconciles `48658` /
`48658` mapped-probability cells exactly to
the shared cutoff client.  No detached mapping-acceptance boolean controls this
surface.

## Decision

`COMPLETE_CORRECTED_N6_R_SURFACE_DIAGNOSTIC_ONLY`. Positive standalone point-estimate R rows: `[]`. None replaces fixed R3 or enters the expert pool; any positive row may enter #378 only as an explicitly exposed comparator.

## Full-sample economics, path risk and tail sensitivity

| scope | r | issues_x | stake_cny | gross_cny | pnl_cny | ending_capital_cny | capital_return | stake_roi | ticket_hit_rate | issue_hit_rate | issue_profitable_rate | armwise_ex_largest_pnl_cny | max_drawdown_fraction | longest_profitable_issue_losing_run | open_underwater_issues | largest_payout_share | payout_hhi | issues_y | matched_lift_cny | armwise_ex_largest_lift_cny | largest_absolute_paired_delta_cny | largest_absolute_paired_delta_issue | lift_ex_largest_absolute_paired_delta_cny |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ALL | 0 | 152 | 155648.0000 | 122136.9084 | -33511.0916 | 66488.9084 | -0.3351 | -0.2153 | 0.0047 | 0.3026 | 0.2697 | -40777.5442 | 0.4932 | 12 | 152 | 0.0679 | 0.0309 | 152 | 0.0000 | 0.0000 | 0.0000 | 22013 | 0.0000 |
| ALL | 1 | 152 | 155648.0000 | 150201.1391 | -5446.8609 | 94553.1391 | -0.0545 | -0.0350 | 0.0042 | 0.2697 | 0.2434 | -21976.8882 | 0.4774 | 17 | 152 | 0.1169 | 0.0455 | 152 | 28064.2307 | 18800.6561 | 17554.0273 | 24104 | 10510.2034 |
| ALL | 2 | 152 | 155648.0000 | 133951.9803 | -21696.0197 | 78303.9803 | -0.2170 | -0.1394 | 0.0037 | 0.2368 | 0.2171 | -38226.0470 | 0.6441 | 19 | 152 | 0.1310 | 0.0508 | 152 | 11815.0720 | 2551.4973 | 17554.0273 | 24104 | -5738.9553 |
| ALL | 3 | 152 | 155648.0000 | 143348.0104 | -12299.9896 | 87700.0104 | -0.1230 | -0.0790 | 0.0037 | 0.2368 | 0.2171 | -35959.6963 | 0.4689 | 19 | 152 | 0.1722 | 0.0675 | 152 | 21211.1020 | 4817.8480 | 24683.7066 | 23021 | -3472.6047 |
| ALL | 4 | 152 | 155648.0000 | 141967.8346 | -13680.1654 | 86319.8346 | -0.1368 | -0.0879 | 0.0036 | 0.2303 | 0.2105 | -37339.8720 | 0.4827 | 19 | 152 | 0.1739 | 0.0688 | 152 | 19830.9263 | 3437.6722 | 24683.7066 | 23021 | -4852.7804 |
| ALL | 5 | 152 | 155648.0000 | 138518.3717 | -17129.6283 | 82870.3717 | -0.1713 | -0.1101 | 0.0034 | 0.2171 | 0.1974 | -40789.3350 | 0.5013 | 19 | 152 | 0.1782 | 0.0719 | 152 | 16381.4633 | -11.7907 | 24683.7066 | 23021 | -8302.2434 |
| ALL | 6 | 152 | 155648.0000 | 138518.3717 | -17129.6283 | 82870.3717 | -0.1713 | -0.1101 | 0.0034 | 0.2171 | 0.1974 | -40789.3350 | 0.5013 | 19 | 152 | 0.1782 | 0.0719 | 152 | 16381.4633 | -11.7907 | 24683.7066 | 23021 | -8302.2434 |

## Annual PnL

| r | 2022 | 2023 | 2024 |
|---|---|---|---|
| 0 | -22412.1996 | -19725.1236 | 8626.2315 |
| 1 | -25316.1133 | -10018.7151 | 29887.9675 |
| 2 | -27702.4803 | -23439.4896 | 29445.9501 |
| 3 | -28545.4201 | -2698.8902 | 18944.3206 |
| 4 | -29925.5958 | -2698.8902 | 18944.3206 |
| 5 | -29925.5958 | -2698.8902 | 15494.8576 |
| 6 | -29925.5958 | -2698.8902 | 15494.8576 |

## Matched lift moving-block evidence

| scope | r | draws | block_length | lift_p05_cny | lift_median_cny | lift_p95_cny |
|---|---|---|---|---|---|---|
| ALL | 0 | 2000 | 10 | 0.0000 | 0.0000 | 0.0000 |
| ALL | 1 | 2000 | 10 | -20725.4280 | 26990.5048 | 78464.7269 |
| ALL | 2 | 2000 | 10 | -40960.0146 | 9936.0199 | 67047.1593 |
| ALL | 3 | 2000 | 10 | -40182.2664 | 20071.6386 | 90472.6997 |
| ALL | 4 | 2000 | 10 | -46550.0229 | 18179.3645 | 90400.4493 |
| ALL | 5 | 2000 | 10 | -48324.5336 | 14817.9250 | 88410.3194 |
| ALL | 6 | 2000 | 10 | -45893.2810 | 13378.8141 | 81829.6200 |

## Action-depth saturation

| scope | r | issues | mean_eligible_changed_legs | mean_actual_changed_legs | support_set_change_rate_vs_prior_r | fully_saturated_rate |
|---|---|---|---|---|---|---|
| ALL | 0 | 172 | 1.8837 | 0.0000 | 0.0000 | 0.1686 |
| ALL | 1 | 172 | 1.8837 | 0.8314 | 0.8314 | 0.4419 |
| ALL | 2 | 172 | 1.8837 | 1.3895 | 0.5581 | 0.6744 |
| ALL | 3 | 172 | 1.8837 | 1.7151 | 0.3256 | 0.8663 |
| ALL | 4 | 172 | 1.8837 | 1.8488 | 0.1337 | 0.9651 |
| ALL | 5 | 172 | 1.8837 | 1.8837 | 0.0349 | 1.0000 |
| ALL | 6 | 172 | 1.8837 | 1.8837 | 0.0000 | 1.0000 |

## Rolling path risk

| r | window_issues | windows | loss_probability | worst_window_pnl_cny | median_window_pnl_cny |
|---|---|---|---|---|---|
| 0 | 20 | 133 | 0.6767 | -18647.4536 | -4500.0797 |
| 0 | 30 | 123 | 0.6341 | -23362.1536 | -7820.6347 |
| 0 | 50 | 103 | 0.7767 | -26045.6521 | -16078.2423 |
| 1 | 20 | 133 | 0.6767 | -16835.0669 | -8381.1080 |
| 1 | 30 | 123 | 0.7073 | -20331.8015 | -10619.2765 |
| 1 | 50 | 103 | 0.7670 | -28898.6619 | -12463.5219 |
| 2 | 20 | 133 | 0.8421 | -18941.9440 | -9265.1336 |
| 2 | 30 | 123 | 0.8618 | -24419.0036 | -12657.9420 |
| 2 | 50 | 103 | 0.8835 | -33805.4020 | -24170.9969 |
| 3 | 20 | 133 | 0.7368 | -18941.9440 | -8516.5138 |
| 3 | 30 | 123 | 0.6585 | -20971.7746 | -9852.8556 |
| 3 | 50 | 103 | 0.8544 | -32127.9686 | -5770.8902 |
| 4 | 20 | 133 | 0.7368 | -18941.9440 | -8516.5138 |
| 4 | 30 | 123 | 0.6585 | -21395.2932 | -9852.8556 |
| 4 | 50 | 103 | 0.8544 | -33508.1444 | -7099.1455 |
| 5 | 20 | 133 | 0.7594 | -18941.9440 | -10203.8520 |
| 5 | 30 | 123 | 0.6585 | -21395.2932 | -11710.6199 |
| 5 | 50 | 103 | 0.8738 | -33508.1444 | -7099.1455 |
| 6 | 20 | 133 | 0.7594 | -18941.9440 | -10203.8520 |
| 6 | 30 | 123 | 0.6585 | -21395.2932 | -11710.6199 |
| 6 | 50 | 103 | 0.8738 | -33508.1444 | -7099.1455 |

## Corrected versus legacy #352

| r | legacy_rows | corrected_rows | common_rows | year_exact_rows | fixture_exact_rows | support_exact_rows | pnl_exact_rows | changed_pnl_rows | corrected_minus_legacy_common_pnl_cny |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 159 | 152 | 152 | 144 | 103 | 2 | 136 | 16 | 4040.5993 |
| 1 | 159 | 152 | 152 | 144 | 103 | 2 | 139 | 13 | 28524.0461 |
| 2 | 159 | 152 | 152 | 144 | 103 | 2 | 138 | 14 | -7295.8291 |
| 3 | 159 | 152 | 152 | 144 | 103 | 3 | 141 | 11 | -26945.5917 |
| 4 | 159 | 152 | 152 | 144 | 103 | 3 | 143 | 9 | -5699.6517 |
| 5 | 159 | 152 | 152 | 144 | 103 | 3 | 144 | 8 | -7291.3504 |
| 6 | 159 | 152 | 152 | 144 | 103 | 3 | 144 | 8 | -7291.3504 |

## Interpretation boundary

R0 and R3 exactly reproduce #376 on 304 issue-arm rows. R1/R2/R4/R5/R6 are newly reconstructed on the same corrected source, not copied from #352. The complete matrix is exposed retrospective evidence and is not an R-selection surface. Two tail diagnostics are deliberately separate: armwise removal of each arm's largest payout and removal of the single largest absolute paired delta. #210/#218 and prospective evidence remain untouched.
