# 结构化决策链 26085 active_v3.3.3 回测

生成时间：2026-08-14 14:39:04Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`339/339`；缺失场次 `[]`。
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
| active_v3 | 1 | 100.0% | 100.0% | 1 | 0.980 | 98.0% | {'single': 237, 'double': 102} |
| active_v3.3.3 | 1 | 100.0% | 100.0% | 1 | 0.980 | 98.0% | {'single': 139, 'double': 154, 'full': 46} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 芬超 | 瓦萨 | TPS图尔库 | -1.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 5 | 意大利杯 | 卡利亚里 | 阿雷佐 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 6 | 德乙 | 基尔 | 圣保利 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 7 | 德乙 | 不伦瑞克 | 波鸿 | 0.000 |  |  | 1+0 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 8 | 奥乙 | 韦尔斯赫塔 | 维也纳快速二队 | 0.000 |  |  | 1+0 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 9 | 挪超 | 罗森博格 | 维京 | 0.000 |  |  | 1+0 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 12 | 葡甲 | 科英布拉大学 | CD费伦斯 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 13 | 丹甲 | 奥尔堡 | 腓特烈西亚 | 0.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 14 | 丹甲 | 科灵 | 瓦埃勒 | 0.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 瑞典甲 | 兰斯克鲁纳 | 奥迪沃德 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 奥甲 | LASK林茨 | 里德 | -1.000 |  |  | 0+1 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 18 | 欧罗巴资格 | 克拉克斯维克 | 波兹南莱赫 | 1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 19 | 荷甲 | 特尔斯达 | 鹿特丹斯巴达 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 20 | 荷乙 | 罗达JC | 海尔蒙德体育 | -1.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 23 | 荷乙 | 赫拉克勒斯 | 邓伯什 | -1.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 24 | 荷乙 | FC埃因霍温 | 马斯特里赫特 | 0.000 |  |  | 1+0 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 25 | 荷乙 | 阿尔梅勒城 | PSV埃因霍温青年 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 26 | 比乙 | 哈塞尔特 | 登德尔 | 0.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 27 | 比乙 | 瑟兰 | 洛克伦 | 0.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 29 | 罗甲 | 阿尔杰什 | 康斯坦察法鲁尔 | 0.000 |  |  | 3+0 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 30 | 波兰甲 | 华沙莱吉亚 | 拉多米亚克 | -1.000 |  |  | 1+0 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 31 | 奥乙 | 圣珀尔滕 | 蓝白林茨 | 0.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 意大利杯 | 蒙扎 | 阿韦利诺 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 34 | 法乙 | 第戎 | 波城 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 35 | 法乙 | 格勒诺布尔 | 梅斯 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 36 | 法乙 | 甘冈 | 布洛涅 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 38 | 法乙 | 南锡 | 蒙彼利埃 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 39 | 法乙 | 圣旺红星 | 索肖 | 0.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 法乙 | 兰斯 | 敦刻尔克 | -1.000 |  |  | 0+3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 法乙 | 圣埃蒂安 | 克莱蒙 | -1.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 42 | 比甲 | 色格拉布鲁日 | 圣特赖登 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 43 | 爱足总杯 | 戈尔韦联 | 布雷流浪者 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 44 | 爱足总杯 | 都柏林大学 | 德里城 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 45 | 爱足总杯 | 沃特福德FC | 阿斯隆城 | -1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 46 | 苏联赛杯 | 基尔马诺克 | 艾尔联 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 47 | 英冠 | 狼队 | 布莱克本 | -1.000 |  |  | 1+0 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 葡超 | 葡萄牙体育 | 吉马良斯 | -2.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;probability_runner_up_protection;raw_strength_missing |
| 51 | 巴西乙 | 圣贝尔纳多 | 博塔弗戈SP | 0.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 52 | 智利甲 | 康塞普西翁大学 | 拉塞雷纳 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 53 | 阿职联 | 竞技俱乐部 | 班菲尔德 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 54 | 巴西乙 | 累西腓体育 | 隆德里纳 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 55 | J1联赛 | 鹿岛鹿角 | 名古屋鲸 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | J1联赛 | 水户蜀葵 | 大阪钢巴 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 57 | J2联赛 | 秋田蓝色闪电 | 富山胜利 | 0.000 |  |  | 1+3 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 59 | J1联赛 | 清水心跳 | 横滨水手 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 60 | J2联赛 | 藤枝MYFC | 磐城 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 64 | J1联赛 | 川崎前锋 | 京都不死鸟 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 65 | J1联赛 | 神户胜利船 | FC东京 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 66 | J1联赛 | 福冈黄蜂 | 大阪樱花 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 67 | J2联赛 | 仙台七夕 | 大分三神 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 69 | J2联赛 | 甲府风林 | 宫崎特格瓦嘉洛 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 70 | J2联赛 | 新泻天鹅 | 北海道札幌冈萨多 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 74 | K1联赛 | FC首尔 | 大田韩亚市民 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 75 | K2联赛 | 忠北清州FC | 全南天龙 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 77 | K2联赛 | 水原三星蓝翼 | 水原FC | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 79 | 德乙 | 柏林赫塔 | 海登海姆 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 81 | 德乙 | 奥斯纳布吕克 | 马格德堡 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 82 | 丹甲 | 希勒勒 | 奥胡斯前进 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 89 | 英乙 | 奥德汉姆 | 维尔港 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 92 | 瑞典超 | 米亚尔比 | 天狼星 | 0.000 |  |  | 0+3 |  | 0 |  |  | 0 | 0 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 96 | 芬甲 | 吉波 | 塞伊奈约基学院 | -1.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 98 | 英冠 | 查尔顿 | 德比郡 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 99 | 英冠 | 米德尔斯堡 | 林肯城 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 102 | 英冠 | 斯托克城 | 斯旺西 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 104 | 英甲 | 布莱克浦 | 威科姆流浪者 | 0.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 105 | 英甲 | 布拉德福德城 | 彼得堡联 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 106 | 英甲 | 伯顿 | 斯蒂夫尼奇 | 0.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 108 | 英甲 | 哈德斯菲尔德 | AFC温布尔登 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 111 | 英乙 | 阿克灵顿 | 科尔切斯特联 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 112 | 英乙 | 巴尼特 | 索尔福德城 | 0.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 115 | 英乙 | 克劳利 | 克鲁 | 0.000 |  |  | 0+1 |  | 0 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 122 | 挪甲 | 布莱尼 | 莫斯 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 124 | 挪甲 | 兰黑姆 | 斯托姆加斯特 | 1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 128 | 荷甲 | 威廉二世 | 奈梅亨 | 1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 129 | 葡甲 | 葡萄牙体育B队 | 沙维什 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 130 | 荷乙 | 福伦丹 | 奥斯 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 131 | 西乙 | FC安道尔 | 休达 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 133 | 捷克甲 | 布拉格斯巴达 | 特普利采 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 138 | 芬甲 | PK-35 | 赫尔辛基预备队 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 142 | 奥乙 | 格拉茨风暴二队 | 阿德米拉 | 1.000 |  |  | 0+1 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 144 | 芬超 | 玛丽港 | 塞伊奈约基 | 1.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 146 | 意大利杯 | 乌迪内斯 | 帕多瓦 | -1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 150 | 奥乙 | 福伊茨贝格 | 黑白布雷根茨 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 151 | 荷甲 | 乌德勒支 | 阿尔克马尔 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 152 | 苏联赛杯 | 邓迪联 | 凯尔特人 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 154 | 西乙 | 皇家奥维耶多 | 格拉纳达 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 157 | 葡甲 | 托里什恩斯 | 佩纳菲耶尔 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 158 | 芬甲 | KTP科特卡 | 卡帕 | -2.000 |  |  | 1+3 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 160 | 奥甲 | 格拉茨风暴 | 阿尔特阿赫 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 161 | 阿职联 | 圣洛伦索 | 圣菲联合 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 163 | 荷甲 | 鹿特丹精英 | PSV埃因霍温 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 164 | 捷克甲 | 比尔森胜利 | 兹林 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 166 | 德乙 | 凯泽斯劳滕 | 卡尔斯鲁厄 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 168 | 意大利杯 | 威尼斯 | 摩德纳 | -1.000 |  |  | 3 |  | 3+0+1 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 170 | 比甲 | 亨克 | 韦斯特洛 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 171 | 爱足总杯 | 斯莱戈流浪者 | 凯里 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 172 | 荷甲 | 锡塔德福图纳 | 坎布尔 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 177 | 西乙 | 马略卡 | 巴利亚多利德 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 179 | 巴西甲 | 弗鲁米嫩塞 | 帕尔梅拉斯 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 181 | 巴西甲 | 巴拉纳竞技 | 布拉干蒂诺红牛 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 186 | 墨超 | 亚特兰特 | 托卢卡 | 1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 192 | 巴西甲 | 圣保罗 | 科里蒂巴 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 195 | 美职 | 休斯敦迪纳摩 | 洛杉矶银河 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 196 | 美职 | 纳什维尔SC | 国际迈阿密 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 197 | 墨超 | 蒙特雷 | 华雷斯 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 198 | 美职 | 科罗拉多急流 | 堪萨斯城体育 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 199 | 美职 | 皇家盐湖城 | 明尼苏达联 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 200 | 美职 | 洛杉矶FC | 圣迭戈FC | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 205 | J2联赛 | 德岛漩涡 | 鸟栖砂岩 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 207 | 荷甲 | 海牙 | 格罗宁根 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 209 | K1联赛 | 富川1995 | 全北现代 | 1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 210 | K1联赛 | 蔚山HD | 江原FC | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 211 | K2联赛 | 首尔衣恋 | 安山绿人 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 213 | K2联赛 | 金浦FC | 天安城 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 215 | 瑞典甲 | 韦纳穆 | 厄斯特松德 | 0.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 216 | 德乙 | 汉诺威96 | 沃尔夫斯堡 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 217 | 德乙 | 德累斯顿 | 达姆施塔特 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 218 | 德乙 | 比勒费尔德 | 科特布斯 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 219 | 丹超 | 欧登塞 | 霍森斯 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 220 | 丹超 | 北西兰 | 锡尔克堡 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 221 | 瑞典超 | 佐加顿斯 | AIK索尔纳 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 224 | 丹甲 | 文德斯尔 | AB格莱萨克瑟 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 226 | 荷甲 | 特温特 | 兹沃勒 | -2.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 227 | 荷甲 | 费耶诺德 | 前进之鹰 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 229 | 波兰甲 | 卢布林莫托 | 卡托维兹 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 230 | 捷克甲 | 俄斯特拉发 | 布尔诺阿特斯 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 231 | 芬超 | 赫尔辛基 | 查路 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 232 | 爱足总杯 | 圣帕特里克竞技 | 沙姆洛克流浪者 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 234 | 苏联赛杯 | 哈茨 | 因弗内斯 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 235 | 苏联赛杯 | 希伯尼安 | 帕尔蒂克蓟花 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 236 | 苏联赛杯 | 斯坦豪斯摩尔 | 马瑟韦尔 | 2.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 237 | 社区盾 | 阿森纳 | 曼彻斯特城 | 0.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 239 | 丹超 | 灵比 | 中日德兰 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 241 | 芬超 | 拉赫蒂 | 库普斯 | 0.000 |  |  | 1+0 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 242 | 比乙 | 比尔肖特 | 根特预备队 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 243 | 芬甲 | MP米凯利 | EIF埃克奈斯 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 245 | 巴西乙 | 铁路工人 | 阿瓦伊 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 249 | 葡甲 | 雷克索斯 | 通德拉 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 250 | 荷甲 | 阿贾克斯 | 海伦芬 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 251 | 西甲 | 桑坦德竞技 | 比利亚雷亚尔 | 0.000 |  |  | 0+1 |  | 0 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 253 | 西乙 | 埃瓦尔 | 特内里费 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 255 | 奥甲 | WSG蒂罗尔 | 萨尔茨堡红牛 | 1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 256 | 挪超 | 布兰 | 汉坎 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 258 | 挪超 | 萨尔普斯堡 | 桑讷菲尤尔 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 260 | 挪甲 | 赫德 | 斯托曼 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 262 | 挪甲 | 赖于福斯 | 奥桑内 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 264 | 苏联赛杯 | 格拉斯哥流浪者 | 圣米伦 | -2.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 266 | 波兰甲 | 克拉科维亚 | 琴斯托霍瓦 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 267 | 意大利杯 | 弗罗西诺内 | 尤维斯塔比亚 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 268 | 丹超 | 兰讷斯 | 哥本哈根 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 270 | 智利甲 | 纽布莱恩斯 | 拉卡莱拉联合 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 273 | 西乙 | 赫罗纳 | 莱加内斯 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 275 | 奥甲 | 维也纳快速 | 格拉茨AK | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 279 | 捷克甲 | 利贝雷茨 | 布拉格斯拉维亚 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 280 | 冰岛超 | KR雷克雅未克 | 贝雷达比历克 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 281 | 冰岛超 | FH哈夫纳夫约杜尔 | 维京古尔 | 1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 282 | 冰岛超 | IBV韦斯特曼纳 | IA阿克拉内斯 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 283 | 爱足总杯 | 波希米亚人 | 朗福德城 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 284 | 阿职联 | 萨米恩托 | 飓风 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 287 | 罗甲 | 胡内多阿拉乌鸦 | 克卢日 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 288 | 法超杯 | 朗斯 | 巴黎圣日耳曼 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 289 | 意大利杯 | 维罗纳 | 恩特拉 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 292 | 智利甲 | 科布雷萨尔 | 康塞普西翁 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 293 | 意大利杯 | 拉齐奥 | 曼托瓦 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 294 | 西乙 | 拉斯帕尔马斯 | 阿尔瓦塞特 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 295 | 葡超 | 布拉加 | 吉尔维森特 | -1.000 |  |  | 3 |  | 0+1+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 296 | 葡超 | 法马利康 | 马里迪莫 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 300 | 智利甲 | 科洛科洛 | 奥伊金斯 | -1.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 301 | 巴西乙 | 巴西雷加塔斯 | 新奥里藏蒂诺 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 303 | 美职 | 芝加哥火焰 | 波特兰伐木者 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 305 | 墨超 | 墨西哥美洲 | 圣路易斯竞技 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 307 | 阿职联 | 巴拉卡斯中央 | 罗萨里奥中央 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 309 | 墨超 | 桑托斯拉古纳 | 瓜达拉哈拉 | 1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 315 | 意大利杯 | 萨索洛 | 切塞纳 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 317 | 丹超 | 布隆德比 | 桑德捷斯基 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 318 | 瑞典超 | 赫根 | 哈尔姆斯塔德 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 320 | 阿职联 | 里奥夸尔托大学生 | 图库曼竞技 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 323 | 荷乙 | 格拉夫夏普 | 阿尔克马尔青年队 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 325 | 罗甲 | 布加勒斯特星 | 博托沙尼 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 329 | 意大利杯 | 巴勒莫 | 莱切 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 330 | 葡超 | 卡萨皮亚 | 本菲卡 | 2.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 332 | 西乙 | 阿尔梅里亚 | 埃尔登斯 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 335 | 巴西甲 | 巴西国际 | 雷莫 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 336 | 阿职联 | 门多萨体操 | 塔勒瑞斯 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 337 | 智利甲 | 巴勒斯坦人 | 瓦奇巴托 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 339 | 墨超 | 帕丘卡 | 普埃布拉 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |

