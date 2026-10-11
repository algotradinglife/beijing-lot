# 工作流与函数边界

当前完整流程版本 **FM-1.5.0**，主选/保护与比分校正按[方向与比分校正](direction-score-adjustment.md)执行。旧函数用于基础和市场证据处理，不能用旧market_review阶段代替新最终分布。

## 顺序与产物

原生λ由长期与近期共同估计（默认alpha=0.5），市场提供有证据的补充，未发现新增信息则保留原生λ。尾部统一按[中心等距规则](scenario-tail-adjustment.md)，最高概率单档为中心，逐层至少一侧>=10%即成对保留，半径最多2，外围0.3。

场次/截止 → 长期/近期攻防及可用对手强度/人员信息 → 原生λ与DC → 同截止市场对照及接受/拒绝账本 → 冻结中心和半径 → 比分分布重加权 → 冻结 → 投影北单并排序 → 独立反馈。

保留数据基准、市场复核和方向校正视图。最终为专家重加权网格，不报告伪造的新DC参数。ρ显式固定，0.65是票级回款因子，不参与概率。

## 历史FM-1.1示例（非当前最终流程）

- 基础λ坡州1.22/釜山1.31，来自赛季主客场双向交叉参考，无对手校正。
- 定性调整：假设釜山进攻投入+0.04，假设压上增加坡州机会+0.02 → 1.24/1.35。
- 交战主情景调整0：仅一场4:1且场地反转，没有直接进入当前相反主客子样本，不能宣称必然重复计数，也不足以证实稳定对位优势。
- 同截止欧赔归一化平均27.0%/26.8%/46.2%；大小球旧报价2.5两边均衡，总均值参考2.674。
- 定性解释分歧：釜山长期实力与目标支持上调，近期状态与防守问题限制幅度，坡州进球机会保留。手工釜山+0.10、坡州0 → 1.24/1.45。
- ρ固定-0.10，最终31.087%/28.149%/40.764%。这是手工情景，不是历史拟合或射门级xG预测。
- 联赛平局70/219=31.963%作背景，不把本场平局直接抬至该值。

这些幅度仅绑定本次示例，不作为未来自动规则。若机制证据不足，可保持0调整并披露分歧，不补造战术原因。

## 既有函数：复用，不再封装相同算法

| 职责 | 现有实现 | 边界 |
|---|---|---|
| 原生近期λ | recent_venue_goals.R / beidan_backend.recent_venue_goals | 同场地历史与近期分布混合，共享截止/权重/ESS/收据；未量化对手强度和阵容 |
| 中心等距目标 | fm15_tail_judgement.R：build_fm15_tail_judgement | 只构造完整分区目标；现有score调整与投影执行 |
| 原始市场抓取/解析 | beidan_backend.market_capture.service.fetch_markets / parse_markets；history中的Euro与OU解析 | 固定间隔、超时重试、保留字节；公司命名空间分离 |
| DC比分与概率 | packages/beidan/R/dixon_coles_grid.R：dixon_coles_score_grid | 显式λ、ρ、让球、尾部界；不学习 |
| 普通/让球及比分诊断 | fundamentals_market_comparison.R：market_score_projection | 纯算术；不把模型均值等同真实xG |
| 大小球价格映射 | fundamentals_total_market.R：asian_total_probability / total_market_constraint | 推盘与半输赢；Poisson定价模型，不能对所有盘口忽略DC四低格影响 |
| 同时点市场参考λ | total_constrained_projection | 固定总均值与ρ反解份额，输出残差；不是自动采用的最终λ |
| 现行选项类别 | classify_outcomes | spread≤0.10三选，其他按Top1>0.50单选，否则双选及保护对 |
| 时序准入/反馈学习 | beidan_backend.temporal_learning | 所有历史拟合、权重/ρ选择共用，不复制 |

