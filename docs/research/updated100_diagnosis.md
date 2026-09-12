# 新增100期收益退化诊断

固定原方案，不学习、不调参；原48期100402–100607对照新增100期100608–101120。
八个方案均取已冻结seed0计划；全部种子的收益分布仍以120号QMD为准。

主要证据：

- U3持仓单选命中59.06%→50.00%，去重后58.25%→50.00%。一致双选77.55%→76.72%，分歧双选72.08%→70.15%。
- U3组命中13.21%→5.82%，中奖组平均返还1054.47→906.58元。收益下降同时包含频率和返还下降。
- 全部可用比赛池市场Top1命中46.43%→43.00%；单选持仓退化更大，不能只用总体场次命中概括。
- 新样本U3基线预测单选66.09%、分歧双选91.55%，实际50.00%、70.15%；市场对应54.36%、69.89%。
- 1010/1011期号段去重单选命中41.86%/38.75%。让球−2单选63.83%→51.10%。联赛样本小且构成变化，不认定因果。
- 9期无下注是合格单选不足2场，不是没有数据；没有计为亏损。
- N5不替换仍为+6.58%ROI，但部分错误单选同时出现在64组，重复持仓不能看作独立下注机会。

## 实现与复现

`scripts/diagnose_updated100.py`只解包冻结计划、审计和特征，输出228421个持仓位置、9108个可用场次、1184条策略期次结算。每项输入及CSV均有SHA256凭据。

`r/fundamentals_updated_diagnosis.R::updated_scope_diagnosis`执行R汇总，核对唯一键、实际结果、概率归一化、每组两单、N5/6/7成本、逐组中奖返还和逐期原结算。`tests/testthat/test-updated-diagnosis.R`覆盖该函数及边界和失败输入。

报告：`quarto/121_updated100_diagnosis.qmd`。默认核验外部文件；`archive_fixture`参数只回放封存CSV，明确不重验外部原数据。CI使用便携快照并执行同一报告。

```sh
python3 scripts/diagnose_updated100.py
Rscript -e 'testthat::test_file("tests/testthat/test-updated-diagnosis.R",stop_on_failure=TRUE)'
quarto render quarto/121_updated100_diagnosis.qmd --execute-dir . --execute --no-cache
quarto render quarto/121_updated100_diagnosis.qmd --execute-dir . --execute --no-cache -P study:data/derived/fundamentals_417/updated100-diagnosis-archive-v1 -P archive_fixture:tests/fixtures/updated100_diagnosis.json.gz
python3 scripts/check_cutoff_governance.py
```

本机需使用仓库已有R库和可写TMPDIR；不在渲染中安装依赖。全仓测试不作为本任务通过声明，其他会话存在大量独立修改。
此次为事后描述，不产生预测或选择接口，不关闭#419/#421；不能据此声称未来收益或cutoff-safe学习验收。

验证：12条R断言通过；实时输入与便携归档分别在新进程执行QMD成功，8张输出CSV逐字节一致；HTML有8张结果表，无执行错误；cutoff governance通过。Codex review未发现需处理的正确性问题，复核了来源哈希、结算、计数口径和报告数值。首次归档发现CSV换行被转换，已改为逐字节封存并成功重放；未修改数据内容。

## 追加：方向与让球数交叉

方向指标区分Top1精确率、Top1召回率、Top2召回率；双选组合另外按被排除方向汇总。按主队有符号让球数与ALL分别输出，不将两层重复加总。无预测或实际样本的分母返回NA。25条R断言覆盖混合结果计数、零分母及总体对账。追加Codex review未发现正确性问题。

新增100期市场Top1从未选让平，基线仅选12场、中4场；实际让平1768场（27.00%）。实际让平的Top2捕捉率市场10.92%、基线41.23%。因此市场总体Top2更高不代表对所有方向都有更好覆盖。这是当前映射实现的排序表现，不将其泛化为所有市场模型的结论。

主队−2的538场，基线Top2命中71.19%，市场79.74%；0球3488场为71.85%与73.28%。方向精确率和完整前后期对照见QMD，选中数量与实际方向数量分别保留。
