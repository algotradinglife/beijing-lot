# 结构化决策链 26071 Shadow v3.2 回测

生成时间：2026-07-03 06:13:53Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
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
| form_recent | 近期胜平负结构和双方走势 | 只作轻权重辅助 |
| competition_context | 联赛/杯赛/淘汰赛等赛制上下文 | 只作风险提示或小权重 |
| llm_intel_protection | 单独解读情报文本并考虑北单让球，判断是否增加保护 | 只能增加保护，不能改主押；当前历史回测无真实 LLM advice 时使用 `script_proxy` |
| data_quality/risk | 缺失、偏移、q高但胜率低、情报与让球冲突 | 关键输入缺失或风险过高时可停 |

## Aggregator

1. `max_q < 1.00` 或关键概率/SP 缺失时停。
2. 主押由让球后概率、`handicap_fit` 和近期形态加权得到；raw 情报必须先过 `handicap_fit`。
3. 当 q/EV 最高方向与主押不同且 q 过线时，将 q 方向加入保护，不反客为主。
4. `llm_intel_protection` 可在情报与让球结构提示死腿风险时追加保护，但必须通过强度或基础概率/q护栏。
5. line-gap 和 drift 只进入诊断/风险标签，不作为 hard gate。

## 指标

| 方案 | 下注场 | 主押命中 | 押+保命中 | 成本 | profit proxy | ROI proxy | 票型 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| active_v3 | 15 | 53.3% | 80.0% | 25 | 8.060 | 32.2% | {'double': 10, 'single': 6} |
| shadow_v3.2 | 15 | 53.3% | 86.7% | 27 | 9.730 | 36.0% | {'double': 9, 'single': 5, 'full': 2} |

## v3 vs shadow_v3.2 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.2 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 9 | 世界杯 | 美国 | 波黑 | -1.000 | 2:0 | 胜(美国) | 3+0 | 1 | 3+0+1 | 1 | -1.000 | 0 | 0 | line_gap_watch;q_top_odds_up |
| 14 | 世界杯 | 葡萄牙 | 克罗地亚 | -1.000 | 2:1 | 平 | 3+0 | 0 | 0+3+1 | 1 | 2.670 | 0 | 3 | q_high_but_probability_low;q_probability_disagree |
| 16 | 世界杯 | 瑞士 | 阿尔及利亚 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |

## 26071 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.2 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 芬兰杯 | 瓦萨 | 国际图尔库 | 0.000 | 2:3 | 负(国际图尔库) | 1+0 | 1 | 1+0 |  | 0.000 | 1 | 0 | 0 | 1.124 | draw | 1 | q_top_odds_up |
| 2 | 世界杯 | 科特迪瓦 | 挪威 | 0.000 | 1:2 | 负(挪威) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 1.462 | away | 0 | q_high_but_probability_low;q_probability_disagree |
| 3 | 世界杯 | 法国 | 瑞典 | -2.000 | 3:0 | 胜(法国) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 0 | 0 | 1.526 | home | 3 | line_gap_watch;q_top_odds_up |
| 4 | 巴西乙 | 博塔弗戈SP | 巴西雷加塔斯 | 0.000 | 0:1 | 负(巴西雷加塔斯) | 0 | 1 | 0 |  | 0.000 | 1 | 3 | 0 | 1.077 | away | 0 | q_probability_disagree |
| 5 | 世界杯 | 墨西哥 | 厄瓜多尔 | 0.000 | 2:0 | 胜(墨西哥) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.329 | home | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |
| 6 | 世界杯 | 英格兰 | 刚果(金) | -2.000 | 2:1 | 负(刚果(金)) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 0 | 0 | 1.252 | home | 3 | line_gap_watch;q_top_odds_up |
| 7 | 芬兰杯 | 赫尔辛基 | 伊尔维斯 | -1.000 | 2:1 | 平 | 0+1 | 1 | 0+1 | 1 | 0.635 | 1 | 0 | 0 | 1.095 | home | 1 | raw_strength_handicap_remapped;raw_strength_not_handicap_result |
| 8 | 世界杯 | 比利时 | 塞内加尔 | 0.000 | 2:2 | 平 | 3 | 0 | 3 |  | 0.000 | 0 | 3 | 3 | 1.138 | home | 3 | line_gap_watch |
| 9 | 世界杯 | 美国 | 波黑 | -1.000 | 2:0 | 胜(美国) | 3+0 | 1 | 3+0+1 |  | 0.000 | 1 | 0 | 0 | 1.887 | home | 3 | line_gap_watch;q_top_odds_up |
| 10 | 挪甲 | 利恩 | 奥桑内 | 0.000 | 6:2 | 胜(利恩) | 3+1 | 1 | 3+1 |  | 0.000 | 1 | 3 | 1 | 1.127 |  |  | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 11 | 冰岛超 | 托尔 | KR雷克雅未克 | 2.000 | 3:3 | 胜(托尔) | 3 | 1 | 3 |  | 0.000 | 1 | 3 | 3 | 1.268 |  |  | q_top_odds_up;raw_strength_missing |
| 12 | 世界杯 | 西班牙 | 奥地利 | -2.000 | 3:0 | 胜(西班牙) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 1.247 | home |  | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_not_handicap_result |
| 13 | 冰岛超 | 维京古尔 | KA阿克雷里 | -2.000 | 3:2 | 负(KA阿克雷里) | 0 | 1 | 0 |  | 0.000 | 1 | 0 | 0 | 1.900 |  |  | q_top_odds_up;raw_strength_missing |
| 14 | 世界杯 | 葡萄牙 | 克罗地亚 | -1.000 | 2:1 | 平 | 3+0 | 0 | 0+3+1 | 1 | 0.643 | 1 | 0 | 3 | 1.223 | away | 0 | q_high_but_probability_low;q_probability_disagree |
| 15 | 巴西乙 | 福塔莱萨 | 庞特普雷塔 | -2.000 | 2:0 | 平 | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.294 |  |  | line_gap_watch;raw_strength_missing |
| 16 | 世界杯 | 瑞士 | 阿尔及利亚 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.875 | home | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |

## 26071_016 专项

{
  "issue": "26071",
  "match_idx": 16,
  "match_id": "26071_016",
  "league": "世界杯",
  "home": "瑞士",
  "away": "阿尔及利亚",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3",
  "active_recommendation": "负(阿尔及利亚)",
  "active_primary": "0",
  "active_selection_codes": "0",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 1,
  "active_profit_proxy": "",
  "shadow_judgment": "胜(瑞士)为押，保负(阿尔及利亚)",
  "shadow_primary": "3",
  "shadow_selection_codes": "3+0",
  "shadow_primary_hit": "",
  "shadow_coverage_hit": "",
  "shadow_stake": 2,
  "shadow_profit_proxy": "",
  "selection_type": "double",
  "prob_top": "3",
  "q_top": "0",
  "p_3": 0.4821153953276072,
  "p_1": 0.2766075536014063,
  "p_0": 0.2412770510709865,
  "sp_3": 1.77,
  "sp_1": 3.24,
  "sp_0": 7.77,
  "q_3": 0.8533442497298648,
  "q_1": 0.8962084736685565,
  "q_0": 1.874722686821565,
  "max_q": 1.8747,
  "raw_strength_side": "home",
  "handicap_fit_code": "3",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "line_gap_watch;q_high_but_probability_low;q_probability_disagree"
}

结论：`llm_chain_bet_protect_stop_v3.2_shadow` 在 v3.1 的基础上增加 `llm_intel_protection` overlay：情报文本先单独按让球结构解读，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.1 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26071_20260703/structured_shadow_26071.csv`
