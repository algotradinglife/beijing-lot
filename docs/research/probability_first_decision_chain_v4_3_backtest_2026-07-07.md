# Probability-first 决策链 v4.3.0000 回测

生成时间：2026-07-07 01:50:45Z

## 边界

- 样本：`llm_decision_snapshots.status='active'` 可复算期号：26071, 26072。
- v3.3.3 为按当前脚本复算的 shadow 口径；v4.2 为现有 `late_proxy_fullcap2` execution artifact，可用期号自动纳入。
- 赛果：优先 `matches.result_code`，主表未结算但 NowScore 完场时只用于命中评估。
- profit proxy：只对已有真实北单 `winning_sp` 的行计算，成本按每覆盖一个结果 1 单位。
- v4.3 不修改 release/default，不写 `llm_decision_snapshots`。
- v4.2 execution artifact 缺失期号：26071。

复现命令：

```bash
python3 scripts/evaluate_probability_first_decision_chain_v4_3.py --issue 26071 --issue 26072
```

## v4.3 规则摘要

1. 主押先锁让球后三结果概率 top；只有极近概率且有结构证据时才允许偏离，本版回测未主动偏离概率 top。
2. q/EV 只竞争保护位：q top 与概率 top 不一致时，不能成为 mandatory single，也不能替换概率 top。
3. SP sanity：源北单 SP 若相对同 payload 欧赔均值或最新北单 SP 严重背离，则源 q 降为风险标签；保护位改用最新北单 SP，缺失时用欧赔均值作为稳定锚。
4. 默认最多双选，避免把 v4.2 的执行压缩问题继续转嫁给全包。

## 整体结果

| arm | rows | 有赛果 | 有SP | 覆盖命中 | 主押命中 | 成本 | 均深 | profit proxy | ROI proxy | 票型 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3.3.3_recomputed | 81 | 81 | 81 | 79.0% | 42.0% | 169 | 2.086 | 15.3200 | 9.1% | {'double': 56, 'single': 9, 'full': 16} |
| v4.2.0004_execution_late_proxy | 65 | 65 | 65 | 89.2% | 46.2% | 135 | 2.077 | 39.4900 | 29.3% | {'double': 56, 'full': 7, 'single': 2} |
| v4.3_probability_first | 81 | 81 | 81 | 71.6% | 49.4% | 145 | 1.790 | 22.0500 | 15.2% | {'double': 64, 'single': 17} |

## 分期结果

| arm | issue | rows | 覆盖命中 | 主押命中 | profit | ROI | 均深 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v3.3.3_recomputed | 26071 | 16 | 87.5% | 56.2% | 8.7900 | 29.3% | 1.875 |
| v3.3.3_recomputed | 26072 | 65 | 76.9% | 38.5% | 6.5300 | 4.7% | 2.138 |
| v4.2.0004_execution_late_proxy | 26072 | 65 | 89.2% | 46.2% | 39.4900 | 29.3% | 2.077 |
| v4.3_probability_first | 26071 | 16 | 75.0% | 50.0% | 5.3900 | 20.7% | 1.625 |
| v4.3_probability_first | 26072 | 65 | 70.8% | 49.2% | 16.6600 | 14.0% | 1.831 |

## #51 / #61 专项

| arm | 期号 | # | 比赛 | 比分 | 赛果 | 押保 | 命中 | 主押 | prob_top | 源q top | 稳定q top | 源SP 3/1/0 | 稳定SP 3/1/0 | risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v3.3.3_recomputed | 26072 | 51 | 庆南FC vs 天安城 | 2:1 | 胜 | 负+胜 | 1 | 负 | 胜 | 负 | 负 | 14.84/1.08/70.94 | 14.84/1.08/70.94 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| v4.3_probability_first | 26072 | 51 | 庆南FC vs 天安城 | 2:1 | 胜 | 胜+平 | 1 | 胜 | 胜 | 负 | 负 | 14.84/1.08/70.94 | 2.41/3.32/3.52 | drop_source_q_top_after_sp_sanity;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| v3.3.3_recomputed | 26072 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负 | 胜+负 | 1 | 胜 | 负 | 胜 | 胜 | 33.51/2.08/2.03 | 33.51/2.08/2.03 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree |
| v4.3_probability_first | 26072 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负 | 负+平 | 1 | 负 | 负 | 胜 | 平 | 33.51/2.08/2.03 | 2.41/3.86/3.05 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| v4.2.0004_execution_late_proxy | 26072 | 51 | 庆南FC vs 天安城 | 2:1 | 胜 | 胜+平 | 1 | 胜 | 胜 | 负 | 负 | 14.84/1.08/70.94 | 2.40/3.32/3.52 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| v4.2.0004_execution_late_proxy | 26072 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负 | 胜 | 0 | 胜 | 负 | 胜 | 平 | 33.51/2.08/2.03 | 2.65/4.06/2.64 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree |

