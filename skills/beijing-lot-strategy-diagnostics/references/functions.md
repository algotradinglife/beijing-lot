# 诊断函数索引与输入契约

从当前 beijing-lot 仓库根目录 source 下列文件，先查看文件头的契约和对应测试。函数对象不是新旧业务的兼容包装；使用原实现，源码缺失时报错，不自动回退到个人目录或重新抓取。

| 问题 | 权威接口（仓库相对路径） | 输入/输出要点 | 对应测试 |
|---|---|---|---|
| 冻结概率读取 | `src/strategy_diagnostic_inputs.py::read_diagnostic_fixtures(catalog_path,catalog_sha256)` | 绑定catalog及每个bundle哈希，返回唯一场次rows与source_hashes；保留字符串ID；无标签、网络和写入 | `tests/test_strategy_diagnostic_inputs.py` |
| 分类概率与校准 | `r/strategy_diagnostic_probabilities.R::strategy_probability_diagnostics(frame,strata,outcomes,breaks)` | 长表：issue/slot/provider_id/model/outcome/probability/actual_outcome，加显式分层列；每个模型同场次、每场完整类别；返回scores/summary/calibration；实际类别概率0时log loss为Inf | `tests/testthat/test-strategy-diagnostic-probabilities.R` |
| 构成与同类变化 | 同文件 `strategy_composition_diagnostics(frame,reference,target)` | segment/stratum/value，一行一个观察；返回ledger/cells/summary；两期必须有相同分层支持；顺序依赖非因果分解 | 同上 |
| 单场价格差 | `r/n7_fixture_price_diagnostic.R::n7_fixture_price_diagnostic(fixtures,audit)` | 唯一issue/slot/provider_id，p/q WDL、handicap；audit含actual_direction/spf_sp/spf_source_sha256/status；校验身份，返回actual_q、estimated_sp、price_ratio | `test-n7-fixture-price-diagnostic.R` |
| 精确损益桥接 | `r/n7_return_attribution.R::n7_return_attribution(funded,evidence,unit_cny)` | funded有issue/arm/seed/sleeve_id/depth/stake/expected_gross/coverage/copies；evidence有actual_rank/estimated_actual_payout/actual_gross_cny；两个payout已含票级因子，勿重复乘；返回groups/periods | `test-n7-return-attribution.R` |
| 分段与价格尾部 | `r/n7_return_diagnostics.R::n7_return_diagnostics(rows,groups,issue_order,initial_capital_cny,block_size,coverage_breaks)` | 完整含现金期账本和桥接列；复用 `strategy_equity_curves`、`n7_sweet_union_summary`，先source对应文件；返回summary/curves/blocks/calibration/price_tails/bridge | `test-n7-return-diagnostics.R` |
| 收益与回撤 | `r/fundamentals_equity_curves.R::strategy_equity_curves(periods,issue_order,initial_capital_cny)` | 逐期金额、model/policy/status/cash_cny；显式期序和本金；停投与计划影子账本分开 | `test-fundamentals-equity-curves.R` |
| 候选排名 | `r/n7_rank_diagnostic.R::n7_rank_diagnostic(x,unit_cny,payout_factor,targets)` | 已冻结候选的curves/audit/fixtures/sleeves/cutoffs；输出实际中奖排名、覆盖成本、累计概率等事后参照 | `test-n7-rank-diagnostic.R` |
| 累计覆盖与成本 | `r/n7_coverage_diagnostic.R::n7_coverage_grid(ranks,targets,caps_cny)` / `n7_coverage_summary(rows)` | 目标累计概率、开组金额限制显式传入；描述已有候选；不能把事后最优行当赛前选择 | `test-n7-coverage-diagnostic.R` |
| 选组重叠 | `r/n7_selection_diagnostics.R::n7_selection_overlap(rows,funded,membership)` / `n7_selection_blocks(rows,issue_order,block_size)` | 绑定同一候选宇宙的组/场次membership；不要直接跨宇宙比较sleeve_id | `test-n7-selection-diagnostics.R` |
| 换组归因 | `r/n7_exchange_attribution.R::n7_verify_attribution_groups(groups,predictions,funded,ranks)` 后 `n7_exchange_attribution(groups,plans,issue_order,trim_k)` | 先重算组账；再分救回/丢失/共同命中及换入回款压力，输入变体遵循原函数约定 | `test-n7-exchange-attribution.R` |
| 分队列诊断 | `r/n7_expanded_diagnostics.R::n7_expanded_diagnostics(rows,issue_order,initial_capital_cny,block_length,probability_breaks)` | 当前七策略账本，需要JOINT对照；summary/curves/paired/blocks/reliability，不能当任意arm通用接口 | `test-n7-expanded-diagnostics.R` |
| 公平组去极值 | 同文件 `n7_expanded_group_trims(groups,plans,trim_k)` | 已核对的完整组/计划账本，剔除自身最大盈利组的成本和回款，保留其他期 | 同上 |
| 补组与现金 | `r/n7_sp_refill_diagnostics.R::n7_sp_refill_diagnostics(rows,issue_order,initial_capital_cny)` | 补组实验专用账本，原计划和增量分开；不是自动补组函数 | `test-n7-sp-refill-diagnostics.R` |

