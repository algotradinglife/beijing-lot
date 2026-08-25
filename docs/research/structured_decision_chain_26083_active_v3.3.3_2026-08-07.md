# 结构化决策链 26083 active_v3.3.3 回测

生成时间：2026-08-07 09:12:43Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`290/290`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 16, 'single': 274} |
| active_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 36, 'single': 244, 'full': 10} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 8 | K2联赛 | 龙仁FC | 釜山IPark | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 9 | 芬甲 | 哈卡 | 吉波 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 10 | 芬甲 | 耶尔文佩 | MP米凯利 | 0.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 11 | 芬超 | 塞伊奈约基 | 格尼斯坦 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 12 | 奥乙 | 圣珀尔滕 | 奥地利维也纳二队 | -1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 13 | 奥乙 | 列夫林 | 韦尔斯赫塔 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 14 | 捷克甲 | 布尔诺兵工厂 | 利贝雷茨 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 16 | 丹超 | 桑德捷斯基 | 维堡 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 瑞典甲 | 厄斯特松德 | 松兹瓦尔 | -1.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 21 | 瑞士甲 | 洛桑乌契 | 拉珀斯维尔约纳 | -1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 22 | 荷甲 | 坎布尔 | 鹿特丹精英 | 0.000 |  |  | 1+0 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 24 | 荷乙 | 芬洛 | 赫拉克勒斯 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 25 | 荷乙 | 奥斯 | 布雷达 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 27 | 荷乙 | 多德雷赫特 | 阿贾克斯青年队 | -1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 28 | 瑞士甲 | 卡鲁日星 | 纳沙泰尔 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 29 | 瑞士甲 | 阿劳 | 尼永奈斯 | -1.000 |  |  | 1+0 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 30 | 德乙 | 波鸿 | 柏林赫塔 | 0.000 |  |  | 3+0 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 33 | 苏冠 | 帕尔蒂克蓟花 | 利文斯顿 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 34 | 英联杯 | 狼队 | 维尔港 | -2.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 35 | 英联杯 | 威科姆流浪者 | 斯蒂夫尼奇 | 0.000 |  |  | 3+0 |  | 3 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 37 | 爱超 | 德里城 | 斯莱戈流浪者 | -1.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 38 | 爱超 | 戈尔韦联 | 德罗赫达联 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 39 | 爱甲 | 布雷流浪者 | 费恩哈普 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 爱甲 | 科夫漫步者 | 条约联 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 爱甲 | 科克城 | 凯里 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 42 | 爱甲 | 都柏林大学 | 韦克斯福德 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 爱甲 | 阿斯隆城 | 朗福德城 | 0.000 |  |  | 1 |  | 3+0+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 46 | 葡超 | 埃斯托里尔 | 法马利康 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 47 | 阿职联 | 罗萨里奥中央 | 阿尔多希维 | -1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 48 | 巴西乙 | 铁路工人 | 圣贝尔纳多 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 巴西乙 | 塞阿拉 | 庞特普雷塔 | -1.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 51 | 阿职联 | 里瓦达维亚独立 | 里奥夸尔托大学生 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 3 | intelligence_missing;raw_strength_missing |
| 52 | J2联赛 | 北海道札幌冈萨多 | 德岛漩涡 | 0.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | intelligence_missing;line_gap_missing;raw_strength_missing |
| 94 | 英联杯 | 伯恩利 | 诺茨郡 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 104 | 英联杯 | 诺维奇 | 米尔顿凯恩斯 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 106 | 英联杯 | 索尔福德城 | 什鲁斯伯里 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 108 | 英联杯 | 斯托克城 | 奥德汉姆 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 111 | 英联杯 | 西汉姆联 | 朴茨茅斯 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 277 | 葡甲 | 本菲卡B队 | 雷克索斯 | 0.000 |  |  | 1+0 |  | 3+1 |  |  | 3 | 1 | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 284 | 英联杯 | 普利茅斯 | 埃克塞特城 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |

