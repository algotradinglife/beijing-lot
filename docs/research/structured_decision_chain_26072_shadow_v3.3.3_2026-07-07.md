# 结构化决策链 26072 shadow_v3.3.3 回测

生成时间：2026-07-07 14:26:13Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`67/67`；缺失场次 `[]`。
- 未结算比赛只生成 shadow 决策，不计入命中率和 profit proxy。
- 本报告不写回 `llm_decision_snapshots`，不生成 active/draft replacement，不改变主策略票池。
- profit proxy 是单腿层面的简化评估：每选一个结果记 1 单位成本，命中返还该场 `winning_sp`；不是 N 串 ticket-level 回放。

## Schema

| 分类 | 作用 | 约束 |
| --- | --- | --- |
| raw_strength | 只判断原始强弱/情报情绪，如“瑞士胜利在望” | 不能直接等同北单让球后胜平负 |
| handicap_fit | 将 raw_strength 谨慎映射到北单整数让球结果 | 深让球必须有大胜/穿盘证据，否则降权或转观察/让球平 |
| market_q_ev | 计算各结果 `q=让球后概率*SP` 和 odds drift 诊断 | q 不再默认决定主押，只在过线且与主押不一致时作为保护/增厚 |
| model_probability | 让球校准后的三结果概率 | 主押基础信号 |
| form_recent | 近期胜平负结构和双方走势 | 轻权重影响主押，并经北单让球映射后输入 `llm_intel_protection` |
| competition_context | 联赛/杯赛/淘汰赛等赛制上下文 | 只作风险提示或小权重 |
| llm_intel_protection | 单独解读情报文本并考虑北单让球，判断是否增加保护 | 只能增加保护，不能改主押；当前历史回测无真实 LLM advice 时使用 `script_proxy` |
| data_quality/risk | 缺失、偏移、q高但胜率低、情报与让球冲突 | 关键输入缺失或风险过高时标记停，不清空押/保 |

## Aggregator

1. `max_q < 1.00` 或关键概率/SP 缺失时标记停；停只是风控观察标签，不覆盖押/保输出。
2. 主押由让球后概率、`handicap_fit` 和近期形态加权得到；raw 情报和近期形态都必须先过北单让球语境。
3. 当 q/EV 最高方向与主押不同且 q 过线时，将 q 方向加入保护，不反客为主。
4. `llm_intel_protection` 可在情报、近期表现与让球结构提示死腿风险时追加保护，但必须通过强度或基础概率/q护栏。
5. 近期表现保护默认只能把单选补成双选；若会把已有双选扩成全包，必须同时满足更高强度与更高概率/q，否则只保留诊断标签。
6. line-gap 和 drift 只进入诊断/风险标签，不作为 hard gate。

## 指标

| 方案 | 下注场 | 主押命中 | 押+保命中 | 成本 | profit proxy | ROI proxy | 票型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| active_v3 | 67 | 37.3% | 49.3% | 98 | 9.090 | 9.3% | {'double': 31, 'single': 36} |
| shadow_v3.3.3 | 67 | 40.3% | 77.6% | 143 | 8.650 | 6.0% | {'double': 48, 'full': 14, 'single': 5} |

