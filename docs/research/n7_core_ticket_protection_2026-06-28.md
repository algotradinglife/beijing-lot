# N7 Core Ticket-Level Protection

## Scope

- Source tickets: `results/high_n_selector_20260628/high_n_selector_selected_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- 每期总预算仍为 `256`：主对照是 `192` N7 core + `64` N5 overlap。
- 保护动作只在 N7 core 的少量 ticket 上加一条腿覆盖，不额外加预算。
- Leg protection snapshot: `1h`; policies: `draw,alt,full`; selection modes: `top_ev,low_hit,risk`; counts: `1,2,3`.

## Baseline Rebuild

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_units | recent_roi | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_core192_n5ov64_rebuilt | 174357.8842 | 1.0181 | 0.1031 | 0.4380 | -17150.0609 | 10 | 40495.9388 | 1.2263 | 0.3065 |


## Decision

- 推荐进入下一轮主测：`sleeve160_tp32_draw_top_ev_k1_n5ov64`: profit `194,452`, ROI `1.14`, maxDD `-16,902`, max full-loss streak `8`, recent profit `68,823`, ex-best ROI `0.54`。结构是 `160` 原始 N7 core + `32` 只投每期 top-EV protected ticket + `64` N5 overlap；保护动作为给该 top-EV 票中最值得补的腿加 `draw`。
- 更防守但收益较弱：`replace192_draw_top_ev_k1_n5ov64`: profit `170,635`, ROI `1.00`, maxDD `-16,638`, max full-loss streak `8`, recent profit `35,944`, ex-best ROI `0.34`。maxDD 略好，但 profit 和近三年都不如推荐版。
- 最低 maxDD 备选：`sleeve160_tp32_full_top_ev_k3_n5ov64`: profit `161,943`, ROI `0.95`, maxDD `-16,364`, max full-loss streak `10`, recent profit `45,016`, ex-best ROI `0.35`。适合只看回撤，但 ROI 明显低于推荐版。
- 不建议追逐最高 profit 的 low-hit 保护：`sleeve160_tp32_draw_low_hit_k1_n5ov64`: profit `266,469`, ROI `1.56`, maxDD `-22,261`, max full-loss streak `10`, recent profit `33,599`, ex-best ROI `0.20`。它主要靠 2018 单期巨奖，maxDD 反而变差，ex-best ROI 也低。

## Top By MaxDD

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_drawdown_full_loss_equiv | max_dead_streak | max_loss_streak | recent_profit_units | recent_roi | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sleeve160_tp32_full_top_ev_k3_n5ov64 | 161942.9329 | 0.9456 | 0.1181 | 0.4425 | -16363.5924 | 63.9203 | 10 | 31 | 45016.3980 | 1.3631 | 0.3512 |
| replace192_draw_top_ev_k1_n5ov64 | 170635.3982 | 0.9963 | 0.1061 | 0.4395 | -16638.1322 | 64.9927 | 8 | 31 | 35944.2896 | 1.0884 | 0.3350 |
| replace192_draw_risk_k1_n5ov64 | 170635.3982 | 0.9963 | 0.1061 | 0.4395 | -16638.1322 | 64.9927 | 8 | 31 | 35944.2896 | 1.0884 | 0.3350 |
| replace192_alt_top_ev_k1_n5ov64 | 160333.7745 | 0.9362 | 0.1091 | 0.4395 | -16638.1322 | 64.9927 | 10 | 31 | 35944.2896 | 1.0884 | 0.2748 |
| replace192_draw_top_ev_k2_n5ov64 | 158604.8483 | 0.9261 | 0.1076 | 0.4395 | -16759.5236 | 65.4669 | 8 | 31 | 32043.3074 | 0.9703 | 0.3082 |
| replace192_draw_risk_k2_n5ov64 | 150659.8386 | 0.8797 | 0.1061 | 0.4395 | -16759.5236 | 65.4669 | 8 | 31 | 32043.3074 | 0.9703 | 0.2618 |
| replace192_full_top_ev_k1_n5ov64 | 153591.2248 | 0.8968 | 0.1106 | 0.4410 | -16843.9515 | 65.7967 | 10 | 31 | 44446.0041 | 1.3459 | 0.2789 |
| replace192_alt_top_ev_k2_n5ov64 | 148296.1264 | 0.8659 | 0.1121 | 0.4410 | -16843.9515 | 65.7967 | 10 | 31 | 32043.3074 | 0.9703 | 0.2480 |
| replace192_draw_risk_k3_n5ov64 | 140906.5487 | 0.8227 | 0.1061 | 0.4395 | -16868.5414 | 65.8927 | 8 | 31 | 28662.1066 | 0.8679 | 0.2429 |
| replace192_draw_top_ev_k3_n5ov64 | 148454.3078 | 0.8668 | 0.1076 | 0.4395 | -16868.5414 | 65.8927 | 8 | 31 | 28662.1066 | 0.8679 | 0.2870 |
| sleeve160_tp32_draw_top_ev_k1_n5ov64 | 194452.4334 | 1.1354 | 0.1061 | 0.4395 | -16901.7829 | 66.0226 | 8 | 31 | 68822.9345 | 2.0840 | 0.5413 |
| sleeve160_tp32_draw_risk_k1_n5ov64 | 192176.6187 | 1.1221 | 0.1061 | 0.4395 | -16901.7829 | 66.0226 | 8 | 31 | 68822.9345 | 2.0840 | 0.5280 |


## Top By Profit

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_units | recent_roi | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sleeve160_tp32_draw_low_hit_k1_n5ov64 | 266468.7160 | 1.5559 | 0.1031 | 0.4380 | -22260.6825 | 10 | 33598.9709 | 1.0174 | 0.1999 |
| sleeve160_tp32_alt_low_hit_k1_n5ov64 | 258292.9541 | 1.5082 | 0.1031 | 0.4380 | -22260.6825 | 10 | 33598.9709 | 1.0174 | 0.1521 |
| sleeve160_tp32_full_low_hit_k1_n5ov64 | 222507.1614 | 1.2992 | 0.1031 | 0.4380 | -22260.6825 | 10 | 41278.0974 | 1.2499 | 0.1970 |
| sleeve160_tp32_draw_low_hit_k2_n5ov64 | 198542.7459 | 1.1593 | 0.1031 | 0.4380 | -22260.6825 | 10 | 32081.1746 | 0.9715 | 0.1840 |
| sleeve160_tp32_alt_low_hit_k2_n5ov64 | 198252.1982 | 1.1576 | 0.1061 | 0.4395 | -22260.6825 | 10 | 32081.1746 | 0.9715 | 0.1823 |
| sleeve160_tp32_draw_top_ev_k1_n5ov64 | 194452.4334 | 1.1354 | 0.1061 | 0.4395 | -16901.7829 | 8 | 68822.9345 | 2.0840 | 0.5413 |
| sleeve160_tp32_draw_risk_k1_n5ov64 | 192176.6187 | 1.1221 | 0.1061 | 0.4395 | -16901.7829 | 8 | 68822.9345 | 2.0840 | 0.5280 |
| sleeve160_tp32_alt_top_ev_k1_n5ov64 | 183567.1888 | 1.0718 | 0.1091 | 0.4395 | -16980.6177 | 10 | 68822.9345 | 2.0840 | 0.4777 |
| sleeve160_tp32_draw_top_ev_k2_n5ov64 | 182660.7915 | 1.0665 | 0.1076 | 0.4395 | -16901.7829 | 8 | 53406.3333 | 1.6172 | 0.4724 |
| sleeve160_tp32_alt_low_hit_k3_n5ov64 | 178786.0913 | 1.0439 | 0.1091 | 0.4410 | -19065.2796 | 10 | 31575.2425 | 0.9561 | 0.1955 |
| sleeve160_tp32_full_low_hit_k2_n5ov64 | 178134.4954 | 1.0401 | 0.1061 | 0.4395 | -22260.6825 | 10 | 35920.7378 | 1.0877 | 0.1917 |
| sleeve160_tp32_draw_low_hit_k3_n5ov64 | 178065.1477 | 1.0397 | 0.1046 | 0.4380 | -18634.3708 | 10 | 31575.2425 | 0.9561 | 0.1913 |


## Interpretation

- `replace192_*` 表示 core 的 192 units 全部使用“少量 ticket 加保护”的重建 core。
- `sleeve160_tp32_*` 表示 160 units 原始 core + 32 units 只投被保护的 ticket + 64 units N5 overlap，更接近小比例保护。
- 如果保护组合 maxDD 没有明显下降、但 profit/ROI 下滑，说明当前保护选择只是稀释凸性，下一步应改进“哪条腿需要保护”的识别，而不是增加保护比例。

Figure: `docs/research/figures/n7_core_ticket_protection_equity_2026-06-28.svg`
