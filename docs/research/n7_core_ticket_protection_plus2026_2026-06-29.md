# N7 Core Ticket-Level Protection

## Scope

- Source tickets: `results/high_n_selector_plus2026_20260629/high_n_selector_selected_tickets.csv` / `ev_m0p95_p0p8_full_opt__budget256_fractional` / `topology_neg0_ge6_d0`.
- 每期总预算仍为 `256`：主对照是 `192` N7 core + `64` N5 overlap。
- 保护动作只在 N7 core 的少量 ticket 上加一条腿覆盖，不额外加预算。
- Leg protection snapshot: `1h`; policies: `draw,alt,full`; selection modes: `top_ev,low_hit,risk`; counts: `1,2,3`.

## Baseline Rebuild

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_units | recent_roi | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| baseline_core192_n5ov64_rebuilt | 173328.8332 | 0.9645 | 0.0855 | 0.6752 | -16419.8459 | 5 | 44779.2885 | 1.3560 | 0.2884 |


## Decision

- 推荐进入下一轮主测：`sleeve160_tp32_draw_top_ev_k1_n5ov64`: profit `197,489`, ROI `1.10`, maxDD `-16,732`, max full-loss streak `5`, recent profit `72,398`, ex-best ROI `0.53`。结构是 `160` 原始 N7 core + `32` 只投每期 top-EV protected ticket + `64` N5 overlap；保护动作为给该 top-EV 票中最值得补的腿加 `draw`。
- 更防守但收益较弱：`replace192_draw_top_ev_k1_n5ov64`: profit `175,757`, ROI `0.98`, maxDD `-16,469`, max full-loss streak `5`, recent profit `40,186`, ex-best ROI `0.35`。maxDD 略好，但 profit 和近三年都不如推荐版。
- 最低 maxDD 备选：`sleeve160_tp32_full_top_ev_k3_n5ov64`: profit `160,645`, ROI `0.89`, maxDD `-16,194`, max full-loss streak `5`, recent profit `48,591`, ex-best ROI `0.33`。适合只看回撤，但 ROI 明显低于推荐版。
- 不建议追逐最高 profit 的 low-hit 保护：`sleeve160_tp32_draw_low_hit_k1_n5ov64`: profit `264,539`, ROI `1.47`, maxDD `-19,436`, max full-loss streak `5`, recent profit `37,174`, ex-best ROI `0.18`。它主要靠 2018 单期巨奖，maxDD 反而变差，ex-best ROI 也低。

## Top By MaxDD

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_drawdown_full_loss_equiv | max_dead_streak | max_loss_streak | recent_profit_units | recent_roi | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| replace192_full_top_ev_k1_n5ov64 | 152488.6228 | 0.8485 | 0.0926 | 0.6766 | -15544.6011 | 60.7211 | 5 | 32 | 48617.9058 | 1.4722 | 0.2617 |
| sleeve160_tp32_full_top_ev_k1_n5ov64 | 174970.9517 | 0.9736 | 0.0926 | 0.6766 | -15796.3316 | 61.7044 | 5 | 32 | 72546.6094 | 2.1968 | 0.4093 |
| sleeve160_tp32_full_top_ev_k3_n5ov64 | 160644.6520 | 0.8939 | 0.0997 | 0.6781 | -16194.1399 | 63.2584 | 5 | 32 | 48591.4724 | 1.4714 | 0.3295 |
| baseline_core192_n5ov64_rebuilt | 173328.8332 | 0.9645 | 0.0855 | 0.6752 | -16419.8459 | 64.1400 | 5 | 37 | 44779.2885 | 1.3560 | 0.2884 |
| replace192_draw_top_ev_k1_n5ov64 | 175756.6499 | 0.9780 | 0.0897 | 0.6752 | -16468.6797 | 64.3308 | 5 | 32 | 40186.3521 | 1.2169 | 0.3498 |
| replace192_draw_risk_k1_n5ov64 | 169796.6702 | 0.9448 | 0.0897 | 0.6752 | -16468.6797 | 64.3308 | 5 | 32 | 40186.3521 | 1.2169 | 0.3166 |
| replace192_alt_top_ev_k1_n5ov64 | 159247.9690 | 0.8861 | 0.0912 | 0.6766 | -16468.6797 | 64.3308 | 5 | 32 | 40186.3521 | 1.2169 | 0.2578 |
| replace192_alt_low_hit_k3_n5ov64 | 202646.4763 | 1.1276 | 0.0912 | 0.6766 | -16502.8488 | 64.4643 | 5 | 37 | 103849.4348 | 3.1447 | 0.5775 |
| sleeve160_tp32_full_top_ev_k2_n5ov64 | 165285.6504 | 0.9197 | 0.0954 | 0.6781 | -16505.6975 | 64.4754 | 5 | 32 | 55817.9823 | 1.6902 | 0.3554 |
| replace192_draw_top_ev_k2_n5ov64 | 163140.0341 | 0.9078 | 0.0912 | 0.6752 | -16590.0710 | 64.8050 | 5 | 32 | 36215.2091 | 1.0966 | 0.3210 |
| replace192_draw_risk_k2_n5ov64 | 155195.0245 | 0.8636 | 0.0897 | 0.6752 | -16590.0710 | 64.8050 | 5 | 32 | 36215.2091 | 1.0966 | 0.2768 |
| replace192_alt_top_ev_k2_n5ov64 | 146114.9053 | 0.8131 | 0.0926 | 0.6781 | -16590.0710 | 64.8050 | 5 | 32 | 36215.2091 | 1.0966 | 0.2262 |


