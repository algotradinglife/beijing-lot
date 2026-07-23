# 结构化决策链 26075 active_v3.3.3 回测

生成时间：2026-07-14 03:33:20Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`25/25`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'full': 3, 'double': 19, 'single': 3} |
| active_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'full': 3, 'double': 20, 'single': 2} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 | 挪超 | 瓦勒伦加 | 奥勒松 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 0 | line_gap_missing;raw_strength_missing |

## 26075 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 苏联赛杯 | 福尔柯克 | 艾尔联 | -1.000 |  |  | 0+3+1 |  | 0+3+1 | 1 | 0.635 |  | 3 | 3 | 1.196 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 2 | 苏联赛杯 | 基尔马诺克 | 拉茨流浪者 | -1.000 |  |  | 0+1 |  | 0+1 | 1 | 0.633 |  | 0 | 0 | 1.401 |  |  | 0 | 0 | q_top_odds_up;raw_strength_missing |
| 3 | 世界杯 | 法国 | 西班牙 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.173 |  |  | 3 | 3 | q_probability_disagree;raw_strength_missing |
| 4 | 欧冠资格 | 沙姆洛克流浪者 | 弗洛里亚纳 | -2.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.743 |  |  | 0 | 0 | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 5 | 韩足总杯 | 全南天龙 | 忠南牙山FC | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.316 |  |  | 0 | 0 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 6 | 芬甲 | 吉波 | MP米凯利 | -1.000 |  |  | 3+0 |  | 3+0 | 1 | 0.730 |  | 0 | 0 | 1.581 |  |  | 3 | 1 | probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 7 | 世界杯 | 英格兰 | 阿根廷 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.503 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 8 | 欧冠资格 | 苏杰斯卡 | 阿拉木图凯拉特 | 1.000 |  |  | 0+3 |  | 0+3 | 1 | 0.751 |  | 3 | 3 | 1.381 |  |  | 0 | 1 | probability_runner_up_protection;q_top_odds_up;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 9 | 欧协资格 | 国际图尔库 | FK萨拉热窝 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.668 |  |  | 3 | 3 | line_gap_missing;raw_strength_missing |
| 10 | 欧协资格 | 圣约瑟夫 | 波希米亚人 | 1.000 |  |  | 0+3 |  | 0+3 | 1 | 0.753 |  | 0 | 0 | 1.410 |  |  | 0 | 1 | line_gap_missing;probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 11 | 波超杯 | 波兹南莱赫 | 扎布热矿工 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.451 |  |  | 3 | 3 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 挪超 | 瓦勒伦加 | 奥勒松 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 0 | 2.890 |  |  | 0 | 0 | line_gap_missing;raw_strength_missing |
| 13 | 欧罗巴资格 | 德里城 | 索非亚中央陆军 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 11.975 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 14 | 欧罗巴资格 | 维斯特里 | 卡拉巴赫 | 2.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.119 |  |  | 0 |  | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 阿根廷杯 | 竞技俱乐部 | 防卫与正义 | -1.000 |  |  | 0+1 |  | 0+1 | 1 | 0.717 |  | 0 | 1 | 33.621 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 16 | 巴西甲 | 博塔弗戈 | 桑托斯 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.413 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 巴西甲 | 维多利亚 | 瓦斯科达伽马 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 5.918 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 18 | 巴西乙 | 巴西雷加塔斯 | 累西腓航海 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 5.181 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 19 | 美职 | CF蒙特利尔 | 多伦多FC | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 17.086 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 20 | 美职 | 芝加哥火焰 | 温哥华白浪 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.607 |  |  | 0 | 0 | raw_strength_missing |
| 21 | 美职 | 圣路易斯城 | 堪萨斯城体育 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.768 |  | 3 | 0 | 2.673 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 22 | 阿根廷杯 | 萨米恩托 | 博卡青年 | 1.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 13.067 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 23 | 墨超 | 内卡萨 | 亚特兰特 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 107.059 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 24 | 美职 | 西雅图海湾人 | 波特兰伐木者 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.744 |  | 3 | 1 | 37.021 |  |  | 3 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 25 | 墨超 | 蒂华纳 | 老虎大学 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 16.579 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 26075_016 专项