除注明 `tests/` 完整路径外，R测试位于 `tests/testthat/`。新增函数必须对应正常、边界和失败路径测试；不要用只匹配文案的测试代替行为验证。

## 结构与单位

- 场次表：一场一行，issue/provider_id为字符串，slot为整数；同一场可有多个模型，但模型标签不能与真实赛果冲突。
- 概率表：一场×模型×类别一行，概率为0–1；各场各模型类别完整且总和为1。类别顺序决定并列排序；不得由实际结果打破平局。
- 组表：issue/arm/seed/sleeve_id唯一；在同一候选宇宙才可比较前缀。copies明确，depth是购买票数，不是净胜球或串长。
- 期账本：issue/arm/seed唯一，须完整保留零投注期。期序来自显式清单，不能依赖CSV当前行序。
- 金额为CNY，SP为无量纲；ROI用实际投入为分母，零投入为NA。正负净收益、命中和盈利期是不同概念。
- `fixture_slots` 是逗号分隔的标识串，读取CSV必须显式设为字符，否则readr可能将其当带千分位的数字，破坏组身份。

## 调用入口

可执行示例：`quarto/160_strategy_diagnostic_handbook.qmd`。参数study绑定已验收的#459快照，python为项目解释器，output为持久化审计输出目录。QMD展示真实36,573场概率诊断、让球类别构成分解和495期损益桥接；这些是方法演示，不是新模型训练。

其他实验按函数契约传入自己的显式快照，不依赖该示例的个人路径、研究期数或模型名字。既有专用函数不匹配新实验结构时，先明确差异，再补最小受测能力；不要用随意重命名掩盖业务语义不同。

## 必需输入凭据校验

`r/n7_component_accounting.R::n7_component_accounting(groups,plans,issue_order,threshold,unit_cny,initial_capital_cny)`
按固定Top128覆盖边界拆分已结算票账本，核对金额、实际前缀命中和完整期账，返回MAIN/LOW/ALL及
与MAIN逐期同投入的分数资金SCALED_ALL对照。只做事后资金归因；不输出未来筛选器或新增票。
最大回撤不能按分量相加，固定128注与实际买入深度必须区分。测试为
`tests/testthat/test-n7-component-accounting.R`，报告为`quarto/165_main_component_diagnostic.qmd`。

`r/strategy_distribution_shape.R::strategy_distribution_shape(fixtures,members,n_legs,prefix_depth)`
精确枚举已冻结组的三赛果独立乘积，比较p/q的Top1–Top2差、熵、实际惊讶度、
预期中奖排名、实际排名并列区间与固定前缀覆盖；单场去重和组重叠须分开报告。
实际惊讶度减熵不是因果归因，也不排除组内依赖。对应测试
`tests/testthat/test-strategy-distribution-shape.R`；入口`quarto/163_distribution_shape_diagnostic.qmd`。

`r/strategy_handicap_diagnostic.R::strategy_handicap_diagnostic(frame,strata,outcomes,breaks)`
复用分类概率验证器，按显式让球数、阶段和赛果统计预测/实际发生率、偏差、
Top1准确率、Top1/Top2召回率与Top2漏选数。正让球加到主队比分；
并列按outcomes顺序；无预测/实际发生时条件率为NA。纯描述性，不拟合或选参数。
测试为`tests/testthat/test-strategy-handicap-diagnostic.R`，入口为
`quarto/162_handicap_probability_diagnostic.qmd`。图中稀疏格子可以不显示，CSV完整保留。

`strategy_verify_diagnostic_inputs(root, hashes, required)` 位于
`r/strategy_diagnostic_probabilities.R`；对每个必需文件要求非空、单值 SHA-256，
并核验本地文件内容。遗漏条目、无效哈希、文件缺失或内容变化均停止。
只读，成功返回 invisible TRUE；由同模块的 testthat 文件覆盖。

## 最近阶段与候选池结构

- `r/n7_recent_structure.R::n7_diagnostic_stage_map(plans,issue_order,reference_issues,initial_capital_cny,block_length)`：单方案完整期账本，显式参考期前缀；返回固定分段、事后最大回撤窗口、恢复信息及资金曲线。没有未来状态识别或学习。
- 同文件 `n7_diagnostic_group_structure(fixtures,funded,ranks,map,unit_cny,payout_factor,n_legs,minimum_sp,cap_cny)`：核对7场成员和实际SP乘积回款，复用损益桥接，对比已选组与同条件25%覆盖候选池；缺成员、错回款或不匹配参数停止。组数不代表独立样本。
- 同文件 `n7_diagnostic_supply(plans,fixtures,ranks,map,minimum_sp,breaks)`：逐场重算SP合格数、核对可用场次和账本差异，统计合格组、下注组、现金与分箱收益；现金期不丢弃。
- 同文件 `n7_diagnostic_depth_distribution(ranks,funded,map,unit_cny,rank_breaks,extra_depths)`：分全部/合格/已选组统计中奖排名分位数、组等权和期等权CDF、未中组距中奖组合所差票数；不执行加深或改变预算。
- 四函数测试：`tests/testthat/test-n7-recent-structure.R`。真实调用及证据结论：`quarto/161_recent295_strategy_diagnostics.qmd`。
