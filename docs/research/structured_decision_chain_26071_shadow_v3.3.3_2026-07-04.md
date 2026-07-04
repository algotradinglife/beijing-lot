# 结构化决策链 26071 shadow_v3.3.3 回测

生成时间：2026-07-04 04:06:25Z

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
| active_v3 | 16 | 50.0% | 75.0% | 26 | 7.060 | 27.2% | {'double': 10, 'single': 6} |
| shadow_v3.3.3 | 16 | 56.2% | 87.5% | 30 | 8.790 | 29.3% | {'double': 10, 'single': 4, 'full': 2} |

## v3 vs shadow_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 巴西乙 | 博塔弗戈SP | 巴西雷加塔斯 | 0.000 | 0:1 | 负(巴西雷加塔斯) | 0 | 1 | 0+3 | 1 | -1.000 | 3 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 9 | 世界杯 | 美国 | 波黑 | -1.000 | 2:0 | 胜(美国) | 3+0 | 1 | 3+0+1 | 1 | -1.000 | 0 | 0 | line_gap_watch;probability_runner_up_protection;q_top_odds_up |
| 14 | 世界杯 | 葡萄牙 | 克罗地亚 | -1.000 | 2:1 | 平 | 3+0 | 0 | 0+3+1 | 1 | 2.670 | 0 | 3 | q_high_but_probability_low;q_probability_disagree |
| 16 | 世界杯 | 瑞士 | 阿尔及利亚 | 0.000 | 2:0 | 胜(瑞士) | 0 | 0 | 3+0 | 1 | 1.060 | 3 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |

## 26071 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | shadow_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 芬兰杯 | 瓦萨 | 国际图尔库 | 0.000 | 2:3 | 负(国际图尔库) | 1+0 | 1 | 1+0 | 0 | 0.743 | 1 | 0 | 0 | 1.124 | draw | 1 | 0 | 0 | probability_runner_up_protection;q_top_odds_up;recent_form_intel_protection |
| 2 | 世界杯 | 科特迪瓦 | 挪威 | 0.000 | 1:2 | 负(挪威) | 0+3 | 1 | 0+3 | 1 | 0.684 | 1 | 0 | 3 | 1.462 | away | 0 | 3 | 3 | q_high_but_probability_low;q_probability_disagree;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 3 | 世界杯 | 法国 | 瑞典 | -2.000 | 3:0 | 胜(法国) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 0 | 0 | 1.526 | home | 3 | 3 |  | line_gap_watch;probability_runner_up_protection;q_top_odds_up |
| 4 | 巴西乙 | 博塔弗戈SP | 巴西雷加塔斯 | 0.000 | 0:1 | 负(巴西雷加塔斯) | 0 | 1 | 0+3 |  | 0.000 | 1 | 3 | 0 | 1.077 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 5 | 世界杯 | 墨西哥 | 厄瓜多尔 | 0.000 | 2:0 | 胜(墨西哥) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.329 | home | 3 | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |
| 6 | 世界杯 | 英格兰 | 刚果(金) | -2.000 | 2:1 | 负(刚果(金)) | 3+0 | 1 | 3+0 |  | 0.000 | 1 | 0 | 0 | 1.252 | home | 3 | 3 |  | line_gap_watch;probability_runner_up_protection;q_top_odds_up |
| 7 | 芬兰杯 | 赫尔辛基 | 伊尔维斯 | -1.000 | 2:1 | 平 | 0+1 | 1 | 0+1 | 1 | 0.676 | 1 | 0 | 0 | 1.095 | home | 1 | 3 | 1 | raw_strength_handicap_remapped;raw_strength_not_handicap_result;recent_form_intel_protection |
| 8 | 世界杯 | 比利时 | 塞内加尔 | 0.000 | 2:2 | 平 | 3 | 0 | 3 |  | 0.000 | 0 | 3 | 3 | 1.138 | home | 3 | 3 | 3 | line_gap_watch |
| 9 | 世界杯 | 美国 | 波黑 | -1.000 | 2:0 | 胜(美国) | 3+0 | 1 | 3+0+1 |  | 0.000 | 1 | 0 | 0 | 1.887 | home | 3 | 0 | 0 | line_gap_watch;probability_runner_up_protection;q_top_odds_up |
| 10 | 挪甲 | 利恩 | 奥桑内 | 0.000 | 6:2 | 胜(利恩) | 3+1 | 1 | 3+1 | 1 | 0.734 | 1 | 3 | 1 | 1.127 |  |  | 0 | 0 | line_gap_watch;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 11 | 冰岛超 | 托尔 | KR雷克雅未克 | 2.000 | 3:3 | 胜(托尔) | 3 | 1 | 3 |  | 0.000 | 1 | 3 | 3 | 1.268 |  |  | 0 |  | q_top_odds_up;raw_strength_missing |
| 12 | 世界杯 | 西班牙 | 奥地利 | -2.000 | 3:0 | 胜(西班牙) | 0+3 | 1 | 0+3 |  | 0.000 | 1 | 0 | 3 | 1.247 | home |  | 3 |  | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_not_handicap_result |
| 13 | 冰岛超 | 维京古尔 | KA阿克雷里 | -2.000 | 3:2 | 负(KA阿克雷里) | 0 | 1 | 0 |  | 0.000 | 1 | 0 | 0 | 1.900 |  |  | 3 |  | q_top_odds_up;raw_strength_missing |
| 14 | 世界杯 | 葡萄牙 | 克罗地亚 | -1.000 | 2:1 | 平 | 3+0 | 0 | 0+3+1 | 1 | 0.643 | 1 | 0 | 3 | 1.223 | away | 0 | 3 | 1 | q_high_but_probability_low;q_probability_disagree |
| 15 | 巴西乙 | 福塔莱萨 | 庞特普雷塔 | -2.000 | 2:0 | 平 | 0 | 0 | 0 |  | 0.000 | 0 | 0 | 0 | 1.294 |  |  | 3 |  | line_gap_watch;raw_strength_missing |
| 16 | 世界杯 | 瑞士 | 阿尔及利亚 | 0.000 | 2:0 | 胜(瑞士) | 0 | 0 | 3+0 |  | 0.000 | 1 | 3 | 0 | 1.875 | home | 3 | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree |

## 26071_016 专项

{
  "issue": "26071",
  "match_idx": 16,
  "match_id": "26071_016",
  "league": "世界杯",
  "home": "瑞士",
  "away": "阿尔及利亚",
  "handicap_line": 0.0,
  "score": "2:0",
  "actual_code": "3",
  "actual_label": "胜(瑞士)",
  "winning_sp": 2.06,
  "active_version": "llm_chain_bet_protect_stop_v3",
  "active_recommendation": "负(阿尔及利亚)",
  "active_primary": "0",
  "active_selection_codes": "0",
  "active_primary_hit": 0,
  "active_coverage_hit": 0,
  "active_stake": 1,
  "active_profit_proxy": -1.0,
  "shadow_judgment": "胜(瑞士)为押，保负(阿尔及利亚)",
  "shadow_primary": "3",
  "shadow_selection_codes": "3+0",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": 1,
  "shadow_coverage_hit": 1,
  "shadow_stake": 2,
  "shadow_profit_proxy": 0.06,
  "shadow_arm": "shadow_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3_shadow",
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
  "form_recent_code": "3",
  "form_recent_confidence": 0.385,
  "form_recent_mapped_code": "3",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "line_gap_watch;q_high_but_probability_low;q_probability_disagree",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(瑞士) 48.2%。\", \"EV/q主线：最高q 负(阿尔及利亚) q=1.87，概率 24.1%，SP 7.77。\", \"让球映射：北单让球为0，原始强弱倾向可直接映射到让球后方向。；资料观点：瑞士分组赛表现更胜阿尔及利亚一筹\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：负(阿尔及利亚) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(瑞士)\", \"score\": \"48.2%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 48.2% / 平 27.7% / 负 24.1%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"负(阿尔及利亚)\", \"score\": \"q 1.87\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.85 / 平 0.90 / 负 1.87\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"胜(瑞士)\", \"score\": \"强度 0.88\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": [\"北单让球为0，原始强弱倾向可直接映射到让球后方向。\", \"资料观点：瑞士分组赛表现更胜阿尔及利亚一筹\", \"资料观点：瑞士分组赛表现更胜阿尔及利亚一筹\"]}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"胜(瑞士)\", \"score\": \"置信 0.39\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": [\"主队近10场 4胜5平1负，进失20/11，半场平7场，近5走势胜-胜-平-平-胜\", \"客队近10场 5胜3平2负，进失20/10，半场平5场，近5走势平-胜-负-胜-胜\"]}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"主队\", \"score\": \"置信 0.88\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": [\"资料观点：瑞士分组赛表现更胜阿尔及利亚一筹\", \"资料观点：瑞士分组赛表现更胜阿尔及利亚一筹\", \"此番对阵整体实力并不算出众兼且防守端表现未如理想的阿尔及利亚\"]}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"knockout / cup\", \"score\": \"权重 0.25\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": [\"赛制/阶段：26世界杯1/16决赛，90分钟平局与保守倾向需要单独留意。\"]}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"可用\", \"score\": \"3 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"analysis/intelligence/probability/sp inputs available\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(瑞士)为押，保负(阿尔及利亚)\", \"score\": \"置信 0.63\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(瑞士) 48.2%。\", \"EV/q主线：最高q 负(阿尔及利亚) q=1.87，概率 24.1%，SP 7.77。\", \"让球映射：北单让球为0，原始强弱倾向可直接映射到让球后方向。；资料观点：瑞士分组赛表现更胜阿尔及利亚一筹\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3_shadow` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26071_20260704_shadow_v3.3.3/structured_shadow_26071.csv`