{
  "issue": "26075",
  "match_idx": 16,
  "match_id": "26075_016",
  "league": "巴西甲",
  "home": "博塔弗戈",
  "away": "桑托斯",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "胜(博塔弗戈)为押，保平",
  "active_primary": "3",
  "active_selection_codes": "3+1",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 2,
  "active_profit_proxy": "",
  "shadow_judgment": "胜(博塔弗戈)为押，保平",
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
  "phase2_probability_primary_probability": 0.478273,
  "phase2_probability_primary_margin": 0.191012,
  "phase2_probability_primary_hit": "",
  "phase2_probability_execution_enabled": 0,
  "phase2_handicap_gated_experiment_id": "phase2_handicap_gated_probability_first",
  "phase2_handicap_gated_experiment_version": "v0.2.0000",
  "phase2_handicap_gated_primary": "3",
  "phase2_handicap_gated_selection_codes": "3+1",
  "phase2_handicap_gated_changed": 0,
  "phase2_handicap_gated_grade": "A",
  "phase2_handicap_gated_primary_probability": 0.478273,
  "phase2_handicap_gated_primary_margin": 0.191012,
  "phase2_handicap_gated_gate_applied": 1,
  "phase2_handicap_gated_primary_hit": "",
  "phase2_handicap_gated_execution_enabled": 0,
  "phase2_league_soft_experiment_id": "phase2_seasonal_league_soft_tiebreak",
  "phase2_league_soft_experiment_version": "v0.1.0000",
  "phase2_league_soft_primary": "3",
  "phase2_league_soft_selection_codes": "3+1",
  "phase2_league_soft_changed": 0,
  "phase2_league_soft_grade": "A",
  "phase2_league_soft_primary_probability": 0.478273,
  "phase2_league_soft_primary_margin": 0.191012,
  "phase2_league_soft_gate_applied": 0,
  "phase2_league_soft_effective_n": 0,
  "phase2_league_soft_adjustment_json": "{\"3\": 0.0, \"1\": 0.0, \"0\": 0.0}",
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
  "p_3": 0.4782728524175944,
  "p_1": 0.2872609910543071,
  "p_0": 0.2344661565280986,
  "sp_3": 1.32,
  "sp_1": 8.4,
  "sp_0": 7.82,
  "sp_complete": 1,
  "sp_missing_codes": "",
  "sp_source": "500_preclose_sp_complete",
  "q_3": 0.6313201651912246,
  "q_1": 2.4129923248561798,
  "q_0": 1.8335253440497312,
  "max_q": 2.413,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "0",
  "form_recent_confidence": 0.438,
  "form_recent_mapped_code": "0",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(博塔弗戈) 47.8%。\", \"EV/q主线：最高q 平 q=2.41，概率 28.7%，SP 8.40。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：平 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(博塔弗戈)\", \"score\": \"47.8%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 47.8% / 平 28.7% / 负 23.4%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"平\", \"score\": \"q 2.41\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.63 / 平 2.41 / 负 1.83\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"负(桑托斯)\", \"score\": \"置信 0.44\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": [\"主队近10场 5胜2平3负，进失18/11，半场平0场，近5走势负-胜-平-胜-胜\", \"客队近10场 5胜3平2负，进失19/11，半场平2场，近5走势胜-胜-胜-负-平\"]}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"league_round\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": [\"赛制/阶段：巴甲\"]}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"可用\", \"score\": \"4 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"analysis/intelligence/probability/sp inputs available\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(博塔弗戈)为押，保平\", \"score\": \"置信 0.44\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(博塔弗戈) 47.8%。\", \"EV/q主线：最高q 平 q=2.41，概率 28.7%，SP 8.40。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26075_20260714_active_v3.3.3/structured_shadow_26075.csv`
