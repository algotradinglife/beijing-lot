# N3 outcome-level EV depth coverage

- Probability input: handicap-aware walk-forward calibration from the existing N3 calibration pipeline.
- Outcome EV: `q_cal = p_cal * estimated_sp`; `single_ev = 0.65 * q_cal - 1`.
- Every 3/1/0 outcome can receive coverage depth; depth target is an increasing function of EV.
- Ticket construction keeps 3 distinct matches per ticket and optionally controls how many high-EV outcomes each ticket contains.
- Same budget: every active issue is replayed at 256 units with fractional scaling.
- Reported depth correlations test the intended invariant: actual outcome coverage depth should be positively correlated with `q_cal`.

## Summary

| strategy | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | roi_ex_best_on_fixed_budget | recent_profit_units | recent_roi_on_deployed_stake | depth_coverage_spearman_q_depth | depth_avg_issue_spearman_q_depth | depth_zero_depth_share | mix_h3_share_actual | mix_h2_share_actual | mix_h1_share_actual |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 672 | -9916.8948 | -0.0576 | 0.3869 | 0.9583 | -10285.0167 | 3 | -0.0661 | -1990.1114 | -0.0603 | 0.7347 | 0.9682 | 0.0889 | 0.4473 | 0.3515 | 0.2012 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 672 | -12619.1050 | -0.0734 | 0.3571 | 0.9613 | -12926.2131 | 3 | -0.0821 | -3522.9248 | -0.1067 | 0.7565 | 0.9736 | 0.0871 | 0.4446 | 0.3542 | 0.2012 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 672 | -13089.3314 | -0.0761 | 0.3690 | 0.9613 | -13187.9727 | 3 | -0.0848 | -5768.9486 | -0.1747 | 0.7592 | 0.9233 | 0.0366 | 0.3170 | 0.3377 | 0.3378 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 672 | -14516.3410 | -0.0844 | 0.3676 | 0.9717 | -14537.0573 | 3 | -0.0914 | -5501.5075 | -0.1666 | 0.7190 | 0.9682 | 0.0294 | 0.3239 | 0.3418 | 0.3343 |
| n3_outcome_evdepth_abs_45h3_35h2_20h1_singleev__budget256_fractional | 672 | -15341.9207 | -0.0892 | 0.3571 | 0.9464 | -16164.4597 | 3 | -0.0986 | -7608.0816 | -0.2304 | 0.8373 | 0.9556 | 0.0810 | 0.4353 | 0.3504 | 0.2068 |
| n3_outcome_evdepth_unconstrained_singleev__budget256_fractional | 672 | -17196.2446 | -0.1000 | 0.3676 | 0.9449 | -17274.5302 | 3 | -0.1087 | -4917.8158 | -0.1489 | 0.6950 | 0.9713 | 0.0087 | 0.4165 | 0.1344 | 0.2351 |


## Depth Correlation

| strategy | n_options | coverage_pearson_q_depth | coverage_spearman_q_depth | target_spearman_q_depth | avg_issue_spearman_q_depth | avg_actual_depth | zero_depth_share | avg_q_selected_options | avg_q_all_options | actual_depth_weighted_hit_rate | avg_winning_sp_on_hit_options |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev | 57927 | 0.5834 | 0.7592 | 0.7027 | 0.9233 | 6.2644 | 0.0366 | 2.5439 | 2.5120 | 0.4367 | 2.7370 |
| n3_outcome_evdepth_abs_45h3_35h2_20h1_singleev | 57927 | 0.6056 | 0.8373 | 0.7027 | 0.9556 | 6.2644 | 0.0810 | 2.5808 | 2.5120 | 0.4395 | 2.7370 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev | 57927 | 0.6334 | 0.7190 | 0.7027 | 0.9682 | 6.2644 | 0.0294 | 2.5382 | 2.5120 | 0.4372 | 2.7370 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev | 62243 | 0.6461 | 0.7347 | 0.6429 | 0.9682 | 5.8301 | 0.0889 | 2.5290 | 2.4294 | 0.4345 | 2.7722 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev | 57927 | 0.6534 | 0.7565 | 0.7027 | 0.9736 | 6.2644 | 0.0871 | 2.5842 | 2.5120 | 0.4405 | 2.7370 |
| n3_outcome_evdepth_unconstrained_singleev | 57927 | 0.6022 | 0.6950 | 0.7027 | 0.9713 | 6.2644 | 0.0087 | 2.5203 | 2.5120 | 0.4351 | 2.7370 |