## 26083 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | J1联赛 | 横滨水手 | 鹿岛鹿角 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.033 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 2 | J1联赛 | 大阪钢巴 | 浦和红钻 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.080 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 3 | K2联赛 | 忠南牙山FC | 安山绿人 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.058 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 4 | K2联赛 | 金浦FC | 忠北清州FC | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.243 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 5 | K2联赛 | 庆南FC | 大邱FC | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.541 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 6 | K2联赛 | 华城FC | 首尔衣恋 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.387 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 7 | K2联赛 | 水原三星蓝翼 | 金海FC | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.538 |  |  |  |  | intelligence_missing;line_gap_watch;raw_strength_missing |
| 8 | K2联赛 | 龙仁FC | 釜山IPark | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.427 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 9 | 芬甲 | 哈卡 | 吉波 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.467 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 10 | 芬甲 | 耶尔文佩 | MP米凯利 | 0.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.159 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 11 | 芬超 | 塞伊奈约基 | 格尼斯坦 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.263 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 12 | 奥乙 | 圣珀尔滕 | 奥地利维也纳二队 | -1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 5.677 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 13 | 奥乙 | 列夫林 | 韦尔斯赫塔 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 3.240 |  |  |  |  | intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 14 | 捷克甲 | 布尔诺兵工厂 | 利贝雷茨 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.703 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 15 | 挪超 | 桑讷菲尤尔 | KFUM奥斯陆 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.431 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 16 | 丹超 | 桑德捷斯基 | 维堡 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 4.833 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 瑞典甲 | 厄斯特松德 | 松兹瓦尔 | -1.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.507 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 18 | 奥甲 | 阿尔特阿赫 | WSG蒂罗尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.576 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 19 | 瑞士甲 | 克林斯 | 伊韦尔东体育 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.320 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 20 | 瑞士甲 | 温特图尔 | 韦尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.471 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 21 | 瑞士甲 | 洛桑乌契 | 拉珀斯维尔约纳 | -1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 3.510 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 22 | 荷甲 | 坎布尔 | 鹿特丹精英 | 0.000 |  |  | 1+0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.348 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 23 | 罗甲 | UTA阿拉德 | 布加勒斯特快速 | 0.000 |  |  | 1+3 |  | 1+3 |  | 0.000 |  | 1 | 1 | 4.792 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 24 | 荷乙 | 芬洛 | 赫拉克勒斯 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 3.638 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 25 | 荷乙 | 奥斯 | 布雷达 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.281 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 26 | 荷乙 | 埃门 | 罗达JC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.655 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 27 | 荷乙 | 多德雷赫特 | 阿贾克斯青年队 | -1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 2.774 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 28 | 瑞士甲 | 卡鲁日星 | 纳沙泰尔 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 7.057 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 29 | 瑞士甲 | 阿劳 | 尼永奈斯 | -1.000 |  |  | 1+0 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.212 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 30 | 德乙 | 波鸿 | 柏林赫塔 | 0.000 |  |  | 3+0 |  | 3 |  | 0.000 |  | 3 | 3 | 1.178 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 31 | 波兰甲 | 克拉科夫维斯瓦 | 普沃茨克维斯瓦 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.476 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | 奥乙 | 蓝白林茨 | 因斯布鲁克 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.673 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 33 | 苏冠 | 帕尔蒂克蓟花 | 利文斯顿 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 3.544 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 34 | 英联杯 | 狼队 | 维尔港 | -2.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.380 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 35 | 英联杯 | 威科姆流浪者 | 斯蒂夫尼奇 | 0.000 |  |  | 3+0 |  | 3 |  | 0.000 |  | 3 | 3 | 1.458 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 36 | 比甲 | 布鲁日 | 科特赖克 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.844 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 37 | 爱超 | 德里城 | 斯莱戈流浪者 | -1.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 88.176 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 38 | 爱超 | 戈尔韦联 | 德罗赫达联 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.295 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 39 | 爱甲 | 布雷流浪者 | 费恩哈普 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.854 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 爱甲 | 科夫漫步者 | 条约联 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 3.348 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 爱甲 | 科克城 | 凯里 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 3.275 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 42 | 爱甲 | 都柏林大学 | 韦克斯福德 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.596 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 爱甲 | 阿斯隆城 | 朗福德城 | 0.000 |  |  | 1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.522 |  |  |  |  | intelligence_missing;line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 44 | 英联杯 | 米德尔斯堡 | 雷克瑟姆 | -1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.042 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 45 | 爱超 | 沙姆洛克流浪者 | 邓多克 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 7.326 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 46 | 葡超 | 埃斯托里尔 | 法马利康 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.462 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 47 | 阿职联 | 罗萨里奥中央 | 阿尔多希维 | -1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 6.245 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 48 | 巴西乙 | 铁路工人 | 圣贝尔纳多 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.765 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 巴西乙 | 塞阿拉 | 庞特普雷塔 | -1.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 4.097 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 50 | 智利甲 | 天主教大学 | 科布雷萨尔 | -2.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 3.930 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 51 | 阿职联 | 里瓦达维亚独立 | 里奥夸尔托大学生 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 3 | 10.621 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 52 | J2联赛 | 北海道札幌冈萨多 | 德岛漩涡 | 0.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 2.989 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 53 | J2联赛 | 八户云罗里 | 富山胜利 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.826 |  |  |  |  | intelligence_missing;line_gap_missing;raw_strength_missing |
| 54 | J2联赛 | 藤枝MYFC | 仙台七夕 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 55 | J1联赛 | 柏太阳神 | 水户蜀葵 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 56 | J1联赛 | FC东京 | 町田泽维亚 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 57 | J1联赛 | 名古屋鲸 | 清水心跳 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 58 | J1联赛 | 大阪樱花 | 冈山绿雉 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 59 | J1联赛 | 福冈黄蜂 | 神户胜利船 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 60 | J2联赛 | RB大宫松鼠 | 新泻天鹅 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 61 | J2联赛 | 磐田喜悦 | 秋田蓝色闪电 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 62 | J2联赛 | 大分三神 | 湘南海洋 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 63 | J2联赛 | 宫崎特格瓦嘉洛 | 横滨FC | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 64 | 葡甲 | 沙维什 | 科英布拉大学 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.407 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 65 | J1联赛 | 广岛三箭 | 千叶市原 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 66 | J2联赛 | 鸟栖砂岩 | 甲府风林 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 67 | K1联赛 | FC安养 | 大田韩亚市民 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 68 | K1联赛 | 富川1995 | 光州FC | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 69 | K1联赛 | 金泉尚武 | FC首尔 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 70 | K1联赛 | 全北现代 | 济州SK | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 71 | K1联赛 | 浦项铁人 | 蔚山HD | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 72 | K2联赛 | 坡州前沿 | 水原FC | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 73 | K2联赛 | 城南FC | 天安城 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 74 | 德乙 | 海登海姆 | 奥斯纳布吕克 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 75 | 德乙 | 达姆施塔特 | 基尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 76 | 德乙 | 卡尔斯鲁厄 | 比勒费尔德 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 77 | 德乙 | 马格德堡 | 不伦瑞克 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 78 | 瑞典甲 | 永斯基 | 奥迪沃德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 79 | 瑞典甲 | 法尔肯贝里 | 诺迪克联 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 80 | 英联杯 | 剑桥联 | 巴尼特 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_large;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 81 | 挪超 | 瓦勒伦加 | 博德闪耀 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 82 | 丹甲 | 奥胡斯前进 | HB克厄 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 83 | 波兰甲 | 拉多米亚克 | 扎布热矿工 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 84 | 英联杯 | 女王公园巡游者 | 米尔沃尔 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 85 | 瑞典超 | 厄尔格里特 | AIK索尔纳 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 86 | 葡甲 | 佩纳菲耶尔 | 波尔蒂芒斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 87 | 瑞典甲 | 厄斯特什 | 兰斯克鲁纳 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 88 | 奥乙 | 维也纳快速二队 | 福伊茨贝格 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 89 | 英联杯 | AFC温布尔登 | 纽波特郡 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 90 | 英联杯 | 巴恩斯利 | 维冈竞技 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 91 | 英联杯 | 布拉德福德城 | 罗奇代尔 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 92 | 英联杯 | 布里斯托尔流浪者 | 彼得堡联 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 93 | 英联杯 | 布罗姆利 | 雷丁 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 94 | 英联杯 | 伯恩利 | 诺茨郡 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 95 | 英联杯 | 伯顿 | 布莱克本 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 96 | 英联杯 | 卡迪夫城 | 斯文登 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_large;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 97 | 英联杯 | 克鲁 | 阿克灵顿 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 98 | 英联杯 | 德比郡 | 林肯城 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 99 | 英联杯 | 弗利特伍德 | 切斯特菲尔德 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 100 | 英联杯 | 吉林汉姆 | 卢顿 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 101 | 英联杯 | 格里姆斯比 | 布莱克浦 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 102 | 英联杯 | 莱斯特城 | 北安普顿 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 103 | 英联杯 | 莱顿东方 | 牛津联 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 104 | 英联杯 | 诺维奇 | 米尔顿凯恩斯 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 105 | 英联杯 | 普雷斯顿 | 哈德斯菲尔德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 106 | 英联杯 | 索尔福德城 | 什鲁斯伯里 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 107 | 英联杯 | 斯托克波特郡 | 唐卡斯特 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 108 | 英联杯 | 斯托克城 | 奥德汉姆 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 109 | 英联杯 | 斯旺西 | 伯明翰 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 110 | 英联杯 | 沃特福德 | 克劳利 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 111 | 英联杯 | 西汉姆联 | 朴茨茅斯 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 112 | 苏超 | 邓迪FC | 阿伯丁 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 113 | 苏超 | 圣米伦 | 圣约翰斯通 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 114 | 挪超 | 维京 | 萨尔普斯堡 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 115 | 苏冠 | 阿布罗斯 | 因弗内斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 116 | 苏冠 | 邓弗姆林竞技 | 艾尔联 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 117 | 苏冠 | 女王公园 | 拉茨流浪者 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 118 | 苏冠 | 斯坦豪斯摩尔 | 格里诺克摩顿 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 119 | 挪甲 | 斯塔贝克 | 利恩 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 120 | 丹甲 | 霍布罗 | AB格莱萨克瑟 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 121 | 葡超 | 马里迪莫 | 卡萨皮亚 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 122 | 荷甲 | 奈梅亨 | 特尔斯达 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 123 | 荷乙 | 邓伯什 | 阿尔梅勒城 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 124 | 奥甲 | 格拉茨AK | 奥地利卢斯特瑙 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 125 | 捷克甲 | 兹林 | 波希米亚人1905 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 126 | 捷克甲 | 特普利采 | 比尔森胜利 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 127 | 瑞典甲 | 北雪平 | 布莱格 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 128 | 芬甲 | 卡帕 | EIF埃克奈斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 129 | 芬甲 | 塞伊奈约基学院 | PK-35 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 130 | 瑞典超 | 米亚尔比 | 埃尔夫斯堡 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 131 | 罗甲 | 康斯坦察法鲁尔 | 奇克塞雷达 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 132 | 波兰甲 | 什切青波贡 | 卢布林莫托 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 133 | 奥乙 | 奥地利萨尔茨堡 | 第一维也纳 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 134 | 奥乙 | 格拉茨风暴二队 | FAC维也纳 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 135 | 奥乙 | 黑白布雷根茨 | 卡普芬贝格 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 136 | 瑞士超 | 洛桑体育 | 伯尔尼年轻人 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 137 | 挪超 | 斯达 | 腓特烈斯塔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 138 | 芬超 | 查路 | 瓦萨 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 139 | 比甲 | 标准列日 | 色格拉布鲁日 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 140 | 英联杯 | 切尔滕汉姆 | 查尔顿 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 141 | 英联杯 | 科尔切斯特联 | 南安普顿 | 2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 142 | 英联杯 | 罗瑟汉姆联 | 西布朗维奇 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 143 | 荷甲 | 前进之鹰 | 威廉二世 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 144 | 葡超 | 吉马良斯 | 阿罗卡 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 145 | 葡甲 | 通德拉 | 阿马兰蒂 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 146 | 奥甲 | 哈特贝格 | 格拉茨风暴 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 147 | 阿职联 | 列斯特拉体育 | 拉普拉塔大学生 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 148 | 阿职联 | 图库曼竞技 | 萨米恩托 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 149 | 荷甲 | PSV埃因霍温 | 锡塔德福图纳 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 150 | 捷克甲 | 姆拉达博莱斯拉夫 | 布拉格斯巴达 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 151 | 波兰甲 | 凯尔采科罗纳 | 华沙莱吉亚 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 152 | 德乙 | 沃尔夫斯堡 | 凯泽斯劳滕 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 153 | 瑞士超 | 塞尔维特 | 草蜢 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 154 | 罗甲 | 布加勒斯特迪纳摩 | 沃伦塔里 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 155 | 法乙 | 布洛涅 | 南锡 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 156 | 法乙 | 克莱蒙 | 兰斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 157 | 法乙 | 敦刻尔克 | 格勒诺布尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 158 | 法乙 | 梅斯 | 甘冈 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 159 | 法乙 | 蒙彼利埃 | 第戎 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 160 | 法乙 | 南特 | 圣旺红星 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 161 | 法乙 | 波城 | 阿讷西 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 162 | 法乙 | 罗德兹 | 拉瓦勒 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 163 | 法乙 | 索肖 | 圣埃蒂安 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 164 | 比甲 | 韦斯特洛 | 圣吉罗斯联合 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 165 | 比甲 | 圣特赖登 | 洛默尔 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 166 | 荷甲 | 阿尔克马尔 | 海牙 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 167 | 巴西甲 | 格雷米奥 | 圣保罗 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 168 | 智利甲 | 瓦奇巴托 | 比尼亚德马埃弗顿 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 169 | 巴西乙 | 维拉诺瓦 | 累西腓体育 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 170 | 葡超 | 阿马多拉之星 | 葡萄牙体育 | 2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 171 | 阿职联 | 蒂格雷 | 河床 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 172 | 美职 | 新英格兰革命 | 休斯敦迪纳摩 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 173 | 巴西甲 | 雷莫 | 米内罗竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 174 | 智利甲 | 科金博联 | 拉塞雷纳 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 175 | 巴西乙 | 博塔弗戈SP | 米内罗美洲 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 176 | 阿职联 | 博卡青年 | 萨斯菲尔德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 177 | 巴西甲 | 科里蒂巴 | 沙佩科恩斯 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 178 | 巴西甲 | 博塔弗戈 | 弗鲁米嫩塞 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 179 | 阿职联 | 科尔多瓦学院 | 门多萨体操 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 180 | 阿职联 | 阿根廷独立 | 普拉腾斯 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 181 | 奥乙 | 阿姆施泰滕 | 阿德米拉 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 182 | J1联赛 | 东京绿茵 | 川崎前锋 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 183 | J2联赛 | 磐城 | FC今治 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 184 | J1联赛 | 长崎成功丸 | 京都不死鸟 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 185 | J2联赛 | 山形山神 | 枥木城 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 186 | 葡甲 | SC法伦斯 | 托里什恩斯 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 187 | 荷甲 | 鹿特丹斯巴达 | 费耶诺德 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 188 | 荷乙 | 海尔蒙德体育 | 格拉夫夏普 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 189 | 丹甲 | 哈维德夫 | 埃斯比约 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 190 | 德乙 | 圣保利 | 菲尔特 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 191 | 德乙 | 纽伦堡 | 德累斯顿 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 192 | 德乙 | 科特布斯 | 汉诺威96 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 193 | 瑞士超 | 卢加诺 | 苏黎世 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 194 | 瑞典超 | 哈马比 | 赫根 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 195 | 瑞典超 | 马尔默 | 代格福什 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 196 | 芬超 | 库普斯 | TPS图尔库 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 197 | 丹甲 | 瓦埃勒 | 希勒勒 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 198 | 丹甲 | 奥尔堡 | 科灵 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 199 | 芬甲 | 赫尔辛基预备队 | KTP科特卡 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 200 | 荷甲 | 兹沃勒 | 阿贾克斯 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 201 | 荷甲 | 格罗宁根 | 乌德勒支 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 202 | 苏超 | 基尔马诺克 | 凯尔特人 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 203 | 挪超 | 利勒斯特伦 | 罗森博格 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 204 | 波兰甲 | 史拉斯科 | 克拉科维亚 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 205 | 捷克甲 | 布拉格斯拉维亚 | 帕尔杜比采 | -2.000 |  |  | 3 |  | 3 |  | 0.000 |  |  |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 206 | 葡甲 | 维泽拉 | 莱里亚 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 207 | 丹甲 | 腓特烈西亚 | 文德斯尔 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 208 | 瑞典甲 | 瓦尔贝里 | 桑德维肯 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 209 | 苏超 | 哈茨 | 邓迪联 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 210 | 苏超 | 马瑟韦尔 | 福尔柯克 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 211 | 比甲 | 沙勒罗瓦 | 奥德赫维里鲁汶 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 212 | 丹超 | 兰讷斯 | 灵比 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 213 | 芬超 | 国际图尔库 | 拉赫蒂 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 214 | 爱超 | 沃特福德FC | 波希米亚人 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 215 | 巴西乙 | 米纳斯吉拉斯竞技 | 克里西乌马 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 216 | 瑞士超 | 巴塞尔 | 图恩 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 217 | 瑞士超 | 圣加仑 | 卢塞恩 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 218 | 瑞士超 | 锡永 | 瓦杜兹 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 219 | 瑞典超 | 哥德堡 | 卡尔马 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 220 | 瑞典超 | 哈尔姆斯塔德 | 加尔斯 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 221 | 葡甲 | A F S | 葡萄牙体育B队 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 222 | 葡甲 | CD费伦斯 | 费尔盖拉斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 223 | 荷甲 | 海伦芬 | 特温特 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 224 | 荷乙 | 马斯特里赫特 | 乌德勒支青年队 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 225 | 英联杯 | 曼斯菲尔德 | 谢菲尔德联 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 226 | 奥甲 | 里德 | 维也纳快速 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 227 | 奥甲 | 沃尔夫斯贝格 | 萨尔茨堡红牛 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 228 | 苏超 | 格拉斯哥流浪者 | 希伯尼安 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 229 | 捷克甲 | 亚布洛内茨 | 斯洛瓦茨科 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 230 | 捷克甲 | 赫拉德茨克拉洛韦 | 俄斯特拉发 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 231 | 挪超 | 汉坎 | 奥勒松 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 232 | 芬超 | 伊尔维斯 | 玛丽港 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 233 | 挪甲 | 海于格松 | 赖于福斯 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 234 | 挪甲 | 桑内斯乌尔夫 | 赫德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 235 | 挪甲 | 松达尔 | 布莱尼 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 236 | 挪甲 | 斯托曼 | 兰黑姆 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 237 | 挪甲 | 斯托姆加斯特 | 埃格尔松 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 238 | 挪甲 | 奥桑内 | 孔斯温厄尔 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 239 | 罗甲 | 佩特罗鲁 | 加拉茨钢铁 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 240 | 波兰甲 | 波兹南莱赫 | 格利维采皮亚斯特 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 241 | 丹超 | 霍森斯 | 布隆德比 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 242 | 芬超 | AC奥卢 | 赫尔辛基 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 243 | 爱超 | 谢尔伯恩 | 圣帕特里克竞技 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 244 | 比甲 | 安德莱赫特 | 拉路维尔 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 245 | 智利甲 | 康塞普西翁 | 康塞普西翁大学 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 246 | 葡超 | 波尔图 | 阿维卡 | -2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 247 | 奥甲 | 奥地利维也纳 | LASK林茨 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 248 | 挪超 | 克里斯蒂安松 | 莫尔德 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 249 | 捷克甲 | 布尔诺阿特斯 | 奥洛穆茨 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  |  |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 250 | 冰岛超 | IA阿克拉内斯 | 托尔 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 251 | 冰岛超 | KA阿克雷里 | FH哈夫纳夫约杜尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 252 | 冰岛超 | 斯塔尔南 | 凯夫拉维克 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 253 | 阿职联 | 圣洛伦索 | 飓风 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 254 | 波兰甲 | 乔治罗尼亚 | 罗兹维德祖 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 255 | 罗甲 | CS克拉约瓦大学 | 阿尔杰什 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 256 | 巴西甲 | 巴伊亚 | 瓦斯科达伽马 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 257 | 巴西甲 | 帕尔梅拉斯 | 巴西国际 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 258 | 智利甲 | 奥伊金斯 | 利马切 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 259 | 巴西乙 | 新奥里藏蒂诺 | 尤文图德 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 260 | 巴西乙 | 累西腓航海 | 戈亚尼亚竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 261 | 葡超 | 吉尔维森特 | 里奥阿维 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 262 | 葡超 | 摩雷伦斯 | 布拉加 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 263 | 葡超 | 本菲卡 | 维塞乌学院 | -2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 264 | 冰岛超 | 贝雷达比历克 | 瓦路尔 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 265 | 阿职联 | 防卫与正义 | 纽维尔老男孩 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 266 | 阿职联 | 拉普拉塔体操 | 巴拉卡斯中央 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 267 | 巴西甲 | 布拉干蒂诺红牛 | 科林蒂安 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 268 | 巴西甲 | 桑托斯 | 巴拉纳竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 269 | 智利甲 | 拉卡莱拉联合 | 科洛科洛 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 270 | 巴西甲 | 弗拉门戈 | 维多利亚 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 271 | 阿职联 | 阿根廷青年人 | 竞技俱乐部 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 272 | 智利甲 | 智利大学 | 巴勒斯坦人 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 273 | 罗甲 | 博托沙尼 | 胡内多阿拉乌鸦 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 274 | 丹超 | 锡尔克堡 | 欧登塞 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 275 | 瑞典超 | 天狼星 | 布鲁马波卡纳 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 276 | 瑞典超 | 韦斯特罗斯 | 佐加顿斯 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 277 | 葡甲 | 本菲卡B队 | 雷克索斯 | 0.000 |  |  | 1+0 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.687 |  |  |  |  | intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 278 | 葡甲 | 洛罗萨卢西塔尼亚 | 波尔图B队 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 279 | 挪甲 | 莫斯 | 奥德 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 280 | 瑞典甲 | 诺尔比 | 厄勒布鲁 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 281 | 荷乙 | PSV埃因霍温青年 | 福伦丹 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 282 | 荷乙 | 阿尔克马尔青年队 | FC埃因霍温 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 283 | 罗甲 | 塞普西 | 布加勒斯特星 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 284 | 英联杯 | 普利茅斯 | 埃克塞特城 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 285 | 葡超 | 圣塔克拉拉 | 葡萄牙国民 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 286 | 冰岛超 | 弗拉姆 | KR雷克雅未克 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 287 | 阿职联 | 班菲尔德 | 贝尔格拉诺 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 288 | 巴西乙 | 戈亚斯 | 隆德里纳 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 289 | 智利甲 | 奥达克斯意大利人 | 纽布莱恩斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 290 | 阿职联 | 圣菲联合 | 科尔多瓦中央 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |

## 26083_016 专项

{
  "issue": "26083",
  "match_idx": 16,
  "match_id": "26083_016",
  "league": "丹超",
  "home": "桑德捷斯基",
  "away": "维堡",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "胜(桑德捷斯基)",
  "active_primary": "3",
  "active_selection_codes": "3",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 1,
  "active_profit_proxy": "",
  "shadow_judgment": "负(维堡)为押，保胜(桑德捷斯基)",
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
  "q_top": "3",
  "p_3": 0.27180271065541844,
  "p_1": 0.27179187445424613,
  "p_0": 0.4564054148903354,
  "sp_3": 17.78,
  "sp_1": 2.96,
  "sp_0": 1.64,
  "q_3": 4.83265219545334,
  "q_1": 0.8045039483845685,
  "q_0": 0.7485048804201501,
  "max_q": 4.8327,
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
  "shadow_chain_json": "[\"概率主线：最高让球后概率 负(维堡) 45.6%。\", \"EV/q主线：最高q 胜(桑德捷斯基) q=4.83，概率 27.2%，SP 17.78。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：胜(桑德捷斯基) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"负(维堡)\", \"score\": \"45.6%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 27.2% / 平 27.2% / 负 45.6%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"胜(桑德捷斯基)\", \"score\": \"q 4.83\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 4.83 / 平 0.80 / 负 0.75\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"无明确方向\", \"score\": \"置信 0.00\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": []}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"常规\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": []}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"有缺口\", \"score\": \"5 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"intelligence_missing\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"负(维堡)为押，保胜(桑德捷斯基)\", \"score\": \"置信 0.41\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 负(维堡) 45.6%。\", \"EV/q主线：最高q 胜(桑德捷斯基) q=4.83，概率 27.2%，SP 17.78。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26083_20260807_active_v3.3.3/structured_shadow_26083.csv`
