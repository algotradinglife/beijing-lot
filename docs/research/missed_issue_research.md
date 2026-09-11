# 未中期归因与概率偏差研究（进行中）

主策略：纯基线C2/U6/P5/BASE，48期100402–100607。
上一轮已提交推送99a4b76a。实时图：#419由#421阻塞；本研究不能替代其跨年因果验收。

## 固定研究问题

1. 整期没有命中任何组时，各组差几场？单选、双选分别贡献多少错误？
   同一错误场影响多少组？区分独立场次数与持仓重复计数。
2. 全体可用比赛上的普通平、让平、主/客净胜至少2/3球、总进球至少5球，
   纯基线及欧赔+大小球市场比分分布是否系统性偏高/偏低？
3. 联赛/杯赛、让球深度、主客近期进失球、积分差、历史大胜率、市场总进球等
   赛前特征是否解释偏差？所有分组都报告样本量，缺失单列；不把多次比较最显著者当成已验证规律。
4. 固定每期1024元，比较N7压2、N6压2、N6压1、赛前删弱场及固定N6/N7混合。
   同时看整期至少中一组、连续未中、投入、ROI、回撤；持有现金与分散效应分开说明。

## 数据与口径

- 原冻结持仓：cap-depth-grid-v1/plans，使用D2_U6_P5_BASE。
- 全体分母：new48-pure-baseline-v1/factors.json中的可用场次，不只取下注场或未中期。
- 原比分分布：new48-expanded-validation-v1/projected中control$scores；不取专家修正概率。
- 市场比分分布：同一projected中的market$grids，身份、盘口和场次cutoff必须相同。
- 基本面：同一projected的features，批准的Titan主源流程；追溯prepared/inputs及原始清洗凭据。
- 标签：经过原研究绑定的settlement-audit.json；严格issue+slot+provider_id，盘口一致。
- 未中期切片用于解释，不用于判断全体概率校准；重叠场次不能当作独立样本扩充数量。
- 整期标签公开后的归因函数不拟合、不选策略；新选择规则的所有学习必须进入共享temporal_learning。

## 已落实

`r/fundamentals_missed_issues.R::missed_issue_diagnostics`返回腿、组、场次、期次四张tidy表。
`tests/testthat/test-fundamentals-missed-issues.R`覆盖单/双选错误、复用、全中、缺标签、身份重复、盘口错配、非法支持和不完整组。
`scripts/diagnose_missed_issues.R`为只读入口，验证原报告绑定，核对48期命中数并保存数据来源哈希。

## 待完成

基本面及全场比分事件概率的可复用汇总、分层偏差表；N6/N7变种冻结和结算；
完整QMD报告、受影响测试、独立Codex review、阶段提交推送。当前不是已完成验收。

## 2026-09-11 阶段证据与字段风险

原策略48期中25期未中；19期至少一组只差1场，6期最近仍差2场以上。
全场比分事件已投影：2561场普通事件、1223场非零让球的打穿事件。
基线打穿预计23.6%、实际31.2%，市场31.5%；普通平预计25.3%、实际25.6%；
让平预计24.0%、实际25.5%。这些是历史描述，不是显著性或未来修正幅度。

字段风险台账：`features$giving_overall_ppg`名称容易误读为让球方场均积分，
实际在`r/fundamentals_three_issue_experts.R:141`定义为让球方向乘双方积分差。
应展示为“让球方相对接球方近期场均积分差”，不能按球队自身积分高低解释。
`giving_venue_ppg`同理。首轮分层CSV的form列表示此差值的<1.5/≥1.5分层，
正式QMD必须用明确的差值列名；不改写原冻结特征。

新增比分事件接口`src/fundamentals_score_events.py::score_event_rows`及测试通过；
`r/fundamentals_event_calibration.R::event_calibration`及10个断言通过。
事件快照`missed-events-v1/events.json`保留全场features/audit与来源哈希。
剩余工作仍包含基本面完整分层、N6/N7变种、QMD、独立审核和提交推送。

