# 结构化决策链 26082 active_v3.3.3 回测

生成时间：2026-08-04 14:49:24Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`42/42`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'single': 37, 'double': 5} |
| active_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'single': 23, 'double': 16, 'full': 3} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2 | 欧冠资格 | 奥林匹亚科斯 | 奈梅亨 | -1.000 |  |  | 0+3 |  | 3+0 |  |  | 3 | 0 | analysis_missing;intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 4 | 欧冠资格 | 布拉格斯巴达 | 里昂 | 0.000 |  |  | 3+1 |  | 0+3 |  |  | 0 | 3 | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 6 | 巴西杯 | 尤文图德 | 米内罗竞技 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | analysis_missing;intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 7 | 巴西杯 | 雷莫 | 桑托斯 | 0.000 |  |  | 3 |  | 0+3 |  |  | 0 | 3 | analysis_missing;intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 9 | 欧冠资格 | 费内巴切 | 格拉茨风暴 | -1.000 |  |  | 3+1 |  | 3+0+1 |  |  | 3 | 1 | analysis_missing;intelligence_missing;line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 10 | 冰岛超 | 凯夫拉维克 | KA阿克雷里 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | analysis_missing;intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 11 | 欧罗巴资格 | 费伦茨瓦罗斯 | 扎布热矿工 | -1.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 冰岛超 | FH哈夫纳夫约杜尔 | KR雷克雅未克 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 13 | 阿职联 | 博卡青年 | 拉普拉塔大学生 | 0.000 |  |  | 1+3 |  | 3+1 |  |  | 3 | 1 | analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 14 | 巴西杯 | 格雷米奥 | 米拉索尔 | 0.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | analysis_missing;intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 15 | 阿职联 | 蒂格雷 | 贝尔格拉诺 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 3 | analysis_missing;intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 16 | 巴西杯 | 弗鲁米嫩塞 | 瓦斯科达伽马 | 0.000 |  |  | 0 |  | 3+0 |  |  | 3 | 0 | analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 巴西杯 | 福塔莱萨 | 帕尔梅拉斯 | 1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 24 | 欧罗巴资格 | 林肯红色小鬼 | 奥莫尼亚 | 1.000 |  |  | 1 |  | 0+3+1 |  |  | 0 | 1 | analysis_missing;intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | 欧协资格 | 阿贾克斯 | 谢尔伯恩 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | analysis_missing;intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 35 | 欧协资格 | 瓦路尔 | 北西兰 | 1.000 |  |  | 3 |  | 0+3+1 |  |  | 0 | 3 | analysis_missing;intelligence_missing;line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 36 | 欧协资格 | 波希米亚人 | 中日德兰 | 2.000 |  |  | 3+1 |  | 3 |  |  | 3 | 3 | analysis_missing;intelligence_missing;line_gap_large;raw_strength_missing |
| 38 | 英联杯 | 布里斯托尔城 | 沃尔索尔 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 39 | 欧罗巴资格 | 本菲卡 | 哈茨 | -2.000 |  |  | 1 |  | 0+1 |  |  | 0 | 1 | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 欧协资格 | 贝尔格莱德游击 | 托博尔 | -1.000 |  |  | 1 |  | 3+1 |  |  | 3 | 1 | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 26082 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 欧冠资格 | 米亚尔比 | 布拉迪斯拉发 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.472 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_watch;raw_strength_missing |
| 2 | 欧冠资格 | 奥林匹亚科斯 | 奈梅亨 | -1.000 |  |  | 0+3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.170 |  |  |  |  | analysis_missing;intelligence_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 3 | 欧冠资格 | 圣吉罗斯联合 | 博德闪耀 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.750 |  |  |  |  | analysis_missing;intelligence_missing;raw_strength_missing |
| 4 | 欧冠资格 | 布拉格斯巴达 | 里昂 | 0.000 |  |  | 3+1 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.364 |  |  |  |  | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 5 | 冰岛超 | 托尔 | 贝雷达比历克 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.782 |  |  |  |  | analysis_missing;intelligence_missing;raw_strength_missing |
| 6 | 巴西杯 | 尤文图德 | 米内罗竞技 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.200 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 7 | 巴西杯 | 雷莫 | 桑托斯 | 0.000 |  |  | 3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.426 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 8 | 丹麦杯 | 霍布罗 | 文德斯尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  |  |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 9 | 欧冠资格 | 费内巴切 | 格拉茨风暴 | -1.000 |  |  | 3+1 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.089 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 10 | 冰岛超 | 凯夫拉维克 | KA阿克雷里 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.643 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 11 | 欧罗巴资格 | 费伦茨瓦罗斯 | 扎布热矿工 | -1.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 20.404 |  |  |  |  | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 冰岛超 | FH哈夫纳夫约杜尔 | KR雷克雅未克 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 23.142 |  |  |  |  | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 13 | 阿职联 | 博卡青年 | 拉普拉塔大学生 | 0.000 |  |  | 1+3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.871 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 14 | 巴西杯 | 格雷米奥 | 米拉索尔 | 0.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.495 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;q_probability_disagree;raw_strength_missing |
| 15 | 阿职联 | 蒂格雷 | 贝尔格拉诺 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 3 | 1.708 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 16 | 巴西杯 | 弗鲁米嫩塞 | 瓦斯科达伽马 | 0.000 |  |  | 0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 17.624 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 17 | 巴西杯 | 福塔莱萨 | 帕尔梅拉斯 | 1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 11.026 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 18 | 欧罗巴资格 | 库普斯 | CS克拉约瓦大学 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 19 | 欧协资格 | 国际图尔库 | 瓦杜兹 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 20 | 欧罗巴资格 | 乔治罗尼亚 | 格拉斯哥流浪者 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 21 | 欧协资格 | 赫尔辛基 | 马瑟韦尔 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 22 | 欧协资格 | 亚布洛内茨 | 里加足球学校 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 23 | 欧协资格 | 克卢日 | 特罗姆瑟 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 24 | 欧罗巴资格 | 林肯红色小鬼 | 奥莫尼亚 | 1.000 |  |  | 1 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 2.765 |  |  |  |  | analysis_missing;intelligence_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 25 | 欧罗巴资格 | 波兹南莱赫 | 克拉克斯维克 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 26 | 欧罗巴资格 | 赫拉德茨克拉洛韦 | 贝西克塔斯 | 1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 27 | 欧罗巴资格 | FC萨尔茨堡 | 帕福斯 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 28 | 欧协资格 | 谢里夫 | 圣加仑 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 29 | 欧协资格 | 琴斯托霍瓦 | 哈马比 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 30 | 欧协资格 | 哥德堡 | 根特 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 31 | 欧罗巴资格 | PAOK塞萨洛尼基 | 安德莱赫特 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_large;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 32 | 欧罗巴资格 | 图恩 | 维京古尔 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_watch;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 33 | 欧协资格 | 阿贾克斯 | 谢尔伯恩 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 4.647 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 34 | 欧协资格 | 布拉加 | 明斯克迪纳摩 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 35 | 欧协资格 | 瓦路尔 | 北西兰 | 1.000 |  |  | 3 |  | 0+3+1 |  | 0.000 |  | 0 | 3 | 30.423 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_watch;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 36 | 欧协资格 | 波希米亚人 | 中日德兰 | 2.000 |  |  | 3+1 |  | 3 |  | 0.000 |  | 3 | 3 | 3.395 |  |  |  |  | analysis_missing;intelligence_missing;line_gap_large;raw_strength_missing |
| 37 | 欧协资格 | 里耶卡 | 伊尔维斯 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 38 | 英联杯 | 布里斯托尔城 | 沃尔索尔 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 39 | 欧罗巴资格 | 本菲卡 | 哈茨 | -2.000 |  |  | 1 |  | 0+1 |  | 0.000 |  | 0 | 1 | 3.257 |  |  |  |  | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 40 | 欧协资格 | 贝尔格莱德游击 | 托博尔 | -1.000 |  |  | 1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 6.241 |  |  |  |  | analysis_missing;intelligence_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 41 | 阿职联 | 圣菲联合 | 拉努斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |
| 42 | 巴西杯 | 科林蒂安 | 巴西国际 | -1.000 |  |  | 3 |  | 3 |  | 0.000 |  |  |  | None |  |  |  |  | advisory_stop;analysis_missing;intelligence_missing;line_gap_missing;prob_or_sp_missing;q_unavailable;raw_strength_missing |