## v3 vs shadow_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 挪甲 | 孔斯温厄尔 | 松达尔 | -1.000 | 5:1 | 胜(孔斯温厄尔) | 0 | 0 | 0+3+1 | 1 | 0.110 | 0 | 0 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 4 | 挪甲 | 赖于福斯 | 斯托曼 | 0.000 | 1:0 | 胜(赖于福斯) | 0 | 0 | 3+0 | 1 | 1.630 | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 5 | 瑞典超 | 天狼星 | 米亚尔比 | -1.000 | 4:4 | 负(米亚尔比) | 0+3 | 1 | 3+0+1 | 1 | -1.000 | 0 | 0 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 7 | 世界杯 | 澳大利亚 | 埃及 | 0.000 | 1:1 | 平 | 3 | 0 | 0+3 | 0 | -1.000 | 0 | 3 | probability_runner_up_protection;q_probability_disagree |
| 8 | 爱超 | 德里城 | 沃特福德FC | -1.000 | 2:4 | 负(沃特福德FC) | 1+3 | 0 | 3+0+1 | 1 | 2.810 | 3 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 9 | 爱超 | 德罗赫达联 | 波希米亚人 | 1.000 | 0:2 | 负(波希米亚人) | 1+0 | 1 | 0+3+1 | 1 | -1.000 | 3 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 10 | 爱超 | 圣帕特里克竞技 | 戈尔韦联 | -1.000 | 3:0 | 胜(圣帕特里克竞技) | 0 | 0 | 3+0+1 | 1 | 0.240 | 3 | 0 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 11 | 爱超 | 斯莱戈流浪者 | 沙姆洛克流浪者 | 1.000 | 1:2 | 平 | 3 | 0 | 0+3 | 0 | -1.000 | 3 | 3 | line_gap_missing;probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 12 | 爱甲 | 科夫漫步者 | 科克城 | 1.000 | 0:1 | 平 | 0+1 | 1 | 0+3+1 | 1 | -1.000 | 3 | 0 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 13 | 爱甲 | 布雷流浪者 | 阿斯隆城 | -1.000 | 1:0 | 平 | 1+0 | 1 | 3+0+1 | 1 | -1.000 | 0 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 14 | 爱甲 | 条约联 | 凯里 | 0.000 | 2:1 | 胜(条约联) | 3+0 | 1 | 0+3 | 1 | 0.000 | 3 | 3 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 15 | 爱甲 | 费恩哈普 | 韦克斯福德 | 1.000 | 1:0 | 胜(费恩哈普) | 1+0 | 0 | 3+1 | 1 | 2.000 | 3 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 17 | 冰岛超 | FH哈夫纳夫约杜尔 | 斯塔尔南 | 0.000 | 2:2 | 平 | 3+1 | 1 | 0+3 | 0 | -5.190 | 3 | 3 | probability_runner_up_protection;raw_strength_missing |
| 18 | 世界杯 | 阿根廷 | 佛得角 | -2.000 | 1:1 | 负(佛得角) | 3+0 | 1 | 0 | 1 | 1.000 | 0 | 0 | q_top_odds_up;raw_strength_not_handicap_result |
| 19 | 世界杯 | 哥伦比亚 | 加纳 | -1.000 | 1:0 | 平 | 3+0 | 0 | 3+0+1 | 1 | 1.940 | 0 | 0 | probability_runner_up_protection;q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 20 | K1联赛 | 全北现代 | 江原FC | 0.000 | 1:2 | 负(江原FC) | 3 | 0 | 3+1 | 0 | -1.000 | 3 | 3 | raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 22 | K1联赛 | FC安养 | 浦项铁人 | 0.000 | 2:3 | 负(浦项铁人) | 3 | 0 | 0+3 | 1 | 1.670 | 0 | 3 | probability_runner_up_protection;q_probability_disagree;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 23 | K2联赛 | 忠北清州FC | 大邱FC | 1.000 | 1:5 | 负(大邱FC) | 1 | 0 | 3+1 | 0 | -1.000 | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 24 | K2联赛 | 安山绿人 | 水原FC | 1.000 | 1:3 | 负(水原FC) | 3 | 0 | 0+3 | 1 | 1.770 | 3 | 3 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 25 | K2联赛 | 坡州前沿 | 龙仁FC | 0.000 | 0:1 | 负(龙仁FC) | 0+3 | 1 | 0+3+1 | 1 | -1.000 | 0 | 3 | q_high_but_probability_low;q_probability_disagree;q_top_odds_up |
| 26 | K2联赛 | 水原三星蓝翼 | 城南FC | -1.000 | 1:0 | 平 | 0 | 0 | 0+1 | 1 | 2.660 | 0 | 0 | line_gap_watch;raw_strength_missing;recent_form_intel_protection |
| 27 | 芬超 | 拉赫蒂 | 格尼斯坦 | 0.000 | 1:0 | 胜(拉赫蒂) | 3+1 | 1 | 0+3 | 1 | 0.000 | 3 | 3 | probability_runner_up_protection;q_top_odds_up;raw_strength_missing |
| 30 | 瑞典超 | 哈尔姆斯塔德 | 韦斯特罗斯 | 0.000 | 1:3 | 负(韦斯特罗斯) | 1 | 0 | 0+1 | 1 | 1.440 | 0 | 1 | q_probability_disagree;raw_strength_missing |
| 32 | 芬超 | 查路 | 伊尔维斯 | 0.000 | 2:1 | 胜(查路) | 1+3 | 1 | 0+1 | 0 | -6.590 | 0 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 芬超 | 塞伊奈约基 | TPS图尔库 | -1.000 | 3:1 | 胜(塞伊奈约基) | 1+0 | 0 | 0+1 | 0 | 0.000 | 0 | 1 | q_probability_disagree;raw_strength_missing |
| 34 | 冰岛超 | IA阿克拉内斯 | 贝雷达比历克 | 0.000 | 1:2 | 负(贝雷达比历克) | 3 | 0 | 0+3 | 1 | 1.420 | 3 | 3 | probability_runner_up_protection;raw_strength_missing |
| 35 | 挪甲 | 赫德 | 斯托姆加斯特 | 1.000 | 4:3 | 胜(赫德) | 3 | 1 | 0+3+1 | 1 | -2.000 | 0 | 3 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 37 | 冰岛超 | IBV韦斯特曼纳 | 瓦路尔 | 0.000 | 1:0 | 胜(IBV韦斯特曼纳) | 1 | 0 | 3+1 | 1 | 1.720 | 3 | 1 | q_high_but_probability_low;q_probability_disagree |
| 38 | 挪甲 | 布莱尼 | 桑内斯乌尔夫 | 0.000 | 1:1 | 平 | 1 | 1 | 3+1 | 1 | -1.000 | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |
| 39 | 世界杯 | 加拿大 | 摩洛哥 | 1.000 | 0:3 | 负(摩洛哥) | 3 | 0 | 3+1 | 0 | -1.000 | 3 | 3 | q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 40 | 爱甲 | 朗福德城 | 都柏林大学 | 0.000 | 2:1 | 胜(朗福德城) | 3 | 1 | 0+3 | 1 | -1.000 | 0 | 3 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 巴西乙 | 克里西乌马 | 累西腓体育 | 0.000 | 1:0 | 胜(克里西乌马) | 0+3 | 1 | 3 | 1 | 1.000 | 3 | 3 | line_gap_watch |
| 42 | 巴西乙 | 新奥里藏蒂诺 | 戈亚尼亚竞技 | 0.000 | 3:0 | 胜(新奥里藏蒂诺) | 0 | 0 | 3+0 | 1 | 1.250 | 3 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 巴西乙 | 隆德里纳 | 巴西雷加塔斯 | 0.000 | 5:0 | 胜(隆德里纳) | 3 | 1 | 0+3 | 1 | -1.000 | 3 | 3 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 44 | 世界杯 | 巴拉圭 | 法国 | 2.000 | 0:1 | 胜(巴拉圭) | 3 | 1 | 0+3 | 1 | -1.000 | 3 | 3 | probability_runner_up_protection |
| 45 | 巴西乙 | 戈亚斯 | 塞阿拉 | 0.000 | 2:0 | 胜(戈亚斯) | 0 | 0 | 3+0+1 | 1 | 0.400 | 3 | 0 | q_high_but_probability_low;q_probability_disagree |
| 47 | K1联赛 | 金泉尚武 | 济州SK | 0.000 | 1:1 | 平 | 1 | 1 | 0+3+1 | 1 | -2.000 | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 48 | K1联赛 | 光州FC | 蔚山HD | 1.000 | 1:1 | 胜(光州FC) | 0 | 0 | 0+3 | 1 | 3.110 | 0 | 0 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 49 | K2联赛 | 金海FC | 首尔衣恋 | 1.000 | 1:3 | 负(首尔衣恋) | 3 | 0 | 0+3 | 1 | 1.500 | 3 | 3 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 50 | K2联赛 | 金浦FC | 忠南牙山FC | -1.000 | 0:2 | 负(忠南牙山FC) | 1+3 | 0 | 0+1 | 1 | 2.220 | 0 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 51 | K2联赛 | 庆南FC | 天安城 | 0.000 | 2:1 | 胜(庆南FC) | 0 | 0 | 0+3 | 1 | 1.410 | 3 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 53 | 瑞典超 | 哥德堡 | AIK索尔纳 | 0.000 | 1:2 | 负(AIK索尔纳) | 0 | 1 | 3+0 | 1 | -1.000 | 3 | 0 | q_high_but_probability_low;q_probability_disagree |
| 54 | 瑞典超 | 卡尔马 | 厄尔格里特 | -1.000 | 3:0 | 胜(卡尔马) | 0 | 0 | 3+0+1 | 1 | 0.330 | 3 | 0 | q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 55 | 挪甲 | 奥德 | 海于格松 | 0.000 | 1:3 | 负(海于格松) | 1 | 0 | 3+1 | 0 | -1.000 | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | 瑞典超 | 埃尔夫斯堡 | 哈马比 | 0.000 | 1:2 | 负(哈马比) | 0+1 | 1 | 1+0 | 1 | 0.000 | 0 | 1 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;recent_form_full_guard;recent_form_intel_protection |
| 57 | 芬甲 | MP米凯利 | 哈卡 | 1.000 | 2:1 | 胜(MP米凯利) | 3+1 | 1 | 0+1 | 0 | -2.510 | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 58 | 世界杯 | 巴西 | 挪威 | -1.000 | 1:2 | 负(挪威) | 0+3 | 1 | 1+0+3 | 1 | -1.000 | 0 | 3 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 59 | 巴西乙 | 累西腓航海 | 尤文图德 | 0.000 | 0:0 | 平 | 1 | 1 | 3+1 | 1 | -1.000 | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 61 | 瑞典超 | 赫根 | 佐加顿斯 | 0.000 | 2:4 | 负(佐加顿斯) | 3 | 0 | 3+0 | 1 | 2.050 | 0 | 3 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree |
| 63 | 冰岛超 | 凯夫拉维克 | 弗拉姆 | 0.000 | 1:1 | 平 | 1 | 1 | 0+1 | 1 | -1.000 | 0 | 1 | q_high_but_probability_low;q_probability_disagree |
| 64 | 巴西乙 | 博塔弗戈SP | 阿瓦伊 | 0.000 | 3:1 | 胜(博塔弗戈SP) | 1 | 0 | 3+1 | 1 | 1.440 | 3 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 65 | 巴西乙 | 维拉诺瓦 | 圣贝尔纳多 | 0.000 | 2:1 | 胜(维拉诺瓦) | 1+0 | 0 | 3+1 | 1 | 2.730 | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 67 | 世界杯 | 美国 | 比利时 | 0.000 | 1:4 | 负(比利时) | 0 | 1 | 0+3 | 1 | -1.000 | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |

## 26072 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 芬甲 | KTP科特卡 | 吉波 | 0.000 | 3:3 | 平 | 3+1 | 1 | 3+1 |  | 0.000 | 1 | 3 | 1 | 1.173 |  |  | 3 | 3 | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 2 | 芬甲 | 耶尔文佩 | 塞伊奈约基学院 | 0.000 | 1:0 | 胜(耶尔文佩) | 3+1 | 1 | 3+1 |  | 0.000 | 1 | 3 | 1 | 1.338 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 3 | 挪甲 | 孔斯温厄尔 | 松达尔 | -1.000 | 5:1 | 胜(孔斯温厄尔) | 0 | 0 | 0+3+1 | 1 | 0.678 | 1 | 0 | 0 | 1.655 | home | 1 | 3 | 1 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 4 | 挪甲 | 赖于福斯 | 斯托曼 | 0.000 | 1:0 | 胜(赖于福斯) | 0 | 0 | 3+0 |  | 0.000 | 1 | 0 | 0 | 1.544 |  |  | 3 | 3 | probability_runner_up_protection;raw_strength_missing |
| 5 | 瑞典超 | 天狼星 | 米亚尔比 | -1.000 | 4:4 | 负(米亚尔比) | 0+3 | 1 | 3+0+1 | 1 | 0.742 | 1 | 0 | 0 | 1.111 | home | 1 | 3 | 1 | probability_runner_up_protection;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 6 | 挪甲 | 兰黑姆 | 斯塔贝克 | 0.000 | 2:5 | 负(斯塔贝克) | 0 | 1 | 0 |  | 0.000 | 1 | 0 | 0 | 1.511 | home | 3 | 0 | 0 |  |
| 7 | 世界杯 | 澳大利亚 | 埃及 | 0.000 | 1:1 | 平 | 3 | 0 | 0+3 |  | 0.000 | 0 | 0 | 3 | 1.257 | away | 0 | 0 | 0 | probability_runner_up_protection;q_probability_disagree |
| 8 | 爱超 | 德里城 | 沃特福德FC | -1.000 | 2:4 | 负(沃特福德FC) | 1+3 | 0 | 3+0+1 |  | 0.000 | 1 | 3 | 1 | 1.200 |  |  | 3 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 9 | 爱超 | 德罗赫达联 | 波希米亚人 | 1.000 | 0:2 | 负(波希米亚人) | 1+0 | 1 | 0+3+1 | 1 | 0.769 | 1 | 3 | 1 | 1.266 |  |  | 0 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 10 | 爱超 | 圣帕特里克竞技 | 戈尔韦联 | -1.000 | 3:0 | 胜(圣帕特里克竞技) | 0 | 0 | 3+0+1 |  | 0.000 | 1 | 3 | 0 | 1.999 | home | 1 | 3 | 1 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 11 | 爱超 | 斯莱戈流浪者 | 沙姆洛克流浪者 | 1.000 | 1:2 | 平 | 3 | 0 | 0+3 | 1 | 0.756 | 0 | 3 | 3 | 1.488 |  |  | 0 | 1 | line_gap_missing;probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 12 | 爱甲 | 科夫漫步者 | 科克城 | 1.000 | 0:1 | 平 | 0+1 | 1 | 0+3+1 | 1 | 0.756 | 1 | 3 | 0 | 1.116 |  |  | 0 | 1 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 13 | 爱甲 | 布雷流浪者 | 阿斯隆城 | -1.000 | 1:0 | 平 | 1+0 | 1 | 3+0+1 | 1 | 0.771 | 1 | 0 | 1 | 1.280 |  |  | 3 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 14 | 爱甲 | 条约联 | 凯里 | 0.000 | 2:1 | 胜(条约联) | 3+0 | 1 | 0+3 |  | 0.000 | 1 | 3 | 3 | 1.441 |  |  | 0 | 0 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 15 | 爱甲 | 费恩哈普 | 韦克斯福德 | 1.000 | 1:0 | 胜(费恩哈普) | 1+0 | 0 | 3+1 | 1 | 0.675 | 1 | 3 | 1 | 1.629 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 16 | 爱超 | 谢尔伯恩 | 邓多克 | 0.000 | 2:1 | 胜(谢尔伯恩) | 3+1 | 1 | 3+1 |  | 0.000 | 1 | 3 | 1 | 1.180 | home | 3 | 3 | 3 | line_gap_missing;q_probability_disagree |
| 17 | 冰岛超 | FH哈夫纳夫约杜尔 | 斯塔尔南 | 0.000 | 2:2 | 平 | 3+1 | 1 | 0+3 |  | 0.000 | 0 | 3 | 3 | 1.506 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 18 | 世界杯 | 阿根廷 | 佛得角 | -2.000 | 1:1 | 负(佛得角) | 3+0 | 1 | 0 |  | 0.000 | 1 | 0 | 0 | 1.566 | home |  | 3 |  | q_top_odds_up;raw_strength_not_handicap_result |
| 19 | 世界杯 | 哥伦比亚 | 加纳 | -1.000 | 1:0 | 平 | 3+0 | 0 | 3+0+1 | 1 | 0.749 | 1 | 0 | 0 | 1.857 | home | 1 | 3 | 1 | probability_runner_up_protection;q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 20 | K1联赛 | 全北现代 | 江原FC | 0.000 | 1:2 | 负(江原FC) | 3 | 0 | 3+1 | 1 | 0.662 | 0 | 3 | 3 | 3.735 |  |  | 0 | 0 | raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 21 | K1联赛 | 大田韩亚市民 | 富川1995 | 0.000 | 2:2 | 平 | 3+0 | 0 | 3+0 |  | 0.000 | 0 | 3 | 0 | 2.135 |  |  | 0 | 0 | line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 22 | K1联赛 | FC安养 | 浦项铁人 | 0.000 | 2:3 | 负(浦项铁人) | 3 | 0 | 0+3 | 1 | 0.665 | 1 | 0 | 3 | 3.141 | away | 0 | 3 | 3 | probability_runner_up_protection;q_probability_disagree;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 23 | K2联赛 | 忠北清州FC | 大邱FC | 1.000 | 1:5 | 负(大邱FC) | 1 | 0 | 3+1 | 1 | 0.686 | 0 | 3 | 1 | 1.327 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 24 | K2联赛 | 安山绿人 | 水原FC | 1.000 | 1:3 | 负(水原FC) | 3 | 0 | 0+3 | 1 | 0.751 | 1 | 3 | 3 | 1.516 |  |  | 0 | 1 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 25 | K2联赛 | 坡州前沿 | 龙仁FC | 0.000 | 0:1 | 负(龙仁FC) | 0+3 | 1 | 0+3+1 | 1 | 0.674 | 1 | 0 | 3 | 4.697 | draw | 1 | 0 | 0 | q_high_but_probability_low;q_probability_disagree;q_top_odds_up |
| 26 | K2联赛 | 水原三星蓝翼 | 城南FC | -1.000 | 1:0 | 平 | 0 | 0 | 0+1 | 1 | 0.668 | 1 | 0 | 0 | 1.417 |  |  | 3 | 1 | line_gap_watch;raw_strength_missing;recent_form_intel_protection |
| 27 | 芬超 | 拉赫蒂 | 格尼斯坦 | 0.000 | 1:0 | 胜(拉赫蒂) | 3+1 | 1 | 0+3 |  | 0.000 | 1 | 3 | 3 | 1.228 |  |  | 0 | 0 | probability_runner_up_protection;q_top_odds_up;raw_strength_missing |
| 28 | 挪甲 | 埃格尔松 | 莫斯 | 0.000 | 3:0 | 胜(埃格尔松) | 0 | 0 | 0 |  | 0.000 | 0 | 3 | 0 | 3.755 | away | 0 | 0 | 0 | q_high_but_probability_low;q_probability_disagree |
| 29 | 瑞典超 | 代格福什 | 马尔默 | 0.000 | 0:1 | 负(马尔默) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 3.873 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 30 | 瑞典超 | 哈尔姆斯塔德 | 韦斯特罗斯 | 0.000 | 1:3 | 负(韦斯特罗斯) | 1 | 0 | 0+1 |  | 0.000 | 1 | 0 | 1 | 1.447 |  |  | 3 | 3 | q_probability_disagree;raw_strength_missing |
| 31 | 芬甲 | EIF埃克奈斯 | PK-35 | 0.000 | 0:3 | 负(PK-35) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 2.668 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 芬超 | 查路 | 伊尔维斯 | 0.000 | 2:1 | 胜(查路) | 1+3 | 1 | 0+1 |  | 0.000 | 0 | 0 | 1 | 2.369 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 芬超 | 塞伊奈约基 | TPS图尔库 | -1.000 | 3:1 | 胜(塞伊奈约基) | 1+0 | 0 | 0+1 |  | 0.000 | 0 | 0 | 1 | 2.835 |  |  | 0 | 0 | q_probability_disagree;raw_strength_missing |
| 34 | 冰岛超 | IA阿克拉内斯 | 贝雷达比历克 | 0.000 | 1:2 | 负(贝雷达比历克) | 3 | 0 | 0+3 |  | 0.000 | 1 | 3 | 3 | 3.530 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 35 | 挪甲 | 赫德 | 斯托姆加斯特 | 1.000 | 4:3 | 胜(赫德) | 3 | 1 | 0+3+1 | 1 | 0.754 | 1 | 0 | 3 | 3.866 |  |  | 0 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 36 | 芬超 | 瓦萨 | 玛丽港 | -2.000 | 4:0 | 胜(瓦萨) | 0+1 | 0 | 0+1 |  | 0.000 | 0 | 0 | 1 | 4.372 |  |  | 3 |  | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 37 | 冰岛超 | IBV韦斯特曼纳 | 瓦路尔 | 0.000 | 1:0 | 胜(IBV韦斯特曼纳) | 1 | 0 | 3+1 |  | 0.000 | 1 | 3 | 1 | 5.145 | home | 3 | 0 | 0 | q_high_but_probability_low;q_probability_disagree |
| 38 | 挪甲 | 布莱尼 | 桑内斯乌尔夫 | 0.000 | 1:1 | 平 | 1 | 1 | 3+1 |  | 0.000 | 1 | 3 | 1 | 2.389 | home | 3 | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |
| 39 | 世界杯 | 加拿大 | 摩洛哥 | 1.000 | 0:3 | 负(摩洛哥) | 3 | 0 | 3+1 | 1 | 0.719 | 0 | 3 | 3 | 1.573 | away | 1 | 0 | 1 | q_top_odds_up;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 40 | 爱甲 | 朗福德城 | 都柏林大学 | 0.000 | 2:1 | 胜(朗福德城) | 3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 4.835 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 巴西乙 | 克里西乌马 | 累西腓体育 | 0.000 | 1:0 | 胜(克里西乌马) | 0+3 | 1 | 3 |  | 0.000 | 1 | 3 | 3 | 1.103 | away | 0 | 3 | 3 | line_gap_watch |
| 42 | 巴西乙 | 新奥里藏蒂诺 | 戈亚尼亚竞技 | 0.000 | 3:0 | 胜(新奥里藏蒂诺) | 0 | 0 | 3+0 |  | 0.000 | 1 | 3 | 0 | 15.470 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 巴西乙 | 隆德里纳 | 巴西雷加塔斯 | 0.000 | 5:0 | 胜(隆德里纳) | 3 | 1 | 0+3 |  | 0.000 | 1 | 3 | 3 | 14.079 |  |  | 0 | 0 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 44 | 世界杯 | 巴拉圭 | 法国 | 2.000 | 0:1 | 胜(巴拉圭) | 3 | 1 | 0+3 |  | 0.000 | 1 | 3 | 3 | 2.891 | away | 0 | 0 |  | probability_runner_up_protection |
| 45 | 巴西乙 | 戈亚斯 | 塞阿拉 | 0.000 | 2:0 | 胜(戈亚斯) | 0 | 0 | 3+0+1 | 1 | 0.681 | 1 | 3 | 0 | 1.564 | draw | 1 | 3 | 3 | q_high_but_probability_low;q_probability_disagree |
| 46 | K1联赛 | FC首尔 | 仁川联 | -1.000 | 1:0 | 平 | 0+3 | 0 | 0+3 |  | 0.000 | 0 | 0 | 3 | 1.647 | home | 1 | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 47 | K1联赛 | 金泉尚武 | 济州SK | 0.000 | 1:1 | 平 | 1 | 1 | 0+3+1 |  | 0.000 | 1 | 3 | 1 | 1.790 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 48 | K1联赛 | 光州FC | 蔚山HD | 1.000 | 1:1 | 胜(光州FC) | 0 | 0 | 0+3 | 1 | 0.751 | 1 | 0 | 0 | 1.233 |  |  | 0 | 1 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 49 | K2联赛 | 金海FC | 首尔衣恋 | 1.000 | 1:3 | 负(首尔衣恋) | 3 | 0 | 0+3 | 1 | 0.754 | 1 | 3 | 3 | 1.754 |  |  | 0 | 1 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 50 | K2联赛 | 金浦FC | 忠南牙山FC | -1.000 | 0:2 | 负(忠南牙山FC) | 1+3 | 0 | 0+1 | 1 | 0.684 | 1 | 0 | 1 | 2.527 | home | 1 | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 51 | K2联赛 | 庆南FC | 天安城 | 0.000 | 2:1 | 胜(庆南FC) | 0 | 0 | 0+3 |  | 0.000 | 1 | 3 | 0 | 23.094 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 52 | K2联赛 | 全南天龙 | 釜山IPark | 1.000 | 3:3 | 胜(全南天龙) | 3+1 | 1 | 3+1 | 1 | 0.765 | 1 | 3 | 1 | 2.328 |  |  | 0 | 1 | line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 53 | 瑞典超 | 哥德堡 | AIK索尔纳 | 0.000 | 1:2 | 负(AIK索尔纳) | 0 | 1 | 3+0 |  | 0.000 | 1 | 3 | 0 | 8.942 | home | 3 | 3 | 3 | q_high_but_probability_low;q_probability_disagree |
| 54 | 瑞典超 | 卡尔马 | 厄尔格里特 | -1.000 | 3:0 | 胜(卡尔马) | 0 | 0 | 3+0+1 | 1 | 0.770 | 1 | 3 | 0 | 2.412 |  |  | 3 | 1 | q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 55 | 挪甲 | 奥德 | 海于格松 | 0.000 | 1:3 | 负(海于格松) | 1 | 0 | 3+1 |  | 0.000 | 0 | 3 | 1 | 20.939 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | 瑞典超 | 埃尔夫斯堡 | 哈马比 | 0.000 | 1:2 | 负(哈马比) | 0+1 | 1 | 1+0 | 3 | 0.718 | 1 | 0 | 1 | 1.378 | draw | 1 | 3 | 3 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;recent_form_full_guard;recent_form_intel_protection |
| 57 | 芬甲 | MP米凯利 | 哈卡 | 1.000 | 2:1 | 胜(MP米凯利) | 3+1 | 1 | 0+1 | 1 | 0.744 | 0 | 3 | 1 | 15.927 | away | 1 | 0 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 58 | 世界杯 | 巴西 | 挪威 | -1.000 | 1:2 | 负(挪威) | 0+3 | 1 | 1+0+3 |  | 0.000 | 1 | 0 | 3 | 1.521 | home | 1 | 3 | 1 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 59 | 巴西乙 | 累西腓航海 | 尤文图德 | 0.000 | 0:0 | 平 | 1 | 1 | 3+1 | 1 | 0.754 | 1 | 3 | 1 | 2.930 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 60 | 世界杯 | 墨西哥 | 英格兰 | 0.000 | 2:3 | 负(英格兰) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 0 | 0 | 1.730 | home | 3 | 3 | 3 | probability_runner_up_protection |
| 61 | 瑞典超 | 赫根 | 佐加顿斯 | 0.000 | 2:4 | 负(佐加顿斯) | 3 | 0 | 3+0 |  | 0.000 | 1 | 0 | 3 | 9.898 | home | 3 | 3 | 3 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree |
| 62 | 瑞典超 | 布鲁马波卡纳 | 加尔斯 | 0.000 | 1:1 | 平 | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.960 |  |  | 0 | 0 | raw_strength_missing |
| 63 | 冰岛超 | 凯夫拉维克 | 弗拉姆 | 0.000 | 1:1 | 平 | 1 | 1 | 0+1 |  | 0.000 | 1 | 0 | 1 | 1.871 | home | 3 | 0 | 0 | q_high_but_probability_low;q_probability_disagree |
| 64 | 巴西乙 | 博塔弗戈SP | 阿瓦伊 | 0.000 | 3:1 | 胜(博塔弗戈SP) | 1 | 0 | 3+1 |  | 0.000 | 1 | 3 | 1 | 3.425 |  |  | 3 | 3 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 65 | 巴西乙 | 维拉诺瓦 | 圣贝尔纳多 | 0.000 | 2:1 | 胜(维拉诺瓦) | 1+0 | 0 | 3+1 |  | 0.000 | 1 | 3 | 1 | 4.074 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 66 | 世界杯 | 葡萄牙 | 西班牙 | 0.000 | 0:1 | 负(西班牙) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 1.141 |  |  | 0 | 0 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 67 | 世界杯 | 美国 | 比利时 | 0.000 | 1:4 | 负(比利时) | 0 | 1 | 0+3 |  | 0.000 | 1 | 0 | 0 | 1.357 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |

## 26072_016 专项

{
  "issue": "26072",
  "match_idx": 16,
  "match_id": "26072_016",
  "league": "爱超",
  "home": "谢尔伯恩",
  "away": "邓多克",
  "handicap_line": 0.0,
  "score": "2:1",
  "actual_code": "3",
  "actual_label": "胜(谢尔伯恩)",
  "winning_sp": 2.05,
  "active_version": "llm_chain_bet_protect_stop_v3",
  "active_recommendation": "胜(谢尔伯恩)为押，保平",
  "active_primary": "3",
  "active_selection_codes": "3+1",
  "active_primary_hit": 1,
  "active_coverage_hit": 1,
  "active_stake": 2,
  "active_profit_proxy": 0.05,
  "shadow_judgment": "胜(谢尔伯恩)为押，保平",
  "shadow_primary": "3",
  "shadow_selection_codes": "3+1",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": 1,
  "shadow_coverage_hit": 1,
  "shadow_stake": 2,
  "shadow_profit_proxy": 0.05,
  "shadow_arm": "shadow_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3_shadow",
  "selection_type": "double",
  "prob_top": "3",
  "q_top": "1",
  "p_3": 0.43481504635128987,
  "p_1": 0.26169376559176055,
  "p_0": 0.3034911880569495,
  "sp_3": 1.95,
  "sp_1": 4.51,
  "sp_0": 3.73,
  "q_3": 0.8478893403850152,
  "q_1": 1.18023888281884,
  "q_0": 1.1320221314524217,
  "max_q": 1.1802,
  "raw_strength_side": "home",
  "handicap_fit_code": "3",
  "form_recent_code": "3",
  "form_recent_confidence": 0.56,
  "form_recent_mapped_code": "3",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "line_gap_missing;q_probability_disagree",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(谢尔伯恩) 43.5%。\", \"EV/q主线：最高q 平 q=1.18，概率 26.2%，SP 4.51。\", \"让球映射：北单让球为0，原始强弱倾向可直接映射到让球后方向。；观点索引：昨6胜5 连胜3天 谢尔伯恩主场迎敌\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：平 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(谢尔伯恩)\", \"score\": \"43.5%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 43.5% / 平 26.2% / 负 30.3%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"平\", \"score\": \"q 1.18\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.85 / 平 1.18 / 负 1.13\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"胜(谢尔伯恩)\", \"score\": \"强度 0.79\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": [\"北单让球为0，原始强弱倾向可直接映射到让球后方向。\", \"观点索引：昨6胜5 连胜3天 谢尔伯恩主场迎敌\", \"观点索引：昨6胜5 连胜3天 谢尔伯恩主场迎敌\"]}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"胜(谢尔伯恩)\", \"score\": \"置信 0.56\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": [\"主队近10场 3胜6平1负，进失12/12，半场平6场，近5走势平-负-平-胜-平\", \"客队近10场 4胜2平4负，进失14/15，半场平3场，近5走势负-胜-胜-胜-负\"]}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"主队\", \"score\": \"置信 0.79\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": [\"观点索引：昨6胜5 连胜3天 谢尔伯恩主场迎敌\", \"观点索引：昨6胜5 连胜3天 谢尔伯恩主场迎敌\", \"昨赞赏告捷 谢尔伯恩能否主场取胜\"]}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"league_round\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": [\"赛制/阶段：爱超\"]}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"可用\", \"score\": \"2 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"analysis/intelligence/probability/sp inputs available\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(谢尔伯恩)为押，保平\", \"score\": \"置信 0.66\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(谢尔伯恩) 43.5%。\", \"EV/q主线：最高q 平 q=1.18，概率 26.2%，SP 4.51。\", \"让球映射：北单让球为0，原始强弱倾向可直接映射到让球后方向。；观点索引：昨6胜5 连胜3天 谢尔伯恩主场迎敌\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3_shadow` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26072_20260707_shadow_v3.3.3/structured_shadow_26072.csv`
