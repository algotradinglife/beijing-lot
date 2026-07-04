# N7 Recommended Strategy Attribution

## Scope

- Target portfolio: `grid_c144_p48_draw_top_ev_k1_n5ov64`.
- Allocation: `144` original N7 core + `48` top-EV draw-protected ticket + `64` N5 overlap.
- Protected ticket analysis compares the protected top-EV ticket against the same unprotected source ticket.

## Component Attribution

| component | stake_units | profit_units | profit_share_of_total | roi | issue_win_rate | max_drawdown_units | recent_profit_units | recent_roi | roi_ex_best_row |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| core | 95904.0000 | 126824.7618 | 0.6202 | 1.3224 | 0.0511 | -14473.5712 | 26120.5225 | 1.4061 | 0.3832 |
| fallback_n5_quality | 576.0000 | -576.0000 | -0.0028 | -1.0000 | 0.0000 | -576.0000 | 0.0000 |  | -1.0000 |
| n5_overlap | 42816.0000 | 5834.2018 | 0.0285 | 0.1363 | 0.2900 | -2511.3182 | 5668.5755 | 0.6866 | 0.0615 |
| protected_top_ev_draw | 31968.0000 | 72416.7445 | 0.3541 | 2.2653 | 0.0105 | -7042.4871 | 51197.3344 | 8.2683 | 0.4723 |


## MaxDD Window

- Window: `23012` `2023-01-10 04:00:00` -> `25012` `2025-01-14 04:00:00`.
- Issues: `113`, wins: `8`, full losses: `67`, profit: `-17,101.6`.

| component | stake_units | profit_units | roi | issue_win_rate | max_drawdown_units |
| --- | --- | --- | --- | --- | --- |
| core | 16272.0000 | -14473.5712 | -0.8895 | 0.0177 | -14473.5712 |
| n5_overlap | 7232.0000 | 2795.9628 | 0.3866 | 0.2832 | -1827.3440 |
| protected_top_ev_draw | 5424.0000 | -5424.0000 | -1.0000 | 0.0000 | -5424.0000 |


## Annual Component PnL

| component | year | stake_units | profit_units | roi | issue_win_rate |
| --- | --- | --- | --- | --- | --- |
| core | 2014 | 16704.0000 | 12794.1835 | 0.7659 | 0.0690 |
| core | 2015 | 8064.0000 | 2636.8767 | 0.3270 | 0.0536 |
| core | 2016 | 7488.0000 | -3910.4987 | -0.5222 | 0.0385 |
| core | 2017 | 6624.0000 | -4461.6766 | -0.6736 | 0.0435 |
| core | 2018 | 8352.0000 | 102466.6996 | 12.2685 | 0.1034 |
| core | 2019 | 7920.0000 | -3998.0397 | -0.5048 | 0.0364 |
| core | 2020 | 5904.0000 | 2184.8049 | 0.3701 | 0.0488 |
| core | 2021 | 8208.0000 | -25.9672 | -0.0032 | 0.0351 |
| core | 2022 | 8064.0000 | -6982.1430 | -0.8658 | 0.0179 |
| core | 2023 | 7920.0000 | 23051.3617 | 2.9105 | 0.0364 |
| core | 2024 | 8496.0000 | -6697.5712 | -0.7883 | 0.0339 |
| core | 2025 | 2160.0000 | 9766.7319 | 4.5216 | 0.1333 |
| fallback_n5_quality | 2020 | 192.0000 | -192.0000 | -1.0000 | 0.0000 |
| fallback_n5_quality | 2021 | 192.0000 | -192.0000 | -1.0000 | 0.0000 |
| fallback_n5_quality | 2022 | 192.0000 | -192.0000 | -1.0000 | 0.0000 |
| n5_overlap | 2014 | 7424.0000 | 287.5495 | 0.0387 | 0.3017 |
| n5_overlap | 2015 | 3584.0000 | -909.9653 | -0.2539 | 0.2500 |
| n5_overlap | 2016 | 3328.0000 | 1592.2156 | 0.4784 | 0.4423 |
| n5_overlap | 2017 | 2944.0000 | -43.2028 | -0.0147 | 0.3261 |
| n5_overlap | 2018 | 3712.0000 | 640.9711 | 0.1727 | 0.2241 |
| n5_overlap | 2019 | 3520.0000 | -1077.6941 | -0.3062 | 0.2545 |
| n5_overlap | 2020 | 2688.0000 | 921.7858 | 0.3429 | 0.3333 |
| n5_overlap | 2021 | 3712.0000 | -52.2019 | -0.0141 | 0.2759 |
| n5_overlap | 2022 | 3648.0000 | -1193.8317 | -0.3273 | 0.1930 |
| n5_overlap | 2023 | 3520.0000 | 6623.8438 | 1.8818 | 0.3455 |
| n5_overlap | 2024 | 3776.0000 | -1050.1518 | -0.2781 | 0.2542 |
| n5_overlap | 2025 | 960.0000 | 94.8835 | 0.0988 | 0.3333 |
| protected_top_ev_draw | 2014 | 5568.0000 | -4354.4871 | -0.7821 | 0.0086 |
| protected_top_ev_draw | 2015 | 2688.0000 | -2688.0000 | -1.0000 | 0.0000 |
| protected_top_ev_draw | 2016 | 2496.0000 | 4671.8942 | 1.8718 | 0.0192 |
| protected_top_ev_draw | 2017 | 2208.0000 | -2208.0000 | -1.0000 | 0.0000 |
| protected_top_ev_draw | 2018 | 2784.0000 | 8366.3114 | 3.0051 | 0.0172 |
| protected_top_ev_draw | 2019 | 2640.0000 | 16423.0572 | 6.2209 | 0.0364 |
| protected_top_ev_draw | 2020 | 1968.0000 | -1968.0000 | -1.0000 | 0.0000 |
| protected_top_ev_draw | 2021 | 2736.0000 | -2736.0000 | -1.0000 | 0.0000 |
| protected_top_ev_draw | 2022 | 2688.0000 | 5712.6343 | 2.1252 | 0.0179 |
| protected_top_ev_draw | 2023 | 2640.0000 | 54749.3344 | 20.7384 | 0.0182 |
| protected_top_ev_draw | 2024 | 2832.0000 | -2832.0000 | -1.0000 | 0.0000 |
| protected_top_ev_draw | 2025 | 720.0000 | -720.0000 | -1.0000 | 0.0000 |


