# U3/U6 固定单选与组选，双选来源配对比较

交付入口：quarto/109_double_source.qmd。48期100402–100607；本金10万元，期预算1024元，实际闲置现金保留，每组64元，无比分保护、专家或重训练。

用户明确要求保持两者Top1一致的单选，按市场概率筛选，只改变双选使用基线或市场Top2。复用 high-hit-filter-v1 的 U3_ORIGINAL/U6_ORIGINAL 封存计划，全部场次、两场单选、分组和资金不变。每组2A+4D+1C，因此市场变体只替换C一场双选的较低方向；四场D的Top2原本相同。原U/P约束及零让球Top2分歧排除规则保持。C场的组选排名仍按基线Top2质量，不能解释为全市场选场实验。

市场q是欧赔、大小球映射的比分概率投射至北单让球赛果。既有预测被封存为暴露历史证据，未重新拟合。变换接口接受原始共享Cutoff对象，绑定源计划、cutoff、实现闭包与新票据，freeze/settle分阶段；这并不消除此前历史暴露或时间代理问题，不满足新的无泄漏样本验收。#419仍被#421阻塞，本轮不改变生命周期。

|版本|中奖组/总组|命中期/48|投入元|净收益元|投入ROI|最大回撤元|
|---|---:|---:|---:|---:|---:|---:|
|U3 基线双选|35/265|19|16960|19946.49|117.61%|2057.14|
|U3 市场双选|27/265|14|16960|8140.49|48.00%|3200.00|
|U6 基线双选|55/497|19|31808|24713.37|77.70%|4416.06|
|U6 市场双选|56/497|17|31808|24395.22|76.70%|4416.06|

U3明显倾向保留基线双选：替换丢失17个中奖组（返奖19630.95元），新增9个（7824.95元），净损失11806.00元。另18个组双方都中，221个都未中。

U6总体近似持平：丢失20个（25680.08元），新增21个（25361.93元），仅减少318.15元；另35组双方都中，421组都未中。中奖组多1个并未增加盈利，且命中期少2期。这是组层面的配对账目，存在复用相关性，不能当作独立样本显著性证据。

当前样本没有支持统一改用市场双选。对于U3，基线双选的收益、命中期数和回撤均优；U6差距很小，不能据318元差异判断稳定优势。U3和U6组选不同，因此同一替换规则的影响也不同。没有据此修改默认策略或重新选场。

## 实现与检查

- 新接口 src/fundamentals_double_source.py::paired_double_source；tests/test_fundamentals_double_source.py 覆盖源不变、票码全集、单选不变、无投注现金、非法源/模式/cutoff。
- scripts/double_source.py 为 freeze/settle 薄入口，复用共享校验与 settle_n7_twocover 权威结算。
- scripts/check_double_source.py 独立按实际方向和最终SP枚举中奖票码，1524组、192行逐项对账，基线腿及票码复现，净收益对齐原U3/U6。
- R/QMD复用 missed_strategy_summary 与 strategy_equity_curves，不新增R函数。旧组件coverage/value仅为原组选元数据，不用于新的支持概率推断；原组合model_any_hit清空。
- 项目解释器运行 `-m pytest tests/test_fundamentals_double_source.py tests/test_fundamentals_consensus_portfolio.py -q`：17项通过。
- `python3 scripts/check_double_source.py --study data/derived/fundamentals_417/double-source-v1`：全部对账通过。
- `python3 scripts/check_cutoff_governance.py`：通过。
- 报告读取器和汇总器两份R testthat文件：各6项断言通过。全仓测试未运行。
- `quarto render quarto/109_double_source.qmd --execute-dir . --execute --no-cache`，源快照及独立归档均在新进程执行；CI新增可移植fixture与渲染入口，远端CI不在本地通过声明内。

阶段诊断：前/中/后各16期，U3基线ROI为37.32%/94.34%/300.56%，市场为42.83%/44.49%/63.66%；U6基线14.63%/106.54%/120.71%，市场58.21%/88.18%/83.97%。市场前段更好，中后段较差；不据此做事后切换。源与归档CSV逐字节一致，HTML表格4/12/192行和两张曲线齐全，收益及回撤图已视觉检查。

独立Codex review通过：无可执行发现。审核者独立通过17项Python测试、治理扫描、12项R断言及192行结算核查，并核对1524组的源/cutoff绑定、配对不变和票码。未重跑渲染或全仓测试。日志 data/derived/fundamentals_417/double-source-review.txt。