## 26085 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | J1联赛 | 东京绿茵 | 柏太阳神 | 0.000 | 1:3 | 负(柏太阳神) | 0 | 1 | 0 |  | 0.000 | 1 | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 2 | 芬超 | 瓦萨 | TPS图尔库 | -1.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.060 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 3 | 罗甲 | 沃伦塔里 | 佩特罗鲁 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.104 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 4 | 芬甲 | 耶尔文佩 | 哈卡 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.051 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 5 | 意大利杯 | 卡利亚里 | 阿雷佐 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.541 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 6 | 德乙 | 基尔 | 圣保利 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.202 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 7 | 德乙 | 不伦瑞克 | 波鸿 | 0.000 |  |  | 1+0 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.145 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 8 | 奥乙 | 韦尔斯赫塔 | 维也纳快速二队 | 0.000 |  |  | 1+0 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.170 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 9 | 挪超 | 罗森博格 | 维京 | 0.000 |  |  | 1+0 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.037 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 10 | 丹超 | 维堡 | 奥胡斯 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.330 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 11 | 瑞典超 | 埃尔夫斯堡 | 韦斯特罗斯 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.319 |  |  |  |  | intelligence_missing;line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 葡甲 | 科英布拉大学 | CD费伦斯 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.046 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 13 | 丹甲 | 奥尔堡 | 腓特烈西亚 | 0.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.617 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 14 | 丹甲 | 科灵 | 瓦埃勒 | 0.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.220 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 瑞典甲 | 兰斯克鲁纳 | 奥迪沃德 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.220 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 16 | 瑞典甲 | 布莱格 | 厄勒布鲁 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.433 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 奥甲 | LASK林茨 | 里德 | -1.000 |  |  | 0+1 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 1.179 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 18 | 欧罗巴资格 | 克拉克斯维克 | 波兹南莱赫 | 1.000 |  |  | 0+1 |  | 0+3+1 |  | 0.000 |  | 0 | 0 | 1.281 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 19 | 荷甲 | 特尔斯达 | 鹿特丹斯巴达 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.116 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 20 | 荷乙 | 罗达JC | 海尔蒙德体育 | -1.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.353 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 21 | 荷乙 | 瓦尔韦克 | 多德雷赫特 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.042 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 22 | 荷乙 | 布雷达 | 芬洛 | -1.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.043 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 23 | 荷乙 | 赫拉克勒斯 | 邓伯什 | -1.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.191 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 24 | 荷乙 | FC埃因霍温 | 马斯特里赫特 | 0.000 |  |  | 1+0 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.194 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 25 | 荷乙 | 阿尔梅勒城 | PSV埃因霍温青年 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.545 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 26 | 比乙 | 哈塞尔特 | 登德尔 | 0.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.650 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 27 | 比乙 | 瑟兰 | 洛克伦 | 0.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.137 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 28 | 西乙 | 皇家社会B队 | 卡斯特利翁 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.178 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 29 | 罗甲 | 阿尔杰什 | 康斯坦察法鲁尔 | 0.000 |  |  | 3+0 |  | 3 |  | 0.000 |  | 3 | 3 | 1.095 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 30 | 波兰甲 | 华沙莱吉亚 | 拉多米亚克 | -1.000 |  |  | 1+0 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.325 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 31 | 奥乙 | 圣珀尔滕 | 蓝白林茨 | 0.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.325 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 意大利杯 | 蒙扎 | 阿韦利诺 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.056 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 33 | 法乙 | 阿讷西 | 罗德兹 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.480 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 34 | 法乙 | 第戎 | 波城 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.125 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 35 | 法乙 | 格勒诺布尔 | 梅斯 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.414 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 36 | 法乙 | 甘冈 | 布洛涅 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.187 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 37 | 法乙 | 拉瓦勒 | 南特 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.258 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 38 | 法乙 | 南锡 | 蒙彼利埃 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.135 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 39 | 法乙 | 圣旺红星 | 索肖 | 0.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.638 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 法乙 | 兰斯 | 敦刻尔克 | -1.000 |  |  | 0+3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.303 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 法乙 | 圣埃蒂安 | 克莱蒙 | -1.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.119 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 42 | 比甲 | 色格拉布鲁日 | 圣特赖登 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.166 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 43 | 爱足总杯 | 戈尔韦联 | 布雷流浪者 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.670 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 44 | 爱足总杯 | 都柏林大学 | 德里城 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.278 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 45 | 爱足总杯 | 沃特福德FC | 阿斯隆城 | -1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.282 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 46 | 苏联赛杯 | 基尔马诺克 | 艾尔联 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.317 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 47 | 英冠 | 狼队 | 布莱克本 | -1.000 |  |  | 1+0 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.267 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 48 | 意大利杯 | 佛罗伦萨 | 贝内文托 | -2.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.191 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 49 | 葡超 | 葡萄牙体育 | 吉马良斯 | -2.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.245 |  |  |  |  | intelligence_missing;line_gap_watch;probability_runner_up_protection;raw_strength_missing |
| 50 | 巴西乙 | 庞特普雷塔 | 累西腓航海 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.080 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 51 | 巴西乙 | 圣贝尔纳多 | 博塔弗戈SP | 0.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.111 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 52 | 智利甲 | 康塞普西翁大学 | 拉塞雷纳 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.035 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 53 | 阿职联 | 竞技俱乐部 | 班菲尔德 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.140 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 54 | 巴西乙 | 累西腓体育 | 隆德里纳 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.172 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 55 | J1联赛 | 鹿岛鹿角 | 名古屋鲸 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 5.226 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 56 | J1联赛 | 水户蜀葵 | 大阪钢巴 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.444 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 57 | J2联赛 | 秋田蓝色闪电 | 富山胜利 | 0.000 |  |  | 1+3 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.302 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 58 | J2联赛 | 枥木城 | 八户云罗里 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.450 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 59 | J1联赛 | 清水心跳 | 横滨水手 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.278 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 60 | J2联赛 | 藤枝MYFC | 磐城 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.083 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 61 | J1联赛 | 冈山绿雉 | 长崎成功丸 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.354 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 62 | J1联赛 | 浦和红钻 | 广岛三箭 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.226 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | J1联赛 | 千叶市原 | 町田泽维亚 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.451 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 64 | J1联赛 | 川崎前锋 | 京都不死鸟 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.300 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 65 | J1联赛 | 神户胜利船 | FC东京 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.395 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 66 | J1联赛 | 福冈黄蜂 | 大阪樱花 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.348 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 67 | J2联赛 | 仙台七夕 | 大分三神 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 8.242 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 68 | J2联赛 | 湘南海洋 | 山形山神 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.241 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 69 | J2联赛 | 甲府风林 | 宫崎特格瓦嘉洛 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.262 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 70 | J2联赛 | 新泻天鹅 | 北海道札幌冈萨多 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.383 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 71 | J2联赛 | FC今治 | RB大宫松鼠 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.182 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 72 | K1联赛 | 光州FC | 浦项铁人 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.593 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 73 | K1联赛 | 济州SK | FC安养 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.381 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 74 | K1联赛 | FC首尔 | 大田韩亚市民 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.368 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 75 | K2联赛 | 忠北清州FC | 全南天龙 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.121 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 76 | K2联赛 | 金海FC | 庆南FC | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.497 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 77 | K2联赛 | 水原三星蓝翼 | 水原FC | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.482 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 78 | K2联赛 | 釜山IPark | 华城FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.650 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 79 | 德乙 | 柏林赫塔 | 海登海姆 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.456 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 80 | 德乙 | 菲尔特 | 纽伦堡 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.148 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 81 | 德乙 | 奥斯纳布吕克 | 马格德堡 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.117 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 82 | 丹甲 | 希勒勒 | 奥胡斯前进 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.095 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 83 | 瑞典甲 | 永斯基 | 厄斯特什 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.437 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 84 | 英冠 | 博尔顿 | 普雷斯顿 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.518 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 85 | 英甲 | 诺茨郡 | 莱斯特城 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.505 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 86 | 英甲 | 牛津联 | 米尔顿凯恩斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.658 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 87 | 英甲 | 雷丁 | 卢顿 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.091 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 88 | 英乙 | 纽波特郡 | 罗奇代尔 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.257 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 89 | 英乙 | 奥德汉姆 | 维尔港 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.097 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 90 | 丹甲 | 埃斯比约 | 霍布罗 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.259 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 91 | 波兰甲 | 卢宾扎格勒比 | 史拉斯科 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.345 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 92 | 瑞典超 | 米亚尔比 | 天狼星 | 0.000 |  |  | 0+3 |  | 0 |  | 0.000 |  | 0 | 0 | 1.025 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 93 | 葡甲 | 莱里亚 | 本菲卡B队 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.487 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 94 | 瑞典甲 | 松兹瓦尔 | 赫尔辛堡 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.165 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 95 | 瑞典甲 | 诺迪克联 | 瓦尔贝里 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.325 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 96 | 芬甲 | 吉波 | 塞伊奈约基学院 | -1.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.330 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 97 | 英冠 | 布里斯托尔城 | 米尔沃尔 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.153 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 98 | 英冠 | 查尔顿 | 德比郡 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.112 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 99 | 英冠 | 米德尔斯堡 | 林肯城 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 6.383 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 100 | 英冠 | 诺维奇 | 西布朗维奇 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.168 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 101 | 英冠 | 朴茨茅斯 | 女王公园巡游者 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.302 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 102 | 英冠 | 斯托克城 | 斯旺西 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.060 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 103 | 英甲 | 巴恩斯利 | 布罗姆利 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.252 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 104 | 英甲 | 布莱克浦 | 威科姆流浪者 | 0.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.075 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 105 | 英甲 | 布拉德福德城 | 彼得堡联 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 33.828 |  |  |  |  | intelligence_missing;line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 106 | 英甲 | 伯顿 | 斯蒂夫尼奇 | 0.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.649 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 107 | 英甲 | 剑桥联 | 维冈竞技 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.110 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 108 | 英甲 | 哈德斯菲尔德 | AFC温布尔登 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 51.557 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 109 | 英甲 | 曼斯菲尔德 | 唐卡斯特 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.323 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 110 | 英甲 | 普利茅斯 | 斯托克波特郡 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.319 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 111 | 英乙 | 阿克灵顿 | 科尔切斯特联 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.112 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 112 | 英乙 | 巴尼特 | 索尔福德城 | 0.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.319 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 113 | 英乙 | 切尔滕汉姆 | 罗瑟汉姆联 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.188 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 114 | 英乙 | 切斯特菲尔德 | 弗利特伍德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.669 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 115 | 英乙 | 克劳利 | 克鲁 | 0.000 |  |  | 0+1 |  | 0 |  | 0.000 |  | 0 | 0 | 1.684 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 116 | 英乙 | 吉林汉姆 | 沃尔索尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.313 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 117 | 英乙 | 格里姆斯比 | 埃克塞特城 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.555 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 118 | 英乙 | 北安普顿 | 斯文登 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.368 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 119 | 英乙 | 特兰米尔流浪者 | 什鲁斯伯里 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.372 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 120 | 英乙 | 约克城 | 布里斯托尔流浪者 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.349 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 121 | 挪超 | KFUM奥斯陆 | 利勒斯特伦 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.163 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 122 | 挪甲 | 布莱尼 | 莫斯 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 95.564 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 123 | 挪甲 | 利恩 | 奥德 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.329 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 124 | 挪甲 | 兰黑姆 | 斯托姆加斯特 | 1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 49.647 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 125 | 丹甲 | HB克厄 | 哈维德夫 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.246 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 126 | 苏联赛杯 | 阿伯丁 | 邓迪FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.309 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 127 | 葡超 | 阿维卡 | 阿马多拉之星 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.221 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 128 | 荷甲 | 威廉二世 | 奈梅亨 | 1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 19.375 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 129 | 葡甲 | 葡萄牙体育B队 | 沙维什 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.066 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 130 | 荷乙 | 福伦丹 | 奥斯 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 19.668 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 131 | 西乙 | FC安道尔 | 休达 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 56.411 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 132 | 奥甲 | 奥地利卢斯特瑙 | 沃尔夫斯贝格 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.241 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 133 | 捷克甲 | 布拉格斯巴达 | 特普利采 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 19.796 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 134 | 捷克甲 | 帕尔杜比采 | 姆拉达博莱斯拉夫 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.322 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 135 | 捷克甲 | 斯洛瓦茨科 | 奥洛穆茨 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.419 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 136 | 瑞典甲 | 桑德维肯 | 北雪平 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 17.914 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 137 | 瑞典甲 | 法尔肯贝里 | 诺尔比 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.225 |  |  |  |  | intelligence_missing;line_gap_large;raw_strength_missing |
| 138 | 芬甲 | PK-35 | 赫尔辛基预备队 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 7.762 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 139 | 罗甲 | 奇克塞雷达 | 塞普西 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.080 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 140 | 波兰甲 | 格利维采皮亚斯特 | 克拉科夫维切斯塔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.538 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 141 | 奥乙 | FAC维也纳 | 阿姆施泰滕 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.087 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 142 | 奥乙 | 格拉茨风暴二队 | 阿德米拉 | 1.000 |  |  | 0+1 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 97.710 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 143 | 意大利杯 | 卡坦扎罗 | 南蒂罗尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.254 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 144 | 芬超 | 玛丽港 | 塞伊奈约基 | 1.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.359 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 145 | 比甲 | 科特赖克 | 安特卫普 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.160 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 146 | 意大利杯 | 乌迪内斯 | 帕多瓦 | -1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 1.184 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 147 | 英冠 | 谢菲尔德联 | 伯明翰 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.427 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 148 | 奥乙 | 奥地利维也纳二队 | 奥地利萨尔茨堡 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.114 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 149 | 奥乙 | 卡普芬贝格 | 因斯布鲁克 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.422 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 150 | 奥乙 | 福伊茨贝格 | 黑白布雷根茨 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 24.107 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 151 | 荷甲 | 乌德勒支 | 阿尔克马尔 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.439 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 152 | 苏联赛杯 | 邓迪联 | 凯尔特人 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 28.614 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 153 | 西乙 | 加的斯 | 维戈塞尔塔B队 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.224 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 154 | 西乙 | 皇家奥维耶多 | 格拉纳达 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 82.259 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 155 | 葡超 | 维塞乌学院 | 圣塔克拉拉 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.108 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 156 | 冰岛超 | 托尔 | 凯夫拉维克 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.530 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 157 | 葡甲 | 托里什恩斯 | 佩纳菲耶尔 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 198.501 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 158 | 芬甲 | KTP科特卡 | 卡帕 | -2.000 |  |  | 1+3 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 15.808 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 159 | 西甲 | 阿拉维斯 | 赫塔费 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.560 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 160 | 奥甲 | 格拉茨风暴 | 阿尔特阿赫 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 17.105 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 161 | 阿职联 | 圣洛伦索 | 圣菲联合 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.214 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 162 | 阿职联 | 阿尔多希维 | 蒂格雷 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.133 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 163 | 荷甲 | 鹿特丹精英 | PSV埃因霍温 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 8.255 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 164 | 捷克甲 | 比尔森胜利 | 兹林 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 45.359 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 165 | 波兰甲 | 罗兹维德祖 | 凯尔采科罗纳 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.247 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 166 | 德乙 | 凯泽斯劳滕 | 卡尔斯鲁厄 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.382 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 167 | 罗甲 | 布加勒斯特快速 | 布加勒斯特迪纳摩 | 0.000 |  |  | 1+3 |  | 1+3 |  | 0.000 |  | 1 | 1 | 1.339 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 168 | 意大利杯 | 威尼斯 | 摩德纳 | -1.000 |  |  | 3 |  | 3+0+1 |  | 0.000 |  | 3 | 3 | 1.731 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 169 | 比甲 | 奥德赫维里鲁汶 | 布鲁日 | 1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.609 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 170 | 比甲 | 亨克 | 韦斯特洛 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 49.232 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 171 | 爱足总杯 | 斯莱戈流浪者 | 凯里 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 183.937 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 172 | 荷甲 | 锡塔德福图纳 | 坎布尔 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 30.323 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 173 | 巴西乙 | 戈亚尼亚竞技 | 维拉诺瓦 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.290 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 174 | 巴西乙 | 克里西乌马 | 戈亚斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.563 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 175 | 意大利杯 | 都灵 | 卡拉拉 | -1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.935 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 176 | 西甲 | 塞维利亚 | 巴列卡诺 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.398 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 177 | 西乙 | 马略卡 | 巴利亚多利德 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 79.001 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 178 | 葡超 | 里奥阿维 | 波尔图 | 1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.522 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 179 | 巴西甲 | 弗鲁米嫩塞 | 帕尔梅拉斯 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.235 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 180 | 阿职联 | 拉普拉塔大学生 | 拉普拉塔体操 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.459 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 181 | 巴西甲 | 巴拉纳竞技 | 布拉干蒂诺红牛 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.205 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 182 | 智利甲 | 利马切 | 智利大学 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.715 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 183 | 巴西乙 | 尤文图德 | 福塔莱萨 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.277 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 184 | 阿职联 | 纽维尔老男孩 | 列斯特拉体育 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.350 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 185 | 阿职联 | 贝尔格拉诺 | 里瓦达维亚独立 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.241 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 186 | 墨超 | 亚特兰特 | 托卢卡 | 1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 80.871 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 187 | 美职 | 亚特兰大联 | 纽约红牛 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.246 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 188 | 美职 | 夏洛特FC | 哥伦布机员 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.418 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 189 | 美职 | CF蒙特利尔 | 华盛顿联 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.353 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 190 | 美职 | 奥兰多城 | FC辛辛那提 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.395 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 191 | 美职 | 多伦多FC | 新英格兰革命 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.094 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 192 | 巴西甲 | 圣保罗 | 科里蒂巴 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 31.872 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 193 | 智利甲 | 比尼亚德马埃弗顿 | 奥达克斯意大利人 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.200 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 194 | 阿职联 | 普拉腾斯 | 博卡青年 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.287 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 195 | 美职 | 休斯敦迪纳摩 | 洛杉矶银河 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 11.670 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 196 | 美职 | 纳什维尔SC | 国际迈阿密 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.089 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 197 | 墨超 | 蒙特雷 | 华雷斯 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 30.640 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 198 | 美职 | 科罗拉多急流 | 堪萨斯城体育 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 141.995 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 199 | 美职 | 皇家盐湖城 | 明尼苏达联 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 37.212 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 200 | 美职 | 洛杉矶FC | 圣迭戈FC | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 45.496 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 201 | 美职 | 圣何塞地震 | 圣路易斯城 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.084 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 202 | 墨超 | 阿特拉斯 | 老虎大学 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.497 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 203 | 奥乙 | 第一维也纳 | 列夫林 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.452 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 204 | J2联赛 | 横滨FC | 磐田喜悦 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.381 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 205 | J2联赛 | 德岛漩涡 | 鸟栖砂岩 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.181 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 206 | 葡甲 | 波尔蒂芒斯 | 维泽拉 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.280 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 207 | 荷甲 | 海牙 | 格罗宁根 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 3.858 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 208 | K1联赛 | 仁川联 | 金泉尚武 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.409 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 209 | K1联赛 | 富川1995 | 全北现代 | 1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 58.608 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 210 | K1联赛 | 蔚山HD | 江原FC | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.125 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 211 | K2联赛 | 首尔衣恋 | 安山绿人 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 118.772 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 212 | K2联赛 | 大邱FC | 忠南牙山FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.926 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 213 | K2联赛 | 金浦FC | 天安城 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 257.228 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 214 | K2联赛 | 坡州前沿 | 城南FC | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.538 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 215 | 瑞典甲 | 韦纳穆 | 厄斯特松德 | 0.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.179 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 216 | 德乙 | 汉诺威96 | 沃尔夫斯堡 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.183 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 217 | 德乙 | 德累斯顿 | 达姆施塔特 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.191 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 218 | 德乙 | 比勒费尔德 | 科特布斯 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 861.496 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 219 | 丹超 | 欧登塞 | 霍森斯 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 187.384 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 220 | 丹超 | 北西兰 | 锡尔克堡 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 23.178 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 221 | 瑞典超 | 佐加顿斯 | AIK索尔纳 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 34.946 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 222 | 瑞典超 | 布鲁马波卡纳 | 厄尔格里特 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.007 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 223 | 瑞典超 | 代格福什 | 哥德堡 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.998 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 224 | 丹甲 | 文德斯尔 | AB格莱萨克瑟 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.125 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 225 | 英冠 | 沃特福德 | 南安普顿 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.418 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 226 | 荷甲 | 特温特 | 兹沃勒 | -2.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 71.075 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 227 | 荷甲 | 费耶诺德 | 前进之鹰 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 42.430 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 228 | 挪超 | 奥勒松 | 瓦勒伦加 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.885 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 229 | 波兰甲 | 卢布林莫托 | 卡托维兹 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.118 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 230 | 捷克甲 | 俄斯特拉发 | 布尔诺阿特斯 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 303.178 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 231 | 芬超 | 赫尔辛基 | 查路 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 44.774 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 232 | 爱足总杯 | 圣帕特里克竞技 | 沙姆洛克流浪者 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.106 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 233 | 葡甲 | 阿马兰蒂 | 洛罗萨卢西塔尼亚 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.059 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 234 | 苏联赛杯 | 哈茨 | 因弗内斯 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 81.395 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 235 | 苏联赛杯 | 希伯尼安 | 帕尔蒂克蓟花 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 522.548 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 236 | 苏联赛杯 | 斯坦豪斯摩尔 | 马瑟韦尔 | 2.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 76.567 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 237 | 社区盾 | 阿森纳 | 曼彻斯特城 | 0.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.136 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 238 | 比甲 | 拉路维尔 | 根特 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.502 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 239 | 丹超 | 灵比 | 中日德兰 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 31.156 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 240 | 芬超 | AC奥卢 | 国际图尔库 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.610 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 241 | 芬超 | 拉赫蒂 | 库普斯 | 0.000 |  |  | 1+0 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.119 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 242 | 比乙 | 比尔肖特 | 根特预备队 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 241.706 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 243 | 芬甲 | MP米凯利 | EIF埃克奈斯 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.084 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 244 | 巴西甲 | 沙佩科恩斯 | 巴伊亚 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.491 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 245 | 巴西乙 | 铁路工人 | 阿瓦伊 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 88.659 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 246 | 葡超 | 葡萄牙国民 | 埃斯托里尔 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.055 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 247 | 瑞典超 | 加尔斯 | 马尔默 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.286 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 248 | 瑞典超 | 卡尔马 | 哈马比 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.642 |  |  |  |  | intelligence_missing;line_gap_large;raw_strength_missing |
| 249 | 葡甲 | 雷克索斯 | 通德拉 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.104 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 250 | 荷甲 | 阿贾克斯 | 海伦芬 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 32.742 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 251 | 西甲 | 桑坦德竞技 | 比利亚雷亚尔 | 0.000 |  |  | 0+1 |  | 0 |  | 0.000 |  | 0 | 0 | 1.260 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 252 | 英冠 | 伯恩利 | 西汉姆联 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.825 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 253 | 西乙 | 埃瓦尔 | 特内里费 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.277 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 254 | 奥甲 | 哈特贝格 | 奥地利维也纳 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.524 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 255 | 奥甲 | WSG蒂罗尔 | 萨尔茨堡红牛 | 1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 53.235 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 256 | 挪超 | 布兰 | 汉坎 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 18.899 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 257 | 挪超 | 莫尔德 | 特罗姆瑟 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.526 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 258 | 挪超 | 萨尔普斯堡 | 桑讷菲尤尔 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 64.243 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 259 | 挪甲 | 埃格尔松 | 斯塔贝克 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.306 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 260 | 挪甲 | 赫德 | 斯托曼 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.184 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 261 | 挪甲 | 孔斯温厄尔 | 海于格松 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.263 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 262 | 挪甲 | 赖于福斯 | 奥桑内 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.263 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 263 | 挪甲 | 松达尔 | 桑内斯乌尔夫 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.297 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 264 | 苏联赛杯 | 格拉斯哥流浪者 | 圣米伦 | -2.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 83.226 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 265 | 罗甲 | 加拉茨钢铁 | CS克拉约瓦大学 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.441 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 266 | 波兰甲 | 克拉科维亚 | 琴斯托霍瓦 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.118 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 267 | 意大利杯 | 弗罗西诺内 | 尤维斯塔比亚 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 34.565 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 268 | 丹超 | 兰讷斯 | 哥本哈根 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 50.181 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 269 | 意大利杯 | 热那亚 | 阿斯科利 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  |  |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 270 | 智利甲 | 纽布莱恩斯 | 拉卡莱拉联合 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 296.498 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 271 | 西甲 | 西班牙人 | 莱万特 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.393 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 272 | 西乙 | 布尔戈斯 | 科尔多瓦 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.241 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 273 | 西乙 | 赫罗纳 | 莱加内斯 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 105.852 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 274 | 葡超 | 阿罗卡 | 摩雷伦斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.444 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 275 | 奥甲 | 维也纳快速 | 格拉茨AK | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 66.982 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 276 | 葡甲 | 波尔图B队 | SC法伦斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.280 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 277 | 比甲 | 洛默尔 | 沙勒罗瓦 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.489 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 278 | 挪超 | 腓特烈斯塔 | 克里斯蒂安松 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.526 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 279 | 捷克甲 | 利贝雷茨 | 布拉格斯拉维亚 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 24.288 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 280 | 冰岛超 | KR雷克雅未克 | 贝雷达比历克 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 88.175 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 281 | 冰岛超 | FH哈夫纳夫约杜尔 | 维京古尔 | 1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 57.264 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 282 | 冰岛超 | IBV韦斯特曼纳 | IA阿克拉内斯 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.124 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 283 | 爱足总杯 | 波希米亚人 | 朗福德城 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 28.263 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 284 | 阿职联 | 萨米恩托 | 飓风 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.250 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 285 | 墨超 | 普马斯 | 克雷塔罗 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.821 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 286 | 波兰甲 | 扎布热矿工 | 克拉科夫维斯瓦 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.551 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 287 | 罗甲 | 胡内多阿拉乌鸦 | 克卢日 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.136 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 288 | 法超杯 | 朗斯 | 巴黎圣日耳曼 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 19.856 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 289 | 意大利杯 | 维罗纳 | 恩特拉 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 290 | 巴西甲 | 瓦斯科达伽马 | 桑托斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.683 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 291 | 巴西甲 | 米内罗竞技 | 格雷米奥 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.811 |  |  |  |  | intelligence_missing;line_gap_large;raw_strength_missing |
| 292 | 智利甲 | 科布雷萨尔 | 康塞普西翁 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.139 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 293 | 意大利杯 | 拉齐奥 | 曼托瓦 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 31.844 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 294 | 西乙 | 拉斯帕尔马斯 | 阿尔瓦塞特 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 385.097 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 295 | 葡超 | 布拉加 | 吉尔维森特 | -1.000 |  |  | 3 |  | 0+1+3 |  | 0.000 |  | 0 | 3 | 29.491 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 296 | 葡超 | 法马利康 | 马里迪莫 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 137.297 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 297 | 阿职联 | 河床 | 阿根廷青年人 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.327 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 298 | 巴西甲 | 维多利亚 | 博塔弗戈 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.186 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 299 | 巴西甲 | 米拉索尔 | 弗拉门戈 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 68.922 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 300 | 智利甲 | 科洛科洛 | 奥伊金斯 | -1.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.650 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 301 | 巴西乙 | 巴西雷加塔斯 | 新奥里藏蒂诺 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.321 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 302 | 巴西乙 | 米内罗美洲 | 米纳斯吉拉斯竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.331 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 303 | 美职 | 芝加哥火焰 | 波特兰伐木者 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 59.306 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 304 | 美职 | 纽约城 | 费城联合 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.752 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 305 | 墨超 | 墨西哥美洲 | 圣路易斯竞技 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 26.642 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 306 | 阿职联 | 科尔多瓦中央 | 科尔多瓦学院 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.365 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 307 | 阿职联 | 巴拉卡斯中央 | 罗萨里奥中央 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.140 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 308 | 美职 | 奥斯汀FC | FC达拉斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.365 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 309 | 墨超 | 桑托斯拉古纳 | 瓜达拉哈拉 | 1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 0 | 142.459 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 310 | 美职 | 西雅图海湾人 | 温哥华白浪 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.324 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 311 | 墨超 | 蒂华纳 | 蓝十字 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.543 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 312 | 芬超 | 格尼斯坦 | 伊尔维斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.343 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 313 | 罗甲 | 克卢日大学 | UTA阿拉德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.864 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 314 | 意大利杯 | 比萨 | 恩波利 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.618 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 315 | 意大利杯 | 萨索洛 | 切塞纳 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 25.473 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 316 | 西乙 | 希洪体育 | 萨瓦德尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.481 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 317 | 丹超 | 布隆德比 | 桑德捷斯基 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 26.119 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 318 | 瑞典超 | 赫根 | 哈尔姆斯塔德 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 345.133 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 319 | 葡甲 | 费尔盖拉斯 | A F S | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.059 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 320 | 阿职联 | 里奥夸尔托大学生 | 图库曼竞技 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.125 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 321 | 冰岛超 | 瓦路尔 | KA阿克雷里 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.744 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 322 | 荷乙 | 阿贾克斯青年队 | 埃门 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.423 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 323 | 荷乙 | 格拉夫夏普 | 阿尔克马尔青年队 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 197.738 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 324 | 比乙 | RFC列日 | 布瑞恩斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.463 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 325 | 罗甲 | 布加勒斯特星 | 博托沙尼 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 26.151 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 326 | 意大利杯 | 克雷莫纳 | 桑普多利亚 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.431 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 327 | 西甲 | 拉科鲁尼亚 | 埃尔切 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.996 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 328 | 英冠 | 卡迪夫城 | 雷克瑟姆 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.221 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 329 | 意大利杯 | 巴勒莫 | 莱切 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.140 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 330 | 葡超 | 卡萨皮亚 | 本菲卡 | 2.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 58.685 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 331 | 冰岛超 | 弗拉姆 | 斯塔尔南 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.450 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 332 | 西乙 | 阿尔梅里亚 | 埃尔登斯 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 195.490 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 333 | 阿职联 | 拉努斯 | 阿根廷独立 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.636 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 334 | 阿职联 | 萨斯菲尔德 | 防卫与正义 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.348 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 335 | 巴西甲 | 巴西国际 | 雷莫 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 140.694 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 336 | 阿职联 | 门多萨体操 | 塔勒瑞斯 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.197 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 337 | 智利甲 | 巴勒斯坦人 | 瓦奇巴托 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 100.605 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 338 | 墨超 | 内卡萨 | 莱昂 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.227 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 339 | 墨超 | 帕丘卡 | 普埃布拉 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 14.535 |  |  |  |  | intelligence_missing;raw_strength_missing |

