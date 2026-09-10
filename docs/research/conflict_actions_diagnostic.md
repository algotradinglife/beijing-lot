# 冲突处理三阶段固定规则研究

主报告 `quarto/62_conflict_actions.qmd`；输出 `data/derived/fundamentals_417/conflict-actions-v1`。
活跃研究属于实时Issue #417；开始前读取为OPEN、PI Review、无依赖。
没有关闭Issue、改生产规则或重训练专家。独立Codex review与证据封存在输出目录。

## 合同与执行顺序

所有方案沿用同一已揭示40期/2313场。版本固定让平1.1.0×0.5及同一前32期高净球模型×0.5，
来源是已验收 `decision-chain-conflict-v1` 与 `integration-weight-v3`。
市场q来自赛前欧赔+大小球比分映射，估算SP=1/q；最终SP只用于结算。
基础策略为概率+集中、双选7串1、每组128票、每票CNY2、最多6组不重叠、一次票级0.65。
冲突是市场Top1不在模型Top2；并列W/D/L，按native slot/provider稳定排序。

1. REESTIMATE：只在冲突场对完整比分分布做50%/100%市场混合，非冲突保持。
   无重新拟合。边际沿用冻结精度并与比分求和核对至1e−12，CURRENT票据精确保持。
2. EXPAND：每组扩一场或所有冲突场为三选。额外预算保留所有原组；固定预算按原组顺序
   买得起才保留完整组，再把余额均匀分为整数票注，余数依固定seed=0的SHA256顺序分配。
   不完整购买复式不是“全选”；所有组均买不起时保持现金。
3. PROTECT：现有反概率专家的四叶最高0.452830<0.6正向阈值，严格门控不触发。
   这是封存模型全叶上界证明，不是当前40期逐行推断。旧包缺完整树，不用两位小数规则
   重建、不重训。另列非专家门控对照：只为入选冲突场买一个未选方向精确比分，每场CNY2。
   排除“其他”桶，避免跨让球方向。EXTRA追加；FIXED去末组，用其预算保护保留场并再投主串关。
   单组无资金空间/保留组无候选时不改变原组合。

三个阶段分别继承CURRENT，不把阶段赢家叠加下去，不根据训练/验证/测试收益选策略。
每阶段全部计划和决策回执落盘后，才读取原R/SQLite审计；本轮没有重新查询数据库。
新增48期不在本研究。原训练32期中8期无当前回放时钟，46端点缺市场，沿用原范围。
所有上游旧专家/市场/基本面派生是已登记诊断证据，不能视为前瞻合规接口；
逐场时钟也不证明共同购票时刻可执行。

## 结果和归因

历史TEST8，CURRENT投入11,008元，ROI33.75%，最大回撤2,165.25元。

|处理|测试ROI|最大回撤元|说明|
|---|---:|---:|---|
|市场混合50%|21.64%|4,352.00|冲突场比分log loss/WDL Brier改善，但收益下降|
|市场混合100%|27.93%|4,354.17|同上|
|每组扩一场EXTRA|2.34%|3,649.75|投入15,360，新增投入增量ROI−77.11%|
|全部冲突EXTRA|−4.41%|4,099.77|投入19,488，增量ROI−53.94%|
|两种三选FIXED|−11.51%|3,099.30|测试段结果相同，不据此合并政策定义|
|原专家POSITIVE门控|33.75%|2,165.25|无正向叶，严格零比分下注|
|冲突比分EXTRA（非专家）|33.78%|2,151.59|比分51笔共102元、净赚37.48元|
|冲突比分FIXED（非专家）|58.20%|2,878.85|减少主串关组并重分配资金，不能仅归因比分|

EXTRA比分训练/验证净亏28.39/20.61元。固定资金方案引发归因疑问后，另加
**事后归因**：相同保留组、相同支持，把全部预算投入主串关，不买比分。
该对照测试ROI57.27%，已经接近带比分58.20%；训练22.82%对带比分23.23%，
验证75.00%对带比分75.38%。主要变化是减少末组和重新分配主串关资金。
这项控制不是事后挑选出的可部署策略，且验证表现低于CURRENT98.22%。
完整600条期次×方案记录、分区收益/回撤、独立比分损益与概率误差在QMD。
初始归因目录 `attribution` 保留为中间证据，修正移除场数统计的最终目录为 `attribution-v2`。

