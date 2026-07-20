# v3.3.3 Phase 2 主押优化实验

日期：2026-07-11
状态：not eligible
开发段：26071, 26072
后段验证：26073, 26074

## 边界

- 仅使用 `active` snapshot 且 `generated_at <= kickoff_at`、已有赛果和真实结算 SP 的行。
- 每个候选逐行冻结 v3.3.3 的选择集合；只允许调整第一主押码，覆盖深度、覆盖命中和组合成本不变。
- 26071-26074 已被反复分析，本报告属于诊断/后段验证，不是最终未见样本。正式晋级仍需至少 300 场历史滚动验证和 5 期或 500 场 paper-forward。
- q-first 只作为消融诊断，不参与候选选择。多分类 Brier 使用同一概率向量，理论上各 arm 完全相同。

## 总体比较

| 段 | arm | n | 主押命中 | 相对基线 | 主押 Brier | 主押 profit | 覆盖命中 | 均深 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development | baseline_v3.3.3 | 72 | 40.3% | +0.0pp | 0.2276 | -0.69 | 77.8% | 2.097 |
| development | draw_aware_gap_0.02 | 72 | 47.2% | +6.9pp | 0.2483 | 12.21 | 77.8% | 2.097 |
| development | draw_aware_gap_0.04 | 72 | 47.2% | +6.9pp | 0.2480 | 12.21 | 77.8% | 2.097 |
| development | draw_aware_gap_0.06 | 72 | 47.2% | +6.9pp | 0.2480 | 12.21 | 77.8% | 2.097 |
| development | handicap_gated_probability_first | 72 | 50.0% | +9.7pp | 0.2548 | 17.69 | 77.8% | 2.097 |
| development | no_handicap_fit | 72 | 43.1% | +2.8pp | 0.2327 | 4.08 | 77.8% | 2.097 |
| development | no_recent_form | 72 | 37.5% | -2.8pp | 0.2248 | -5.77 | 77.8% | 2.097 |
| development | probability_first | 72 | 47.2% | +6.9pp | 0.2483 | 12.21 | 77.8% | 2.097 |
| development | q_first_diagnostic | 72 | 29.2% | -11.1pp | 0.1957 | 0.28 | 77.8% | 2.097 |
| validation | baseline_v3.3.3 | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | draw_aware_gap_0.02 | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | draw_aware_gap_0.04 | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | draw_aware_gap_0.06 | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | handicap_gated_probability_first | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | no_handicap_fit | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | no_recent_form | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | probability_first | 25 | 40.0% | +0.0pp | 0.2397 | -0.96 | 72.0% | 1.840 |
| validation | q_first_diagnostic | 25 | 36.0% | -4.0pp | 0.2449 | 7.81 | 72.0% | 1.840 |

开发段自动选择的候选为 `handicap_gated_probability_first`。开发段相对基线 +9.7pp，后段验证 +0.0pp；当前判断：**not eligible**。

## 分期对照

| 期号 | arm | n | 主押命中 | Brier | 主押 profit |
| --- | --- | --- | --- | --- | --- |
| 26071 | baseline_v3.3.3 | 7 | 57.1% | 0.2545 | 2.83 |
| 26071 | handicap_gated_probability_first | 7 | 57.1% | 0.2545 | 2.83 |
| 26072 | baseline_v3.3.3 | 65 | 38.5% | 0.2247 | -3.52 |
| 26072 | handicap_gated_probability_first | 65 | 49.2% | 0.2549 | 14.86 |
| 26073 | baseline_v3.3.3 | 10 | 20.0% | 0.2059 | -4.02 |
| 26073 | handicap_gated_probability_first | 10 | 20.0% | 0.2059 | -4.02 |
| 26074 | baseline_v3.3.3 | 15 | 53.3% | 0.2621 | 3.06 |
| 26074 | handicap_gated_probability_first | 15 | 53.3% | 0.2621 | 3.06 |

## A/B/C 主押等级

等级只使用决策时点主押概率和概率间距：A 为高概率且明显领先，B 为中等强度，其他为 C。

| 段 | 等级 | n | 命中 | Brier | 主押 profit |
| --- | --- | --- | --- | --- | --- |
| development | A | 43 | 53.5% | 0.2574 | 11.92 |
| development | B | 20 | 50.0% | 0.2630 | 6.05 |
| development | C | 9 | 33.3% | 0.2241 | -0.28 |
| validation | A | 17 | 41.2% | 0.2465 | -0.27 |
| validation | B | 5 | 60.0% | 0.2763 | 2.31 |
| validation | C | 3 | 0.0% | 0.1398 | -3.00 |

## 分层稳定性

联赛仅显示样本数不少于 3 的分组；小分组只用于定位，不作为规则依据。

