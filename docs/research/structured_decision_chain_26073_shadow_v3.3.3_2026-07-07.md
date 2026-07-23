# 结构化决策链 26073 shadow_v3.3.3 回测

生成时间：2026-07-07 13:36:12Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`10/10`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'single': 7, 'double': 3} |
| shadow_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'full': 2, 'double': 4, 'single': 4} |

## v3 vs shadow_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 世界杯 | 阿根廷 | 埃及 | -1.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 0 | intelligence_missing;line_gap_watch;probability_runner_up_protection;raw_strength_missing |
| 2 | 欧冠资格 | 弗洛里亚纳 | 沙姆洛克流浪者 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 3 | 世界杯 | 瑞士 | 哥伦比亚 | 0.000 |  |  | 3+0 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 4 | 巴西乙 | 米纳斯吉拉斯竞技 | 铁路工人 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 7 | 欧罗巴资格 | 卡拉巴赫 | 维斯特里 | -3.000 |  |  | 0+1 |  | 0 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 10 | 世界杯 | 法国 | 摩洛哥 | -1.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |

## 26073 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 世界杯 | 阿根廷 | 埃及 | -1.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 0 | 1.887 |  |  |  |  | intelligence_missing;line_gap_watch;probability_runner_up_protection;raw_strength_missing |
| 2 | 欧冠资格 | 弗洛里亚纳 | 沙姆洛克流浪者 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.321 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 3 | 世界杯 | 瑞士 | 哥伦比亚 | 0.000 |  |  | 3+0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.139 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 4 | 巴西乙 | 米纳斯吉拉斯竞技 | 铁路工人 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.142 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 5 | 欧冠资格 | 阿拉木图凯拉特 | 苏杰斯卡 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.159 |  |  |  |  | intelligence_missing;line_gap_large;raw_strength_missing |
| 6 | 巴西乙 | 庞特普雷塔 | 克里西乌马 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.316 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 7 | 欧罗巴资格 | 卡拉巴赫 | 维斯特里 | -3.000 |  |  | 0+1 |  | 0 |  | 0.000 |  | 0 | 0 | 1.008 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 8 | 欧协资格 | 波希米亚人 | 圣约瑟夫 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.178 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 9 | 欧罗巴资格 | 索非亚中央陆军 | 德里城 | -2.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.367 |  |  |  |  | intelligence_missing;line_gap_watch;q_probability_disagree;raw_strength_missing |
| 10 | 世界杯 | 法国 | 摩洛哥 | -1.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 0 | 1.236 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |

## 26073_016 专项

未找到 #16。

结论：`llm_chain_bet_protect_stop_v3.3.3_shadow` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26073_20260707_shadow_v3.3.3/structured_shadow_26073.csv`