结论：NO_RULE_PROMOTION。不恢复常规比分保护，不默认混合或三选。
保留概率误差改善线索和资金分配归因供新数据检验；保护专家导出缺口登记DQ-023，交独立模型会话。

## 函数与历史学习清单

|层|实现|约束/测试|
|---|---|---|
|冻结分布重建|R既有 `signal_rate_score_choices` → `project_signal_rate_grid`|旧纯投射接口作为诊断依赖；R输入/实现hash，之后共享Cutoff逐场复验；不采用该旧函数的选场输出|
|比分混合|`conflict_score_projection`|精确schema、整数比分、p/q归一化、原边际核对；显式Cutoff；无拟合；输入和参数seal|
|比分候选|`conflict_score_offer`|仅未改CURRENT分布；选未选方向的合法精确比分；权威 `expected_option` 映射；Cutoff/seal验证|
|基础选场|既有 `rank_double_candidates`、`n7_baseline_plan`|同概率集中规则；无未来标签；显式逐场Cutoff|
|完整票池资金|`fund_complete_plan`|显式Cutoff、CNY2预算、seed；完整支持每票至少1注，余数固定hash；不拟合|
|三选|`expand_conflict_plan`|显式Cutoff；核对固定市场冲突、方向、身份；ONE/ALL、EXTRA/FIXED独立对照|
|比分资金|`conflict_protection_plan`|显式Cutoff；精确比分保护方向、价格、身份；固定重投，不用最终SP|
|专家上界|`reverse_positive_ceiling`|共享Cutoff须晚于模型且非训练期；验证receipt seal、四叶支持与Laplace比例；若可发正向则失败要求真实推断，不伪造信号|
|结算|既有 `settle_n7_baseline`；新 `settle_conflict_protection`|只读原审计；一次0.65；中奖SP缺失pending，身份/比分错配失败|
|统计|R `conflict_action_tables` 调用既有 `integration_weight_summary`|无学习；分区ROI、CNY回撤、比分/增量损益、完整逐期表、Brier和score log loss|

新Python函数都在 `tests/test_fundamentals_conflict_actions.py` 有测试，包括后验标签/SP变更
不影响支持/票据、无资金完整组、不买比分情况、边界门控、报价/身份/时钟错误。
R函数在 `tests/testthat/test-fundamentals-conflict-actions.R`，包括归因与概率评分。
无新历史fit、窗口选择、时钟工具或跨cutoff缓存。源hash、Cutoff、参数和传递实现由共享框架绑定。
独立checker不调用新投射/三选/比分决策函数，自行重建480方案、6939概率记录和40个归因计划。

## 复现

显式设置项目Python/R库，仓库根目录运行；新输出目录由封存contract声明源路径、版本、规则与预算。

```sh
Rscript scripts/prepare_conflict_action_scores.R <parent-study> <new-study>
"$PROJECT_PYTHON" scripts/run_conflict_actions.py --study <new-study> --stage REESTIMATE
"$PROJECT_PYTHON" scripts/run_conflict_actions.py --study <new-study> --stage EXPAND
"$PROJECT_PYTHON" scripts/run_conflict_actions.py --study <new-study> --stage PROTECT
"$PROJECT_PYTHON" scripts/attribute_conflict_score_funding.py --study <new-study> --output <new-attribution>
"$PROJECT_PYTHON" scripts/check_conflict_actions.py --study <new-study> --attribution <new-attribution>
quarto render quarto/62_conflict_actions.qmd --execute-dir . --execute --no-cache -P study:<new-study> -P attribution:<new-attribution>
```

不新增依赖；使用既有NumPy/pandas、标准库itertools、tidyverse及项目SQLite审计/结算实现。
旧N7资金接口仅支持固定432元/组，不能表达不同完整票数的同总预算分配；新增函数只补此能力，
不另写优化器或求解库。CI新增函数测试、cutoff治理与可移植离线QMD fixture；fixture只重放呈现，
不宣称运行模型或采集数据。远程CI是否执行与Codex verdict在验收文件单列。
