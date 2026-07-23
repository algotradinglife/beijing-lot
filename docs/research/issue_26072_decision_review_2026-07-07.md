# 26072 期决策复盘

生成时间：2026-07-07 04:36:25Z

## 数据边界

- 赛果/结算：`matches` 中 26072 共 67 场，已有赛果和 `winning_sp` 的场次 67 场。
- 决策样本：结构化决策产物覆盖 65 场，#66/#67 没有赛前结构化决策产物，不纳入押/保命中率。
- 收益口径：单腿 proxy，每覆盖一个结果计 1 单位成本；命中返还该场真实北单 `winning_sp`。这不是 N 串票级收益。
- 默认复盘对象：`shadow_v3.3.3`。v4.2 late-proxy 只作为观察版对照，strict 等非实战版本不纳入。

本期真实赛果分布：{'平': 15, '胜': 27, '负': 25}

## 总览

| 版本 | 决策场 | 无决策 | 押+保命中 | 主押命中 | 保中 | 成本 | 均深 | profit proxy | ROI proxy | 票型 | 漏中结果 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shadow_v3.3.3 默认 | 65 | 2 | 76.9% | 38.5% | 38.5% | 139 | 2.14 | 6.53 | 4.7% | {'double': 46, 'full': 14, 'single': 5} | {'平': 6, '负': 4, '胜': 5} |
| v4.2.0004 late-proxy 观察 | 65 | 2 | 89.2% | 46.2% | 43.1% | 135 | 2.08 | 39.49 | 29.3% | {'double': 56, 'full': 7, 'single': 2} | {'负': 3, '平': 2, '胜': 2} |
| v4.2.0005 late-proxy 观察 | 65 | 2 | 90.8% | 47.7% | 43.1% | 136 | 2.09 | 41.54 | 30.5% | {'double': 57, 'full': 7, 'single': 1} | {'负': 2, '平': 2, '胜': 2} |

## 默认版漏中

| # | 比赛 | 比分 | 赛果 | 押保 | 概率top | q top | P 3/1/0 | q 3/1/0 | 标签 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 17 | FH哈夫纳夫约杜尔 vs 斯塔尔南 | 2:2 | 平(5.19) | 负+胜 | 胜 | 胜 | 36.0%/32.3%/31.7% | 1.51/1.42/0.59 | probability_runner_up_protection;raw_strength_missing |
| 11 | 斯莱戈流浪者 vs 沙姆洛克流浪者 | 1:2 | 平(3.88) | 负+胜 | 胜 | 胜 | 42.0%/25.1%/32.9% | 1.49/0.93/0.73 | line_gap_missing;probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 21 | 大田韩亚市民 vs 富川1995 | 2:2 | 平(3.57) | 胜+负 | 胜 | 负 | 55.0%/24.8%/20.1% | 1.02/0.68/2.13 | line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 62 | 布鲁马波卡纳 vs 加尔斯 | 1:1 | 平(3.25) | 负 | 负 | 负 | 27.7%/25.3%/47.0% | 0.48/1.36/1.96 | raw_strength_missing |
| 46 | FC首尔 vs 仁川联 | 1:0 | 平(3.06) | 负+胜 | 负 | 胜 | 22.5%/25.9%/51.5% | 1.65/0.76/0.98 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 7 | 澳大利亚 vs 埃及 | 1:1 | 平(2.59) | 负+胜 | 负 | 胜 | 31.7%/30.1%/38.3% | 1.26/1.00/0.85 | probability_runner_up_protection;q_probability_disagree |
| 32 | 查路 vs 伊尔维斯 | 2:1 | 胜(6.59) | 负+平 | 负 | 平 | 30.2%/27.0%/42.8% | 2.25/2.37/0.57 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 36 | 瓦萨 vs 玛丽港 | 4:0 | 胜(3.01) | 负+平 | 负 | 平 | 25.2%/25.4%/49.4% | 0.58/4.37/0.97 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 33 | 塞伊奈约基 vs TPS图尔库 | 3:1 | 胜(2.97) | 负+平 | 负 | 平 | 27.3%/30.5%/42.2% | 0.37/2.83/2.54 | q_probability_disagree;raw_strength_missing |
| 57 | MP米凯利 vs 哈卡 | 2:1 | 胜(2.51) | 负+平 | 胜 | 平 | 43.8%/26.3%/29.9% | 0.46/15.93/8.05 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 28 | 埃格尔松 vs 莫斯 | 3:0 | 胜(2.12) | 负 | 胜 | 负 | 41.8%/29.4%/28.8% | 0.58/1.46/3.75 | q_high_but_probability_low;q_probability_disagree |
| 20 | 全北现代 vs 江原FC | 1:2 | 负(4.03) | 胜+平 | 胜 | 胜 | 45.4%/28.5%/26.1% | 3.74/0.62/0.62 | raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 23 | 忠北清州FC vs 大邱FC | 1:5 | 负(3.45) | 胜+平 | 胜 | 平 | 44.9%/24.3%/30.8% | 1.00/1.33/0.83 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 39 | 加拿大 vs 摩洛哥 | 0:3 | 负(3.17) | 胜+平 | 胜 | 胜 | 45.5%/24.4%/30.2% | 1.57/0.62/0.95 | q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 55 | 奥德 vs 海于格松 | 1:3 | 负(2.07) | 胜+平 | 胜 | 平 | 41.8%/29.4%/28.8% | 2.42/20.94/0.35 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 默认版保护救票