## v3.3.3 -> v4.3 切换

| 期号 | # | 比赛 | 比分 | 赛果 | v3.3.3 | v4.3 | v3命中 | v4.3命中 | prob_top | 源q top | 稳定q top | risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26071 | 1 | 瓦萨 vs 国际图尔库 | 2:3 | 负 | 平+负 | 负+平 | 1 | 1 | 负 | 负 | 负 |  |
| 26071 | 2 | 科特迪瓦 vs 挪威 | 1:2 | 负 | 负+胜 | 负+平 | 1 | 1 | 负 | 胜 | 胜 | q_top_not_used_as_primary |
| 26071 | 3 | 法国 vs 瑞典 | 3:0 | 胜 | 胜+负 | 负 | 1 | 0 | 负 | 负 | 负 | source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26071 | 4 | 博塔弗戈SP vs 巴西雷加塔斯 | 0:1 | 负 | 负+胜 | 胜+平 | 1 | 0 | 胜 | 负 | 平 | q_top_not_used_as_primary;q_top_stabilized_0_to_1 |
| 26071 | 5 | 墨西哥 vs 厄瓜多尔 | 2:0 | 胜 | 胜+负 | 胜+平 | 1 | 1 | 胜 | 负 | 胜 | q_top_not_used_as_primary;q_top_stabilized_0_to_3 |
| 26071 | 6 | 英格兰 vs 刚果(金) | 2:1 | 负 | 胜+负 | 负 | 1 | 1 | 负 | 负 | 负 | source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26071 | 8 | 比利时 vs 塞内加尔 | 2:2 | 平 | 胜 | 胜+平 | 0 | 1 | 胜 | 胜 | 胜 |  |
| 26071 | 9 | 美国 vs 波黑 | 2:0 | 胜 | 胜+负+平 | 负+胜 | 1 | 1 | 负 | 负 | 负 |  |
| 26071 | 10 | 利恩 vs 奥桑内 | 6:2 | 胜 | 胜+平 | 胜 | 1 | 1 | 胜 | 平 | 平 | q_top_not_used_as_primary |
| 26071 | 12 | 西班牙 vs 奥地利 | 3:0 | 胜 | 负+胜 | 负 | 1 | 0 | 负 | 胜 | 负 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_0;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26071 | 13 | 维京古尔 vs KA阿克雷里 | 3:2 | 负 | 负 | 负+平 | 1 | 1 | 负 | 负 | 负 |  |
| 26071 | 14 | 葡萄牙 vs 克罗地亚 | 2:1 | 平 | 负+胜+平 | 负+平 | 1 | 1 | 负 | 胜 | 负 | q_top_not_used_as_primary;q_top_stabilized_3_to_0 |
| 26071 | 16 | 瑞士 vs 阿尔及利亚 | 2:0 | 胜 | 胜+负 | 胜+平 | 1 | 1 | 胜 | 负 | 负 | q_top_not_used_as_primary |
| 26072 | 3 | 孔斯温厄尔 vs 松达尔 | 5:1 | 胜 | 负+胜+平 | 负+胜 | 1 | 1 | 负 | 负 | 负 |  |
| 26072 | 4 | 赖于福斯 vs 斯托曼 | 1:0 | 胜 | 胜+负 | 负+平 | 1 | 0 | 负 | 负 | 平 | q_top_stabilized_0_to_1 |
| 26072 | 5 | 天狼星 vs 米亚尔比 | 4:4 | 负 | 胜+负+平 | 负 | 1 | 1 | 负 | 负 | 负 |  |
| 26072 | 6 | 兰黑姆 vs 斯塔贝克 | 2:5 | 负 | 负 | 负+平 | 1 | 1 | 负 | 负 | 负 |  |
| 26072 | 8 | 德里城 vs 沃特福德FC | 2:4 | 负 | 胜+负+平 | 胜+负 | 1 | 1 | 胜 | 平 | 负 | q_top_not_used_as_primary;q_top_stabilized_1_to_0 |
| 26072 | 9 | 德罗赫达联 vs 波希米亚人 | 0:2 | 负 | 负+胜+平 | 胜+负 | 1 | 1 | 胜 | 平 | 负 | q_top_not_used_as_primary;q_top_stabilized_1_to_0 |
| 26072 | 10 | 圣帕特里克竞技 vs 戈尔韦联 | 3:0 | 胜 | 胜+负+平 | 胜+负 | 1 | 1 | 胜 | 负 | 负 |  |
| 26072 | 11 | 斯莱戈流浪者 vs 沙姆洛克流浪者 | 1:2 | 平 | 负+胜 | 胜+负 | 0 | 0 | 胜 | 胜 | 胜 |  |
| 26072 | 12 | 科夫漫步者 vs 科克城 | 0:1 | 平 | 负+胜+平 | 胜 | 1 | 0 | 胜 | 负 | 胜 | q_top_not_used_as_primary;q_top_stabilized_0_to_3 |
| 26072 | 13 | 布雷流浪者 vs 阿斯隆城 | 1:0 | 平 | 胜+负+平 | 负+平 | 1 | 1 | 负 | 平 | 负 | q_top_stabilized_1_to_0 |
| 26072 | 14 | 条约联 vs 凯里 | 2:1 | 胜 | 负+胜 | 胜+平 | 1 | 1 | 胜 | 胜 | 胜 |  |
| 26072 | 15 | 费恩哈普 vs 韦克斯福德 | 1:0 | 胜 | 胜+平 | 胜+负 | 1 | 1 | 胜 | 平 | 负 | q_top_not_used_as_primary;q_top_stabilized_1_to_0 |
| 26072 | 17 | FH哈夫纳夫约杜尔 vs 斯塔尔南 | 2:2 | 平 | 负+胜 | 胜+平 | 0 | 1 | 胜 | 胜 | 平 | q_top_stabilized_3_to_1 |
| 26072 | 19 | 哥伦比亚 vs 加纳 | 1:0 | 平 | 胜+负+平 | 负+胜 | 1 | 0 | 负 | 负 | 负 |  |
| 26072 | 21 | 大田韩亚市民 vs 富川1995 | 2:2 | 平 | 胜+负 | 胜 | 0 | 0 | 胜 | 负 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_3;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 22 | FC安养 vs 浦项铁人 | 2:3 | 负 | 负+胜 | 负+平 | 1 | 1 | 负 | 胜 | 负 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 24 | 安山绿人 vs 水原FC | 1:3 | 负 | 负+胜 | 胜+平 | 1 | 0 | 胜 | 胜 | 平 | q_top_stabilized_3_to_1;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 25 | 坡州前沿 vs 龙仁FC | 0:1 | 负 | 负+胜+平 | 负+平 | 1 | 1 | 负 | 胜 | 负 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 26 | 水原三星蓝翼 vs 城南FC | 1:0 | 平 | 负+平 | 负 | 1 | 0 | 负 | 负 | 胜 | q_top_stabilized_0_to_3 |
| 26072 | 27 | 拉赫蒂 vs 格尼斯坦 | 1:0 | 胜 | 负+胜 | 胜+平 | 1 | 1 | 胜 | 胜 | 平 | q_top_stabilized_3_to_1 |
| 26072 | 28 | 埃格尔松 vs 莫斯 | 3:0 | 胜 | 负 | 胜+平 | 0 | 1 | 胜 | 负 | 平 | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_1;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 29 | 代格福什 vs 马尔默 | 0:1 | 负 | 负+胜 | 负+平 | 1 | 1 | 负 | 胜 | 平 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 31 | EIF埃克奈斯 vs PK-35 | 0:3 | 负 | 负+胜 | 负+平 | 1 | 1 | 负 | 胜 | 平 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 32 | 查路 vs 伊尔维斯 | 2:1 | 胜 | 负+平 | 负+胜 | 0 | 1 | 负 | 平 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 34 | IA阿克拉内斯 vs 贝雷达比历克 | 1:2 | 负 | 负+胜 | 胜+平 | 1 | 0 | 胜 | 胜 | 平 | q_top_stabilized_3_to_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 35 | 赫德 vs 斯托姆加斯特 | 4:3 | 胜 | 负+胜+平 | 负+胜 | 1 | 1 | 负 | 胜 | 平 | q_top_stabilized_3_to_1;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 37 | IBV韦斯特曼纳 vs 瓦路尔 | 1:0 | 胜 | 胜+平 | 胜 | 1 | 1 | 胜 | 平 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 39 | 加拿大 vs 摩洛哥 | 0:3 | 负 | 胜+平 | 胜 | 0 | 0 | 胜 | 胜 | 胜 |  |
| 26072 | 40 | 朗福德城 vs 都柏林大学 | 2:1 | 胜 | 负+胜 | 负+平 | 1 | 0 | 负 | 胜 | 胜 | drop_source_q_top_after_sp_sanity;source_sp_anomaly_0;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 41 | 克里西乌马 vs 累西腓体育 | 1:0 | 胜 | 胜 | 胜+平 | 1 | 1 | 胜 | 胜 | 胜 |  |
| 26072 | 42 | 新奥里藏蒂诺 vs 戈亚尼亚竞技 | 3:0 | 胜 | 胜+负 | 胜+平 | 1 | 1 | 胜 | 负 | 平 | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_1;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 43 | 隆德里纳 vs 巴西雷加塔斯 | 5:0 | 胜 | 负+胜 | 胜+平 | 1 | 1 | 胜 | 胜 | 胜 | source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 44 | 巴拉圭 vs 法国 | 0:1 | 胜 | 负+胜 | 胜 | 1 | 1 | 胜 | 胜 | 胜 |  |
| 26072 | 45 | 戈亚斯 vs 塞阿拉 | 2:0 | 胜 | 胜+负+平 | 胜+平 | 1 | 1 | 胜 | 负 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_3;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 46 | FC首尔 vs 仁川联 | 1:0 | 平 | 负+胜 | 负 | 0 | 0 | 负 | 胜 | 负 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 47 | 金泉尚武 vs 济州SK | 1:1 | 平 | 负+胜+平 | 胜+平 | 1 | 1 | 胜 | 平 | 负 | q_top_stabilized_1_to_0 |
| 26072 | 49 | 金海FC vs 首尔衣恋 | 1:3 | 负 | 负+胜 | 胜+平 | 1 | 0 | 胜 | 胜 | 胜 |  |
| 26072 | 50 | 金浦FC vs 忠南牙山FC | 0:2 | 负 | 负+平 | 负+胜 | 1 | 1 | 负 | 平 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 51 | 庆南FC vs 天安城 | 2:1 | 胜 | 负+胜 | 胜+平 | 1 | 1 | 胜 | 负 | 负 | drop_source_q_top_after_sp_sanity;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 52 | 全南天龙 vs 釜山IPark | 3:3 | 胜 | 胜+平 | 胜 | 1 | 1 | 胜 | 平 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 53 | 哥德堡 vs AIK索尔纳 | 1:2 | 负 | 胜+负 | 胜+平 | 1 | 0 | 胜 | 负 | 平 | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_1;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 54 | 卡尔马 vs 厄尔格里特 | 3:0 | 胜 | 胜+负+平 | 胜+负 | 1 | 1 | 胜 | 负 | 负 | source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 56 | 埃尔夫斯堡 vs 哈马比 | 1:2 | 负 | 平+负 | 负+平 | 1 | 1 | 负 | 平 | 胜 | q_top_stabilized_1_to_3 |
| 26072 | 57 | MP米凯利 vs 哈卡 | 2:1 | 胜 | 负+平 | 胜 | 0 | 1 | 胜 | 平 | 胜 | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 58 | 巴西 vs 挪威 | 1:2 | 负 | 平+负+胜 | 负+平 | 1 | 1 | 负 | 胜 | 负 | q_top_not_used_as_primary;q_top_stabilized_3_to_0 |
| 26072 | 60 | 墨西哥 vs 英格兰 | 2:3 | 负 | 胜+负 | 负+平 | 1 | 1 | 负 | 负 | 胜 | q_top_stabilized_0_to_3 |
| 26072 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负 | 胜+负 | 负+平 | 1 | 1 | 负 | 胜 | 平 | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_3;source_sp_sanity_anomaly |

