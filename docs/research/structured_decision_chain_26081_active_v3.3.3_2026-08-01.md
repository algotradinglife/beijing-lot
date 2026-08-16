# 结构化决策链 26081 active_v3.3.3 回测

生成时间：2026-08-01 12:29:57Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`202/202`；缺失场次 `[]`。
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
| active_v3 | 39 | 33.3% | 43.6% | 56 | 0.300 | 0.5% | {'single': 114, 'double': 88} |
| active_v3.3.3 | 39 | 46.2% | 64.1% | 71 | -1.670 | -2.4% | {'single': 61, 'double': 112, 'full': 29} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3 | 芬甲 | EIF埃克奈斯 | 赫尔辛基预备队 | 0.000 | 2:0 | 胜(EIF埃克奈斯) | 1+0 | 0 | 3+1 | 1 | 2.100 | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 4 | 波兰甲 | 普沃茨克维斯瓦 | 罗兹维德祖 | 0.000 | 0:0 | 平 | 3 | 0 | 0+3 | 0 | -1.000 | 0 | 3 | intelligence_missing;line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 5 | 丹甲 | 奥胡斯前进 | 奥尔堡 | 0.000 | 1:2 | 负(奥尔堡) | 1+0 | 1 | 3+1 | 0 | -3.990 | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 6 | 芬甲 | PK-35 | 哈卡 | 0.000 | 1:4 | 负(哈卡) | 0+1 | 1 | 0+3 | 1 | 0.000 | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 7 | 奥乙 | 阿德米拉 | 维也纳快速二队 | 0.000 | 0:1 | 负(维也纳快速二队) | 3+1 | 0 | 3 | 0 | 1.000 | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 8 | 奥乙 | 奥地利维也纳二队 | 蓝白林茨 | 0.000 | 0:3 | 负(蓝白林茨) | 1 | 0 | 0+1 | 1 | 0.800 | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 10 | 奥乙 | 福伊茨贝格 | 阿姆施泰滕 | 0.000 | 1:1 | 平 | 0+1 | 1 | 3+0 | 0 | -7.200 | 3 | 0 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 11 | 奥乙 | 因斯布鲁克 | 黑白布雷根茨 | 0.000 | 5:0 | 胜(因斯布鲁克) | 0 | 0 | 3+0 | 1 | 0.970 | 3 | 0 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 14 | 丹甲 | AB格莱萨克瑟 | 腓特烈西亚 | 0.000 | 1:1 | 平 | 1+3 | 1 | 0+1 | 1 | 0.000 | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 丹甲 | HB克厄 | 瓦埃勒 | 1.000 | 0:2 | 负(瓦埃勒) | 0 | 1 | 3+0 | 1 | -1.000 | 3 | 0 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 16 | 瑞典甲 | 奥迪沃德 | 诺尔比 | -1.000 | 0:0 | 负(诺尔比) | 3+0 | 1 | 0+3 | 1 | 0.000 | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 17 | 奥甲 | LASK林茨 | 格拉茨AK | -1.000 | 3:0 | 胜(LASK林茨) | 0 | 0 | 3+0 | 1 | 1.650 | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 18 | 瑞士甲 | 伊韦尔东体育 | 卡鲁日星 | -1.000 | 1:1 | 负(卡鲁日星) | 3 | 0 | 0+3+1 | 1 | 0.070 | 0 | 3 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 19 | 瑞士甲 | 韦尔 | 纳沙泰尔 | 0.000 | 1:2 | 负(纳沙泰尔) | 0+1 | 1 | 3+0 | 1 | 0.000 | 3 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 20 | 瑞士甲 | 尼永奈斯 | 拉珀斯维尔约纳 | 0.000 | 1:2 | 负(拉珀斯维尔约纳) | 0+1 | 1 | 0 | 1 | 1.000 | 0 | 0 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 24 | 波兰甲 | 卢布林莫托 | 乔治罗尼亚 | 0.000 | 1:2 | 负(乔治罗尼亚) | 1+3 | 0 | 0+3+1 | 1 | 1.730 | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 26 | 爱超 | 邓多克 | 斯莱戈流浪者 | -1.000 | 1:1 | 负(斯莱戈流浪者) | 3 | 0 | 3+0 | 1 | 1.580 | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 27 | 爱甲 | 布雷流浪者 | 凯里 | -1.000 | 0:4 | 负(凯里) | 0 | 1 | 0+1 | 1 | -1.000 | 0 | 0 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 28 | 爱甲 | 科夫漫步者 | 韦克斯福德 | 0.000 | 1:0 | 胜(科夫漫步者) | 1+3 | 1 | 3+0+1 | 1 | -1.000 | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 30 | 爱甲 | 条约联 | 朗福德城 | 0.000 | 0:1 | 负(朗福德城) | 1 | 0 | 3+0+1 | 1 | 1.120 | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 31 | 爱甲 | 阿斯隆城 | 都柏林大学 | 0.000 | 0:0 | 平 | 1+3 | 1 | 0+1 | 1 | 0.000 | 0 | 1 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 35 | 美职 | 纽约城 | 多伦多FC | -1.000 | 1:1 | 负(多伦多FC) | 0 | 1 | 0+1 | 1 | -1.000 | 0 | 0 | intelligence_missing;raw_strength_missing |
| 36 | 智利甲 | 康塞普西翁大学 | 奥达克斯意大利人 | 0.000 | 0:1 | 负(奥达克斯意大利人) | 1 | 0 | 3+1 | 0 | -1.000 | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 37 | 墨超 | 普埃布拉 | 瓜达拉哈拉 | 1.000 | 1:1 | 胜(普埃布拉) | 0 | 0 | 0+3 | 1 | 1.890 | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 39 | 墨超 | 华雷斯 | 普马斯 | 0.000 | 1:5 | 负(普马斯) | 1+3 | 0 | 0+3+1 | 1 | 1.310 | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | K1联赛 | 全北现代 | FC首尔 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 42 | K1联赛 | 浦项铁人 | 金泉尚武 | 0.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 43 | K2联赛 | 忠南牙山FC | 城南FC | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 44 | K2联赛 | 天安城 | 龙仁FC | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 46 | K2联赛 | 华城FC | 大邱FC | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 47 | 丹甲 | 希勒勒 | 埃斯比约 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 49 | 芬超 | TPS图尔库 | 玛丽港 | -1.000 |  |  | 1+0 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 50 | 波兰甲 | 格利维采皮亚斯特 | 克拉科夫维斯瓦 | 0.000 |  |  | 1+3 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 51 | 瑞典超 | 赫根 | 卡尔马 | -1.000 |  |  | 3+0 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 54 | 英联杯 | 特兰米尔流浪者 | 罗奇代尔 | 0.000 |  |  | 0+1 |  | 0 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 58 | 苏冠 | 艾尔联 | 阿布罗斯 | 0.000 |  |  | 0+1 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 59 | 苏冠 | 格里诺克摩顿 | 帕尔蒂克蓟花 | 1.000 |  |  | 0+1 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 60 | 苏冠 | 因弗内斯 | 邓弗姆林竞技 | 0.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 61 | 苏冠 | 利文斯顿 | 女王公园 | -1.000 |  |  | 1+3 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 62 | 苏冠 | 拉茨流浪者 | 斯坦豪斯摩尔 | -1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 丹甲 | 科灵 | 哈维德夫 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 65 | 捷克甲 | 利贝雷茨 | 特普利采 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 66 | 捷克甲 | 俄斯特拉发 | 布拉格斯拉维亚 | 1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 67 | 捷克甲 | 斯洛瓦茨科 | 布尔诺阿特斯 | -1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 68 | 芬超 | 拉赫蒂 | 查路 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 70 | 瑞典甲 | 北雪平 | 赫尔辛堡 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 71 | 瑞典甲 | 布莱格 | 兰斯克鲁纳 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 72 | 罗甲 | 沃伦塔里 | UTA阿拉德 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 74 | 瑞士超 | 苏黎世 | 塞尔维特 | 0.000 |  |  | 0+1 |  | 0 |  |  | 0 | 0 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 76 | 挪超 | 斯达 | 维京 | 1.000 |  |  | 1+3 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 78 | 芬超 | 格尼斯坦 | 库普斯 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 81 | 奥乙 | 第一维也纳 | 格拉茨风暴二队 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 82 | 智利甲 | 科布雷萨尔 | 拉卡莱拉联合 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 84 | 捷克甲 | 比尔森胜利 | 布尔诺兵工厂 | -1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_large;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 85 | 瑞士超 | 图恩 | 伯尔尼年轻人 | 0.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 86 | 罗甲 | CS克拉约瓦大学 | 佩特罗鲁 | -1.000 |  |  | 1+3 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 88 | 阿职联 | 里奥夸尔托大学生 | 班菲尔德 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 89 | 智利甲 | 比尼亚德马埃弗顿 | 科洛科洛 | 1.000 |  |  | 3+0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 91 | 巴西杯 | 瓦斯科达伽马 | 弗鲁米嫩塞 | 0.000 |  |  | 3+0 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 92 | 阿职联 | 拉普拉塔大学生 | 防卫与正义 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 94 | 智利甲 | 巴勒斯坦人 | 科金博联 | 0.000 |  |  | 0+3 |  | 0 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 95 | 巴西杯 | 米内罗竞技 | 尤文图德 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 99 | 美职 | 华盛顿联 | 纳什维尔SC | 0.000 |  |  | 0+1 |  | 0 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 100 | 美职 | 国际迈阿密 | 哥伦布机员 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 101 | 美职 | CF蒙特利尔 | 新英格兰革命 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 102 | 美职 | 纽约红牛 | 奥兰多城 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 103 | 美职 | 费城联合 | 亚特兰大联 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 104 | 美职 | 温哥华白浪 | 洛杉矶FC | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 105 | 智利甲 | 利马切 | 纽布莱恩斯 | 0.000 |  |  | 0+3 |  | 3+1+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 106 | 巴西杯 | 桑托斯 | 雷莫 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 107 | 美职 | 芝加哥火焰 | 夏洛特FC | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 109 | 美职 | 明尼苏达联 | 圣迭戈FC | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_watch;raw_strength_missing |
| 111 | 墨超 | 莱昂 | 帕丘卡 | 0.000 |  |  | 3+0 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 112 | 墨超 | 阿特拉斯 | 蒙特雷 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 113 | 美职 | 科罗拉多急流 | 奥斯汀FC | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 114 | 美职 | 洛杉矶银河 | FC达拉斯 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 115 | 美职 | 波特兰伐木者 | 西雅图海湾人 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 116 | 墨超 | 蓝十字 | 亚特兰特 | -2.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 117 | 奥乙 | 韦尔斯赫塔 | 奥地利萨尔茨堡 | 0.000 |  |  | 3+0 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 121 | K2联赛 | 釜山IPark | 首尔衣恋 | 0.000 |  |  | 1+3 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 123 | K2联赛 | 全南天龙 | 坡州前沿 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 124 | K2联赛 | 安山绿人 | 金海FC | 0.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 126 | 丹超 | 北西兰 | 兰讷斯 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 127 | 丹超 | 中日德兰 | 霍森斯 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 128 | 瑞典超 | 哥德堡 | 代格福什 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 130 | 芬超 | 瓦萨 | 国际图尔库 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 131 | 丹甲 | 文德斯尔 | 霍布罗 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 132 | 波兰甲 | 华沙莱吉亚 | 卢宾扎格勒比 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 134 | 捷克甲 | 奥洛穆茨 | 姆拉达博莱斯拉夫 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 137 | 芬超 | AC奥卢 | 伊尔维斯 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 139 | 冰岛超 | IA阿克拉内斯 | 维京古尔 | 1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 142 | 瑞典超 | AIK索尔纳 | 厄尔格里特 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 144 | 奥甲 | 奥地利卢斯特瑙 | 里德 | 0.000 |  |  | 0+1 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 145 | 挪超 | KFUM奥斯陆 | 克里斯蒂安松 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 146 | 挪超 | 莫尔德 | 萨尔普斯堡 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 151 | 挪甲 | 利恩 | 松达尔 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 152 | 挪甲 | 奥德 | 奥桑内 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 153 | 挪甲 | 赖于福斯 | 斯塔贝克 | 1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 155 | 捷克甲 | 波希米亚人1905 | 赫拉德茨克拉洛韦 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 157 | 波兰甲 | 史拉斯科 | 琴斯托霍瓦 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 158 | 荷超杯 | PSV埃因霍温 | 阿尔克马尔 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 159 | 丹超 | 锡尔克堡 | 哥本哈根 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 160 | 爱超 | 圣帕特里克竞技 | 德里城 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 162 | 奥甲 | 维也纳快速 | 阿尔特阿赫 | -1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 165 | 阿职联 | 阿尔多希维 | 拉普拉塔体操 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 167 | 爱超 | 波希米亚人 | 戈尔韦联 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 171 | 巴西杯 | 帕尔梅拉斯 | 福塔莱萨 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 174 | 智利甲 | 智利大学 | 瓦奇巴托 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 177 | 墨超 | 墨西哥美洲 | 桑托斯拉古纳 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 179 | 墨超 | 托卢卡 | 内卡萨 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 180 | 罗甲 | 克卢日大学 | 博托沙尼 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 182 | 爱甲 | 都柏林大学 | 条约联 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 184 | 爱甲 | 朗福德城 | 费恩哈普 | -1.000 |  |  | 1+3 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 185 | 爱甲 | 凯里 | 科夫漫步者 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 188 | 瑞典超 | 佐加顿斯 | 韦斯特罗斯 | -1.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 193 | 英联杯 | 约克城 | 克劳利 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 194 | 苏超 | 凯尔特人 | 邓迪FC | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 195 | 罗甲 | 布加勒斯特星 | 康斯坦察法鲁尔 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 196 | 冰岛超 | 瓦路尔 | 斯塔尔南 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 197 | 阿职联 | 萨米恩托 | 里瓦达维亚独立 | 0.000 |  |  | 0+1 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 198 | 阿职联 | 萨斯菲尔德 | 阿根廷独立 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 199 | 阿职联 | 普拉腾斯 | 塔勒瑞斯 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 200 | 巴西杯 | 巴拉纳竞技 | 维多利亚 | -1.000 |  |  | 3+1 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 201 | 阿职联 | 科尔多瓦中央 | 圣洛伦索 | 0.000 |  |  | 0+1 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |

## 26081 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 罗甲 | 阿尔杰什 | 奇克塞雷达 | -1.000 | 1:0 | 平 | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.563 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 2 | 芬甲 | KTP科特卡 | 塞伊奈约基学院 | -2.000 | 2:1 | 负(塞伊奈约基学院) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 0 | 1.044 |  |  |  |  | intelligence_missing;line_gap_watch;probability_runner_up_protection;raw_strength_missing |
| 3 | 芬甲 | EIF埃克奈斯 | 赫尔辛基预备队 | 0.000 | 2:0 | 胜(EIF埃克奈斯) | 1+0 | 0 | 3+1 |  | 0.000 | 1 | 3 | 1 | 1.156 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 4 | 波兰甲 | 普沃茨克维斯瓦 | 罗兹维德祖 | 0.000 | 0:0 | 平 | 3 | 0 | 0+3 |  | 0.000 | 0 | 0 | 3 | 1.139 |  |  |  |  | intelligence_missing;line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 5 | 丹甲 | 奥胡斯前进 | 奥尔堡 | 0.000 | 1:2 | 负(奥尔堡) | 1+0 | 1 | 3+1 |  | 0.000 | 0 | 3 | 1 | 1.279 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 6 | 芬甲 | PK-35 | 哈卡 | 0.000 | 1:4 | 负(哈卡) | 0+1 | 1 | 0+3 |  | 0.000 | 1 | 0 | 0 | 1.196 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 7 | 奥乙 | 阿德米拉 | 维也纳快速二队 | 0.000 | 0:1 | 负(维也纳快速二队) | 3+1 | 0 | 3 |  | 0.000 | 0 | 3 | 3 | 1.110 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 8 | 奥乙 | 奥地利维也纳二队 | 蓝白林茨 | 0.000 | 0:3 | 负(蓝白林茨) | 1 | 0 | 0+1 |  | 0.000 | 1 | 0 | 1 | 1.451 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 9 | 奥乙 | 卡普芬贝格 | 列夫林 | 1.000 | 0:4 | 负(列夫林) | 3 | 0 | 3 |  | 0.000 | 0 | 3 | 3 | 1.178 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 10 | 奥乙 | 福伊茨贝格 | 阿姆施泰滕 | 0.000 | 1:1 | 平 | 0+1 | 1 | 3+0 |  | 0.000 | 0 | 3 | 0 | 1.313 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 11 | 奥乙 | 因斯布鲁克 | 黑白布雷根茨 | 0.000 | 5:0 | 胜(因斯布鲁克) | 0 | 0 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.482 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 12 | 捷克甲 | 布拉格斯巴达 | 兹林 | -2.000 | 3:1 | 平 | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.273 |  |  |  |  | intelligence_missing;line_gap_large;raw_strength_missing |
| 13 | 挪超 | 瓦勒伦加 | 汉坎 | -1.000 | 0:3 | 负(汉坎) | 0 | 1 | 0 |  | 0.000 | 1 | 0 | 0 | 1.219 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 14 | 丹甲 | AB格莱萨克瑟 | 腓特烈西亚 | 0.000 | 1:1 | 平 | 1+3 | 1 | 0+1 |  | 0.000 | 1 | 0 | 1 | 1.329 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 丹甲 | HB克厄 | 瓦埃勒 | 1.000 | 0:2 | 负(瓦埃勒) | 0 | 1 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.283 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 16 | 瑞典甲 | 奥迪沃德 | 诺尔比 | -1.000 | 0:0 | 负(诺尔比) | 3+0 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 1.097 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 17 | 奥甲 | LASK林茨 | 格拉茨AK | -1.000 | 3:0 | 胜(LASK林茨) | 0 | 0 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.331 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 18 | 瑞士甲 | 伊韦尔东体育 | 卡鲁日星 | -1.000 | 1:1 | 负(卡鲁日星) | 3 | 0 | 0+3+1 |  | 0.000 | 1 | 0 | 3 | 1.160 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 19 | 瑞士甲 | 韦尔 | 纳沙泰尔 | 0.000 | 1:2 | 负(纳沙泰尔) | 0+1 | 1 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.372 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 20 | 瑞士甲 | 尼永奈斯 | 拉珀斯维尔约纳 | 0.000 | 1:2 | 负(拉珀斯维尔约纳) | 0+1 | 1 | 0 |  | 0.000 | 1 | 0 | 0 | 1.144 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 21 | 瑞士甲 | 克林斯 | 温特图尔 | 1.000 | 2:0 | 胜(克林斯) | 3 | 1 | 3 |  | 0.000 | 1 | 3 | 3 | 1.167 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 22 | 比超杯 | 布鲁日 | 圣吉罗斯联合 | 0.000 | 1:1 | 平 | 3+0 | 0 | 3+0 |  | 0.000 | 0 | 3 | 0 | 1.247 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 23 | 罗甲 | 加拉茨钢铁 | 布加勒斯特迪纳摩 | 0.000 | 1:1 | 平 | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.197 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 24 | 波兰甲 | 卢布林莫托 | 乔治罗尼亚 | 0.000 | 1:2 | 负(乔治罗尼亚) | 1+3 | 0 | 0+3+1 |  | 0.000 | 1 | 0 | 1 | 1.222 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 25 | 奥乙 | FAC维也纳 | 圣珀尔滕 | 0.000 | 1:0 | 胜(FAC维也纳) | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.509 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 26 | 爱超 | 邓多克 | 斯莱戈流浪者 | -1.000 | 1:1 | 负(斯莱戈流浪者) | 3 | 0 | 3+0 |  | 0.000 | 1 | 3 | 3 | 1.181 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 27 | 爱甲 | 布雷流浪者 | 凯里 | -1.000 | 0:4 | 负(凯里) | 0 | 1 | 0+1 |  | 0.000 | 1 | 0 | 0 | 1.610 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 28 | 爱甲 | 科夫漫步者 | 韦克斯福德 | 0.000 | 1:0 | 胜(科夫漫步者) | 1+3 | 1 | 3+0+1 |  | 0.000 | 1 | 3 | 1 | 1.229 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 29 | 爱甲 | 费恩哈普 | 科克城 | 2.000 | 0:3 | 负(科克城) | 3+1 | 0 | 3+1 |  | 0.000 | 0 | 3 | 1 | 1.071 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 30 | 爱甲 | 条约联 | 朗福德城 | 0.000 | 0:1 | 负(朗福德城) | 1 | 0 | 3+0+1 |  | 0.000 | 1 | 3 | 1 | 1.185 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 31 | 爱甲 | 阿斯隆城 | 都柏林大学 | 0.000 | 0:0 | 平 | 1+3 | 1 | 0+1 |  | 0.000 | 1 | 0 | 1 | 1.170 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 32 | 苏超 | 邓迪联 | 格拉斯哥流浪者 | 1.000 | 1:1 | 胜(邓迪联) | 3+1 | 1 | 3+1 |  | 0.000 | 1 | 3 | 3 | 1.237 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 33 | 挪超 | 博德闪耀 | 利勒斯特伦 | -2.000 | 4:0 | 胜(博德闪耀) | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.333 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 34 | 爱超 | 德罗赫达联 | 沙姆洛克流浪者 | 1.000 | 0:0 | 胜(德罗赫达联) | 3 | 1 | 3 |  | 0.000 | 1 | 3 | 3 | 1.183 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 35 | 美职 | 纽约城 | 多伦多FC | -1.000 | 1:1 | 负(多伦多FC) | 0 | 1 | 0+1 |  | 0.000 | 1 | 0 | 0 | 1.217 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 36 | 智利甲 | 康塞普西翁大学 | 奥达克斯意大利人 | 0.000 | 0:1 | 负(奥达克斯意大利人) | 1 | 0 | 3+1 |  | 0.000 | 0 | 3 | 1 | 1.148 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 37 | 墨超 | 普埃布拉 | 瓜达拉哈拉 | 1.000 | 1:1 | 胜(普埃布拉) | 0 | 0 | 0+3 |  | 0.000 | 1 | 0 | 0 | 1.100 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 38 | 墨超 | 圣路易斯竞技 | 蒂华纳 | 0.000 | 0:0 | 平 | 3 | 0 | 3 |  | 0.000 | 0 | 3 | 3 | 1.368 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 39 | 墨超 | 华雷斯 | 普马斯 | 0.000 | 1:5 | 负(普马斯) | 1+3 | 0 | 0+3+1 |  | 0.000 | 1 | 0 | 1 | 1.217 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | K1联赛 | 江原FC | 富川1995 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.418 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 41 | K1联赛 | 全北现代 | FC首尔 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.182 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 42 | K1联赛 | 浦项铁人 | 金泉尚武 | 0.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.247 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 43 | K2联赛 | 忠南牙山FC | 城南FC | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.162 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 44 | K2联赛 | 天安城 | 龙仁FC | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.263 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 45 | K2联赛 | 忠北清州FC | 水原三星蓝翼 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.346 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 46 | K2联赛 | 华城FC | 大邱FC | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.022 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 47 | 丹甲 | 希勒勒 | 埃斯比约 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.044 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 48 | 瑞典甲 | 厄斯特松德 | 厄斯特什 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.028 |  |  |  |  | intelligence_missing;line_gap_large;q_probability_disagree;raw_strength_missing |
| 49 | 芬超 | TPS图尔库 | 玛丽港 | -1.000 |  |  | 1+0 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.109 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 50 | 波兰甲 | 格利维采皮亚斯特 | 克拉科夫维斯瓦 | 0.000 |  |  | 1+3 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.080 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 51 | 瑞典超 | 赫根 | 卡尔马 | -1.000 |  |  | 3+0 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.003 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 52 | 瑞典甲 | 桑德维肯 | 松兹瓦尔 | -1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.099 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 53 | 瑞典甲 | 瓦尔贝里 | 法尔肯贝里 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.112 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 54 | 英联杯 | 特兰米尔流浪者 | 罗奇代尔 | 0.000 |  |  | 0+1 |  | 0 |  | 0.000 |  | 0 | 0 | 1.192 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 55 | 苏超 | 福尔柯克 | 圣米伦 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.048 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 56 | 挪超 | 腓特烈斯塔 | 桑讷菲尤尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.058 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 57 | 冰岛超 | IBV韦斯特曼纳 | 弗拉姆 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.250 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 58 | 苏冠 | 艾尔联 | 阿布罗斯 | 0.000 |  |  | 0+1 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.371 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 59 | 苏冠 | 格里诺克摩顿 | 帕尔蒂克蓟花 | 1.000 |  |  | 0+1 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 1.134 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 60 | 苏冠 | 因弗内斯 | 邓弗姆林竞技 | 0.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.195 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 61 | 苏冠 | 利文斯顿 | 女王公园 | -1.000 |  |  | 1+3 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.485 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 62 | 苏冠 | 拉茨流浪者 | 斯坦豪斯摩尔 | -1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.537 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 丹甲 | 科灵 | 哈维德夫 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.050 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 64 | 奥甲 | WSG蒂罗尔 | 格拉茨风暴 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.950 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 65 | 捷克甲 | 利贝雷茨 | 特普利采 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.797 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 66 | 捷克甲 | 俄斯特拉发 | 布拉格斯拉维亚 | 1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.373 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 67 | 捷克甲 | 斯洛瓦茨科 | 布尔诺阿特斯 | -1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 2.213 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 68 | 芬超 | 拉赫蒂 | 查路 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.512 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 69 | 挪甲 | 布莱尼 | 斯托姆加斯特 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.210 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 70 | 瑞典甲 | 北雪平 | 赫尔辛堡 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.482 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 71 | 瑞典甲 | 布莱格 | 兰斯克鲁纳 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.119 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 72 | 罗甲 | 沃伦塔里 | UTA阿拉德 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.410 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 73 | 波兰甲 | 克拉科夫维切斯塔 | 波兹南莱赫 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.879 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 74 | 瑞士超 | 苏黎世 | 塞尔维特 | 0.000 |  |  | 0+1 |  | 0 |  | 0.000 |  | 0 | 0 | 1.109 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 75 | 瑞士超 | 巴塞尔 | 洛桑体育 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.248 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 76 | 挪超 | 斯达 | 维京 | 1.000 |  |  | 1+3 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.381 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 77 | 丹超 | 灵比 | 奥胡斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.355 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 78 | 芬超 | 格尼斯坦 | 库普斯 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.056 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 79 | 瑞士甲 | 阿劳 | 洛桑乌契 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.163 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 80 | 苏超 | 阿伯丁 | 哈茨 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.853 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 81 | 奥乙 | 第一维也纳 | 格拉茨风暴二队 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 1.735 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 82 | 智利甲 | 科布雷萨尔 | 拉卡莱拉联合 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.287 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 83 | 奥甲 | 萨尔茨堡红牛 | 哈特贝格 | -2.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.437 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 84 | 捷克甲 | 比尔森胜利 | 布尔诺兵工厂 | -1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 2.420 |  |  |  |  | intelligence_missing;line_gap_large;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 85 | 瑞士超 | 图恩 | 伯尔尼年轻人 | 0.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.234 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 86 | 罗甲 | CS克拉约瓦大学 | 佩特罗鲁 | -1.000 |  |  | 1+3 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.721 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 87 | 阿职联 | 门多萨体操 | 圣菲联合 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.133 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 88 | 阿职联 | 里奥夸尔托大学生 | 班菲尔德 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.308 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 89 | 智利甲 | 比尼亚德马埃弗顿 | 科洛科洛 | 1.000 |  |  | 3+0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 1.764 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 90 | 葡超杯 | 波尔图 | 托里什恩斯 | -3.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.144 |  |  |  |  | intelligence_missing;line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 91 | 巴西杯 | 瓦斯科达伽马 | 弗鲁米嫩塞 | 0.000 |  |  | 3+0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.031 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 92 | 阿职联 | 拉普拉塔大学生 | 防卫与正义 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 2.562 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 93 | 阿职联 | 贝尔格拉诺 | 阿根廷青年人 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.084 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 94 | 智利甲 | 巴勒斯坦人 | 科金博联 | 0.000 |  |  | 0+3 |  | 0 |  | 0.000 |  | 0 | 0 | 1.108 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 95 | 巴西杯 | 米内罗竞技 | 尤文图德 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.415 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 96 | 墨超 | 克雷塔罗 | 老虎大学 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.057 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 97 | 阿职联 | 竞技俱乐部 | 蒂格雷 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.121 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 98 | 美职 | FC辛辛那提 | 圣何塞地震 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.312 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 99 | 美职 | 华盛顿联 | 纳什维尔SC | 0.000 |  |  | 0+1 |  | 0 |  | 0.000 |  | 0 | 0 | 1.292 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 100 | 美职 | 国际迈阿密 | 哥伦布机员 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.577 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 101 | 美职 | CF蒙特利尔 | 新英格兰革命 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.168 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 102 | 美职 | 纽约红牛 | 奥兰多城 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.293 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 103 | 美职 | 费城联合 | 亚特兰大联 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 3.095 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 104 | 美职 | 温哥华白浪 | 洛杉矶FC | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.782 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 105 | 智利甲 | 利马切 | 纽布莱恩斯 | 0.000 |  |  | 0+3 |  | 3+1+0 |  | 0.000 |  | 3 | 0 | 1.063 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 106 | 巴西杯 | 桑托斯 | 雷莫 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.320 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 107 | 美职 | 芝加哥火焰 | 夏洛特FC | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.280 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 108 | 美职 | 堪萨斯城体育 | 休斯敦迪纳摩 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.164 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 109 | 美职 | 明尼苏达联 | 圣迭戈FC | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.478 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 110 | 美职 | 圣路易斯城 | 皇家盐湖城 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.205 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 111 | 墨超 | 莱昂 | 帕丘卡 | 0.000 |  |  | 3+0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.008 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 112 | 墨超 | 阿特拉斯 | 蒙特雷 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.080 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 113 | 美职 | 科罗拉多急流 | 奥斯汀FC | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 3.223 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 114 | 美职 | 洛杉矶银河 | FC达拉斯 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.135 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 115 | 美职 | 波特兰伐木者 | 西雅图海湾人 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 1.084 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 116 | 墨超 | 蓝十字 | 亚特兰特 | -2.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 5.169 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 117 | 奥乙 | 韦尔斯赫塔 | 奥地利萨尔茨堡 | 0.000 |  |  | 3+0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.144 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 118 | K1联赛 | 蔚山HD | FC安养 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.577 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 119 | K1联赛 | 大田韩亚市民 | 光州FC | -1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 9.283 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 120 | K1联赛 | 济州SK | 仁川联 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.163 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 121 | K2联赛 | 釜山IPark | 首尔衣恋 | 0.000 |  |  | 1+3 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.244 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 122 | K2联赛 | 金浦FC | 庆南FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.759 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 123 | K2联赛 | 全南天龙 | 坡州前沿 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.350 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 124 | K2联赛 | 安山绿人 | 金海FC | 0.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.041 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 125 | 瑞士超 | 瓦杜兹 | 圣加仑 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.540 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 126 | 丹超 | 北西兰 | 兰讷斯 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 22.365 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 127 | 丹超 | 中日德兰 | 霍森斯 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 9.546 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 128 | 瑞典超 | 哥德堡 | 代格福什 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 17.016 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 129 | 瑞典超 | 布鲁马波卡纳 | 马尔默 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.528 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 130 | 芬超 | 瓦萨 | 国际图尔库 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.141 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 131 | 丹甲 | 文德斯尔 | 霍布罗 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.151 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 132 | 波兰甲 | 华沙莱吉亚 | 卢宾扎格勒比 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 31.809 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 133 | 苏超 | 圣约翰斯通 | 基尔马诺克 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.319 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 134 | 捷克甲 | 奥洛穆茨 | 姆拉达博莱斯拉夫 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 48.090 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 135 | 瑞典甲 | 诺迪克联 | 永斯基 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.689 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 136 | 丹超 | 布隆德比 | 维堡 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.400 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 137 | 芬超 | AC奥卢 | 伊尔维斯 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.044 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 138 | 爱超 | 沃特福德FC | 谢尔伯恩 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.539 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 139 | 冰岛超 | IA阿克拉内斯 | 维京古尔 | 1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 9.184 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 140 | 瑞士超 | 锡永 | 卢塞恩 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.631 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 141 | 瑞士超 | 草蜢 | 卢加诺 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.498 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 142 | 瑞典超 | AIK索尔纳 | 厄尔格里特 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 10.873 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 143 | 奥甲 | 沃尔夫斯贝格 | 奥地利维也纳 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.503 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 144 | 奥甲 | 奥地利卢斯特瑙 | 里德 | 0.000 |  |  | 0+1 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.120 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 145 | 挪超 | KFUM奥斯陆 | 克里斯蒂安松 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 13.275 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 146 | 挪超 | 莫尔德 | 萨尔普斯堡 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 17.785 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 147 | 挪超 | 奥勒松 | 特罗姆瑟 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 11.450 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 148 | 挪甲 | 埃格尔松 | 桑内斯乌尔夫 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.167 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 149 | 挪甲 | 赫德 | 莫斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.175 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 150 | 挪甲 | 孔斯温厄尔 | 斯托曼 | -2.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 6.874 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 151 | 挪甲 | 利恩 | 松达尔 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.057 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 152 | 挪甲 | 奥德 | 奥桑内 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 15.820 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 153 | 挪甲 | 赖于福斯 | 斯塔贝克 | 1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 18.213 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 154 | 苏超 | 希伯尼安 | 马瑟韦尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.550 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 155 | 捷克甲 | 波希米亚人1905 | 赫拉德茨克拉洛韦 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.286 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 156 | 罗甲 | 胡内多阿拉乌鸦 | 塞普西 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.612 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 157 | 波兰甲 | 史拉斯科 | 琴斯托霍瓦 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.841 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 158 | 荷超杯 | PSV埃因霍温 | 阿尔克马尔 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 13.213 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 159 | 丹超 | 锡尔克堡 | 哥本哈根 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 44.660 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 160 | 爱超 | 圣帕特里克竞技 | 德里城 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 29.315 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 161 | 智利甲 | 康塞普西翁 | 天主教大学 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.790 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 162 | 奥甲 | 维也纳快速 | 阿尔特阿赫 | -1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 62.790 |  |  |  |  | intelligence_missing;line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 163 | 挪超 | 布兰 | 罗森博格 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.285 |  |  |  |  | intelligence_missing;line_gap_large;raw_strength_missing |
| 164 | 阿职联 | 列斯特拉体育 | 巴拉卡斯中央 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.536 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 165 | 阿职联 | 阿尔多希维 | 拉普拉塔体操 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.758 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 166 | 捷克甲 | 帕尔杜比采 | 亚布洛内茨 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.341 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 167 | 爱超 | 波希米亚人 | 戈尔韦联 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 30.903 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 168 | 波兰甲 | 卡托维兹 | 拉多米亚克 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.774 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 169 | 罗甲 | 布加勒斯特快速 | 克卢日 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.361 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 170 | 智利甲 | 拉塞雷纳 | 奥伊金斯 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.299 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 171 | 巴西杯 | 帕尔梅拉斯 | 福塔莱萨 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 25.289 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 172 | 阿职联 | 纽维尔老男孩 | 博卡青年 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.483 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 173 | 巴西杯 | 米拉索尔 | 格雷米奥 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.865 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 174 | 智利甲 | 智利大学 | 瓦奇巴托 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 18.899 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 175 | 阿职联 | 河床 | 罗萨里奥中央 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.441 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 176 | 巴西杯 | 巴西国际 | 科林蒂安 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.620 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 177 | 墨超 | 墨西哥美洲 | 桑托斯拉古纳 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 24.490 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 178 | 阿职联 | 拉努斯 | 科尔多瓦学院 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.909 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 179 | 墨超 | 托卢卡 | 内卡萨 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 64.129 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 180 | 罗甲 | 克卢日大学 | 博托沙尼 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 38.143 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 181 | 芬超 | 塞伊奈约基 | 赫尔辛基 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.184 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 182 | 爱甲 | 都柏林大学 | 条约联 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 25.511 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 183 | 爱甲 | 韦克斯福德 | 布雷流浪者 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.324 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 184 | 爱甲 | 朗福德城 | 费恩哈普 | -1.000 |  |  | 1+3 |  | 0+1 |  | 0.000 |  | 0 | 1 | 99.055 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 185 | 爱甲 | 凯里 | 科夫漫步者 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.139 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 186 | 爱甲 | 科克城 | 阿斯隆城 | -1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 3 | 2.689 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 187 | 丹超 | 欧登塞 | 桑德捷斯基 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.736 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 188 | 瑞典超 | 佐加顿斯 | 韦斯特罗斯 | -1.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 23.044 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 189 | 瑞典超 | 哈尔姆斯塔德 | 天狼星 | 1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.817 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 190 | 波兰甲 | 克拉科维亚 | 什切青波贡 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.797 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 191 | 挪甲 | 兰黑姆 | 海于格松 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.347 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 192 | 瑞典甲 | 厄勒布鲁 | 韦纳穆 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.801 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 193 | 英联杯 | 约克城 | 克劳利 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 28.095 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 194 | 苏超 | 凯尔特人 | 邓迪FC | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 17.265 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 195 | 罗甲 | 布加勒斯特星 | 康斯坦察法鲁尔 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 38.917 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 196 | 冰岛超 | 瓦路尔 | 斯塔尔南 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 1.185 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 197 | 阿职联 | 萨米恩托 | 里瓦达维亚独立 | 0.000 |  |  | 0+1 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.186 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 198 | 阿职联 | 萨斯菲尔德 | 阿根廷独立 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.547 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 199 | 阿职联 | 普拉腾斯 | 塔勒瑞斯 | 0.000 |  |  | 3+1 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.263 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 200 | 巴西杯 | 巴拉纳竞技 | 维多利亚 | -1.000 |  |  | 3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 22.781 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 201 | 阿职联 | 科尔多瓦中央 | 圣洛伦索 | 0.000 |  |  | 0+1 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.440 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 202 | 阿职联 | 飓风 | 图库曼竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.486 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |

## 26081_016 专项

{
  "issue": "26081",
  "match_idx": 16,
  "match_id": "26081_016",
  "league": "瑞典甲",
  "home": "奥迪沃德",
  "away": "诺尔比",
  "handicap_line": -1.0,
  "score": "0:0",
  "actual_code": "0",
  "actual_label": "负(诺尔比)",
  "winning_sp": 2.34,
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "胜(奥迪沃德)为押，保负(诺尔比)",
  "active_primary": "3",
  "active_selection_codes": "3+0",
  "active_primary_hit": 0,
  "active_coverage_hit": 1,
  "active_stake": 2,
  "active_profit_proxy": 0.34,
  "shadow_judgment": "负(诺尔比)为押，保胜(奥迪沃德)",
  "shadow_primary": "0",
  "shadow_selection_codes": "0+3",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": 1,
  "shadow_coverage_hit": 1,
  "shadow_stake": 2,
  "shadow_profit_proxy": 0.34,
  "shadow_arm": "active_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3",
  "selection_type": "double",
  "prob_top": "0",
  "q_top": "3",
  "p_3": 0.31090572005635614,
  "p_1": 0.23125623831892453,
  "p_0": 0.45783804162471936,
  "sp_3": 3.53,
  "sp_1": 3.75,
  "sp_0": 2.21,
  "q_3": 1.0974971917989371,
  "q_1": 0.8672108936959669,
  "q_0": 1.0118220719906297,
  "max_q": 1.0975,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "",
  "form_recent_confidence": "",
  "form_recent_mapped_code": "",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "intelligence_missing;q_probability_disagree;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 负(诺尔比) 45.8%。\", \"EV/q主线：最高q 胜(奥迪沃德) q=1.10，概率 31.1%，SP 3.53。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：胜(奥迪沃德) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"负(诺尔比)\", \"score\": \"45.8%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 31.1% / 平 23.1% / 负 45.8%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"胜(奥迪沃德)\", \"score\": \"q 1.10\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 1.10 / 平 0.87 / 负 1.01\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"无明确方向\", \"score\": \"置信 0.00\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": []}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"常规\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": []}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"有缺口\", \"score\": \"3 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"intelligence_missing\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"负(诺尔比)为押，保胜(奥迪沃德)\", \"score\": \"置信 0.46\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 负(诺尔比) 45.8%。\", \"EV/q主线：最高q 胜(奥迪沃德) q=1.10，概率 31.1%，SP 3.53。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26081_20260801_active_v3.3.3/structured_shadow_26081.csv`