| # | 比赛 | 比分 | 赛果 | 押保 | 单腿收益 | 标签 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | KTP科特卡 vs 吉波 | 3:3 | 平(3.52) | 胜+平 | 1.52 | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 3 | 孔斯温厄尔 vs 松达尔 | 5:1 | 胜(2.11) | 负+胜+平 | -0.89 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 5 | 天狼星 vs 米亚尔比 | 4:4 | 负(2.42) | 胜+负+平 | -0.58 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 8 | 德里城 vs 沃特福德FC | 2:4 | 负(3.81) | 胜+负+平 | 0.81 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 科夫漫步者 vs 科克城 | 0:1 | 平(4.02) | 负+胜+平 | 1.02 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 13 | 布雷流浪者 vs 阿斯隆城 | 1:0 | 平(3.95) | 胜+负+平 | 0.95 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 14 | 条约联 vs 凯里 | 2:1 | 胜(3.30) | 负+胜 | 1.30 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 19 | 哥伦比亚 vs 加纳 | 1:0 | 平(2.94) | 胜+负+平 | -0.06 | probability_runner_up_protection;q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 26 | 水原三星蓝翼 vs 城南FC | 1:0 | 平(3.66) | 负+平 | 1.66 | line_gap_watch;raw_strength_missing;recent_form_intel_protection |
| 27 | 拉赫蒂 vs 格尼斯坦 | 1:0 | 胜(2.60) | 负+胜 | 0.60 | probability_runner_up_protection;q_top_odds_up;raw_strength_missing |
| 35 | 赫德 vs 斯托姆加斯特 | 4:3 | 胜(3.02) | 负+胜+平 | 0.02 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 38 | 布莱尼 vs 桑内斯乌尔夫 | 1:1 | 平(5.58) | 胜+平 | 3.58 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |
| 40 | 朗福德城 vs 都柏林大学 | 2:1 | 胜(4.75) | 负+胜 | 2.75 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 隆德里纳 vs 巴西雷加塔斯 | 5:0 | 胜(2.98) | 负+胜 | 0.98 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 44 | 巴拉圭 vs 法国 | 0:1 | 胜(3.24) | 负+胜 | 1.24 | probability_runner_up_protection |
| 47 | 金泉尚武 vs 济州SK | 1:1 | 平(3.06) | 负+胜+平 | 0.06 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 48 | 光州FC vs 蔚山HD | 1:1 | 胜(4.11) | 负+胜 | 2.11 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 51 | 庆南FC vs 天安城 | 2:1 | 胜(2.41) | 负+胜 | 0.41 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |

## v3.3.3 vs v4.2.0005 late-proxy

v4.2.0005 的主要价值是修正 v4.2.0004 在 #61 上的异常 SP/q 单选问题。它把 #61 从单选胜改成 `负+平`，覆盖了实际客胜。

切换后救回的场次：

| # | 比赛 | 比分 | 赛果 | v3.3.3 | v4.2.0005 | v3收益 | v4收益 | 标签 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 | 澳大利亚 vs 埃及 | 1:1 | 平 | 负+胜 | 负+平 | -2.0000 | 0.5900 | probability_runner_up_protection;q_probability_disagree |
| 11 | 斯莱戈流浪者 vs 沙姆洛克流浪者 | 1:2 | 平 | 负+胜 | 负+平 | -2.0000 | 1.8800 | line_gap_missing;probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 20 | 全北现代 vs 江原FC | 1:2 | 负 | 胜+平 | 平+负 | -2.0000 | 2.0300 | raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 21 | 大田韩亚市民 vs 富川1995 | 2:2 | 平 | 胜+负 | 胜+平 | -2.0000 | 1.5700 | line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 23 | 忠北清州FC vs 大邱FC | 1:5 | 负 | 胜+平 | 胜+平+负 | -2.0000 | 0.4500 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 28 | 埃格尔松 vs 莫斯 | 3:0 | 胜 | 负 | 胜+负 | -1.0000 | 0.1200 | q_high_but_probability_low;q_probability_disagree |
| 32 | 查路 vs 伊尔维斯 | 2:1 | 胜 | 负+平 | 负+胜 | -2.0000 | 4.5900 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 塞伊奈约基 vs TPS图尔库 | 3:1 | 胜 | 负+平 | 负+平+胜 | -2.0000 | -0.0300 | q_probability_disagree;raw_strength_missing |
| 36 | 瓦萨 vs 玛丽港 | 4:0 | 胜 | 负+平 | 负+平+胜 | -2.0000 | 0.0100 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 39 | 加拿大 vs 摩洛哥 | 0:3 | 负 | 胜+平 | 胜+负 | -2.0000 | 1.1700 | q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 57 | MP米凯利 vs 哈卡 | 2:1 | 胜 | 负+平 | 胜+负 | -2.0000 | 0.5100 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 62 | 布鲁马波卡纳 vs 加尔斯 | 1:1 | 平 | 负 | 负+平 | -1.0000 | 1.2500 | raw_strength_missing |

切换后丢失的场次：

| # | 比赛 | 比分 | 赛果 | v3.3.3 | v4.2.0005 | v3收益 | v4收益 | 标签 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 天狼星 vs 米亚尔比 | 4:4 | 负 | 胜+负+平 | 平+胜 | -0.5800 | -2.0000 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 27 | 拉赫蒂 vs 格尼斯坦 | 1:0 | 胜 | 负+胜 | 平+负 | 0.6000 | -2.0000 | probability_runner_up_protection;q_top_odds_up;raw_strength_missing |
| 48 | 光州FC vs 蔚山HD | 1:1 | 胜 | 负+胜 | 负+平 | 2.1100 | -2.0000 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |

## 重点场

