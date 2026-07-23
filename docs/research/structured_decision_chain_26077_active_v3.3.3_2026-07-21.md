# 结构化决策链 26077 active_v3.3.3 回测

生成时间：2026-07-21 08:04:53Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`74/74`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 43, 'single': 26, 'full': 5} |
| active_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 51, 'single': 15, 'full': 8} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 29 | 巴西乙 | 铁路工人 | 庞特普雷塔 | -1.000 |  |  | 3+1 |  | 3+0 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 35 | 美职 | 费城联合 | 纽约红牛 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 37 | 美职 | 夏洛特FC | 亚特兰大联 | -1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 0 | 3 | line_gap_watch;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 39 | 南俱杯 | 拉努斯 | 西恩夏诺 | -1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 3 | 1 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 42 | 美职 | 休斯敦迪纳摩 | 华盛顿联 | -1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 0 | 3 | line_gap_watch;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 44 | 美职 | 纳什维尔SC | CF蒙特利尔 | -1.000 |  |  | 3 |  | 3+0 |  |  | 3 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 49 | 美职 | 洛杉矶FC | 皇家盐湖城 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 51 | 美职 | 圣何塞地震 | 奥兰多城 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 54 | 欧协资格 | 里加足球学校 | 维斯特里 | -3.000 |  |  | 3 |  | 3+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 56 | 欧罗巴资格 | 特罗姆瑟 | 赫拉德茨克拉洛韦 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 59 | 欧罗巴资格 | 特温特 | 费伦茨瓦罗斯 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 欧协资格 | 里耶卡 | 德里城 | -2.000 |  |  | 3 |  | 3+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 67 | 巴西甲 | 博塔弗戈 | 维多利亚 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 72 | 南俱杯 | 博卡青年 | 奥伊金斯 | -2.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 74 | 巴西乙 | 博塔弗戈SP | 尤文图德 | 0.000 |  |  | 0 |  | 0+3 |  |  | 3 | 3 | probability_runner_up_protection;raw_strength_missing |

