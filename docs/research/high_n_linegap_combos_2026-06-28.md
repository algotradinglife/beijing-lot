# High-N line_gap combo audit

## Scope

- Source strategy: `ev_m0p95_p0p8_full_opt__budget256_fractional`
- Input: `results/high_n_selector_20260628/high_n_selector_enriched_source_tickets.csv`
- `line_gap = -beidan_handicap - asian_handicap_1h` is already joined in the enriched ticket file.
- Positive support net means the chosen outcomes are more aligned with the line_gap direction; `0` means mostly flat/neutral or balanced.

## Same-Budget Combo Replay

| combo | issues | tickets | profit_units | roi | issue_win_rate | max_drawdown_units | ex_best_roi | recent_issues | recent_profit_units | recent_roi | recent_max_drawdown_units |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| exact_6n0_1p3_net0 | 207 | 310 | 151058.9667 | 2.8506 | 0.0048 | -38400.0000 | -1.0000 | 57 | 189458.9667 | 12.9838 | -14336.0000 |
| neg0_4_pos3_3_net_pos | 266 | 385 | -40618.7154 | -0.5965 | 0.0038 | -46848.0000 | -1.0000 | 45 | 15957.2846 | 1.3852 | -5632.0000 |
| flat_shape | 622 | 3979 | 105944.6410 | 0.6653 | 0.0145 | -38783.9359 | 0.3174 | 129 | 12783.0588 | 0.3871 | -28672.0000 |
| neg0_7_net0 | 604 | 3058 | -6063.2041 | -0.0392 | 0.0099 | -49143.5044 | -0.3950 | 122 | 7002.5938 | 0.2242 | -26880.0000 |
| net_0 | 648 | 4481 | 17923.2420 | 0.1080 | 0.0154 | -49370.3190 | -0.1306 | 129 | 1422.7873 | 0.0431 | -28672.0000 |
| net_abs_ge3 | 529 | 3141 | 24681.8294 | 0.1823 | 0.0416 | -15946.1811 | -0.0147 | 69 | 1390.1674 | 0.0787 | -8960.0000 |
| all | 669 | 12972 | 111291.2322 | 0.6498 | 0.0717 | -23640.2992 | 0.0977 | 129 | 533.1251 | 0.0161 | -23640.2992 |
| exact_6n0_1p3_net_pos | 378 | 744 | -32910.8549 | -0.3401 | 0.0132 | -58914.2359 | -0.5612 | 64 | -7299.7082 | -0.4455 | -8192.0000 |
| exact_6n0_1p3_net_neg | 90 | 123 | -23040.0000 | -1.0000 | 0.0000 | -23040.0000 | -0.9889 | 33 | -8448.0000 | -1.0000 | -8448.0000 |
| neg0_4_pos3_3_net0 | 120 | 156 | 16381.6838 | 0.5333 | 0.0083 | -28160.0000 | -1.0000 | 39 | -9984.0000 | -1.0000 | -9984.0000 |
| net_positive_1plus | 650 | 7066 | 26703.3865 | 0.1605 | 0.0600 | -23754.5081 | 0.0554 | 123 | -10067.5544 | -0.3197 | -18567.5797 |
| neg0_7_net_pos | 621 | 4019 | 79021.9644 | 0.4971 | 0.0403 | -29922.9505 | 0.3298 | 110 | -12070.2542 | -0.4286 | -22242.9505 |
| neg0_7_net_neg | 326 | 856 | 959702.0610 | 11.4995 | 0.0031 | -75520.0000 | -1.0000 | 86 | -22016.0000 | -1.0000 | -22016.0000 |
| net_negative_1plus | 433 | 1425 | 932310.0610 | 8.4107 | 0.0023 | -96512.0000 | -1.0000 | 108 | -27648.0000 | -1.0000 | -27648.0000 |


## Recent line_gap Net Buckets

| linegap_net_bucket | tickets | issues | hit_rate | profit_units | raw_roi | avg_abs_line_gap | avg_ll_good_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 1153 | 129 | 0.0026 | 10531.2150 | 0.7272 | 0.1999 | 0.3955 |
| >=3 | 177 | 64 | 0.0113 | -70.3729 | -0.0356 | 0.4240 | 0.0452 |
| 1:2 | 748 | 123 | 0.0040 | -2786.6392 | -0.2956 | 0.3118 | 0.2553 |
| -2:-1 | 434 | 108 | 0.0000 | -6840.4021 | -1.0000 | 0.2713 | 0.3134 |


## Recent Topology x line_gap Net

