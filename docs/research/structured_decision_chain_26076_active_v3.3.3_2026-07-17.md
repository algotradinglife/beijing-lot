# 结构化决策链 26076 active_v3.3.3 回测

生成时间：2026-07-17 08:36:15Z

## 数据边界

- 输入只读取 `llm_decision_snapshots.status='active'` 的 `input_payload_json`，即赛前决策输入；赛果只用于事后评估。
- 快照完整性：`91/91`；缺失场次 `[]`。
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
| active_v3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 41, 'single': 43, 'full': 7} |
| active_v3.3.3 | 0 | 缺 | 缺 | 0 | 0 | 缺 | {'double': 60, 'single': 13, 'full': 18} |

## v3 vs active_v3.3.3 切换明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | shadow命中 | profit差 | prob_top | q_top | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 30 | K1联赛 | 仁川联 | 全北现代 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 31 | K1联赛 | 济州SK | 浦项铁人 | 0.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 33 | K2联赛 | 金浦FC | 大邱FC | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 35 | K2联赛 | 城南FC | 釜山IPark | 0.000 |  |  | 0 |  | 0+3+1 |  |  | 0 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 38 | 芬超 | 赫尔辛基 | 瓦萨 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 39 | 瑞典超 | AIK索尔纳 | 加尔斯 | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_probability_disagree;raw_strength_missing |
| 40 | 瑞典甲 | 厄斯特松德 | 兰斯克鲁纳 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 41 | 芬甲 | EIF埃克奈斯 | 耶尔文佩 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 42 | 挪超 | 克里斯蒂安松 | 萨尔普斯堡 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 挪超 | 利勒斯特伦 | KFUM奥斯陆 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 0 | raw_strength_missing |
| 44 | 挪超 | 斯达 | 罗森博格 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 46 | 芬超 | 塞伊奈约基 | 库普斯 | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 47 | 芬甲 | KTP科特卡 | PK-35 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 48 | 瑞典甲 | 厄斯特什 | 布莱格 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 罗甲 | 加拉茨钢铁 | 克卢日 | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 54 | 罗甲 | CS克拉约瓦大学 | UTA阿拉德 | -1.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 55 | 巴西乙 | 克里西乌马 | 维拉诺瓦 | -1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 0 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 57 | 巴西乙 | 庞特普雷塔 | 戈亚斯 | 1.000 |  |  | 3+1 |  | 3+0+1 |  |  | 3 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 58 | 冰岛超 | 瓦路尔 | 弗拉姆 | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 60 | 巴西乙 | 戈亚尼亚竞技 | 米纳斯吉拉斯竞技 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 61 | 墨超 | 普马斯 | 帕丘卡 | 0.000 |  |  | 3+1 |  | 3+0 |  |  | 3 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 62 | 墨超 | 蒙特雷 | 桑托斯拉古纳 | -1.000 |  |  | 3 |  | 3+0+1 |  |  | 3 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 墨超 | 瓜达拉哈拉 | 托卢卡 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 64 | 墨超 | 克雷塔罗 | 墨西哥美洲 | 0.000 |  |  | 0+1 |  | 0+3 |  |  | 0 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 65 | K1联赛 | FC安养 | 光州FC | -1.000 |  |  | 3+1 |  | 3+0+1 |  |  | 0 | 3 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 67 | K2联赛 | 庆南FC | 安山绿人 | -1.000 |  |  | 3+1 |  | 3+0+1 |  |  | 0 | 1 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 68 | K2联赛 | 水原三星蓝翼 | 坡州前沿 | -1.000 |  |  | 3+1 |  | 3+0+1 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 69 | K2联赛 | 忠北清州FC | 天安城 | 0.000 |  |  | 3 |  | 3+0 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 70 | K2联赛 | 龙仁FC | 华城FC | 0.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 73 | 瑞典甲 | 诺迪克联 | 厄勒布鲁 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 74 | 罗甲 | 克卢日大学 | 康斯坦察法鲁尔 | -1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 0 | 3 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 78 | 瑞典超 | 哈尔姆斯塔德 | 赫根 | 1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 3 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 79 | 芬超 | 查路 | 国际图尔库 | 1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 80 | 冰岛超 | KR雷克雅未克 | 斯塔尔南 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 83 | 芬超 | TPS图尔库 | 伊尔维斯 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 84 | 罗甲 | 胡内多阿拉乌鸦 | 奇克塞雷达 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 0 | q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 86 | 瑞典超 | 厄尔格里特 | 佐加顿斯 | 1.000 |  |  | 0+1 |  | 0+3+1 |  |  | 0 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 87 | 瑞典超 | 卡尔马 | 马尔默 | 0.000 |  |  | 0+1 |  | 0+3 |  |  | 0 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 88 | 瑞典甲 | 诺尔比 | 松兹瓦尔 | 0.000 |  |  | 3 |  | 3+1 |  |  | 3 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 89 | 罗甲 | 布加勒斯特快速 | 塞普西 | -1.000 |  |  | 0 |  | 0+1 |  |  | 0 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 90 | 冰岛超 | 凯夫拉维克 | IA阿克拉内斯 | 0.000 |  |  | 3 |  | 3+0 |  |  | 3 | 0 | q_probability_disagree;raw_strength_missing |
| 91 | 冰岛超 | FH哈夫纳夫约杜尔 | 贝雷达比历克 | 0.000 |  |  | 0 |  | 0+3 |  |  | 0 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 26076 全场明细