## 26077 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | K1联赛 | 济州SK | 江原FC | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.639 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 2 | K1联赛 | 蔚山HD | 仁川联 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.273 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 3 | K1联赛 | 全北现代 | 大田韩亚市民 | -1.000 |  |  | 0+1 |  | 0+1 | 1 | 0.708 |  | 0 | 0 | 1.783 | home | 1 | 3 | 1 | line_gap_watch;raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 4 | 欧冠资格 | 米亚尔比 | 林肯红色小鬼 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.117 |  |  | 0 | 0 | q_top_odds_up;raw_strength_missing |
| 5 | 芬甲 | 卡帕 | 赫尔辛基预备队 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.211 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 6 | 欧冠资格 | 奥胡斯 | 波兹南莱赫 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.750 |  | 3 | 1 | 1.375 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 7 | 瑞典甲 | 法尔肯贝里 | 赫尔辛堡 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.605 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 8 | 欧冠资格 | 费内巴切 | 扎布热矿工 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.457 |  |  | 3 |  | q_top_odds_up;raw_strength_missing |
| 9 | 欧冠资格 | 格拉茨风暴 | 哈茨 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.379 |  |  | 3 | 1 | q_top_odds_up;raw_strength_missing |
| 10 | 苏联赛杯 | 因弗内斯 | 圣约翰斯通 | 1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.752 |  | 3 | 3 | 1.589 |  |  | 0 | 1 | line_gap_watch;raw_strength_missing;recent_form_intel_protection |
| 11 | 欧冠资格 | 拉恩 | 贝尔格莱德红星 | 2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.828 |  |  | 0 |  | raw_strength_missing |
| 13 | 南俱杯 | 蒙得维的亚国民 | 蒂格雷 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.992 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 14 | 巴西甲 | 米内罗竞技 | 巴伊亚 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.175 |  |  | 3 | 3 | q_probability_disagree;raw_strength_missing |
| 15 | 巴西乙 | 新奥里藏蒂诺 | 克里西乌马 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.754 |  | 3 | 1 | 1.409 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 16 | 巴西乙 | 阿瓦伊 | 米内罗美洲 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.709 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 南俱杯 | 委内瑞拉中央大学 | 桑托斯 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.712 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 18 | 巴西乙 | 维拉诺瓦 | 福塔莱萨 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.255 | home | 3 | 3 | 3 | probability_runner_up_protection;q_probability_disagree |
| 19 | 墨超 | 蓝十字 | 普埃布拉 | -2.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 0 | 3 | 1.154 |  |  | 3 |  | line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 20 | 墨超 | 托卢卡 | 普马斯 | -1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.782 |  |  | 0 | 0 | q_top_odds_up;raw_strength_missing |
| 21 | K1联赛 | 富川1995 | FC安养 | 0.000 |  |  | 0+3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.085 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 22 | K1联赛 | 光州FC | 金泉尚武 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.250 |  |  | 0 | 0 | line_gap_watch;raw_strength_missing |
| 23 | K1联赛 | FC首尔 | 浦项铁人 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.128 |  |  | 3 | 3 | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 24 | 欧冠资格 | 奥莫尼亚 | 阿拉木图凯拉特 | -1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 6.519 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 25 | 挪超 | 博德闪耀 | 汉坎 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 17.164 |  |  | 3 |  | line_gap_watch;q_top_odds_up;raw_strength_missing |
| 26 | 挪超 | 利勒斯特伦 | 维京 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 15.438 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 27 | 欧协资格 | 巴沙克谢希尔 | 国际图尔库 | -2.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 4.770 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 28 | 南俱杯 | 麦德林独立 | 瓦斯科达伽马 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 4.699 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 29 | 巴西乙 | 铁路工人 | 庞特普雷塔 | -1.000 |  |  | 3+1 |  | 3+0 | 1 | 0.757 |  | 0 | 0 | 2.727 |  |  | 3 | 1 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 30 | 巴西乙 | 塞阿拉 | 巴西雷加塔斯 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.754 |  | 3 | 1 | 1.671 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 31 | 美职 | FC辛辛那提 | 温哥华白浪 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 15.971 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 美职 | 哥伦布机员 | 纽约城 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 27.730 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 美职 | 国际迈阿密 | 芝加哥火焰 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.617 |  |  | 3 | 3 | line_gap_watch;q_top_odds_up;raw_strength_missing |
| 34 | 美职 | 新英格兰革命 | 多伦多FC | -1.000 |  |  | 0+1 |  | 0+1 | 1 | 0.772 |  | 0 | 1 | 8.754 |  |  | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 35 | 美职 | 费城联合 | 纽约红牛 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 26.607 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 36 | 巴西乙 | 戈亚斯 | 累西腓体育 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.264 |  |  | 3 | 3 | raw_strength_missing |
| 37 | 美职 | 夏洛特FC | 亚特兰大联 | -1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.684 |  | 0 | 3 | 8.456 |  |  | 3 | 1 | line_gap_watch;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 38 | 南俱杯 | 水晶体育 | 布拉干蒂诺红牛 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.360 |  |  | 0 | 0 | raw_strength_missing |
| 39 | 南俱杯 | 拉努斯 | 西恩夏诺 | -1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.635 |  | 3 | 1 | 16.477 |  |  | 0 | 0 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 巴西甲 | 沙佩科恩斯 | 弗拉门戈 | 1.000 |  |  | 0+3+1 |  | 0+3+1 | 1 | 0.763 |  | 0 | 3 | 6.802 |  |  | 0 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 41 | 巴西甲 | 圣保罗 | 巴拉纳竞技 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.714 |  | 3 | 1 | 7.110 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 42 | 美职 | 休斯敦迪纳摩 | 华盛顿联 | -1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.691 |  | 0 | 3 | 19.098 |  |  | 3 | 1 | line_gap_watch;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 43 | 美职 | 堪萨斯城体育 | 明尼苏达联 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 18.754 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 44 | 美职 | 纳什维尔SC | CF蒙特利尔 | -1.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.068 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 45 | 巴西乙 | 累西腓航海 | 隆德里纳 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.761 |  | 3 | 3 | 1.552 |  |  | 0 | 0 | line_gap_large;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 46 | 美职 | 奥斯汀FC | 西雅图海湾人 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.429 |  |  | 0 | 0 | line_gap_watch;raw_strength_missing |
| 47 | 美职 | 科罗拉多急流 | 圣迭戈FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.506 |  |  | 3 | 3 | line_gap_watch;raw_strength_missing |
| 48 | 美职 | 洛杉矶银河 | 圣路易斯城 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.673 |  | 3 | 3 | 1.265 |  |  | 0 | 0 | line_gap_watch;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 49 | 美职 | 洛杉矶FC | 皇家盐湖城 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 21.708 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 50 | 美职 | 波特兰伐木者 | FC达拉斯 | 0.000 |  |  | 0+3+1 |  | 0+3+1 |  | 0.000 |  | 3 | 1 | 7.520 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 51 | 美职 | 圣何塞地震 | 奥兰多城 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 12.809 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 52 | 欧罗巴资格 | 卡拉巴赫 | 索非亚中央陆军 | -1.000 |  |  | 0+3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.685 |  |  | 3 | 1 | line_gap_missing;q_probability_disagree;raw_strength_missing |
| 53 | 欧协资格 | 塔林弗洛拉 | 新圣徒 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 7.689 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 54 | 欧协资格 | 里加足球学校 | 维斯特里 | -3.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 0 | 1 | 33.457 |  |  | 3 |  | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 55 | 欧罗巴资格 | 哈马比 | 安德莱赫特 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 16.089 |  |  | 3 | 3 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | 欧罗巴资格 | 特罗姆瑟 | 赫拉德茨克拉洛韦 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 11.025 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 57 | 欧协资格 | 加尔斯 | 北西兰 | 0.000 |  |  | 0+1 |  | 0+1 | 1 | 0.754 |  | 0 | 0 | 1.355 |  |  | 3 | 3 | line_gap_missing;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 58 | 欧协资格 | 克卢日大学 | 布兰 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.282 |  |  | 0 | 0 | line_gap_missing;raw_strength_missing |
| 59 | 欧罗巴资格 | 特温特 | 费伦茨瓦罗斯 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 16.013 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 60 | 欧罗巴资格 | 贝西克塔斯 | 中日德兰 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.779 |  | 3 | 1 | 3.878 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 61 | 欧罗巴资格 | 圣加仑 | 本菲卡 | 1.000 |  |  | 0+3+1 |  | 0+3+1 | 1 | 0.696 |  | 0 | 1 | 79.684 |  |  | 0 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing;recent_form_intel_protection |
| 62 | 欧协资格 | 巴尼亚卢卡战士 | 佩特罗库布 | -1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.685 |  | 3 | 1 | 26.288 |  |  | 3 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing;recent_form_intel_protection |
| 63 | 欧协资格 | 里耶卡 | 德里城 | -2.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 0 | 1 | 51.805 |  |  | 3 |  | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 64 | 欧协资格 | 斯塔尔南 | 伊尔维斯 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.713 |  | 3 | 1 | 15.093 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 65 | 欧协资格 | 瓦路尔 | 莫斯塔尔泽林斯基 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.763 |  | 3 | 3 | 1.422 |  |  | 0 | 0 | line_gap_missing;q_top_odds_up;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 66 | 南俱杯 | 玻利瓦尔 | 格雷米奥 | -1.000 |  |  | 0+1 |  | 0+1 | 1 | 0.633 |  | 0 | 1 | 2302.961 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 67 | 巴西甲 | 博塔弗戈 | 维多利亚 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 22.873 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 68 | 巴西甲 | 科林蒂安 | 雷莫 | -1.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.988 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 69 | 阿职联 | 贝尔格拉诺 | 罗萨里奥中央 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 4.951 |  |  | 3 | 3 | raw_strength_missing |
| 70 | 阿职联 | 萨米恩托 | 阿根廷青年人 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.328 |  |  | 0 | 0 | line_gap_watch;raw_strength_missing |
| 71 | 巴西乙 | 米纳斯吉拉斯竞技 | 圣贝尔纳多 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.215 |  |  | 3 | 3 | line_gap_watch;raw_strength_missing |
| 72 | 南俱杯 | 博卡青年 | 奥伊金斯 | -2.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 35.079 |  |  | 3 |  | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 73 | 南俱杯 | 圣菲独立 | 加拉加斯 | -1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.707 |  | 3 | 1 | 36.466 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 74 | 巴西乙 | 博塔弗戈SP | 尤文图德 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 3 | 3 | 1.110 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 75 | 阿职联 | 防卫与正义 | 阿尔多希维 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 3.260 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 26077_016 专项