| 版本 | # | 比赛 | 比分 | 赛果 | 押保 | 命中 | 收益 | P 3/1/0 | q 3/1/0 | SP 3/1/0 | 原因/标签 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| shadow_v3.3.3 默认 | 51 | 庆南FC vs 天安城 | 2:1 | 胜(2.41) | 负+胜 | 1 | 0.4100 | 37.4%/30.1%/32.6% | 5.54/0.32/23.09 | 14.84/1.08/70.94 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| shadow_v3.3.3 默认 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负(3.05) | 胜+负 | 1 | 1.0500 | 29.5%/32.7%/37.8% | 9.90/0.68/0.77 | 33.51/2.08/2.03 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree |
| shadow_v3.3.3 默认 | 63 | 凯夫拉维克 vs 弗拉姆 | 1:1 | 平(5.01) | 负+平 | 1 | 3.0100 | 26.6%/25.8%/47.5% | 1.39/1.87/0.71 | 5.21/7.24/1.49 | q_high_but_probability_low;q_probability_disagree |
| v4.2.0004 late-proxy 观察 | 51 | 庆南FC vs 天安城 | 2:1 | 胜(2.41) | 胜+平 | 1 | 0.4100 | 37.4%/30.1%/32.6% | 0.90/1.00/1.15 | 2.40/3.32/3.52 | sp_repriced_after_late_refresh;severe_sp_repriced_after_late_refresh;full_required_but_value_below_threshold |
| v4.2.0004 late-proxy 观察 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负(3.05) | 胜 | 0 | -1.0000 | 29.5%/32.7%/37.8% | 0.78/1.33/1.00 | 2.65/4.06/2.64 | sp_repriced_after_late_refresh;severe_sp_repriced_after_late_refresh;late_refresh_proxy |
| v4.2.0004 late-proxy 观察 | 63 | 凯夫拉维克 vs 弗拉姆 | 1:1 | 平(5.01) | 负+平 | 1 | 3.0100 | 26.6%/25.8%/47.5% | 0.69/1.24/1.17 | 2.58/4.80/2.46 | sp_repriced_after_late_refresh;severe_sp_repriced_after_late_refresh;direct_buy |
| v4.2.0005 late-proxy 观察 | 51 | 庆南FC vs 天安城 | 2:1 | 胜(2.41) | 胜+平 | 1 | 0.4100 | 37.4%/30.1%/32.6% | 0.90/1.00/1.15 | 2.40/3.32/3.52 | sp_repriced_after_late_refresh;severe_sp_repriced_after_late_refresh;full_required_but_value_below_threshold |
| v4.2.0005 late-proxy 观察 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负(3.05) | 负+平 | 1 | 1.0500 | 29.5%/32.7%/37.8% | 0.71/1.26/1.15 | 2.41/3.86/3.05 | sp_repriced_after_late_refresh;severe_sp_repriced_after_late_refresh;late_refresh_proxy;extreme_source_q_repriced_probability_guard;restored_probability_top_0 |
| v4.2.0005 late-proxy 观察 | 63 | 凯夫拉维克 vs 弗拉姆 | 1:1 | 平(5.01) | 负+平 | 1 | 3.0100 | 26.6%/25.8%/47.5% | 1.05/1.24/0.88 | 3.93/4.80/1.86 | sp_repriced_after_late_refresh;direct_buy |

## 标签分布

| 标签 | 次数 |
| --- | --- |
| q_probability_disagree | 43 |
| raw_strength_missing | 39 |
| q_high_but_probability_low | 31 |
| probability_runner_up_protection | 28 |
| recent_form_intel_protection | 23 |
| line_gap_watch | 13 |
| line_gap_missing | 13 |
| raw_strength_not_handicap_result | 10 |
| raw_strength_handicap_remapped | 9 |
| q_top_odds_up | 7 |
| recent_form_full_guard | 6 |
| reverse_intel_adjacent_protection | 3 |

## 结论

1. `shadow_v3.3.3` 本期表现可用：覆盖命中率高，保护腿贡献明显，符合“先胜率、q 做保”的方向。
2. 本期 profit proxy 为正，但不要把它等同 N 串收益；它说明腿级押保质量尚可，后续还要进入票池组合和资金深度复盘。
3. #61 验证了我们前面的问题判断：极端早盘北单 SP/q 不能主导执行。v4.2.0005 的 extreme source q guard 是正确修复方向。
4. v4.2.0005 仍只能作为观察版：它会改变保护结构，救回一部分场，也会丢掉一部分原 v3.3.3 覆盖，尚不足以替代默认版。
5. 下一步策略开发应继续沿着 `v4.3 probability-first`：胜率决定主押，q/EV 决定保护和厚度，欧赔均值/临场 SP 只做异常锚和 sanity check。

明细 CSV：`results/issue_reviews/issue_26072_decision_variant_review.csv`