| # | 比赛 | 主队 | 客队 | 让球 | 比分 | 赛果 | active_v3 | active命中 | active_v3.3.3 | 情报保 | 情报强度 | shadow命中 | prob_top | q_top | max_q | raw | fit | 近期 | 近况映射 | risk_tags |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 罗甲 | 沃伦塔里 | 博托沙尼 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 1 | 1 | 1.325 |  |  | 3 | 3 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 2 | 芬甲 | 赫尔辛基预备队 | 哈卡 | 1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.695 |  | 3 | 3 | 1.546 |  |  | 0 | 1 | raw_strength_missing;recent_form_intel_protection |
| 3 | 芬甲 | 卡帕 | 塞伊奈约基学院 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.566 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 4 | 瑞典超 | 哥德堡 | 布鲁马波卡纳 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.717 |  | 3 | 1 | 2.108 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 5 | 瑞典超 | 米亚尔比 | 韦斯特罗斯 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.050 |  |  | 3 | 3 | line_gap_watch;raw_strength_missing |
| 6 | 挪超 | 博德闪耀 | 腓特烈斯塔 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 3.371 |  |  | 3 |  | q_top_odds_up;raw_strength_missing |
| 7 | 罗甲 | 布加勒斯特星 | 阿尔杰什 | -1.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.540 |  |  | 0 | 0 | line_gap_missing;raw_strength_missing |
| 8 | 爱足总杯 | 费恩哈普 | 布雷流浪者 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.609 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 9 | 爱足总杯 | 凯里 | 谢尔伯恩 | 1.000 |  |  | 0+3+1 |  | 0+3+1 |  | 0.000 |  | 0 | 0 | 2.047 |  |  | 0 | 1 | line_gap_missing;probability_runner_up_protection;raw_strength_missing |
| 10 | 爱足总杯 | 圣帕特里克竞技 | 韦克斯福德 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.163 |  |  | 3 |  | line_gap_missing;q_top_odds_up;raw_strength_missing |
| 11 | 爱足总杯 | 条约联 | 都柏林大学 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.403 |  |  | 3 | 3 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 12 | 爱足总杯 | 沃特福德FC | 科夫漫步者 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.736 |  | 3 | 1 | 2.036 |  |  | 3 | 1 | line_gap_missing;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 13 | 爱足总杯 | 沙姆洛克流浪者 | 科克城 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.635 |  | 3 | 0 | 2.532 |  |  | 0 | 0 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 14 | 阿根廷杯 | 圣洛伦索 | 列斯特拉体育 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 7.625 |  |  | 3 | 3 | probability_runner_up_protection;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 15 | 巴西乙 | 圣贝尔纳多 | 阿瓦伊 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.508 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 16 | 巴西乙 | 米内罗美洲 | 塞阿拉 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 3 | 0 | 1.887 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 17 | 巴西甲 | 巴伊亚 | 沙佩科恩斯 | -1.000 |  |  | 0+1 |  | 0+1 |  | 0.000 |  | 3 | 0 | 5.611 |  |  | 0 | 0 | q_probability_disagree;raw_strength_missing |
| 18 | 巴西甲 | 弗鲁米嫩塞 | 布拉干蒂诺红牛 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 3.932 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 19 | 巴西甲 | 米拉索尔 | 格雷米奥 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.943 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 20 | 巴西乙 | 隆德里纳 | 博塔弗戈SP | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.557 |  |  | 3 | 3 | raw_strength_missing |
| 21 | 巴西乙 | 福塔莱萨 | 新奥里藏蒂诺 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.749 |  | 3 | 3 | 1.112 |  |  | 0 | 0 | line_gap_watch;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 22 | 美职 | 纳什维尔SC | 亚特兰大联 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.773 |  | 3 | 0 | 2.905 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 23 | 阿根廷杯 | 河床 | 阿尔多希维 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.773 |  | 3 | 0 | 4.462 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 24 | 墨超 | 圣路易斯竞技 | 蓝十字 | 1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.728 |  | 3 | 1 | 2.135 |  |  | 0 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 25 | 墨超 | 莱昂 | 阿特拉斯 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.252 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 26 | 美职 | 洛杉矶银河 | 洛杉矶FC | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 2.259 |  |  | 3 | 3 | raw_strength_missing |
| 27 | 墨超 | 华雷斯 | 普埃布拉 | -1.000 |  |  | 3+0+1 |  | 3+0+1 | 1 | 0.749 |  | 0 | 0 | 1.738 |  |  | 3 | 1 | probability_runner_up_protection;raw_strength_missing;recent_form_intel_protection |
| 28 | K1联赛 | 大田韩亚市民 | 蔚山HD | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.143 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 29 | K1联赛 | 江原FC | 金泉尚武 | -1.000 |  |  | 3+0 |  | 3+0 | 1 | 0.748 |  | 0 | 0 | 1.440 |  |  | 3 | 1 | line_gap_watch;probability_runner_up_protection;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection |
| 30 | K1联赛 | 仁川联 | 全北现代 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.484 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 31 | K1联赛 | 济州SK | 浦项铁人 | 0.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 3.207 |  |  | 0 | 0 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 32 | K2联赛 | 全南天龙 | 忠南牙山FC | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 0 | 1.137 |  |  | 0 | 0 | probability_runner_up_protection;raw_strength_missing |
| 33 | K2联赛 | 金浦FC | 大邱FC | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.634 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 34 | K2联赛 | 水原FC | 首尔衣恋 | 0.000 |  |  | 0+1 |  | 0+1 | 1 | 0.702 |  | 0 | 1 | 2.704 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 35 | K2联赛 | 城南FC | 釜山IPark | 0.000 |  |  | 0 |  | 0+3+1 |  | 0.000 |  | 0 | 1 | 3.713 |  |  | 0 | 0 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 36 | 瑞典甲 | 奥迪沃德 | 瓦尔贝里 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.704 |  | 3 | 3 | 1.960 |  |  | 0 | 0 | raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 37 | 挪超 | 汉坎 | 特罗姆瑟 | 0.000 |  |  | 0+3 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.942 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 38 | 芬超 | 赫尔辛基 | 瓦萨 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.006 |  |  | 0 | 0 | line_gap_watch;q_probability_disagree;raw_strength_missing |
| 39 | 瑞典超 | AIK索尔纳 | 加尔斯 | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.772 |  |  | 0 | 0 | q_probability_disagree;raw_strength_missing |
| 40 | 瑞典甲 | 厄斯特松德 | 兰斯克鲁纳 | 0.000 |  |  | 3+1 |  | 3+0 | 1 | 0.720 |  | 3 | 0 | 1.408 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 41 | 芬甲 | EIF埃克奈斯 | 耶尔文佩 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.703 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 42 | 挪超 | 克里斯蒂安松 | 萨尔普斯堡 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.119 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 43 | 挪超 | 利勒斯特伦 | KFUM奥斯陆 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 0 | 1.595 |  |  | 3 | 1 | raw_strength_missing |
| 44 | 挪超 | 斯达 | 罗森博格 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.995 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 45 | 芬超 | AC奥卢 | 格尼斯坦 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 1.352 |  |  | 0 | 0 | raw_strength_missing |
| 46 | 芬超 | 塞伊奈约基 | 库普斯 | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 7.107 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 47 | 芬甲 | KTP科特卡 | PK-35 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.476 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 48 | 瑞典甲 | 厄斯特什 | 布莱格 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.583 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 49 | 罗甲 | 加拉茨钢铁 | 克卢日 | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 2.063 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 50 | 挪超 | 莫尔德 | 布兰 | 0.000 |  |  | 3+0 |  | 3+0 |  | 0.000 |  | 3 | 0 | 2.181 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 51 | 挪超 | 维京 | 桑讷菲尤尔 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 8.183 |  |  | 3 |  | raw_strength_missing |
| 52 | 冰岛超 | 托尔 | 维京古尔 | 2.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 4.186 |  |  | 0 |  | line_gap_large;raw_strength_missing |
| 53 | 苏联赛杯 | 阿伯丁 | 女王公园 | -1.000 |  |  | 0+3+1 |  | 0+3+1 |  | 0.000 |  | 3 | 0 | 1.885 |  |  | 0 | 0 | line_gap_missing;probability_runner_up_protection;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 54 | 罗甲 | CS克拉约瓦大学 | UTA阿拉德 | -1.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.774 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 55 | 巴西乙 | 克里西乌马 | 维拉诺瓦 | -1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.741 |  | 0 | 3 | 6.541 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 56 | 巴西乙 | 累西腓体育 | 铁路工人 | 0.000 |  |  | 3+1 |  | 3+1 | 1 | 0.702 |  | 3 | 1 | 1.971 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 57 | 巴西乙 | 庞特普雷塔 | 戈亚斯 | 1.000 |  |  | 3+1 |  | 3+0+1 | 1 | 0.765 |  | 3 | 0 | 4.714 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 58 | 冰岛超 | 瓦路尔 | 弗拉姆 | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 4.463 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 59 | 世界杯 | 法国 | 英格兰 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.942 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 60 | 巴西乙 | 戈亚尼亚竞技 | 米纳斯吉拉斯竞技 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 6.971 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 61 | 墨超 | 普马斯 | 帕丘卡 | 0.000 |  |  | 3+1 |  | 3+0 | 1 | 0.694 |  | 3 | 0 | 2.999 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 62 | 墨超 | 蒙特雷 | 桑托斯拉古纳 | -1.000 |  |  | 3 |  | 3+0+1 |  | 0.000 |  | 3 | 1 | 1.587 |  |  | 0 | 0 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 63 | 墨超 | 瓜达拉哈拉 | 托卢卡 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.725 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 64 | 墨超 | 克雷塔罗 | 墨西哥美洲 | 0.000 |  |  | 0+1 |  | 0+3 | 1 | 0.761 |  | 0 | 3 | 4.406 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 65 | K1联赛 | FC安养 | 光州FC | -1.000 |  |  | 3+1 |  | 3+0+1 | 1 | 0.772 |  | 0 | 3 | 1.595 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 66 | K1联赛 | 富川1995 | FC首尔 | 1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.723 |  | 3 | 1 | 1.735 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 67 | K2联赛 | 庆南FC | 安山绿人 | -1.000 |  |  | 3+1 |  | 3+0+1 | 1 | 0.772 |  | 0 | 1 | 1.713 |  |  | 3 | 1 | line_gap_watch;probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 68 | K2联赛 | 水原三星蓝翼 | 坡州前沿 | -1.000 |  |  | 3+1 |  | 3+0+1 | 1 | 0.740 |  | 3 | 1 | 1.113 |  |  | 3 | 1 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 69 | K2联赛 | 忠北清州FC | 天安城 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 0 | 0 | 2.644 |  |  | 3 | 3 | probability_runner_up_protection;raw_strength_missing |
| 70 | K2联赛 | 龙仁FC | 华城FC | 0.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 1.855 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 71 | 瑞典甲 | 北雪平 | 桑德维肯 | -1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.676 |  | 3 | 1 | 1.576 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 72 | 瑞典甲 | 韦纳穆 | 永斯基 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 3 | 0 | 5.041 |  |  | 0 | 0 | q_probability_disagree;raw_strength_missing |
| 73 | 瑞典甲 | 诺迪克联 | 厄勒布鲁 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.770 |  |  | 3 | 3 | line_gap_large;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 74 | 罗甲 | 克卢日大学 | 康斯坦察法鲁尔 | -1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.725 |  | 0 | 3 | 4.510 |  |  | 1 | 1 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 75 | 冰岛超 | IBV韦斯特曼纳 | KA阿克雷里 | 0.000 |  |  | 3 |  | 3 |  | 0.000 |  | 3 | 3 | 6.263 |  |  | 3 | 3 | raw_strength_missing |
| 76 | 瑞典超 | 哈马比 | 代格福什 | -2.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 23.083 |  |  | 3 |  | line_gap_watch;q_top_odds_up;raw_strength_missing |
| 77 | 瑞典超 | 埃尔夫斯堡 | 天狼星 | 1.000 |  |  | 3+1 |  | 3+1 | 1 | 0.764 |  | 3 | 1 | 2.672 |  |  | 0 | 1 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 78 | 瑞典超 | 哈尔姆斯塔德 | 赫根 | 1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.783 |  | 3 | 1 | 2.021 |  |  | 0 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 79 | 芬超 | 查路 | 国际图尔库 | 1.000 |  |  | 0 |  | 0+1 | 1 | 0.760 |  | 0 | 1 | 2.566 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 80 | 冰岛超 | KR雷克雅未克 | 斯塔尔南 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 6.682 |  |  | 3 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 81 | 罗甲 | 佩特罗鲁 | 布加勒斯特迪纳摩 | 0.000 |  |  | 0 |  | 0 |  | 0.000 |  | 0 | 0 | 1.272 |  |  | 0 | 0 | line_gap_missing;raw_strength_missing |
| 82 | 世界杯 | 西班牙 | 阿根廷 | 0.000 |  |  | 3+1 |  | 3+1 |  | 0.000 |  | 3 | 1 | 1.425 |  |  | 0 | 0 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 83 | 芬超 | TPS图尔库 | 伊尔维斯 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 1.155 |  |  | 0 | 0 | probability_runner_up_protection;q_probability_disagree;raw_strength_missing |
| 84 | 罗甲 | 胡内多阿拉乌鸦 | 奇克塞雷达 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 1.097 |  |  | 3 | 3 | q_probability_disagree;q_top_odds_up;raw_strength_missing |
| 85 | 芬超 | 玛丽港 | 拉赫蒂 | 1.000 |  |  | 0+1 |  | 0+1 | 1 | 0.759 |  | 3 | 1 | 4.615 |  |  | 0 | 1 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 86 | 瑞典超 | 厄尔格里特 | 佐加顿斯 | 1.000 |  |  | 0+1 |  | 0+3+1 | 1 | 0.770 |  | 0 | 1 | 4.750 |  |  | 0 | 1 | probability_runner_up_protection;q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_intel_protection |
| 87 | 瑞典超 | 卡尔马 | 马尔默 | 0.000 |  |  | 0+1 |  | 0+3 | 1 | 0.719 |  | 0 | 3 | 2.256 |  |  | 3 | 3 | q_high_but_probability_low;q_probability_disagree;raw_strength_missing;recent_form_full_guard;recent_form_intel_protection;reverse_intel_adjacent_protection |
| 88 | 瑞典甲 | 诺尔比 | 松兹瓦尔 | 0.000 |  |  | 3 |  | 3+1 |  | 0.000 |  | 3 | 1 | 2.770 |  |  | 3 | 3 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 89 | 罗甲 | 布加勒斯特快速 | 塞普西 | -1.000 |  |  | 0 |  | 0+1 |  | 0.000 |  | 0 | 1 | 4.085 |  |  | 0 | 0 | line_gap_missing;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |
| 90 | 冰岛超 | 凯夫拉维克 | IA阿克拉内斯 | 0.000 |  |  | 3 |  | 3+0 |  | 0.000 |  | 3 | 0 | 4.061 |  |  | 3 | 3 | q_probability_disagree;raw_strength_missing |
| 91 | 冰岛超 | FH哈夫纳夫约杜尔 | 贝雷达比历克 | 0.000 |  |  | 0 |  | 0+3 |  | 0.000 |  | 0 | 3 | 2.332 |  |  | 0 | 0 | line_gap_watch;q_high_but_probability_low;q_probability_disagree;raw_strength_missing |

