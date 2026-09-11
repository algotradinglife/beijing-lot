# 固定预算互补策略诊断

48个已暴露历史期100402–100607；纯基线、每期预算1,024元、初始资金100,000元。
主策略C2/U6/P5/BASE。2026-09-11，本轮不是新测试或因果验收，不完成#421，也不改变默认策略。

## 结果

| 实际钱包组合 | 净收益元 | 预算ROI | 最大回撤元 | 实际投入元 | 辅策略独立相关性 |
|---|---:|---:|---:|---:|---:|
| 原主策略1024 | 30,678.31 | 62.42% | 8,470.38 | 47,744 | — |
| 主768 + C2/U16/P6/SINGLE75 256 | 31,871.87 | 64.84% | 8,214.38 | 48,768 | 0.329 |
| 主512 + C2/U6/P4/BASE 512 | 33,154.36 | 67.45% | 8,305.62 | 49,152 | 0.982 |
| 主512 + C2/U2/P4/BASE 512 | 21,730.02 | 44.21% | 4,288.00 | 39,936 | 0.608 |
| 主768 + RANDOM_Q64_S41911 256 | 22,888.54 | 46.57% | 5,389.90 | 48,768 | 0.619 |

精确相关性见QMD和结果表；上表后三行是用于解释权衡的事后示例。
独立相关性按逐期净收益计算，不使用累计曲线。75%替换辅策略单独收益41,508.04元、
回撤9,216元，在主策略亏损期合计盈利7,302.08元，确有不同的结果暴露。
然而组合最大回撤只减少256元（3.0%），剔除相对主策略增益最大一期后，组合增益变成−9,385.18元。
低相关性没有自动转化为稳健的回撤改善。

U6/P4组合增加收益2,476.05元、回撤减少164.77元，但源相关性0.982，属于相近持仓微调。
剔除最大配对增益期后增益为−303.06元，不是强互补证据。
U2/P4组合回撤下降49.4%，但收益只保留70.8%，实际投入仅保留83.6%；不能把全部改善归因于分散。
随机seed41911的75/25组合回撤下降36.4%、收益保留74.6%，实际投入没有减少，值得记录；
但该辅策略独立亏损3,069.32元，另外两个seed的同权重组合回撤为8,767.57/8,803.19元，
并不复现其改善，不能只选中间seed宣布成功。

目前不替换主策略。后续若研究互补，重点应是固定质量范围内的不同比赛/票据暴露和共同亏损，
而不是挑历史最好的seed；seed集合和权重需在严格cutoff之前确定。当前48期已全部暴露。

## 方法与复用

155候选（既有148个 + 3候选池seed + 3高概率池随机选组 + 1联合覆盖），
每个独立、50/50、75/25，外加MAIN，共466×48=22,368份实际计划。
两条独立进程分片生成，全部冻结后再打开本轮结算；相同持仓只结算一次组件，提高效率。
钱包固定且不互转，整组购买，完全相同持仓去重后继续扫描，不把全额收益线性加权。
无额外跨策略U/P限制；部分重复基本注分别付费结算并记录数量。新随机候选列表额度不是实际投注额度。
全部组2元基本注、0.65仅在整张中奖七串一上乘一次；结算SP只用于结算。

- Python四个复用函数：`src/fundamentals_complement.py`，生成/目录去重/分配/结算。
- R描述汇总：`r/fundamentals_complement.R::complement_summary`，输入已结算逐期tibble。
- QMD：`quarto/87_complement_portfolios.qmd`，8张表、16幅收益/回撤/散点图、逐期ROI。
- 薄入口：`scripts/complement_grid.py`，阶段init/freeze/seal/settle/report；每阶段拒绝覆盖已有结果。
- 独立复算：`scripts/check_complement_grid.py`，完整基本注、钱包、源顺序、去重、返奖和旧148方案回归。
- 输入/代码/参数/冻结计划绑定：`data/derived/fundamentals_417/complement-grid-v1`。
- 可移植归档：`tests/fixtures/complement_report.json.gz`；仅报告重渲染，不是完整模型重放。

生成/组装接口显式使用共享Cutoff并验证原输入身份，无新增历史拟合；原算法及其时间证据仍为已暴露诊断。
新时期的seed、权重、策略选择必须走共享`src/temporal_learning`，此接口不授权因果/前瞻使用。

## 验证

- `python -m pytest tests/test_fundamentals_complement.py tests/test_fundamentals_n7_single.py tests/test_fundamentals_compression_breadth.py tests/test_fundamentals_compression_bridge.py -q`：69 passed，使用项目固定测试环境。
- 新四个Python函数→`tests/test_fundamentals_complement.py`三项复合契约测试；另有22,368份独立复算。
- 新R函数→`tests/testthat/test-fundamentals-complement.R`17断言。
- R依赖`equity-curves`25、`pure-report`6、`drawdown-plot`16断言通过，共64断言，使用`testthat::test_file(...,stop_on_failure=TRUE)`。
- `python scripts/check_complement_grid.py --study data/derived/fundamentals_417/complement-grid-v1`：22,368通过，原148策略逐期结果一致。
- `python scripts/check_cutoff_governance.py`：PASS。
- QMD在新进程执行、无缓存，真实输入与恢复归档各渲染一次通过；HTML含8表16图，目检回撤图。
- 另外以Python独立核对全部466组R财务、相关性、共同亏损、尾部汇总通过。
- CI新增对应测试、归档恢复与QMD执行步骤。

首次pytest在`/tmp`配额耗尽时出现13项子进程失败；迁移临时目录到工作区后同一69项全部通过。
未运行仓库全量`Rscript tests/testthat.R`：共享工作区包含本任务外的在研变更与外部数据测试；
本次运行受影响R函数及依赖的四个文件，没有把未运行的全仓库检查称为通过。
Codex独立只读审核结论：No blocking findings。审核另外核对了暂存实现与冻结工件哈希、归档身份及466份汇总；审核不冒充重新执行测试。最终审核记录在`data/derived/fundamentals_417/complement-review.txt`。#419仍由#421阻塞，本轮不关闭任何Issue。