## 26082_016 专项

{
  "issue": "26082",
  "match_idx": 16,
  "match_id": "26082_016",
  "league": "巴西杯",
  "home": "弗鲁米嫩塞",
  "away": "瓦斯科达伽马",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "负(瓦斯科达伽马)",
  "active_primary": "0",
  "active_selection_codes": "0",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 1,
  "active_profit_proxy": "",
  "shadow_judgment": "胜(弗鲁米嫩塞)为押，保负(瓦斯科达伽马)",
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
  "p_3": 0.4297666240515012,
  "p_1": 0.3115137980430139,
  "p_0": 0.25871957790548494,
  "sp_3": 1.26,
  "sp_1": 5.09,
  "sp_0": 68.12,
  "q_3": 0.5415059463048915,
  "q_1": 1.5856052320389407,
  "q_0": 17.623977646921634,
  "max_q": 17.624,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "",
  "form_recent_confidence": "",
  "form_recent_mapped_code": "",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "analysis_missing;intelligence_missing;line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(弗鲁米嫩塞) 43.0%。\", \"EV/q主线：最高q 负(瓦斯科达伽马) q=17.62，概率 25.9%，SP 68.12。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：负(瓦斯科达伽马) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(弗鲁米嫩塞)\", \"score\": \"43.0%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 43.0% / 平 31.2% / 负 25.9%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"负(瓦斯科达伽马)\", \"score\": \"q 17.62\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.54 / 平 1.59 / 负 17.62\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"无明确方向\", \"score\": \"置信 0.00\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": []}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"cup\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": []}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"有缺口\", \"score\": \"6 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"analysis_missing\", \"intelligence_missing\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"胜(弗鲁米嫩塞)为押，保负(瓦斯科达伽马)\", \"score\": \"置信 0.37\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(弗鲁米嫩塞) 43.0%。\", \"EV/q主线：最高q 负(瓦斯科达伽马) q=17.62，概率 25.9%，SP 68.12。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26082_20260804_active_v3.3.3/structured_shadow_26082.csv`