## 26076_016 专项

{
  "issue": "26076",
  "match_idx": 16,
  "match_id": "26076_016",
  "league": "巴西乙",
  "home": "米内罗美洲",
  "away": "塞阿拉",
  "handicap_line": 0.0,
  "score": "",
  "actual_code": "",
  "actual_label": "",
  "winning_sp": "",
  "active_version": "llm_chain_bet_protect_stop_v3.3.3",
  "active_recommendation": "负(塞阿拉)为押，保胜(米内罗美洲)",
  "active_primary": "0",
  "active_selection_codes": "0+3",
  "active_primary_hit": "",
  "active_coverage_hit": "",
  "active_stake": 2,
  "active_profit_proxy": "",
  "shadow_judgment": "负(塞阿拉)为押，保胜(米内罗美洲)",
  "shadow_primary": "0",
  "shadow_selection_codes": "0+3",
  "shadow_stop_flag": 0,
  "shadow_primary_hit": "",
  "shadow_coverage_hit": "",
  "shadow_stake": 2,
  "shadow_profit_proxy": "",
  "phase2_primary_experiment_id": "phase2_probability_first_within_coverage",
  "phase2_primary_experiment_version": "v0.1.0000",
  "phase2_probability_primary": "3",
  "phase2_probability_selection_codes": "3+0",
  "phase2_probability_changed": 1,
  "phase2_probability_grade": "B",
  "phase2_probability_primary_probability": 0.376342,
  "phase2_probability_primary_margin": 0.063407,
  "phase2_probability_primary_hit": "",
  "phase2_probability_execution_enabled": 0,
  "phase2_handicap_gated_experiment_id": "phase2_handicap_gated_probability_first",
  "phase2_handicap_gated_experiment_version": "v0.2.0000",
  "phase2_handicap_gated_primary": "3",
  "phase2_handicap_gated_selection_codes": "3+0",
  "phase2_handicap_gated_changed": 1,
  "phase2_handicap_gated_grade": "B",
  "phase2_handicap_gated_primary_probability": 0.376342,
  "phase2_handicap_gated_primary_margin": 0.063407,
  "phase2_handicap_gated_gate_applied": 1,
  "phase2_handicap_gated_primary_hit": "",
  "phase2_handicap_gated_execution_enabled": 0,
  "phase2_league_soft_experiment_id": "phase2_seasonal_league_soft_tiebreak",
  "phase2_league_soft_experiment_version": "v0.1.0000",
  "phase2_league_soft_primary": "0",
  "phase2_league_soft_selection_codes": "0+3",
  "phase2_league_soft_changed": 0,
  "phase2_league_soft_grade": "C",
  "phase2_league_soft_primary_probability": 0.302935,
  "phase2_league_soft_primary_margin": 0.063407,
  "phase2_league_soft_gate_applied": 0,
  "phase2_league_soft_effective_n": 19,
  "phase2_league_soft_adjustment_json": "{\"3\": 0.01, \"1\": 0.006864, \"0\": -0.01}",
  "phase2_league_soft_primary_hit": "",
  "phase2_league_soft_execution_enabled": 0,
  "phase3_protection_experiment_id": "phase3_drop_switched_ev_home_protection",
  "phase3_protection_experiment_version": "v0.1.0000",
  "phase3_protection_baseline_codes": "0+3",
  "phase3_protection_candidate_codes": "0+3",
  "phase3_protection_triggered": 0,
  "phase3_protection_removed_code": "",
  "phase3_protection_reason": "not_triggered",
  "phase3_protection_execution_enabled": 0,
  "shadow_arm": "active_v3.3.3",
  "shadow_version": "llm_chain_bet_protect_stop_v3.3.3",
  "selection_type": "double",
  "prob_top": "3",
  "q_top": "0",
  "p_3": 0.37634189503403204,
  "p_1": 0.31072300658712565,
  "p_0": 0.3129350983788423,
  "sp_3": 2.42,
  "sp_1": 2.37,
  "sp_0": 6.03,
  "sp_complete": 1,
  "sp_missing_codes": "",
  "sp_source": "500_preclose_sp_complete",
  "q_3": 0.9107473859823575,
  "q_1": 0.7364135256114879,
  "q_0": 1.8869986432244192,
  "max_q": 1.887,
  "raw_strength_side": "",
  "handicap_fit_code": "",
  "form_recent_code": "0",
  "form_recent_confidence": 0.63,
  "form_recent_mapped_code": "0",
  "llm_intel_source": "script_proxy",
  "llm_intel_protect": "",
  "llm_intel_strength": 0.0,
  "llm_intel_should_protect": 0,
  "risk_tags": "probability_runner_up_protection;q_probability_disagree;raw_strength_missing",
  "shadow_chain_json": "[\"概率主线：最高让球后概率 胜(米内罗美洲) 37.6%。\", \"EV/q主线：最高q 负(塞阿拉) q=1.89，概率 31.3%，SP 6.03。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\", \"动作规则：押由让球后概率+handicap_fit+近期形态决定；q方向仅在不一致且过线时进入保护/增厚；-1/受让1盘口的让球平按近邻保护评估。\", \"概率保护：当第二高让球后概率不低且与第一名接近时，作为防死票保护候选；全包数量由票池阶段控制。\", \"保护：胜(米内罗美洲) 来自 q/EV 与主押不一致。\"]",
  "shadow_categories_json": "[{\"key\": \"model_probability\", \"label\": \"让球后概率\", \"result\": \"胜(米内罗美洲)\", \"score\": \"37.6%\", \"verdict\": \"主押基础信号\", \"evidence\": [\"胜 37.6% / 平 31.1% / 负 31.3%\"]}, {\"key\": \"market_q_ev\", \"label\": \"q / EV\", \"result\": \"负(塞阿拉)\", \"score\": \"q 1.89\", \"verdict\": \"只做保护/增厚，不直接反客为主\", \"evidence\": [\"胜 0.91 / 平 0.74 / 负 1.89\"]}, {\"key\": \"handicap_fit\", \"label\": \"让球映射\", \"result\": \"无明确映射\", \"score\": \"强度 0.00\", \"verdict\": \"情报强弱先过北单让球语境\", \"evidence\": []}, {\"key\": \"form_recent\", \"label\": \"近期形态\", \"result\": \"负(塞阿拉)\", \"score\": \"置信 0.63\", \"verdict\": \"轻权重影响主押，并可触发保护\", \"evidence\": [\"主队近10场 1胜2平7负，进失7/16，半场平3场，近5走势平-负-负-负-胜\", \"客队近10场 3胜2平5负，进失9/13，半场平3场，近5走势平-负-负-负-平\"]}, {\"key\": \"raw_strength\", \"label\": \"情报强弱\", \"result\": \"未识别\", \"score\": \"置信 0.00\", \"verdict\": \"只判断原始强弱，不直接等同让球结果\", \"evidence\": []}, {\"key\": \"llm_intel_protection\", \"label\": \"情报保护层\", \"result\": \"未触发\", \"score\": \"强度 0.00\", \"verdict\": \"只能增加保护，不能改主押\", \"evidence\": []}, {\"key\": \"competition_context\", \"label\": \"赛制语境\", \"result\": \"league_round\", \"score\": \"权重 0.00\", \"verdict\": \"只作风险提示或小权重\", \"evidence\": [\"赛制/阶段：巴乙\"]}, {\"key\": \"data_quality\", \"label\": \"数据质量/风险\", \"result\": \"可用\", \"score\": \"3 个风险标签\", \"verdict\": \"关键缺失才触发停牌\", \"evidence\": [\"analysis/intelligence/probability/sp inputs available\"]}, {\"key\": \"final_aggregation\", \"label\": \"脚本汇总\", \"result\": \"负(塞阿拉)为押，保胜(米内罗美洲)\", \"score\": \"置信 0.46\", \"verdict\": \"固定规则合成押/保/停\", \"evidence\": [\"概率主线：最高让球后概率 胜(米内罗美洲) 37.6%。\", \"EV/q主线：最高q 负(塞阿拉) q=1.89，概率 31.3%，SP 6.03。\", \"让球映射：\", \"情报保护层：script_proxy 未建议新增保护。\"]}]"
}

结论：`llm_chain_bet_protect_stop_v3.3.3` 明确采用“胜率主押、q/EV 增厚保护”的框架：主押先看让球后概率、让球映射和近期形态；q 不反客为主，只在与主押不一致且过线时进入保护/增厚。相较 v3.3.2，本版修正情报解析：`未尝败绩`/`不败` 类短语不再被 `败绩` 负面词反向命中；主场/作客语境在别名未直接命中时只作为弱证据，避免标题形容词压过概率主线。`llm_intel_protection` overlay 单独消化情报文本和近期表现，并且必须先映射到北单让球结构，只能提出“是否增加保护”的建议，最终仍由脚本按强度、概率/q护栏汇总。当前快照没有真实 LLM advice 时，该层来源显示为 `script_proxy`；接入真实 LLM 后应写入同一 schema，再与 v3/v3.3.1/v3.3.2/v3.3.3 做 shadow 对照。

CSV 明细：`results/structured_decision_chain_shadow/26076_20260717_active_v3.3.3/structured_shadow_26076.csv`