## Mix Realization

| strategy | tickets | h3_share_actual | h2_share_actual | h1_share_actual | h0_share_actual | avg_ticket_ev_proxy | avg_ticket_q_product | top_patterns |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev | 120960 | 0.3170 | 0.3377 | 0.3378 | 0.0074 | 24.5358 | 39.2858 | HHH:38350;MHH:32486;MMH:28413;MLH:8493;LHH:8364;LLH:3954 |
| n3_outcome_evdepth_abs_45h3_35h2_20h1_singleev | 120960 | 0.4353 | 0.3504 | 0.2068 | 0.0074 | 27.8498 | 44.3843 | HHH:52650;MHH:35528;MMH:18808;LHH:6862;MLH:4251;LLH:1961 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev | 120960 | 0.3239 | 0.3418 | 0.3343 | 0.0000 | 25.3055 | 40.4700 | HHH:39176;MHH:26395;MMH:19721;LHH:14949;MLH:12227;LLH:8492 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev | 120960 | 0.4473 | 0.3515 | 0.2012 | 0.0000 | 25.7036 | 41.0825 | HHH:54108;MHH:30039;MMH:14454;LHH:12477;MLH:5580;LLH:4302 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev | 120960 | 0.4446 | 0.3542 | 0.2012 | 0.0000 | 28.6986 | 45.6902 | HHH:53784;MHH:30232;MMH:13885;LHH:12608;MLH:6455;LLH:3996 |
| n3_outcome_evdepth_unconstrained_singleev | 120960 | 0.4165 | 0.1344 | 0.2351 | 0.2140 | 26.3563 | 42.0866 | HHH:50382;MMH:19027;MHH:13850;MMM:12590;MLH:6554;MML:6416 |


## Annual For Top Strategies