## Top By Profit

| portfolio | profit_units | roi | issue_win_rate | non_full_loss_rate | max_drawdown_units | max_dead_streak | recent_profit_units | recent_roi | roi_ex_best_issue |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| sleeve160_tp32_draw_low_hit_k1_n5ov64 | 264538.8881 | 1.4720 | 0.0855 | 0.6752 | -19436.0470 | 5 | 37174.0454 | 1.1257 | 0.1818 |
| sleeve160_tp32_alt_low_hit_k1_n5ov64 | 256363.1262 | 1.4265 | 0.0855 | 0.6752 | -19436.0470 | 5 | 37174.0454 | 1.1257 | 0.1363 |
| sleeve160_tp32_alt_low_hit_k2_n5ov64 | 234836.3285 | 1.3067 | 0.0883 | 0.6766 | -19436.0470 | 5 | 74170.2073 | 2.2459 | 0.3796 |
| sleeve160_tp32_full_low_hit_k1_n5ov64 | 220577.3335 | 1.2274 | 0.0855 | 0.6752 | -19436.0470 | 5 | 44853.1719 | 1.3582 | 0.1791 |
| replace192_alt_low_hit_k2_n5ov64 | 215560.5261 | 1.1995 | 0.0883 | 0.6766 | -18008.0296 | 5 | 113243.1256 | 3.4291 | 0.6132 |
| sleeve160_tp32_alt_low_hit_k3_n5ov64 | 203174.1985 | 1.1306 | 0.0912 | 0.6766 | -16745.8470 | 5 | 60826.2891 | 1.8419 | 0.3243 |
| replace192_alt_low_hit_k3_n5ov64 | 202646.4763 | 1.1276 | 0.0912 | 0.6766 | -16502.8488 | 5 | 103849.4348 | 3.1447 | 0.5775 |
| sleeve160_tp32_full_low_hit_k2_n5ov64 | 201880.6396 | 1.1234 | 0.0883 | 0.6766 | -19436.0470 | 5 | 65171.7844 | 1.9735 | 0.3171 |
| sleeve160_tp32_draw_top_ev_k1_n5ov64 | 197489.2553 | 1.0989 | 0.0897 | 0.6752 | -16732.3304 | 5 | 72398.0090 | 2.1923 | 0.5348 |
| sleeve160_tp32_draw_low_hit_k2_n5ov64 | 196612.9180 | 1.0940 | 0.0855 | 0.6752 | -19436.0470 | 5 | 35656.2490 | 1.0797 | 0.1666 |
| sleeve160_tp32_draw_risk_k1_n5ov64 | 190246.7907 | 1.0586 | 0.0897 | 0.6752 | -16732.3304 | 5 | 72398.0090 | 2.1923 | 0.4945 |
| sleeve160_tp32_draw_top_ev_k2_n5ov64 | 183214.2884 | 1.0195 | 0.0912 | 0.6752 | -16732.3304 | 5 | 56981.4077 | 1.7255 | 0.4553 |


## Interpretation

- `replace192_*` 表示 core 的 192 units 全部使用“少量 ticket 加保护”的重建 core。
- `sleeve160_tp32_*` 表示 160 units 原始 core + 32 units 只投被保护的 ticket + 64 units N5 overlap，更接近小比例保护。
- 如果保护组合 maxDD 没有明显下降、但 profit/ROI 下滑，说明当前保护选择只是稀释凸性，下一步应改进“哪条腿需要保护”的识别，而不是增加保护比例。

Figure: `docs/research/figures/n7_core_ticket_protection_plus2026_2026-06-29.svg`
