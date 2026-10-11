# V球研究用途与接口口径

依据：V球[提示词广场](https://vfootball.coze.site/prompts)及[开放schema](https://vfootball.coze.site/api/open/schema)，2026-10-07读取。这里是用途改编，不复制完整提示词，也不声明新接口已由本地客户端实现。执行时重读当前schema，使用真实数据验证可用性。源快照和SHA见仓库results/beidan-strategy-prompts-20261007。prompt示例不是数据契约，冲突时以schema/semantics与真实响应为准。

## 用途选择

只为本次任务调用必要模块，不因为平台有接口就全量抓取。路径均相对/api/open，参数按当前schema。

| 平台用途 | 在本技能中的应用 | 接口候选与产物 |
|---|---|---|
| 首次接入 | 必要的数据契约发现 | schema；字段/阶段/时间/权限清单 |
| 当日赛事筛选 | 北单指定窗口覆盖检查；不把竞彩池当北单池 | bd/matches、matches、fixtures/changes；候选与缺口表 |
| 赛前综合报告 | 用户要求解释某场时提供证据背景 | matches/detail、availability、prediction、odds；事实/推断分列 |
| 阵容与伤停 | 可选赛前风险背景，记录预计/实际首发及公布时间 | matches/lineups、injuries、teams/injuries、teams/fixtures；伤停/赛程密度说明 |
| xG与射门质量 | 赛前预测输入核对；历史过程数据另列 | matches/prediction；已完赛历史stats/batch、shotmap、player-stats用于研究 |
| 赔率轨迹 | 用户指定时检查快照变化及历史报价证据 | matches/odds、odds/flow、odds/board；公司/市场/时间轨迹 |
| 必发与市场观察 | 可选一致性说明，不能当北单结算价或直接改概率 | matches/wom、odds/board；来源与缺口 |
| 实时局势 | 更新比赛进度，最终比分确认前保留进行中状态 | matches/live、live-series、incidents；观察时间与延迟 |
| 球队长期画像 | 用户要求时提供样本背景，不替代对手ρfit | teams、form、fixtures、trends/team、transfers、injuries |
| 球员趋势 | 可选阵容解释；身份和近期样本明确 | players/list、players、trends/player、player-stats |
| 联赛背景 | 联赛定位、赛程匹配与历史支持说明 | leagues、standings、stats、teams；不据当前排名回填历史特征 |
| 赛后复盘 | 已冻结策略的结构/深度/资金归因，过程解释单列 | detail、stats、incidents、shotmap、player-stats、odds/flow |

前三个基座的公式、准入和原生排序仍由现有函数负责。新增背景不能主观调整lambda/rho、单/双/三选或票序；用户要求引入特征时另建有截止和测试的分析，不能把叙述性“置信度”伪装为校准概率。实时模块不产生滚球购票，不变更冻结单。旧数据无历史可用时间时只可诊断，不能把现在伤停/积分榜当作当时已知。

## 组合成日常工作流程

用户希望大部分用途都可用：不要把综合报告、阵容/球队/联赛背景仅限制为用户逐接口点名。根据当前任务、覆盖、调用预算和已有快照组合模块；缺背景不额外剔除本来满足基座准入的场次。分层取数，摘要默认简洁，详细证据进QMD或网页展开项。

- **窗口检查**：在售北单与明确时间赛程、联赛定位、平台匹配、availability模块覆盖、赛程变更。给三基座可用池和缺口，先不逐场展开所有高成本背景。
- **生成新一期**：基础输入冻结后，为候选/入选场次汇总赛前预测、联赛积分背景、球队近期走势与赛程密度；覆盖允许时补充预计/实际阵容、伤停和赔率轨迹。关键缺阵或用户关注的球员再展开球员趋势、转会和历史射门质量。wom在有覆盖时作为市场观察补充。所有影响决策的字段都必须在截止前；截止后查询只能放入单独的后续观察报告，不回写赛前依据。
- **赛中跟踪**：定时主流程以比分、比赛状态和结算源为准；用户需要过程监控时启用live-series/incidents等详细模块，明确更新间隔与额度。不因补充模块失败阻塞已有准确票单的比分/收益更新。新增监控模块需要现有客户端支持或有测试的扩展，不声明尚未实现的请求已自动运行。
- **赛后复盘**：先做票级命中、结构/深度与实际SP归因；有覆盖时再呈现比赛统计、射门图、球员表现、事件和赛前赔率轨迹。区别概率预测表现与比赛过程描述，跨轮调参另走策略诊断和截止治理。

报告的事实来源/时间、推断理由与不确定性分开。球队、球员、市场等背景是解释层；如果要成为准入门槛、分类规则或概率特征，明确提出分析变更并独立验证，不能静默加权。技能可以指导调用上述用途，但当前小时程序仍只执行已有实现，完整报告扩展须按当前函数/API契约落地。

## 先核对口径，再用字段

每个请求核对semantics的data_role、status_scope、temporal_scope、freshness、units、null_policy、not_for和pitfalls；保留端点、字段路径、模型生成/采集/可用时间、预计或实际、覆盖与estimated标记。字段存在不等于适用赛前。模型generated_at早于截止也不自动证明当时观察可用。

xG分开保存：

| 类型 | schema字段线索 | 使用边界 |
|---|---|---|
| 赛前预测 | matches/prediction → markets.expected_goals.home/away | 当前xG-DC的lambda来源；生成时间及获取可用性需满足截止 |
| 滚球累积 | matches/live → stats.home.xg、stats.away.xg、xg_per_minute | 进行中监控，不能替代赛前预测 |
| 比赛过程统计 | matches/stats → stats.home/away.xg.actual | live/finished；estimated=true保留估算标识，不当作实际实测 |
| 球员/射门 | player-stats的expected_goals/expected_assists；shotmap的xg/xgot | 样本与来源不同；射后xGOT不等于赛前lambda |
| 球队/联赛趋势 | trends/team或leagues/stats | 样本/单位/缺失处理先核验，不直接平均成单场lambda |

schema当前将matches/availability定义为**数据模块覆盖探测**，不是球员伤停名单。先探测可用模块再查lineups/injuries；available=false是当前缺口，不永久缓存到完赛。matches/stats属于live/finished，即使提示词归类“赛前”，目标场未开赛也不能拿它替代prediction。null、空数组、no_prediction_data不是概率0。

当前leagues/stats说明可能把上游缺xG球队按0参与汇总；缺失比例未披露时不直接用于ρ拟合或联赛先验。只有已截止的可信历史可进入共享temporal_learning。

## 赛程、身份与覆盖缺口

北单bd_match_id/matchId与平台match_id/vfootballMatchId分开。bd/matches返回未匹配platform/null时先走联赛赛程核对；竞彩jc/matches是另一销售池。显式日期与[start,end)二次过滤，不依赖未传日期的套餐默认窗口。

核对bd/matches的dataSource（live/cache/stale）、cacheAgeMs、mode、saleDay：stale提示过期并按显式新鲜度政策处理；lastSaleDay不冒充当前销售日。北单销售日以schema说明的北京时间10:00边界解释，不等同自然日。bd/match的source=history可能是停售后的近期留存，不当作赛前现价。是否可研究准入与是否仍可销售分开；endTime截止已过的场次不标作可实际购买。

fixtures/changes支持since增量：保存返回until或最大changed_at作为下次水位，truncated继续读取；不凭当前时钟推进。冻结前变更触发重新验证窗口/让球/身份，必要时新冻结；冻结后推迟、中断、取消只更新观察状态。特殊比赛的退款/无效结算必须有北单官方规则与标签，不能自行按比分猜收益。

控制调用量：先availability探测、只批量查需用场次、复用哈希绑定的响应；遵守plan_contract、套餐时间窗、限流头与Retry-After，重试有界。权限、套餐历史窗、配额/429、网络/parser故障与平台无数据分别报告，不能统一说没有比赛。普通小时更新不强制附加球员/射门/市场请求。

## 输出证据与复盘

可选证据表行单位为fixture×模块×观察快照，列含source_url/endpoint、field_path、generated_at、observed_at、availability_class、match_status、unit、estimated、coverage/reason，键与join cardinality显式。网页为用户显示必要的时间、来源、缺口，详细技术字段放QMD；不加未经请求的风险门槛。

复盘沿冻结票单核对：数据/匹配 → 概率 → 分类/组结构 → 联合保护 → 购买排名 → 实际SP结算。分别给结构未覆盖、结构覆盖但排名段未购、已购未结算、已购中奖；支持数和理论上限明确。红牌/伤停/射门图只能解释过程，不证明因果或足以调参；跨期Top1/Top2、Brier/Log Loss与收益比较交由策略诊断技能。重复原回测使用原快照、截止、代码身份和固定观察版，不现场新采集替换历史输入。