## 高 q / 低胜率切换样本

| 期号 | # | 比赛 | 比分 | 赛果 | v4.3 | 命中 | prob_top | 源q top | 稳定q top | 源q | q方向p | risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 26071 | 2 | 科特迪瓦 vs 挪威 | 1:2 | 负 | 负+平 | 1 | 负 | 胜 | 胜 | 1.462 | 28.6% | q_top_not_used_as_primary |
| 26071 | 5 | 墨西哥 vs 厄瓜多尔 | 2:0 | 胜 | 胜+平 | 1 | 胜 | 负 | 胜 | 1.329 | 24.1% | q_top_not_used_as_primary;q_top_stabilized_0_to_3 |
| 26071 | 16 | 瑞士 vs 阿尔及利亚 | 2:0 | 胜 | 胜+平 | 1 | 胜 | 负 | 负 | 1.875 | 24.1% | q_top_not_used_as_primary |
| 26072 | 2 | 耶尔文佩 vs 塞伊奈约基学院 | 1:0 | 胜 | 胜+平 | 1 | 胜 | 平 | 负 | 1.338 | 27.5% | q_top_stabilized_1_to_0 |
| 26072 | 10 | 圣帕特里克竞技 vs 戈尔韦联 | 3:0 | 胜 | 胜+负 | 1 | 胜 | 负 | 负 | 1.999 | 33.0% |  |
| 26072 | 15 | 费恩哈普 vs 韦克斯福德 | 1:0 | 胜 | 胜+负 | 1 | 胜 | 平 | 负 | 1.629 | 23.0% | q_top_not_used_as_primary;q_top_stabilized_1_to_0 |
| 26072 | 21 | 大田韩亚市民 vs 富川1995 | 2:2 | 平 | 胜 | 0 | 胜 | 负 | 胜 | 2.134 | 20.1% | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_3;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 22 | FC安养 vs 浦项铁人 | 2:3 | 负 | 负+平 | 1 | 负 | 胜 | 负 | 3.141 | 32.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 23 | 忠北清州FC vs 大邱FC | 1:5 | 负 | 胜+平 | 0 | 胜 | 平 | 平 | 1.327 | 24.3% |  |
| 26072 | 25 | 坡州前沿 vs 龙仁FC | 0:1 | 负 | 负+平 | 1 | 负 | 胜 | 负 | 4.697 | 27.2% | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 28 | 埃格尔松 vs 莫斯 | 3:0 | 胜 | 胜+平 | 1 | 胜 | 负 | 平 | 3.755 | 28.8% | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_1;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 29 | 代格福什 vs 马尔默 | 0:1 | 负 | 负+平 | 1 | 负 | 胜 | 平 | 3.873 | 27.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 30 | 哈尔姆斯塔德 vs 韦斯特罗斯 | 1:3 | 负 | 负+平 | 1 | 负 | 平 | 负 | 1.447 | 30.4% | q_top_stabilized_1_to_0 |
| 26072 | 31 | EIF埃克奈斯 vs PK-35 | 0:3 | 负 | 负+平 | 1 | 负 | 胜 | 平 | 2.668 | 27.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 32 | 查路 vs 伊尔维斯 | 2:1 | 胜 | 负+胜 | 1 | 负 | 平 | 胜 | 2.369 | 27.0% | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 33 | 塞伊奈约基 vs TPS图尔库 | 3:1 | 胜 | 负+平 | 0 | 负 | 平 | 平 | 2.835 | 30.5% | source_sp_anomaly_0;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 35 | 赫德 vs 斯托姆加斯特 | 4:3 | 胜 | 负+胜 | 1 | 负 | 胜 | 平 | 3.866 | 34.0% | q_top_stabilized_3_to_1;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 36 | 瓦萨 vs 玛丽港 | 4:0 | 胜 | 负+平 | 0 | 负 | 平 | 平 | 4.372 | 25.4% | source_sp_anomaly_0;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 37 | IBV韦斯特曼纳 vs 瓦路尔 | 1:0 | 胜 | 胜 | 1 | 胜 | 平 | 胜 | 5.145 | 23.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 38 | 布莱尼 vs 桑内斯乌尔夫 | 1:1 | 平 | 胜+平 | 1 | 胜 | 平 | 平 | 2.390 | 29.4% |  |
| 26072 | 40 | 朗福德城 vs 都柏林大学 | 2:1 | 胜 | 负+平 | 0 | 负 | 胜 | 胜 | 4.835 | 28.6% | drop_source_q_top_after_sp_sanity;source_sp_anomaly_0;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 42 | 新奥里藏蒂诺 vs 戈亚尼亚竞技 | 3:0 | 胜 | 胜+平 | 1 | 胜 | 负 | 平 | 15.470 | 25.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_1;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 45 | 戈亚斯 vs 塞阿拉 | 2:0 | 胜 | 胜+平 | 1 | 胜 | 负 | 胜 | 1.564 | 25.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_3;source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 46 | FC首尔 vs 仁川联 | 1:0 | 平 | 负 | 0 | 负 | 胜 | 负 | 1.647 | 22.5% | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_0;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 47 | 金泉尚武 vs 济州SK | 1:1 | 平 | 胜+平 | 1 | 胜 | 平 | 负 | 1.790 | 30.1% | q_top_stabilized_1_to_0 |
| 26072 | 50 | 金浦FC vs 忠南牙山FC | 0:2 | 负 | 负+胜 | 1 | 负 | 平 | 胜 | 2.527 | 26.1% | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 51 | 庆南FC vs 天安城 | 2:1 | 胜 | 胜+平 | 1 | 胜 | 负 | 负 | 23.094 | 32.6% | drop_source_q_top_after_sp_sanity;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 52 | 全南天龙 vs 釜山IPark | 3:3 | 胜 | 胜 | 1 | 胜 | 平 | 胜 | 2.327 | 23.7% | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 53 | 哥德堡 vs AIK索尔纳 | 1:2 | 负 | 胜+平 | 0 | 胜 | 负 | 平 | 8.942 | 25.1% | drop_source_q_top_after_sp_sanity;q_top_stabilized_0_to_1;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 54 | 卡尔马 vs 厄尔格里特 | 3:0 | 胜 | 胜+负 | 1 | 胜 | 负 | 负 | 2.412 | 31.7% | source_sp_anomaly_0;source_sp_sanity_anomaly |
| 26072 | 55 | 奥德 vs 海于格松 | 1:3 | 负 | 胜+平 | 0 | 胜 | 平 | 平 | 20.939 | 29.4% | source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 56 | 埃尔夫斯堡 vs 哈马比 | 1:2 | 负 | 负+平 | 1 | 负 | 平 | 胜 | 1.378 | 25.3% | q_top_stabilized_1_to_3 |
| 26072 | 57 | MP米凯利 vs 哈卡 | 2:1 | 胜 | 胜 | 1 | 胜 | 平 | 胜 | 15.927 | 26.3% | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_3;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 58 | 巴西 vs 挪威 | 1:2 | 负 | 负+平 | 1 | 负 | 胜 | 负 | 1.521 | 29.8% | q_top_not_used_as_primary;q_top_stabilized_3_to_0 |
| 26072 | 59 | 累西腓航海 vs 尤文图德 | 0:0 | 平 | 胜+平 | 1 | 胜 | 平 | 平 | 2.930 | 29.8% | source_sp_anomaly_0;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 61 | 赫根 vs 佐加顿斯 | 2:4 | 负 | 负+平 | 1 | 负 | 胜 | 平 | 9.898 | 29.5% | drop_source_q_top_after_sp_sanity;q_top_stabilized_3_to_1;source_sp_anomaly_3;source_sp_sanity_anomaly |
| 26072 | 63 | 凯夫拉维克 vs 弗拉姆 | 1:1 | 平 | 负+平 | 1 | 负 | 平 | 平 | 1.871 | 25.8% |  |
| 26072 | 64 | 博塔弗戈SP vs 阿瓦伊 | 3:1 | 胜 | 胜+平 | 1 | 胜 | 平 | 胜 | 3.425 | 29.8% | q_top_stabilized_1_to_3;source_sp_anomaly_1;source_sp_sanity_anomaly |
| 26072 | 65 | 维拉诺瓦 vs 圣贝尔纳多 | 2:1 | 胜 | 胜+负 | 1 | 胜 | 平 | 负 | 4.074 | 29.8% | drop_source_q_top_after_sp_sanity;q_top_stabilized_1_to_0;source_sp_anomaly_0;source_sp_anomaly_1;source_sp_anomaly_3;source_sp_sanity_anomaly |

完整 CSV：`docs/research/probability_first_decision_chain_v4_3_backtest_2026-07-07.csv`

## 结论

当前小样本结论偏向：v4.3 的 probability-first 框架是正确方向，尤其能直接修复 #61 这类“源北单 SP 极端导致 q 爆表、主押偏离概率 top”的问题；#51 也不再让源 q 方向主导主押。但 v4.3 双选默认覆盖率仍低于 v3.3.3，说明保护位还不够稳，不能替换默认。

上线判断：

- 不建议上线为 active/default；`shadow_v3.3.3` 继续保持默认。
- 可以进入下一步 execution/diagnostic 的逻辑：概率 top 主押硬约束、源 SP sanity 异常标签、q top 稳定化前后切换标签、源 q 不得成为 mandatory single。
- 暂不进入默认执行的逻辑：直接用欧赔均值替代北单 SP、把 stable q top 强制作为保护、扩大到默认全包。
- 下一步应把这些约束接入 v4.2 execution compression contract，并用 26073+ forward settlement 继续观察错删/新增保护。
