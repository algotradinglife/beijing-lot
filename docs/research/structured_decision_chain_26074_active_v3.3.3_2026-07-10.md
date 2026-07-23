# 结构化决策链 26074 active_v3.3.3 回测

生成时间：2026-07-10 15:27:43Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`65/65`；缺失场次 `[]`。
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
| active_v3 | 2 | 50.0% | 50.0% | 3 | 3.250 | 108.3% | {'single': 55, 'double': 10} |
| active_v3.3.3 | 2 | 0.0% | 50.0% | 3 | 3.250 | 108.3% | {'single': 16, 'double': 39, 'full': 10} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | K2联赛 | 天安城 | 金海FC | 0.000 | 0:1 | 负(金海FC) | 0+1 | 1 | 3+0 | 1 | 0.000 | 3 | 0 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 3 | 芬甲 | KTP科特卡 | 耶尔文佩 | -1.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 4 | 芬超 | 瓦萨 | 塞伊奈约基 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 6 | 爱超 | 邓多克 | 德罗赫达联 | -1.000 |  |  | 0+3 |  | 0 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 7 | 爱甲 | 布雷流浪者 | 都柏林大学 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 8 | 爱甲 | 科克城 | 朗福德城 | -2.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 9 | 爱甲 | 费恩哈普 | 条约联 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 10 | 爱甲 | 韦克斯福德 | 凯里 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 11 | 爱甲 | 阿斯隆城 | 科夫漫步者 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 12 | 世界杯 | 西班牙 | 比利时 | -1.000 |  |  | 1+0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 13 | 爱超 | 沃特福德FC | 圣帕特里克竞技 | 1.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 16 | K1联赛 | 蔚山HD | 全北现代 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 19 | K2联赛 | 安山绿人 | 水原三星蓝翼 | 1.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 20 | K2联赛 | 大邱FC | 城南FC | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 21 | K2联赛 | 华城FC | 坡州前沿 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 23 | 挪超 | 腓特烈斯塔 | 利勒斯特伦 | 0.000 |  |  | 1+0 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 24 | 芬超 | 拉赫蒂 | 赫尔辛基 | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 25 | 瑞典超 | 米亚尔比 | AIK索尔纳 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 26 | 芬甲 | 哈卡 | EIF埃克奈斯 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 27 | 芬甲 | 塞伊奈约基学院 | MP米凯利 | 0.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 28 | 挪超 | 奥勒松 | 莫尔德 | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 31 | 瑞典超 | 厄尔格里特 | 赫根 | 1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 挪超 | 特罗姆瑟 | 瓦勒伦加 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 爱超 | 戈尔韦联 | 斯莱戈流浪者 | -1.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 34 | 芬甲 | 赫尔辛基预备队 | 吉波 | 1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 35 | 世界杯 | 挪威 | 英格兰 | 1.000 |  |  | 3+0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 36 | 世界杯 | 阿根廷 | 瑞士 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 37 | K1联赛 | 济州SK | 大田韩亚市民 | 0.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 39 | K1联赛 | FC首尔 | 江原FC | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 41 | K2联赛 | 釜山IPark | 金浦FC | 0.000 |  |  | 3 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 42 | 瑞典超 | 哈马比 | 卡尔马 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 43 | 瑞典超 | 马尔默 | 哥德堡 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 45 | 挪超 | KFUM奥斯陆 | 博德闪耀 | 1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 46 | 巴西乙 | 铁路工人 | 新奥里藏蒂诺 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 48 | 瑞典超 | 布鲁马波卡纳 | 天狼星 | 1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 挪超 | 布兰 | 斯达 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 50 | 挪超 | 罗森博格 | 克里斯蒂安松 | -1.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 52 | 挪超 | 萨尔普斯堡 | 维京 | 1.000 |  |  | 3 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 54 | 冰岛超 | KA阿克雷里 | IA阿克拉内斯 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 55 | 冰岛超 | 弗拉姆 | 托尔 | -2.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | 冰岛超 | KR雷克雅未克 | IBV韦斯特曼纳 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 57 | 巴西乙 | 阿瓦伊 | 累西腓航海 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 58 | 阿根廷杯 | 里瓦达维亚独立 | 蒂格雷 | 0.000 |  |  | 1+0 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 59 | 冰岛超 | FH哈夫纳夫约杜尔 | 瓦路尔 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 60 | 巴西乙 | 戈亚尼亚竞技 | 福塔莱萨 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 61 | 巴西乙 | 巴西雷加塔斯 | 戈亚斯 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 62 | 瑞典超 | 佐加顿斯 | 哈尔姆斯塔德 | -2.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 冰岛超 | 贝雷达比历克 | 凯夫拉维克 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 26074 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | K2联赛 | 水原FC | 全南天龙 | -1.000 | 5:0 | 胜(水原FC) | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.644 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 2 | K2联赛 | 天安城 | 金海FC | 0.000 | 0:1 | 负(金海FC) | 0+1 | 1 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.677 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 3 | 芬甲 | KTP科特卡 | 耶尔文佩 | -1.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.549 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 4 | 芬超 | 瓦萨 | 塞伊奈约基 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.859 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 5 | 芬甲 | PK-35 | 卡帕 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.142 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 6 | 爱超 | 邓多克 | 德罗赫达联 | -1.000 |  |  | 0+3 |  | 0 |  | 0.000 |  | 0 | 0 | 1.132 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 7 | 爱甲 | 布雷流浪者 | 都柏林大学 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 2.087 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 8 | 爱甲 | 科克城 | 朗福德城 | -2.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.472 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 9 | 爱甲 | 费恩哈普 | 条约联 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 2.894 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 10 | 爱甲 | 韦克斯福德 | 凯里 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.228 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 11 | 爱甲 | 阿斯隆城 | 科夫漫步者 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.592 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 12 | 世界杯 | 西班牙 | 比利时 | -1.000 |  |  | 1+0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.431 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 13 | 爱超 | 沃特福德FC | 圣帕特里克竞技 | 1.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 3.089 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 14 | 巴西乙 | 尤文图德 | 维拉诺瓦 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.606 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 巴西乙 | 累西腓体育 | 博塔弗戈SP | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.932 |  |  |  |  | intelligence_missing;line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 16 | K1联赛 | 蔚山HD | 全北现代 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.129 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 17 | K1联赛 | 金泉尚武 | 富川1995 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 4.090 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 18 | K1联赛 | 光州FC | 浦项铁人 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 4.037 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 19 | K2联赛 | 安山绿人 | 水原三星蓝翼 | 1.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.406 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 20 | K2联赛 | 大邱FC | 城南FC | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.150 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 21 | K2联赛 | 华城FC | 坡州前沿 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.412 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 22 | K2联赛 | 龙仁FC | 忠北清州FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.486 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 23 | 挪超 | 腓特烈斯塔 | 利勒斯特伦 | 0.000 |  |  | 1+0 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.351 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 24 | 芬超 | 拉赫蒂 | 赫尔辛基 | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.272 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 25 | 瑞典超 | 米亚尔比 | AIK索尔纳 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.294 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 26 | 芬甲 | 哈卡 | EIF埃克奈斯 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 2.277 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 27 | 芬甲 | 塞伊奈约基学院 | MP米凯利 | 0.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.103 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 28 | 挪超 | 奥勒松 | 莫尔德 | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.108 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 29 | 芬超 | 格尼斯坦 | 玛丽港 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 15.325 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 30 | 芬超 | TPS图尔库 | AC奥卢 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 3.861 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 31 | 瑞典超 | 厄尔格里特 | 赫根 | 1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.740 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 挪超 | 特罗姆瑟 | 瓦勒伦加 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.621 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 爱超 | 戈尔韦联 | 斯莱戈流浪者 | -1.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 6.395 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 34 | 芬甲 | 赫尔辛基预备队 | 吉波 | 1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.500 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 35 | 世界杯 | 挪威 | 英格兰 | 1.000 |  |  | 3+0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 1.110 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 36 | 世界杯 | 阿根廷 | 瑞士 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 0 | 2.015 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 37 | K1联赛 | 济州SK | 大田韩亚市民 | 0.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.099 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 38 | K1联赛 | 仁川联 | FC安养 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.368 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 39 | K1联赛 | FC首尔 | 江原FC | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.267 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 40 | K2联赛 | 忠南牙山FC | 庆南FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.213 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 41 | K2联赛 | 釜山IPark | 金浦FC | 0.000 |  |  | 3 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.251 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 42 | 瑞典超 | 哈马比 | 卡尔马 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.018 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 43 | 瑞典超 | 马尔默 | 哥德堡 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.222 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 44 | 瑞典超 | 韦斯特罗斯 | 代格福什 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.403 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 45 | 挪超 | KFUM奥斯陆 | 博德闪耀 | 1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.252 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 46 | 巴西乙 | 铁路工人 | 新奥里藏蒂诺 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.377 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 47 | 瑞典超 | 加尔斯 | 埃尔夫斯堡 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.300 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 48 | 瑞典超 | 布鲁马波卡纳 | 天狼星 | 1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 5.634 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 挪超 | 布兰 | 斯达 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 3.629 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 50 | 挪超 | 罗森博格 | 克里斯蒂安松 | -1.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 4.937 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 51 | 挪超 | 桑讷菲尤尔 | 汉坎 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.399 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 52 | 挪超 | 萨尔普斯堡 | 维京 | 1.000 |  |  | 3 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 5.286 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 53 | 罗超杯 | CS克拉约瓦大学 | 克卢日大学 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.144 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 54 | 冰岛超 | KA阿克雷里 | IA阿克拉内斯 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.127 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 55 | 冰岛超 | 弗拉姆 | 托尔 | -2.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 3.929 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | 冰岛超 | KR雷克雅未克 | IBV韦斯特曼纳 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 7.529 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 57 | 巴西乙 | 阿瓦伊 | 累西腓航海 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.144 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 58 | 阿根廷杯 | 里瓦达维亚独立 | 蒂格雷 | 0.000 |  |  | 1+0 |  | 3+1 |  | 0.000 |  | 3 | 1 | 5.078 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 59 | 冰岛超 | FH哈夫纳夫约杜尔 | 瓦路尔 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.196 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 60 | 巴西乙 | 戈亚尼亚竞技 | 福塔莱萨 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.110 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 61 | 巴西乙 | 巴西雷加塔斯 | 戈亚斯 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.242 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 62 | 瑞典超 | 佐加顿斯 | 哈尔姆斯塔德 | -2.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 7.439 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 冰岛超 | 贝雷达比历克 | 凯夫拉维克 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 9.780 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 64 | 巴西乙 | 米内罗美洲 | 隆德里纳 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.317 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 65 | 巴西乙 | 塞阿拉 | 米纳斯吉拉斯竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.295 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |

## 26074_016 专项

{
  "issue": "26074",
  "match_idx": 16,
  "match_id": "26074_016",
  "league": "K1联赛",
  "home": "蔚山HD",
  "away": "全北现代",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "负(全北现代)",
  "active_primary": "0",
  "active_selection_codes": "0",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 1,
  "active_profit_proxy": "",
  "shadow_judgment": "负(全北现代)为押，保胜(蔚山HD)",
  "shadow_primary": "0",
  "shadow_selection_codes": "0+3",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": "",
  "shadow_coverage_hit": "",
  "shadow_stake": 2,
  "shadow_profit_proxy": "",
  "shadow_arm": "active_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3",
  "selection_type": "double",
  "prob_top": "0",
  "q_top": "0",
  "p_3": 0.3271598770678475,
  "p_1": 0.29397559203320517,
  "p_0": 0.3788645308989473,
  "sp_3": 2.66,
  "sp_1": 3.44,
  "sp_0": 2.98,
  "sp_complete": 1,
  "sp_missing_codes": "",
  "sp_source": "sqlite_matches_sp_fill",
  "q_3": 0.8702452730004744,
  "q_1": 1.0112760365942257,
  "q_0": 1.1290163020788628,
  "max_q": 1.129,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "",
  "form_recent_confidence": "",
  "form_recent_mapped_code": "",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "intelligence_missing;probability_runner_up_protection;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 负(全北现代) 37.9%。\", \"EV/q主线：最高q 负(全北现代) q=1.13，概率 37.9%，SP 2.98。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：胜(蔚山HD) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"负(全北现代)\", \"score\": \"37.9%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 32.7% / 平 29.4% / 负 37.9%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"负(全北现代)\", \"score\": \"q 1.13\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.87 / 平 1.01 / 负 1.13\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"无明确方向\", \"score\": \"置信 0.00\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": []}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"常规\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": []}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"有缺口\", \"score\": \"3 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"intelligence_missing\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"负(全北现代)为押，保胜(蔚山HD)\", \"score\": \"置信 0.43\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 负(全北现代) 37.9%。\", \"EV/q主线：最高q 负(全北现代) q=1.13，概率 37.9%，SP 2.98。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26074_20260710_active_v3.3.3/structured_shadow_26074.csv`