source_extraction.R中的ExtractTitanMarkets等已有源适配层仍是另一作者未跟踪工作；此草案不修改或提交它，不将其视为已验收依赖。V球专用现有研究投影如r/vfootball_fixed_dc.R需满足自身输入/截止契约；不为模拟数据伪造平台generated_at。

## 已整合到beidan的三个函数

1. **fundamental_goal_baseline(context, fixture, policy)**：实际签名为fundamental_goal_baseline(context, fixture, policy, repository_root)。接收由beidan_backend.fundamental_probability.build_goal_baseline_context建立的共享上下文、场次tibble、显式rho/tail_tolerance/minimum_matches/lambda_digits政策。当前实现仅做主客场统计快照的手工交叉均值，返回sealed scenario及typed tibbles/共享收据；平台预期进球仍复用既有投影，不伪装成此函数支持的模式。统计快照与逐场比分不是同一观察单位；支持量不足明确拒绝，不复制时序逻辑。测试模式标签、场地子样本、无覆盖、零场分母、空/坏时间和目标排除。
2. **apply_goal_adjustments(parameters, adjustments, policy)**：只执行人工账本中的数值调整，返回每步与最终λ。输入参数携带场次、截止身份、版本；调整表主键adjustment_id，字段stage、parameter、delta_goals、evidence_ids、reason、overlap_group、status。实际参数列为单个evidence_id，stage=qualitative/market_review。policy显式max_absolute_delta及evidence_context，由build_adjustment_evidence_context把证据的发布/可用时间、来源哈希、身份交给共享时序模块准入；引用和决策绑定须匹配。每次只允许一个stage，各次证据和政策累计保存，前瞻用途不接受历史代理上下文。参数仅lambda_home/lambda_away；ρ另由显式政策供给。证据缺失、版本不符、重复ID、非法阶段、调整后非正λ拒绝；没有被选中的候选调整不执行。函数不判断战意、不学习幅度、不暗设系数。测试本例顺序回放、typed-empty零调整、重复与错绑定、非法值和目标参数非正。
3. **compare_fundamental_market(fundamental, market, totals, decision)**：验证同场同截止及概率单位，输出概率差、λ总量/差、报价年龄与缺失状态、市场反解残差；实际market列company_id/fixture_id/quote_at/odds_home/odds_draw/odds_away，totals列company_id/fixture_id/quote_at/line/over_decimal/under_decimal；decision含issue_id/cutoff_utc/max_quote_age_hours/total_bounds。只比较，不生成自动调整。当前限>=2.5的半球大小盘，DC四格质量抵消；其他盘拒绝，避免静默使用Poisson忽略DC结算。复用价格和投影函数。测试旧报价、空市场typed-tibble、缺一个结果、公司重复、普通/让球口径不符、未来报价、同场错截止。

### 整期历史基础估算与复盘

`EstimateFundamentalIssue(fixtures, history, source_hashes, policy, repository_root)`：fixtures为完整单期名单，严格列顺序fixture_id/issue_id/provider_id/home/away/home_id/away_id/handicap/cutoff_utc，截止是每场明确的UTC POSIXct。history使用已核验事实表，不带目标标签；接口按场次分组一次，共享准入排除全期所有目标原生ID及截止后的记录。policy显式rho/tail_tolerance/minimum_matches/lambda_digits；已准入主队主场、客队客场记录等权，复用既有交叉均值基础函数。输出全期状态、参数、普通/让球概率、完整比分网格、样本量和共享收据；仅data_baseline，定性及盘口未评估。缺截止、样本不足和不可行λ/ρ逐场明确失败；不静默填补或裁剪。

`ReviewFundamentalIssue(estimate, fixtures, history, labels)`：估算封印及输入/实现身份先校验，labels为fixture_id/home_goals/away_goals（整数或NA）。取消、无比分与无估算分别保留；复用DcAccuracyDiagnostic输出Brier/log loss/Top1/Top2/边际概率对照，并输出实际比分概率和排序、总进球误差。它不回写λ/ρ、不拟合或选择参数。名单及赛果须固定文件哈希或源capture ID；cache_only读“当前缓存”不能代替固定输入。去赛果名单与赛果分开，估算保存后再打开标签。

