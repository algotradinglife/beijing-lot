# 概率与候选场次

## 获取与匹配

V球平台 https://vfootball.coze.site/：先GET /api/open/schema自发现端点、参数和semantics。后续请求用X-API-Key请求头，凭据从环境注入，禁止写进技能、QMD、日志或fixture。北单赛程、场号、球队、让球、赛前SP、比分及结算SP统一使用Nowscore，不调用V球 /api/open/bd/matches 或 /api/open/bd/match。V球仅用于赛前xG及相关足球研究；具体参数以本次schema为准。只保留真实响应，缺失写“平台暂无此数据”。保存原始响应、URL（脱敏）、采集时间、来源哈希。

先检查联赛目录是否包含目标联赛，读取对应联赛赛程确定平台match id；不要只查预测端点的已有id就认为比赛不存在。北单fixture_key与平台id做显式一对一映射，核对联赛、主客、当地/UTC开赛时间、队名别名。冲突、多个候选、未匹配分别记台账，不静默选近似匹配。比较匹配前后场数，判断数据缺失与匹配错误。

赛前北单SP来源必须记录，不能把平台结算SP当作赛前报价。使用Nowscore赛前快照，明确源和截止；无可信快照就不可用。读NAS分析数据用beidan::read_dataset()/dataset_query()及catalog，不直接打开Parquet。冻结根由BEIDAN_PARQUET_ROOT显式设置；临时捕获用BEIDAN_HOT_ROOT。不要依赖已退役Sandisk或按目录新旧推断版本。

## 三个基座

- BEIDAN：beidan::PrematchSPProbabilities(prematch_sp,cutoff)，完整三项正SP的倒数归一化。若使用prepared epoch，beidan::SelectProbabilityBase(epoch,base="beidan")；准备阶段也要绑定beidan基座。
- XG_DC：source("r/vfootball_month_backtest.R")后ProjectPrematchXg(forecasts,cutoff,tail_tolerance=1e-10,method="platform_draw_dc")。lambda为V球真实赛前xG，平台平局概率校准rho，再按真实北单handicap投影W/D/L。forecast字段以函数当前契约为准（fixture_id、lambda_home/away、platform_draw、generated_at、handicap）。缺失/非法参数保留failures，不补造xG，不用赛后xG。
- OPPONENT_RHO：source("r/vfootball_fixed_dc.R")及source("r/vfootball_rho_optimization.R")，OptimizeVfootballRho(forecast,context,cutoff,method="opponent",policy=jsonlite::fromJSON("config/vfootball_rho_policy.json"),repository_root=root)。保持原xG lambda，拟合对手调整攻防rho，读取probabilities/parameters/ledger/failures。

SelectProbabilityBase的"dc"是欧赔/大小球DC，不是V球xG-DC；它目前不接受"xg_dc"或"opponent"，不要编造统一选择器。上述是当前实际入口。

context由src/vfootball_rho_context.py的build_rho_context建立，通过包共享temporal_learning执行。显式cutoff必须绑定输入快照、完整目标期排除范围、来源/代码哈希、最大source/label时间、历史支持/ESS、策略参数和重放凭据。排除整个目标期及未来/未结算标签，不能只排除购买子集。缺历史或rho不可行拒绝输出。历史报告时钟代理仅可诊断；前瞻使用需真实观察可用性或已记录的保守安全边界。不能借用更晚轮次fit/cache。

## 可用性台账

按基座分别给出窗口赛程数、映射成功数、赛前预测有效数、完整报价数、Top1 SP准入数、三/双/单选候选数、可生成组数，以及逐场排除原因和截止。SP门槛对应各基座自己的Top1赛果，不能统用北单Top1。匹配到有效概率仍不等于满足购票门槛。三基座概率表为tibble，键fixture_id/outcome，W/D/L三行、有限非负、每场和1；时间是明确时区的POSIXct。