## 26085_016 专项

{
  "issue": "26085",
  "match_idx": 16,
  "match_id": "26085_016",
  "league": "瑞典甲",
  "home": "布莱格",
  "away": "厄勒布鲁",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "胜(布莱格)为押，保负(厄勒布鲁)",
  "active_primary": "3",
  "active_selection_codes": "3+0",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 2,
  "active_profit_proxy": "",
  "shadow_judgment": "胜(布莱格)为押，保负(厄勒布鲁)",
  "shadow_primary": "3",
  "shadow_selection_codes": "3+0",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": "",
  "shadow_coverage_hit": "",
  "shadow_stake": 2,
  "shadow_profit_proxy": "",
  "shadow_arm": "active_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3",
  "selection_type": "double",
  "prob_top": "3",
  "q_top": "0",
  "p_3": 0.4666639781599993,
  "p_1": 0.25986992823589744,
  "p_0": 0.27346609360410323,
  "sp_3": 1.7,
  "sp_1": 4.47,
  "sp_0": 5.24,
  "q_3": 0.7933287628719988,
  "q_1": 1.1616185792144615,
  "q_0": 1.432962330485501,
  "max_q": 1.433,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "",
  "form_recent_confidence": "",
  "form_recent_mapped_code": "",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(布莱格) 46.7%。\", \"EV/q主线：最高q 负(厄勒布鲁) q=1.43，概率 27.4%，SP 5.24。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：负(厄勒布鲁) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(布莱格)\", \"score\": \"46.7%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 46.7% / 平 26.0% / 负 27.3%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"负(厄勒布鲁)\", \"score\": \"q 1.43\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.79 / 平 1.16 / 负 1.43\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"无明确方向\", \"score\": \"置信 0.00\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": []}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"常规\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": []}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"有缺口\", \"score\": \"5 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"intelligence_missing\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(布莱格)为押，保负(厄勒布鲁)\", \"score\": \"置信 0.41\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(布莱格) 46.7%。\", \"EV/q主线：最高q 负(厄勒布鲁) q=1.43，概率 27.4%，SP 5.24。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26085_20260814_active_v3.3.3/structured_shadow_26085.csv`