| topology | linegap_net_bucket | tickets | issues | hit_rate | profit_units | raw_roi | avg_abs_line_gap | avg_ll_good_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| neg0_6_pos3_1_draw_0 | 0 | 101 | 57 | 0.0099 | 15136.7417 | 15.5641 | 0.2054 | 0.3960 |
| neg0_7_pos3_0_draw_0 | 0 | 710 | 122 | 0.0028 | 1840.0866 | 0.2605 | 0.1934 | 0.1662 |
| neg0_7_pos3_0_draw_0 | 1:2 | 379 | 107 | 0.0053 | 1330.2342 | 0.3381 | 0.3090 | 0.1504 |
| neg0_4_pos3_3_draw_0 | 1:2 | 47 | 37 | 0.0213 | 858.0286 | 1.6634 | 0.3178 | 0.1702 |
| neg0_0_pos3_7_draw_0 | 0 | 45 | 33 | 0.0000 | -483.2535 | -1.0000 | 0.1666 | 1.3333 |
| neg0_4_pos3_3_draw_0 | 0 | 51 | 39 | 0.0000 | -493.6750 | -1.0000 | 0.2154 | 0.7451 |
| neg0_6_pos3_1_draw_0 | -2:-1 | 52 | 33 | 0.0000 | -510.0961 | -1.0000 | 0.2459 | 0.2692 |
| neg0_5_pos3_2_draw_0 | 1:2 | 79 | 48 | 0.0000 | -770.2446 | -1.0000 | 0.3070 | 0.2405 |
| neg0_5_pos3_2_draw_0 | 0 | 70 | 41 | 0.0000 | -792.5592 | -1.0000 | 0.1988 | 0.3571 |
| neg0_6_pos3_1_draw_0 | 1:2 | 98 | 61 | 0.0000 | -891.0691 | -1.0000 | 0.3095 | 0.1939 |
| neg0_7_pos3_0_draw_0 | >=3 | 79 | 36 | 0.0000 | -940.5214 | -1.0000 | 0.4158 | 0.0253 |
| neg0_7_pos3_0_draw_0 | -2:-1 | 270 | 86 | 0.0000 | -2687.1044 | -1.0000 | 0.2661 | 0.1481 |


## Recent line_gap Shape

| linegap_shape | tickets | issues | hit_rate | profit_units | raw_roi | avg_abs_line_gap |
| --- | --- | --- | --- | --- | --- | --- |
| all_flat | 1059 | 129 | 0.0028 | 11888.4633 | 0.9058 | 0.1877 |
| positive_only | 669 | 117 | 0.0075 | -533.3909 | -0.0588 | 0.3148 |
| pos_dominant | 87 | 45 | 0.0000 | -996.4404 | -1.0000 | 0.4201 |
| balanced_pos_neg | 122 | 61 | 0.0000 | -1352.4293 | -1.0000 | 0.3489 |
| negative_only | 539 | 118 | 0.0000 | -8003.8898 | -1.0000 | 0.2824 |


## Recent Average Absolute Gap

| abs_gap_bucket | tickets | issues | hit_rate | profit_units | raw_roi | avg_abs_line_gap |
| --- | --- | --- | --- | --- | --- | --- |
| <0.20 | 764 | 127 | 0.0026 | 9781.3481 | 1.1170 | 0.1509 |
| >=0.40 | 225 | 83 | 0.0133 | -201.2212 | -0.0578 | 0.4540 |
| 0.20-0.30 | 887 | 128 | 0.0011 | -3984.2443 | -0.3809 | 0.2495 |
| 0.30-0.40 | 642 | 124 | 0.0031 | -5062.7576 | -0.4902 | 0.3428 |


## Read

- The best recent line_gap niche is not strong positive support. It is the exact `6n0+1p3` topology with `support_net = 0`.
- Positive support helps some `neg0_7` and `neg0_4_pos3_3` pockets, but the effect is small and not enough to become the main selector.
- Strong absolute line_gap generally looks dangerous in this ticket pool; the high-payoff hits cluster more around neutral/balanced line_gap states.
- Keep line_gap as a diagnostic/risk tag for now. Do not promote it to a hard gate ahead of topology.

## Files

- `results/high_n_linegap_combos_20260628/linegap_same_budget_combo_replay.csv`
- `results/high_n_linegap_combos_20260628/linegap_recent_topology_net.csv`
- `results/high_n_linegap_combos_20260628/linegap_recent_net_bucket.csv`
- `results/high_n_linegap_combos_20260628/linegap_recent_shape.csv`
- `results/high_n_linegap_combos_20260628/linegap_recent_abs_gap.csv`