| 段 | 维度 | 分组 | n | 基线 | 候选 | 差值 |
| --- | --- | --- | --- | --- | --- | --- |
| development | handicap_bucket | home_gets_1 | 12 | 41.7% | 41.7% | +0.0pp |
| development | handicap_bucket | home_gets_2plus | 2 | 50.0% | 50.0% | +0.0pp |
| development | handicap_bucket | home_gives_1 | 13 | 23.1% | 38.5% | +15.4pp |
| development | handicap_bucket | home_gives_2plus | 5 | 40.0% | 40.0% | +0.0pp |
| development | handicap_bucket | level | 40 | 45.0% | 57.5% | +12.5pp |
| validation | handicap_bucket | home_gets_1 | 2 | 50.0% | 50.0% | +0.0pp |
| validation | handicap_bucket | home_gives_1 | 7 | 28.6% | 28.6% | +0.0pp |
| validation | handicap_bucket | home_gives_2plus | 5 | 60.0% | 60.0% | +0.0pp |
| validation | handicap_bucket | level | 11 | 36.4% | 36.4% | +0.0pp |
| development | intelligence_status | missing | 1 | 100.0% | 100.0% | +0.0pp |
| development | intelligence_status | ok | 71 | 39.4% | 49.3% | +9.9pp |
| validation | intelligence_status | missing | 25 | 40.0% | 40.0% | +0.0pp |
| development | league | K1联赛 | 6 | 16.7% | 16.7% | +0.0pp |
| development | league | K2联赛 | 8 | 62.5% | 75.0% | +12.5pp |
| development | league | 世界杯 | 10 | 20.0% | 40.0% | +20.0pp |
| development | league | 冰岛超 | 6 | 66.7% | 50.0% | -16.7pp |
| development | league | 巴西乙 | 8 | 62.5% | 75.0% | +12.5pp |
| development | league | 挪甲 | 8 | 37.5% | 25.0% | -12.5pp |
| development | league | 爱甲 | 5 | 20.0% | 40.0% | +20.0pp |
| development | league | 爱超 | 5 | 60.0% | 60.0% | +0.0pp |
| development | league | 瑞典超 | 8 | 37.5% | 75.0% | +37.5pp |
| development | league | 芬甲 | 4 | 50.0% | 50.0% | +0.0pp |
| development | league | 芬超 | 4 | 0.0% | 25.0% | +25.0pp |
| validation | league | 世界杯 | 4 | 0.0% | 0.0% | +0.0pp |
| validation | league | 巴西乙 | 4 | 25.0% | 25.0% | +0.0pp |
| validation | league | 爱甲 | 5 | 60.0% | 60.0% | +0.0pp |

## 候选切换明细

| 段 | 期号 | # | 比赛 | 赛果 | 冻结覆盖 | 旧押 | 新押 | 旧中 | 新中 | fit | form |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| development | 26072 | 4 | 赖于福斯 vs 斯托曼 | 胜 | 3+0 | 3 | 0 | 1 | 0 | - | 3 |
| development | 26072 | 5 | 天狼星 vs 米亚尔比 | 负 | 3+0+1 | 3 | 0 | 0 | 1 | 1 | 3 |
| development | 26072 | 13 | 布雷流浪者 vs 阿斯隆城 | 平 | 3+0+1 | 3 | 0 | 0 | 0 | - | 3 |
| development | 26072 | 14 | 条约联 vs 凯里 | 胜 | 0+3 | 0 | 3 | 0 | 1 | - | 0 |
| development | 26072 | 17 | FH哈夫纳夫约杜尔 vs 斯塔尔南 | 平 | 0+3 | 0 | 3 | 0 | 0 | - | 0 |
| development | 26072 | 19 | 哥伦比亚 vs 加纳 | 平 | 3+0+1 | 3 | 0 | 0 | 0 | 1 | 3 |
| development | 26072 | 27 | 拉赫蒂 vs 格尼斯坦 | 胜 | 0+3 | 0 | 3 | 0 | 1 | - | 0 |
| development | 26072 | 34 | IA阿克拉内斯 vs 贝雷达比历克 | 负 | 0+3 | 0 | 3 | 1 | 0 | - | 0 |
| development | 26072 | 43 | 隆德里纳 vs 巴西雷加塔斯 | 胜 | 0+3 | 0 | 3 | 0 | 1 | - | 0 |
| development | 26072 | 47 | 金泉尚武 vs 济州SK | 平 | 0+3+1 | 0 | 3 | 0 | 0 | - | 0 |
| development | 26072 | 51 | 庆南FC vs 天安城 | 胜 | 0+3 | 0 | 3 | 0 | 1 | - | 0 |
| development | 26072 | 56 | 埃尔夫斯堡 vs 哈马比 | 负 | 1+0 | 1 | 0 | 0 | 1 | 1 | 3 |
| development | 26072 | 58 | 巴西 vs 挪威 | 负 | 1+0+3 | 1 | 0 | 0 | 1 | 1 | 3 |
| development | 26072 | 60 | 墨西哥 vs 英格兰 | 负 | 3+0 | 3 | 0 | 0 | 1 | 3 | 3 |
| development | 26072 | 61 | 赫根 vs 佐加顿斯 | 负 | 3+0 | 3 | 0 | 0 | 1 | 3 | 3 |

## 结论

- 覆盖集合和成本 invariant 由测试与逐行审计保证，因此覆盖率、平均深度及覆盖 profit 不因主押候选变化。
- 当前样本不足 Phase 2 晋级门槛；即使后段改善，也只能发布为新的 paper shadow，不能修改 `active_v3.3.3`。
- 后续重点是扩大严格开赛前 snapshot 样本，并验证 A/B/C 命中是否单调；不单独因本报告调整资金权重。
