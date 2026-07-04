# N7 Protected Dynamic Ratio

## Scope

- 每期仍固定 `256` units。
- 不降仓，只在几个固定比例候选之间切换。
- Normal: `grid_c144_p48_draw_top_ev_k1_n5ov64`; balanced: `grid_c128_p48_draw_top_ev_k1_n5ov80`; safe: `grid_c128_p16_draw_top_ev_k1_n5ov112`; ultra-safe: `grid_c128_p16_full_top_ev_k3_n5ov112`.
- 动态选择只用当前 issue 前的组合 equity、drawdown depth、loss streak、dead streak。

## Summary

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_drawdown_full_loss_equiv | max_dead_streak | max_loss_streak | recent_profit_units | recent_roi | roi_ex_best_issue | model_mix | state_mix |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed::grid_c128_p16_draw_top_ev_k1_n5ov112 | 146649.8895 | 0.8563 | 0.1839 | 0.4395 | -14014.7663 | 54.7452 | 8 | 25 | 50204.0274 | 1.5202 | 0.3711 | grid_c128_p16_draw_top_ev_k1_n5ov112:669 | fixed:669 |
| dd8_13_normal_balanced_safe | 178978.6516 | 1.0450 | 0.1256 | 0.4395 | -15434.7838 | 60.2921 | 8 | 30 | 81242.5068 | 2.4601 | 0.5435 | grid_c128_p16_draw_top_ev_k1_n5ov112:117;grid_c128_p48_draw_top_ev_k1_n5ov80:255;grid_c144_p48_draw_top_ev_k1_n5ov64:297 | balanced:255;normal:297;safe:117 |
| dd10_15_normal_balanced_safe | 180924.2777 | 1.0564 | 0.1211 | 0.4395 | -15801.9039 | 61.7262 | 8 | 30 | 81014.6402 | 2.4532 | 0.5549 | grid_c128_p16_draw_top_ev_k1_n5ov112:85;grid_c128_p48_draw_top_ev_k1_n5ov80:179;grid_c144_p48_draw_top_ev_k1_n5ov64:405 | balanced:179;normal:405;safe:85 |
| loss_only_8_14 | 181683.7156 | 1.0608 | 0.1196 | 0.4395 | -15949.9563 | 62.3045 | 8 | 30 | 81750.1367 | 2.4755 | 0.5594 | grid_c128_p16_draw_top_ev_k1_n5ov112:80;grid_c128_p48_draw_top_ev_k1_n5ov80:163;grid_c144_p48_draw_top_ev_k1_n5ov64:426 | balanced:163;normal:426;safe:80 |
| fixed::grid_c128_p48_draw_top_ev_k1_n5ov80 | 191914.6183 | 1.1206 | 0.1241 | 0.4395 | -16063.5178 | 62.7481 | 8 | 31 | 81501.2959 | 2.4679 | 0.6192 | grid_c128_p48_draw_top_ev_k1_n5ov80:669 | fixed:669 |
| dd12_16_normal_balanced_safe | 193256.2721 | 1.1284 | 0.1136 | 0.4395 | -16245.3935 | 63.4586 | 8 | 30 | 82989.4693 | 2.5130 | 0.6123 | grid_c128_p16_draw_top_ev_k1_n5ov112:70;grid_c128_p48_draw_top_ev_k1_n5ov80:130;grid_c144_p48_draw_top_ev_k1_n5ov64:469 | balanced:130;normal:469;safe:70 |
| dd_only_10_15 | 194943.2835 | 1.1383 | 0.1106 | 0.4395 | -16495.5609 | 64.4358 | 8 | 30 | 82708.9308 | 2.5045 | 0.6222 | grid_c128_p16_draw_top_ev_k1_n5ov112:9;grid_c128_p48_draw_top_ev_k1_n5ov80:68;grid_c144_p48_draw_top_ev_k1_n5ov64:592 | balanced:68;normal:592;safe:9 |
| fixed::grid_c144_p48_draw_top_ev_k1_n5ov64 | 204499.7081 | 1.1941 | 0.1061 | 0.4395 | -17101.6084 | 66.8032 | 8 | 31 | 82986.4323 | 2.5129 | 0.6587 | grid_c144_p48_draw_top_ev_k1_n5ov64:669 | fixed:669 |
| fixed::grid_core192_n5ov64 | 174357.8842 | 1.0181 | 0.1031 | 0.4380 | -17150.0609 | 66.9924 | 10 | 31 | 40495.9388 | 1.2263 | 0.3065 | grid_core192_n5ov64:669 | fixed:669 |
| dd10_15_normal_balanced_ultra | 119624.3842 | 0.6985 | 0.1241 | 0.4380 | -22136.8286 | 86.4720 | 10 | 30 | 29232.5470 | 0.8852 | 0.2130 | grid_c128_p16_full_top_ev_k3_n5ov112:135;grid_c128_p48_draw_top_ev_k1_n5ov80:207;grid_c144_p48_draw_top_ev_k1_n5ov64:327 | balanced:207;normal:327;safe:135 |


## Best Profit With No Worse MaxDD Than Fixed Normal

| portfolio | profit_units | roi | max_drawdown_units | max_dead_streak | recent_profit_units | roi_ex_best_issue | model_mix |
| --- | --- | --- | --- | --- | --- | --- | --- |
| fixed::grid_c144_p48_draw_top_ev_k1_n5ov64 | 204499.7081 | 1.1941 | -17101.6084 | 8 | 82986.4323 | 0.6587 | grid_c144_p48_draw_top_ev_k1_n5ov64:669 |


## Interpretation

- 如果动态组合不能同时提高 profit 并降低 maxDD，说明比例切换的信号还不够好；固定比例优先。
- 若动态组合降低 maxDD 但牺牲明显 profit，可作为大回撤后的风控模式，而不是默认模式。
- Figure: `docs/research/figures/n7_protection_dynamic_ratio_equity_2026-06-28.svg`
