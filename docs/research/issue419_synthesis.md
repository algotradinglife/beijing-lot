# #419 阶段收尾分析与验收缺口

分析入口：[QMD81](../../quarto/81_issue419_synthesis.qmd)。本文件是其摘要、证据索引与复现说明。
实时状态以 [Issue #419](https://github.com/algotradinglife/beijing-lot/issues/419) 的原生图和Project字段为准。
本次不把历史收益冠军升级为生产策略，不改动#210/#218。

## 结论

纯基线压两场、概率排序、赛果不替换，配合适度复用限制，值得作为下一阶段的固定候选。
但现有2010年40期与后续48期均为已暴露研究，不能满足原合同的严格因果跨年份验收。
本阶段报告可以验收，整个#419不能据此认定已完成。

最新48期统一预算49,152元，初始本金100,000元，单组两场单选、五场双选，32张基本票×2元。
不使用专家或比分保护，0.65只在命中票的七场SP乘积后计算一次。

|条件U/P|实际投入|净收益|预算ROI|最大回撤|前24期净收益|后24期净收益|
|---|---:|---:|---:|---:|---:|---:|
|原放宽16/6|49,152|23,809.10|48.44%|9,842.01|27,462.40|-3,653.30|
|收益候选6/5|47,744|30,678.31|62.42%|8,470.38|33,768.35|-3,090.04|
|折中候选6/4|48,000|28,458.13|57.90%|7,689.55|33,819.11|-5,360.97|
|低回撤候选2/4|34,560|15,536.90|31.61%|3,747.41|10,014.26|5,522.64|

U是单场进入不同七场复式的上限；P是任意两组的共同场次数上限。它们不是基本票数量。
U2/P4相对同实际投入原方案增加收益2,771.09元、减少回撤2,447.62元；剔除自身最大盈利期仍盈利10,648.40元。
所以不能把低回撤完全解释成少买，也不能忽略该条件是在37种历史比较后被关注的选择偏差。
U6/P5原始收益最高，但后半段亏损；不宜仅按总ROI认定它优于低回撤候选。

## 对此前研究的解释

1. **压一场与压两场的结论并不矛盾。** QMD69在40期专家整合概率、各方案实际投入55,040元、重新按压缩后概率选组的合同下，压一场QUALITY净收益31,181.03元，压两场QUALITY仅615.46元。后续纯基线48期、保留不重叠前缀再扩组的合同不同，不能只归因于压缩深度。
2. **增加组数不等于增加独立覆盖。** 同一场或同一单选跨组复用造成共同失败；并集必须用共享赛果情景计算，不能把每组概率相加。QMD69的UNION压两场虽增加模型覆盖，仍净亏10,697.99元。
3. **替换赛果的收益可能集中于尾部。** QMD79的75%单选替换增益集中于100514，剔除同一期后相对原方案少赚约8,037元；50%阈值根本未触发。本阶段不恢复比分保护，也不把这些阈值当成已校准规律。
4. **限制越紧不一定越好。** 同一候选池上的顺序选组有路径依赖。U2/P2的收益与回撤都不如U2/P4，U2/P6则略亏；更严的限制也可能迫使低质量选场或闲置现金。

## 证据索引

|问题|报告与实现证据|
|---|---|
|原深度×压缩规则×扩组矩阵、随机对照、并集与HHI、5/10/20期风险|[QMD69](../../quarto/69_compression_breadth.qmd)、[说明](compression_breadth_diagnostic.md)、`scripts/check_compression_breadth.py`；4,560计划历史重放|
|旧／新合同因素桥接|[QMD70](../../quarto/70_compression_bridge.qmd)、[说明](compression_bridge_diagnostic.md)、`scripts/check_compression_bridge.py`；1,440计划|
|新增48期纯基线／专家对照|[QMD76](../../quarto/76_pure_baseline_variants.qmd)、[说明](new48_pure_baseline_variants.md)、`scripts/check_pure_baseline.py`；3,456纯基线结果|
|重复场次赛果变化与50%无触发证据|[QMD78](../../quarto/78_repeated_support_variants.qmd)、[QMD79](../../quarto/79_single50_comparison.qmd)|
|37组复用限制与等投入对照|[QMD80](../../quarto/80_reuse_cap_grid.qmd)、`scripts/check_reuse_cap_grid.py`；3,552计划|
|综合结论、验收矩阵、候选资金曲线与逐期ROI|[QMD81](../../quarto/81_issue419_synthesis.qmd)|

不同阶段不拼接为同一收益曲线。旧40期专家与新48期纯基线模型／预算不同，所有旧分区名称不改变已暴露性质。
旧实验已通过的检查是绑定其原提交的历史证据，不能冒充本次在当前实现上重新跑过全部旧实验。

## 原合同仍需完成什么

原合同要求严格先验概率、开发期定规则、转移期封存后评分、跨年份稳定性及剔除最大年份。
目前的历史时间代理和显式cutoff参数不足以证明输入在赛前真实可用；单年度48期也无法做有意义的年份剔除。
因此不能授予`COMPRESSION_BREADTH_SIGNAL`，也不能将未验证简单判为`NO_USEFUL_EXCHANGE`。

已创建 [#421](https://github.com/algotradinglife/beijing-lot/issues/421) 承接验收缺口。
拟将其设为#419的子任务和阻塞项，并赋Task类型，但该原生图更新被自动审批拒绝，尚待明确批准。
当前链接仅指向拟议验收任务，不代表`parent`、`blockedBy`或Project路由已建立；#419仍保持开放。
验收工作应在原生Issue Graph中分解并阻挡#419的最终关闭，不能只在本地文档记一个待办。
后续合同应保留：

- 使用已观测可用时间或有文档依据的保守安全边界，排除只有历史代理的决策输入。
- 全部学习、规则选择和时间治理使用`src/temporal_learning`，含导入闭包、最大时间、分区、缓存与独立重放收据。
- 明确哪些目标年已暴露；候选封存先于目标标签读取，不将已暴露转移年份改名为新holdout。
- 比较原方案及U2/P4、U6/P4、U6/P5，并保留原深度／随机对照；不能用目标ROI再次调参。
- 检查同预算／同投入、期级覆盖、独立票据、HHI、回撤与恢复、5/10/20期亏损窗口、最大期／年份剔除。
- 所有结论只授权纸面研究。真实前瞻挑战需另行冻结，不由本报告自动启动实盘。

## 复现与验证

R分析复用`read_pure_baseline_report`、`reuse_cap_summary`、`strategy_equity_curves`和`plot_strategy_equity`；
测试对应`test-fundamentals-pure-report.R`、`test-fundamentals-reuse-caps.R`和`test-fundamentals-equity-curves.R`。
QMD81没有定义新函数、拟合模型或修改封存计划。

使用项目已配置的R、Python和Quarto环境；渲染期间不安装依赖。
完整原输入存在时：

```sh
quarto render quarto/81_issue419_synthesis.qmd --execute-dir . --execute --no-cache
```

从提交中的可移植fixture重放报告，输出路径必须尚不存在：

```sh
python scripts/prepare_n7_single_fixture.py --fixture tests/fixtures/reuse_cap_grid_report.json.gz --output /path/new-419-report-input
quarto render quarto/81_issue419_synthesis.qmd --execute-dir . --execute --no-cache -P study:/path/new-419-report-input -P archived_report:true
```

归档只核验结果与收据哈希并执行分析，不等同原始数据、模型或票据全链重放。
新报告代码由本次提交绑定，输入沿用QMD80封存结果；不会修改旧收据来把新文档冒充旧冻结的一部分。
每个读者可从QMD81输入身份表取得结果SHA256与计划freeze seal。
