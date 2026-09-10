# 冻结专家的整合权重诊断

本研究只优化整合层。让平 1.1.0 和前 32 期训练后的高净球 `100305/frozen-experts.pkl` 固定；不训练专家，也不以本研究收益重写其概率。报告入口为 `quarto/60_integration_weight_returns.qmd`，最终数据目录为 `data/derived/fundamentals_417/integration-weight-v3`。v1/v2 为中间诊断证据，不作为最终验收版本。

## 固定口径

- 让平权重 0、0.1、0.25、0.5、0.7、0.75、1；高净球权重固定 0.5。让平权重 0 不等于无专家基线。
- 赛前 SP 代理固定为欧赔＋大小球映射结果概率 q 的倒数，权重变化不得改变 q。逐场按模型概率取两个方向，以 `sum(p/q)/2 - penalty*w^2` 选权重。同分选更低权重。这是局部目标，不是全局组合最优声明。
- 惩罚网格固定 0、0.01、0.025、0.05、0.1、0.25、0.5、1。验证期按净收益选择，同分选更大惩罚；不在测试期重新选规则。
- 7 串 1，覆盖概率排序、连续七场集中分组，最多六组、组间不重叠，每组 128 注，每注 2 元，仅一次票级 0.65。沿用用户已授权的最多六组预算，实际下注最高 1,536 元，不买比分保护。
- 原训练期可回放的 24 期是训练内诊断。100305—100312 八期验证；100313、100314、100315、100316、100317、100318、100319、100401 八期测试。这些历史数据已被查看，不能称为未见的前瞻测试。
- 2,359 个专家端点中，46 个缺少可用市场分布，被所有规则一致排除。原因逐行保存在 `scope-exclusions.json`。

## 调用与历史学习清单

| 层 | 实际调用 | 约束／证据 |
|---|---|---|
| 专家 | `load_calibrated_draw`、`predict_calibrated_draw`、`predict_experts`、`predict_signal_rates` | 冻结文件／版本／源码校验；只调用预测，分别取 w=0、w=1；每批明确 Cutoff；不 fit |
| 分数投射 | R `signal_rate_score_choices`、`project_signal_rate_grid`、`score_coverage_choices` | 从冻结端点生成各权重的完整比分投射，再聚合 W/D/L；高净球版本不变；R 实现哈希在生成前记录并在结束时核验 |
| 市场代理 | R `ev_candidate_factors`，旧研究的 Euro+OU 分布 | 不读取结算 SP；q 在各权重下相同；旧归档市场和基本面分布属于被明确列入清单的诊断输入，不授予前瞻资格 |
| 权重路由 | `select_integration_weights` | 只接受无标签的精确列集及共享 Cutoff 对象；返回参数、概率输入、截止时间回执；不学习专家 |
| 票据 | `rank_double_candidates`、`n7_baseline_plan` | 沿用单一实现，固定参数与每场 Cutoff；不以标签挑票；保存全部候选计划后才结算 |
| 惩罚选择（本轮唯一新增学习） | `select_integration_penalty` → `prepare_learning_context` | 输入只为验证期逐期收益；共享 AvailabilityFilter、PartitionPolicy、WeightingPolicy、实现闭包和 cache key；ESS 最低 8 个独立期次；绑定 R 投射、诊断标签时钟、规划／结算与运行入口 |
| 标签时钟 | 共享 `diagnostic_label_clock` | 最后截止时间＋6小时的历史代理；非观察到的结算发布时刻。必须早于目标 cutoff，否则失败 |
| 结算 | `settle_n7_baseline` | 已保存的 R/SQLite 审计；训练／验证／测试分开，冻结惩罚后才读取测试审计；绑定实际读取字节哈希 |
| 报告 | R `integration_weight_summary` | ROI=净收益/实际投入，按期排序计算 CNY 最大回撤；不学习、不选策略 |

不使用学习缓存。固定端点保留原始逐场截止时间；惩罚回执有 cutoff、最大来源／标签时间、验证期分区、权重账本、ESS、参数和依赖闭包。测试标签修改不进入权重路由；测试覆盖目标／未来标签变更，以及改变最终 SP 和赛果后票据支持不变。训练上的 `SELECTED_PENALTY` 仅是事后查看同一已选参数，不能认为训练期当时已选定该规则。

所有输出属于逐场截止时间的历史回放，不能证明同一张票在同一购买时刻可执行。参考问题总账 DQ-018（ABSTAIN 仍影响概率）、DQ-021（精度导致集中分组变化）和 DQ-022（市场门控排除）。不根据这些已查看的测试收益直接建议部署。

## 重放顺序

在仓库根目录，显式使用项目 Python 和已配置的 R 库，不在运行时安装依赖。

1. `scripts/prepare_integration_weight_endpoints.py --output <新目录>/endpoints.json`：冻结专家端点。
2. `scripts/prepare_integration_weight_candidates.R <Python路径> <新目录>`：声明所需 contract、分区审计清单和 high 输入后生成权重候选。只读取冻结预测；R 代码依赖写入输出。
3. `scripts/run_integration_weight_diagnostic.py --study <新目录>`：要求未存在计划目录，生成不可覆写的计划、验证选择回执及分列结算结果。
4. `scripts/check_integration_weight_results.py --study <新目录>`：独立核对固定 q、逐场最优权重、选场／分组、实际返还和验证选择。
5. 干净渲染 QMD、Codex review 后用 `scripts/seal_integration_weight_study.py --study <新目录>` 固化最终依赖和数据哈希。

函数测试：`tests/test_fundamentals_integration_weight.py`、`tests/test_integration_weight_script_contracts.py`、`tests/testthat/test-fundamentals-integration-weight.R`。专家参数接口及治理检查继续使用既有测试。中间版本结果不替代最终版本的依赖核验。