## Protected Ticket Cases

| case | n_tickets | share | base_raw_profit | protected_raw_profit | delta_raw_profit | base_raw_roi | protected_raw_roi | avg_source_pred_ev | avg_source_pred_hit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rescued_by_draw | 3 | 0.0045 | -35.6571 | 15883.4672 | 15919.1243 | -1.0000 | 222.7249 | 17354.8529 | 0.0016 |
| base_hit_diluted | 4 | 0.0060 | 24756.4123 | 24698.4755 | -57.9368 | 427.3000 | 213.1500 | 17124.1723 | 0.0019 |
| still_dead_extra_cost | 659 | 0.9895 | -7552.9898 | -15105.9797 | -7552.9898 | -1.0000 | -1.0000 | 16802.8890 | 0.0011 |


## Protected Ticket Feature Comparison

| sample | n | issues | avg_source_pred_ev | median_source_pred_ev | avg_source_pred_hit | median_source_pred_hit | avg_selector_score | avg_line_gap_support_net | avg_abs_line_gap | avg_ll_bad | raw_hit_rate | raw_roi |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all_core_tickets | 9113 | 666 | 8629.2529 | 756.9783 | 0.0016 | 0.0009 | 176.6809 | 1.2357 | 0.3101 | 0.0002 | 0.0048 | 1.0647 |
| protected_top_ev_ticket | 666 | 666 | 16807.3049 | 15020.7928 | 0.0011 | 0.0006 | 339.4212 | 1.6742 | 0.3655 | 0.0000 | 0.0105 | 1.6658 |


## Changed Leg Breakdown

By action:

| base_to_protected | n | rescues | rescue_rate | delta_raw_profit | avg_draw_1h_p | avg_line_gap |
| --- | --- | --- | --- | --- | --- | --- |
| 0->10 | 660 | 3 | 0.0045 | 8379.9639 | 0.2023 | 0.5837 |
| 3->31 | 6 | 0 | 0.0000 | -71.7662 | 0.2226 | -0.5493 |


By handicap:

| hcp_bucket | n | rescues | rescue_rate | delta_raw_profit | avg_draw_1h_p | avg_line_gap |
| --- | --- | --- | --- | --- | --- | --- |
| -2 | 567 | 3 | 0.0053 | 9601.9586 | 0.1944 | 0.6514 |
| <=-3 | 1 | 0 | 0.0000 | -11.6364 | 0.1715 | -1.2292 |
| >=+2 | 4 | 0 | 0.0000 | -30.6233 | 0.2147 | -0.8073 |
| +1 | 2 | 0 | 0.0000 | -41.1429 | 0.2385 | -0.0333 |
| -1 | 92 | 0 | 0.0000 | -1210.3583 | 0.2517 | 0.1862 |


By draw probability bucket:

| draw_1h_p_bucket | n | rescues | rescue_rate | delta_raw_profit | avg_draw_1h_p | avg_line_gap |
| --- | --- | --- | --- | --- | --- | --- |
| <0.24 | 575 | 3 | 0.0052 | 9586.7235 | 0.1937 | 0.5947 |
| 0.28-0.32 | 5 | 0 | 0.0000 | -75.8066 | 0.2880 | 0.3593 |
| 0.24-0.28 | 86 | 0 | 0.0000 | -1202.7192 | 0.2563 | 0.4446 |


Top leagues by protected-ticket delta:

| league | n | rescues | rescue_rate | delta_raw_profit | avg_draw_1h_p | avg_line_gap |
| --- | --- | --- | --- | --- | --- | --- |
| 西甲 | 59 | 1 | 0.0169 | 7548.1975 | 0.1925 | 0.5929 |
| 巴西甲 | 11 | 1 | 0.0909 | 4358.3145 | 0.2298 | 0.7513 |
| 希腊超 | 10 | 1 | 0.1000 | 3041.0847 | 0.2100 | 0.6452 |
| 欧会杯 | 3 | 0 | 0.0000 | -16.8843 | 0.2198 | 0.1675 |
| 日职乙 | 3 | 0 | 0.0000 | -21.3822 | 0.2625 | 0.6250 |
| 阿甲 | 3 | 0 | 0.0000 | -23.0400 | 0.2082 | 0.5611 |
| 南球杯 | 3 | 0 | 0.0000 | -26.0069 | 0.2025 | 0.6484 |
| 美职业 | 3 | 0 | 0.0000 | -26.2095 | 0.2281 | 0.3457 |
| 南美预选 | 3 | 0 | 0.0000 | -27.2709 | 0.1979 | 0.6667 |
| 爱甲 | 3 | 0 | 0.0000 | -30.8245 | 0.2033 | 0.2348 |
| 亚洲预选 | 3 | 0 | 0.0000 | -30.8364 | 0.2000 | 0.6996 |
| 瑞士超 | 3 | 0 | 0.0000 | -32.7111 | 0.2164 | 0.5833 |
| 捷甲 | 3 | 0 | 0.0000 | -36.0727 | 0.1818 | 0.4533 |
| 俄超 | 3 | 0 | 0.0000 | -39.8222 | 0.2051 | 0.4583 |
| 意乙 | 4 | 0 | 0.0000 | -40.1824 | 0.2195 | 0.6195 |
| 奥甲 | 4 | 0 | 0.0000 | -40.6261 | 0.1837 | 0.6250 |
| 英甲 | 4 | 0 | 0.0000 | -45.9294 | 0.2237 | 0.4406 |
| 美洲杯 | 6 | 0 | 0.0000 | -47.2199 | 0.2252 | 0.4167 |
| 欧国联 | 8 | 0 | 0.0000 | -47.9782 | 0.2180 | 0.5710 |
| 波兰超 | 5 | 0 | 0.0000 | -48.6446 | 0.2163 | 0.6689 |


## Interpretation

- Total portfolio profit is `204,499.7`. The component table shows how much each sleeve actually contributes after fixed-budget scaling.
- Protected draw rescues `3` of `666` top-EV tickets, with raw delta profit `15,919.1` before portfolio scaling.
- If protected-ticket gains concentrate in a few rescue cases, use the protection sleeve as a convex add-on, not as a broad hedge.
- The changed-leg tables identify where draw protection is paying for itself: action transition, handicap bucket, draw probability, line-gap bucket, and league.
- Figure: `docs/research/figures/n7_recommended_attribution_equity_2026-06-28.svg`
