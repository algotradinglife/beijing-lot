# Top2 基线的可复用评测

这些方案是资金效率与覆盖优化的对照基线。第三赛果购买权重不是经过校准的新概率。
比较同时保留预算、实际投入、现金、整体覆盖、命中期数、收益、ROI和回撤。
不能用各组命中概率之和代表整期至少一组命中的概率。

## R 接口

`r/n7_top2_coverage.R` 提供：

- `n7_top2_options(bundle, cutoffs, python, model_id, policy, third_penalty,
  target_coverage, group_cap, unit_cny, payout_factor, minimum_sp)`：单个方案。
- `n7_top2_batch(bundle, cutoffs, python, model_id, policies, third_penalty,
  target_coverage, group_cap, unit_cny, payout_factor, minimum_sp)`：同一输入上的多个方案，
  返回以方案名为键的列表，每项结构与单方案接口相同。
- `n7_top2_allocate(prepared, cutoffs, seed, worlds_count, budget_cny, max_actions)`：
  调用既有联合选组器；随机种子、模拟次数、预算均显式传入。

批量接口每次只执行一次原生时点校验和组合表准备，各方案调用同一个
`n7_top2_transform()` 内部实现。没有持久缓存、隐藏全局状态、跨期模型复用或重复业务实现。
调用方不应自行构造内部 transform 所需的已校验基础对象。

`policies` 可含 PROB、SOFT、HARD、FULL，但不能重复或为空：

| 方案 | 购买顺序 | 准入 |
|---|---|---|
| PROB | 原组合概率降序 | 达到目标真实覆盖的最小前缀，受组金额上限约束 |
| SOFT | 每出现一个第三赛果，组合购买分数乘 `third_penalty` | 同上；真实覆盖仍使用原概率 |
| HARD | 仅保留各场原 Top2，按原组合概率排序 | 同上；达不到目标则不买该组 |
| FULL | 买齐128种原 Top2组合 | 仍需达到目标真实覆盖且不超过金额上限 |

固定原组选项使用 `r/third_outcome_tickets.R` 的
`third_outcome_ticket_plan()` 与 `third_outcome_ticket_settle()`。
前者不读结果，后者必须在计划冻结后调用。
DISCOUNT50 把原第三赛果一半购买权重移给原第二赛果；HARD只允许原Top2。
它们保持原PROB选中的组和票数，不重新执行25%覆盖准入，故应与完整选组方案分开解释。

`r/n7_baseline_comparison.R` 提供
`n7_baseline_comparison(periods, issue_order, stage_order, baseline_policy, initial_capital_cny)`。
它只分析已冻结、已结算账本，不进行拟合或选策略。返回：

- `curves`：合计账户和各分段独立账户，均含初始资金行；
- `summary`：投入、净收益、ROI百分比、命中/盈利期、中奖组数、现金、回撤、最低资金、去最大盈利期净收益；
- `paired`：各段相对指定基线救回/丢失的命中期和净收益变化。

输入必须完整保留零投注期。零投入ROI为NA；身份、分段映射、账务或资金不足时失败，
不把无法支付的计划当作已执行收益。阶段和期序由参数明确提供，不能由收益高低分组。

## QMD 入口和证据链

1. `quarto/177_top2_outside_validation.qmd`：读取绑定哈希的既有输入，按共享时序库冻结模型与四种基线计划，随后结算。
2. `quarto/178_top2_outside_fixed.qmd`：验证前一步凭据与独立重放结果，生成固定原组的三个购买规则，再结算。
3. `quarto/179_top2_outside_conclusion.qmd`：读取明确绑定的结果，调用汇总接口，画收益/回撤图、做价格桥接和独立模拟覆盖。

运行时提供项目 Python、输入目录、输出目录及要求的哈希参数；从仓库根执行，
显式使用 `--execute-dir` 和 `--execute-params`，不依赖RStudio变量或工作区恢复。
输出目录必须是新的版本化持久目录，不能覆盖冻结结果。
先执行持久化布局检查，最后执行对应测试、独立重放、完整QMD渲染和Codex review。

本轮配置 `config/top2_outside_validation.json` 固定390评价期。494期快照中最早10期用于预热，
94期已研究回撤窗口不计入评价，但计入每10个连续历史期更新一次的时钟，共49个模型块。
截止前历史仍通过共享时序库准入；最后场次加48小时仅为历史诊断标签时间代理。
新增数据应建立新的明确输入与配置，不能直接修改已验收快照或复用不匹配的模型缓存。

## 性能与一致性

对真实100708期，重构前四次单方案准备和批量准备的完整返回对象逐项完全一致。
一次测量分别为3.796秒与2.585秒，局部减少约32%；不是全程加速率或统计性能保证。
单方案和批量接口共用同一个转换实现，测试还覆盖非法方案、重复方案、空候选、
模型/时点/场次身份不匹配。后续提速需要继续提供真实数据等价性和耗时证据。