| strategy | year | n_issues | profit_units | roi_on_deployed_stake | issue_win_rate | non_full_loss_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2014 | 116 | -2801.0373 | -0.0943 | 0.3448 | 0.9310 | -3584.6990 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2015 | 56 | 862.5357 | 0.0602 | 0.5179 | 1.0000 | -590.4297 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2016 | 52 | -1504.4222 | -0.1130 | 0.3846 | 0.9808 | -2254.5725 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2017 | 46 | 785.1876 | 0.0667 | 0.5217 | 1.0000 | -531.8304 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2018 | 58 | -1487.5084 | -0.1002 | 0.3448 | 0.9655 | -1571.5869 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2019 | 55 | -1497.4746 | -0.1064 | 0.3273 | 1.0000 | -1579.1614 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2020 | 44 | -1679.4036 | -0.1491 | 0.3182 | 0.9091 | -1981.7324 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2021 | 58 | 1103.5485 | 0.0743 | 0.3793 | 0.9655 | -1097.9010 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2022 | 58 | -1101.8085 | -0.0742 | 0.3621 | 0.9655 | -1664.8723 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2023 | 55 | -1057.4255 | -0.0751 | 0.3636 | 0.9455 | -1899.2463 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2024 | 59 | -3514.7232 | -0.2327 | 0.2373 | 0.9492 | -3942.8070 |
| n3_outcome_evdepth_abs_33h3_34h2_33h1_singleev__budget256_fractional | 2025 | 15 | -1196.7999 | -0.3117 | 0.4000 | 0.9333 | -1300.1128 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2014 | 116 | -2974.9546 | -0.1002 | 0.3707 | 0.9483 | -3677.9086 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2015 | 56 | 22.4145 | 0.0016 | 0.3929 | 1.0000 | -1438.6939 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2016 | 52 | -1716.4155 | -0.1289 | 0.3269 | 0.9808 | -2303.4509 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2017 | 46 | 546.2535 | 0.0464 | 0.3913 | 1.0000 | -605.9368 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2018 | 58 | -2223.6568 | -0.1498 | 0.2931 | 0.9828 | -2223.6568 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2019 | 55 | -1022.3364 | -0.0726 | 0.4000 | 1.0000 | -1216.8866 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2020 | 44 | -758.3108 | -0.0673 | 0.3409 | 0.8864 | -1668.7642 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2021 | 58 | 766.6418 | 0.0516 | 0.4828 | 0.9828 | -1372.0282 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2022 | 58 | -1654.4692 | -0.1114 | 0.3276 | 0.9655 | -1752.1574 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2023 | 55 | -1720.6261 | -0.1222 | 0.3818 | 0.9818 | -2456.8603 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2024 | 59 | -3081.1495 | -0.2040 | 0.3390 | 0.9661 | -3386.6972 |
| n3_outcome_evdepth_local_33h3_34h2_33h1_singleev__budget256_fractional | 2025 | 15 | -699.7319 | -0.1822 | 0.3333 | 1.0000 | -720.4482 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2014 | 116 | -1670.6803 | -0.0563 | 0.3448 | 0.9052 | -2923.1276 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2015 | 56 | -656.9035 | -0.0458 | 0.3750 | 1.0000 | -1636.6484 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2016 | 52 | -775.7081 | -0.0583 | 0.4423 | 1.0000 | -872.0735 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2017 | 46 | -112.3818 | -0.0095 | 0.3913 | 0.9565 | -1025.8195 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2018 | 58 | -1963.3364 | -0.1322 | 0.3621 | 0.9655 | -2171.6994 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2019 | 55 | -542.9446 | -0.0386 | 0.4909 | 0.9818 | -1161.9455 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2020 | 44 | -193.5786 | -0.0172 | 0.4091 | 0.8864 | -1640.4199 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2021 | 58 | 1575.9334 | 0.1061 | 0.5000 | 0.9828 | -915.5553 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2022 | 58 | -3587.1835 | -0.2416 | 0.2414 | 0.9310 | -3587.1835 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2023 | 55 | -21.1420 | -0.0015 | 0.4000 | 1.0000 | -1223.2347 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2024 | 59 | -2106.4017 | -0.1395 | 0.3390 | 0.9661 | -2415.0223 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_n3ev__budget256_fractional | 2025 | 15 | 137.4323 | 0.0358 | 0.4667 | 1.0000 | -406.3806 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2014 | 116 | -2386.5621 | -0.0804 | 0.3534 | 0.9397 | -3541.9075 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2015 | 56 | 647.1526 | 0.0451 | 0.4464 | 1.0000 | -1445.6007 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2016 | 52 | -1557.7477 | -0.1170 | 0.3269 | 1.0000 | -2546.8682 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2017 | 46 | 88.8144 | 0.0075 | 0.4348 | 0.9783 | -666.1152 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2018 | 58 | -1790.6423 | -0.1206 | 0.2931 | 0.9655 | -2003.1189 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2019 | 55 | -1358.7286 | -0.0965 | 0.3636 | 1.0000 | -2054.6714 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2020 | 44 | -1842.7650 | -0.1636 | 0.2727 | 0.9091 | -2705.7515 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2021 | 58 | 1495.9136 | 0.1007 | 0.4483 | 0.9310 | -1257.1258 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2022 | 58 | -2391.6151 | -0.1611 | 0.2586 | 0.9483 | -2519.2120 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2023 | 55 | -813.2950 | -0.0578 | 0.3818 | 0.9455 | -1776.0543 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2024 | 59 | -1866.3288 | -0.1236 | 0.3559 | 0.9661 | -2470.7894 |
| n3_outcome_evdepth_local_45h3_35h2_20h1_singleev__budget256_fractional | 2025 | 15 | -843.3011 | -0.2196 | 0.3333 | 1.0000 | -901.2265 |


Equity curve SVG: `docs/research/figures/n3_outcome_ev_depth_coverage_equity_2026-06-28.svg`

## Files

- Summary: `results/n3_outcome_ev_depth_coverage_20260628/n3_outcome_ev_depth_summary.csv`
- Option depth: `results/n3_outcome_ev_depth_coverage_20260628/n3_outcome_ev_depth_option_depth.csv`
- Depth correlation: `results/n3_outcome_ev_depth_coverage_20260628/n3_outcome_ev_depth_correlation.csv`
- Annual: `results/n3_outcome_ev_depth_coverage_20260628/n3_outcome_ev_depth_annual.csv`