日期次日00:00 UTC仅是历史诊断代理，不是实际标签可用性；未注册北单的足球历史记录按MATCH原生ID命名，完整目标名单提供准确目标期排除。source-published full-time不自动等于已验证90分钟比分。真实可用性或比分范围不明时不能宣称严格赛前回测。已执行示例为quarto/fundamental_issues_review_20261011.qmd；数值、样本量和原生让球验证分别见test-fundamental-issue.R及test_fundamental_issue.py。当前接口不含盘口/伤停微调或下注收益。

这三个业务边界已实现，方法与数据支持仍为手工诊断；当前快照上下文构建器使用共享FIXED_PRIOR_FIT，只授权HISTORICAL_DIAGNOSTIC，不能当作生产前瞻预测接口或改声明绕过限制；抓取器、DC、总进球求根及分类已有，不能再建平行实现。代码放packages/beidan/R并配packages/beidan/tests/testthat；采集后端放包内Python。QMD只组织输入和结果，skill只组织判断与调用。

## 数据契约与冻结

- fixture：一行/场次；字符fixture_id/issue_id/source_ids，POSIXct decision_at/kickoff_at与时区，整数handicap；同源ID关系需验证，不猜映射。
- evidence：一行/事实或假设；字符evidence_id/domain/source_url/availability_class，事件/发表/采集时间分别记录；nullable发布时间只代表未知。skill填写direction/reliability/overlap解释，函数验证结构与引用。
- stats：一行/球队×场地×窗口；整数matches/goals_for/goals_against，explicit窗口与可用时间、源hash；零场为不足，不把率设0。
- adjustments：一行/调整，delta_goals单位球/场；stage=qualitative或market_review；当前每项调整引用一个主要evidence_id，关联表保留补充证据，不能将多个证据ID串在字段里。另一参数或零调整也是一行审计事项；候选与已执行明确区分。
- parameters：一行/场次×stage×scenario；double lambda_home/lambda_away/rho与source_mode，绑定输入、截止及调整账本。
- probabilities：一行/场次×stage×scenario×market×outcome；W/D/L各三行，probability∈[0,1]、组内和1，省略尾部质量明示。
- market_quotes：一行/来源×公司×报价时间×盘口，价格单位decimal或HK明确；同分钟冲突按权威解析规则记录，不静默平均；等权公司不是独立样本。
- feedback：一行/冻结预测ID×赛果版本，标签可用时间、实际比分、误差度量；不回写预测。

分析表用tibble，显式键/类型/空表/可空字段。验证源hash、加入关系cardinality、未匹配行及排除计数。发布复用统一versioning生命周期；小型诊断产物在NVMe，NAS分析表经read_dataset/dataset_query读，不直接打开Parquet。

## 判断职责

Skill负责判断：证据可靠性、强弱方向、战意机制、单场交战权重、定性与盘口是否一致、是否调整及手工幅度、不确定性与解释。函数负责执行：数据与引用校验、准入框架调用、统计、数值调整、概率、差异表、冻结与回放接口。不能把叙述误包装为“战意+固定0.1”的自动规则。

当前分类与专家三选候选分别呈现。本例最高与最低差12.615个百分点，代码双选；Top1−Top2=9.676、Top2−Top3=2.939个百分点，专家可认为舍弃第三项不稳。尚未批准新分类阈值，不擅自更改实现。

反馈同时比较纯基本面和市场复核后概率，用log loss/Brier/校准及低比分诊断定位偏差；学习λ修正系数、近期权重、ρ、联赛先验、分类阈值必须在此前窗口、目标身份排除、共享上下文与收据/独立回放内执行。函数的安装、测试、独立审查与示例验收记录见quarto/paju79_probability_package_20261010.qmd；不把代码验证称为概率已校准或已通过PI验收。