## 固定N6比较初算（待独立验收）

六种方案全量288份计划已在本轮结算前冻结，路径missed-comparison-v1。
N6候选为既有512个N7候选的所有六场子集，加按TOP2概率排序的六场不重叠前缀，
再按TOP2排序、U6/P5扩组。压一/两场均用共享TOP1压缩接口。
删弱场删除原组所选支持概率最低场，保留其他支持，不补组；混合固定512/512且不跨钱包挪钱。

初算：N7整期23/48命中、净收益30678元；N6压1为34/48、2632元；
N6压2为33/48、1201元；删弱场为36/48、7451元，最大回撤4196元。
两种混合均29/48命中，净收益7299/15204元。
命中频率提升没有同步提高收益，N6压2回撤反而高于原N7。不能按整期命中率单独选优。

已新增n6_diagnostic_plan、drop_weak_leg、fixed_n67_wallets、settle_missed_portfolio及对应测试；
R统一汇总missed_strategy_summary及6项断言通过。正式QMD、独立票据复算、完整基本面分层、
Codex审核及提交推送仍待完成；当前汇总不是最终验收结论。

## 完整报告与验证记录

正式入口：`quarto/88_missed_issue_research.qmd`，默认`missed-research-v2`，共11表3图。
十三个基本面维度全部展示样本量、实际频率、预测频率、偏差和Brier；缺失单列。
大让球（绝对值≥2）245场：基线打穿约15.9%，实际71/245=29.0%，市场29.5%。
让1球978场：基线25.5%，实际31.7%，市场32.0%。偏差在大让球场更明显。
现存特征没有独立跨级身份字段；报告没有把杯赛冒充跨级。此项是数据限制，非已验证结论。

- Python：`python -m pytest tests/test_fundamentals_missed_portfolio.py tests/test_fundamentals_n6_diagnostic.py tests/test_fundamentals_score_events.py tests/test_fundamentals_n7_single.py -q`，41 passed。
- R：`testthat::test_file(...,stop_on_failure=TRUE)`运行missed-issues13、missed-summary6、event-calibration13、event-strata6、equity-curves25、drawdown-plot16、pure-report6，共85断言通过。
- 新项目函数各对应同名主题测试文件；没有QMD内函数。Python包含N6选择1函数、组合3函数、比分事件1函数；R包含归因/事件校准/基本面分层/策略汇总4函数。
- `python scripts/check_missed_comparison.py`：288份票据独立返奖及预算复算通过，原N7的48期收益/命中逐期一致。
- `python scripts/check_cutoff_governance.py`：PASS，无新增历史拟合。
- QMD真实输入、归档输入均在新进程执行，无缓存且错误致命；11表3图，已目检回撤图。
- 夹具`tests/fixtures/missed_research_report.json.gz`含所有报告数据；恢复使用既有prepare_n7_single_fixture.py。
- CI新增函数测试、夹具恢复及QMD执行。全仓库`Rscript tests/testthat.R`没有执行：共享工作区含本任务外在研改动，本轮覆盖受影响函数及其依赖，不声称全仓库检查通过。

当前产物完整；最后验收仍需Codex独立审核结论及提交推送。早期段落的“待完成”记载为阶段记录，以本节为当前状态。

## 最终验收

Codex独立只读审核：**No blocking findings**。审核独立重算288份结算、746组弱场删除，
核对钱包、一次0.65、事件分母、汇总与回执；未发现新增历史学习。
审核日志：`data/derived/fundamentals_417/missed-review.txt`。审核子进程无法访问GitHub，
主会话已单独核对实时图；不将本地代码审核当作#421因果验收。
另以Python独立验证全场让平/打穿概率等于原p/q因子，并核对六组资金曲线与整期命中。
当前目标要求的诊断、基本面分层、固定N6/N7对照、函数测试与QMD均已交付；
不变更默认策略、不关闭#419/#421。上述早期“待完成”条目现已由本节验收覆盖。