{
  "issue": "26077",
  "match_idx": 16,
  "match_id": "26077_016",
  "league": "巴西乙",
  "home": "阿瓦伊",
  "away": "米内罗美洲",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "胜(阿瓦伊)为押，保平",
  "active_primary": "3",
  "active_selection_codes": "3+1",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 2,
  "active_profit_proxy": "",
  "shadow_judgment": "胜(阿瓦伊)为押，保平",
  "shadow_primary": "3",
  "shadow_selection_codes": "3+1",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": "",
  "shadow_coverage_hit": "",
  "shadow_stake": 2,
  "shadow_profit_proxy": "",
  "phase2_primary_experiment_id": "phase2_probability_first_within_coverage",
  "phase2_primary_experiment_version": "v0.1.0000",
  "phase2_probability_primary": "3",
  "phase2_probability_selection_codes": "3+1",
  "phase2_probability_changed": 0,
  "phase2_probability_grade": "A",
  "phase2_probability_primary_probability": 0.444972,
  "phase2_probability_primary_margin": 0.147183,
  "phase2_probability_primary_hit": "",
  "phase2_probability_execution_enabled": 0,
  "phase2_handicap_gated_experiment_id": "phase2_handicap_gated_probability_first",
  "phase2_handicap_gated_experiment_version": "v0.2.0000",
  "phase2_handicap_gated_primary": "3",
  "phase2_handicap_gated_selection_codes": "3+1",
  "phase2_handicap_gated_changed": 0,
  "phase2_handicap_gated_grade": "A",
  "phase2_handicap_gated_primary_probability": 0.444972,
  "phase2_handicap_gated_primary_margin": 0.147183,
  "phase2_handicap_gated_gate_applied": 1,
  "phase2_handicap_gated_primary_hit": "",
  "phase2_handicap_gated_execution_enabled": 0,
  "phase2_league_soft_experiment_id": "phase2_seasonal_league_soft_tiebreak",
  "phase2_league_soft_experiment_version": "v0.1.0000",
  "phase2_league_soft_primary": "3",
  "phase2_league_soft_selection_codes": "3+1",
  "phase2_league_soft_changed": 0,
  "phase2_league_soft_grade": "A",
  "phase2_league_soft_primary_probability": 0.45202,
  "phase2_league_soft_primary_margin": 0.147183,
  "phase2_league_soft_gate_applied": 0,
  "phase2_league_soft_effective_n": 27,
  "phase2_league_soft_adjustment_json": "{\"3\": 0.007048, \"1\": 0.01, \"0\": -0.01}",
  "phase2_league_soft_primary_hit": "",
  "phase2_league_soft_execution_enabled": 0,
  "phase3_protection_experiment_id": "phase3_drop_switched_ev_home_protection",
  "phase3_protection_experiment_version": "v0.1.0000",
  "phase3_protection_baseline_codes": "3+1",
  "phase3_protection_candidate_codes": "3+1",
  "phase3_protection_triggered": 0,
  "phase3_protection_removed_code": "",
  "phase3_protection_reason": "not_triggered",
  "phase3_protection_execution_enabled": 0,
  "shadow_arm": "active_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3",
  "selection_type": "double",
  "prob_top": "3",
  "q_top": "1",
  "p_3": 0.4449721473749263,
  "p_1": 0.29778952618751087,
  "p_0": 0.25723832643756284,
  "sp_3": 1.61,
  "sp_1": 5.74,
  "sp_0": 4.81,
  "sp_complete": 1,
  "sp_missing_codes": "",
  "sp_source": "500_preclose_sp_complete",
  "q_3": 0.7164051572736314,
  "q_1": 1.7093118803163125,
  "q_0": 1.2373163501646771,
  "max_q": 1.7093,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "3",
  "form_recent_confidence": 0.455,
  "form_recent_mapped_code": "3",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "q_high_but_probability_low;q_probability_disagree;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(阿瓦伊) 44.5%。\", \"EV/q主线：最高q 平 q=1.71，概率 29.8%，SP 5.74。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：平 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(阿瓦伊)\", \"score\": \"44.5%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 44.5% / 平 29.8% / 负 25.7%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"平\", \"score\": \"q 1.71\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.72 / 平 1.71 / 负 1.24\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"胜(阿瓦伊)\", \"score\": \"置信 0.46\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": [\"主队近10场 3胜1平6负，进失12/15，半场平2场，近5走势平-胜-负-负-胜\", \"客队近10场 1胜3平6负，进失8/13，半场平4场，近5走势平-平-负-负-负\"]}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"league_round\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": [\"赛制/阶段：巴乙\"]}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"可用\", \"score\": \"3 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"analysis/intelligence/probability/sp inputs available\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(阿瓦伊)为押，保平\", \"score\": \"置信 0.47\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(阿瓦伊) 44.5%。\", \"EV/q主线：最高q 平 q=1.71，概率 29.8%，SP 5.74。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26077_20260721_active_v3.3.3/structured_shadow_26077.csv`
