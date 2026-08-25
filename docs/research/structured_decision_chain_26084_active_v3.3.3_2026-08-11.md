# 结构化决策链 26084 active_v3.3.3 回测

生成时间：2026-08-11 09:15:12Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`47/47`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 5, 'single': 42} |
| active_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'full': 4, 'single': 32, 'double': 11} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 亚冠精英资格 | 江原FC | 大阪钢巴 | 0.000 |  |  | 1+3 |  | 0+3+1 |  |  | 0 | 1 | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 4 | 欧冠资格 | 奈梅亨 | 奥林匹亚科斯 | 0.000 |  |  | 0+1 |  | 0+3 |  |  | 0 | 0 | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 7 | 欧冠资格 | 里昂 | 布拉格斯巴达 | -1.000 |  |  | 0 |  | 3+0+1 |  |  | 3 | 0 | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 8 | 解放者杯 | 弗鲁米嫩塞 | 里瓦达维亚独立 | -1.000 |  |  | 0+3 |  | 0+1 |  |  | 0 | 0 | intelligence_missing;raw_strength_missing |
| 9 | 南俱杯 | 博卡青年 | 雷科莱塔 | -2.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 10 | 巴西乙 | 阿瓦伊 | 巴西雷加塔斯 | 0.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 解放者杯 | 拉普拉塔大学生 | 天主教大学 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 13 | 南俱杯 | 玻利瓦尔 | 圣保罗 | -1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 14 | 欧超杯 | 巴黎圣日耳曼 | 阿斯顿维拉 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 18 | 南俱杯 | 蒂格雷 | 蒙得维的亚城力矩 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 43 | 解放者杯 | 米拉索尔 | 基多体育大学 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 44 | 南俱杯 | 瓦斯科达伽马 | 亚松森奥林匹亚 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 45 | 南俱杯 | 桑托斯 | 马卡拉 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |

## 26084 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 亚冠精英资格 | 江原FC | 大阪钢巴 | 0.000 |  |  | 1+3 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 1.229 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 2 | 欧冠资格 | 博德闪耀 | 圣吉罗斯联合 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.294 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 3 | 瑞典甲 | 赫尔辛堡 | 韦纳穆 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.246 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 4 | 欧冠资格 | 奈梅亨 | 奥林匹亚科斯 | 0.000 |  |  | 0+1 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.371 |  |  |  |  | intelligence_missing;probability_runner_up_protection;raw_strength_missing |
| 5 | 欧冠资格 | 布拉迪斯拉发 | 米亚尔比 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.182 |  |  |  |  | intelligence_missing;line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 6 | 欧冠资格 | 格拉茨风暴 | 费内巴切 | 0.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.268 |  |  |  |  | intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 7 | 欧冠资格 | 里昂 | 布拉格斯巴达 | -1.000 |  |  | 0 |  | 3+0+1 |  | 0.000 |  | 3 | 0 | 3.425 |  |  |  |  | intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 8 | 解放者杯 | 弗鲁米嫩塞 | 里瓦达维亚独立 | -1.000 |  |  | 0+3 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.296 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 9 | 南俱杯 | 博卡青年 | 雷科莱塔 | -2.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.391 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 10 | 巴西乙 | 阿瓦伊 | 巴西雷加塔斯 | 0.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.898 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 11 | 阿职联 | 塔勒瑞斯 | 拉努斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 2.152 |  |  |  |  | intelligence_missing;raw_strength_missing |
| 12 | 解放者杯 | 拉普拉塔大学生 | 天主教大学 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 3.829 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 13 | 南俱杯 | 玻利瓦尔 | 圣保罗 | -1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 2.171 |  |  |  |  | intelligence_missing;q_probability_disagree;raw_strength_missing |
| 14 | 欧超杯 | 巴黎圣日耳曼 | 阿斯顿维拉 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 3.129 |  |  |  |  | intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 15 | 解放者杯 | 帕尔梅拉斯 | 波特诺山丘 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 16 | 解放者杯 | 普拉腾斯 | 科金博联 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 17 | 南俱杯 | 布拉干蒂诺红牛 | 米内罗竞技 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 18 | 南俱杯 | 蒂格雷 | 蒙得维的亚城力矩 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 19 | 阿根廷杯 | 图库曼竞技 | 阿根廷独立 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 20 | 欧协资格 | 托博尔 | 贝尔格莱德游击 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 21 | 欧协资格 | 伊尔维斯 | 里耶卡 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 22 | 欧协资格 | 里加足球学校 | 亚布洛内茨 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 23 | 欧罗巴资格 | 奥莫尼亚 | 林肯红色小鬼 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 24 | 欧罗巴资格 | CS克拉约瓦大学 | 库普斯 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 25 | 欧罗巴资格 | 贝西克塔斯 | 赫拉德茨克拉洛韦 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 26 | 欧罗巴资格 | 帕福斯 | FC萨尔茨堡 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 27 | 欧罗巴资格 | 扎布热矿工 | 费伦茨瓦罗斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 28 | 欧协资格 | 明斯克迪纳摩 | 布拉加 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 29 | 欧协资格 | 北西兰 | 瓦路尔 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_large;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 30 | 欧协资格 | 特罗姆瑟 | 克卢日 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 31 | 欧协资格 | 哈马比 | 琴斯托霍瓦 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 32 | 欧协资格 | 中日德兰 | 波希米亚人 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 33 | 欧罗巴资格 | 克拉克斯维克 | 波兹南莱赫 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 34 | 欧罗巴资格 | 维京古尔 | 图恩 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 35 | 欧协资格 | 瓦杜兹 | 国际图尔库 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 36 | 欧协资格 | 圣加仑 | 谢里夫 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 37 | 欧罗巴资格 | 格拉斯哥流浪者 | 乔治罗尼亚 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 38 | 欧罗巴资格 | 安德莱赫特 | PAOK塞萨洛尼基 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 39 | 欧协资格 | 马瑟韦尔 | 赫尔辛基 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 40 | 欧协资格 | 根特 | 哥德堡 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 41 | 欧罗巴资格 | 哈茨 | 本菲卡 | 1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 42 | 欧协资格 | 谢尔伯恩 | 阿贾克斯 | 2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 43 | 解放者杯 | 米拉索尔 | 基多体育大学 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 44 | 南俱杯 | 瓦斯科达伽马 | 亚松森奥林匹亚 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 45 | 南俱杯 | 桑托斯 | 马卡拉 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 46 | 解放者杯 | 罗萨里奥中央 | 科林蒂安 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 47 | 南俱杯 | 西恩夏诺 | 博塔弗戈 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |

## 26084_016 专项

{
  "issue": "26084",
  "match_idx": 16,
  "match_id": "26084_016",
  "league": "解放者杯",
  "home": "普拉腾斯",
  "away": "科金博联",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "胜(普拉腾斯)",
  "active_primary": "3",
  "active_selection_codes": "3",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 1,
  "active_profit_proxy": "",
  "shadow_judgment": "胜(普拉腾斯)",
  "shadow_primary": "3",
  "shadow_selection_codes": "3",
  "shadow_stop_flag": 1,
  "shadow_primary_hit": "",
  "shadow_coverage_hit": "",
  "shadow_stake": 1,
  "shadow_profit_proxy": "",
  "shadow_arm": "active_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3",
  "selection_type": "single",
  "prob_top": "3",
  "q_top": "",
  "p_3": 0.4544327046299027,
  "p_1": 0.2847653533096833,
  "p_0": 0.260801942060414,
  "sp_3": null,
  "sp_1": null,
  "sp_0": null,
  "q_3": null,
  "q_1": null,
  "q_0": null,
  "max_q": null,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "",
  "form_recent_confidence": "",
  "form_recent_mapped_code": "",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "advisory_stop;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(普拉腾斯) 45.4%。\", \"EV/q主线：最高q 停 q=缺，概率 缺，SP 缺。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"停牌：关键概率或SP输入缺失；max_q=缺 低于 1.00；风险标签过多且q缓冲不足\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(普拉腾斯)\", \"score\": \"45.4%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 45.4% / 平 28.5% / 负 26.1%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"缺\", \"score\": \"q 缺\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 缺 / 平 缺 / 负 缺\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"无明确方向\", \"score\": \"置信 0.00\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": []}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"cup\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": []}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"有缺口\", \"score\": \"6 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"intelligence_missing\", \"q_unavailable\", \"prob_or_sp_missing\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(普拉腾斯)\", \"score\": \"置信 0.38\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(普拉腾斯) 45.4%。\", \"EV/q主线：最高q 停 q=缺，概率 缺，SP 缺。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26084_20260811_active_v3.3.3/structured_shadow_26084.csv`
