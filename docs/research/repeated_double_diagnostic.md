# #419 扩组重叠双选替换诊断

入口：quarto/71_repeated_double.qmd；完整本地输出：data/derived/fundamentals_417/repeated-double-v2。

## 合同

用户指定：扩组出现重叠场次时，当前双选保留概率最高方向，把第二方向改为第三方向；当前单选不动。按冻结组序处理，任何前序出现（包括单选）都计为重叠；第三次及以后仍为Top1+Top3，不交替，也不回改旧组。平概率按W/D/L确定顺序。

固定原不重叠前缀、场次、组序、单选角色、组units、预算和现金；一场/两场单选 × TOP2/COMPRESSED选组 × STRICT/FREE限制 × BASE/ADJUSTED，40期共640计划。不重新选组，不加钱，不做比分保护或专家重训。每策略分配预算合计55,040元。STRICT每场至多两组、组间至多两场重叠；FREE沿用父计划放宽配置。

仅40期已暴露2010数据的回顾诊断，沿用原24/8/8分区标签，不宣称新样本外检验或满足#419跨年因果验收。实时原生Issue Graph为开放、无依赖；不关闭Issue、不合并、不晋升默认策略。

## 结果

下表收益率=净收益/分配预算（包括持有现金）；QMD另列投注回报、全部逐期结果及回撤。

|方案|原净收益元|调整后净收益元|调整后预算回报|净收益变化元|原最大回撤元|新最大回撤元|
|---|---:|---:|---:|---:|---:|---:|
|D1_COMPRESSED_FREE|44,268.63|16,653.41|30.26%|-27,615.22|7,968.19|13,162.71|
|D1_COMPRESSED_STRICT|21,173.79|20,165.36|36.64%|-1,008.42|5,946.77|9,431.33|
|D1_TOP2_FREE|44,268.63|16,653.41|30.26%|-27,615.22|7,968.19|13,162.71|
|D1_TOP2_STRICT|21,173.79|20,165.36|36.64%|-1,008.42|5,946.77|9,431.33|
|D2_COMPRESSED_FREE|17,267.72|6,114.71|11.11%|-11,153.01|5,478.63|12,954.44|
|D2_COMPRESSED_STRICT|21,408.65|17,715.56|32.19%|-3,693.09|3,248.79|8,681.52|
|D2_TOP2_FREE|18,598.14|8,966.00|16.29%|-9,632.14|5,478.63|11,228.89|
|D2_TOP2_STRICT|21,686.87|16,572.80|30.11%|-5,114.07|3,248.79|9,129.52|

8个对照都收益下降、回撤上升。严格限制下有的方案净增加命中组，但收益仍下降；票级返奖不同，不能把命中数量当收益。固定组集合的持仓HHI不变，实际支持下平均模型并集覆盖全部下降。不建议无条件启用本变种。没有继续搜索阈值来优化这40期。

## 实现与测试

- src/fundamentals_n7_diversity.py：replace_repeated_double_tail验证冻结原计划，替换后重建完整物理票及金额元数据；evaluate_fixed_supports复用既有breadth_scenarios/breadth_metrics，对实际支持独立评估，保留原设计回执、不复用旧支持矩阵。
- tests/test_fundamentals_repeated_double.py：两深度、首现/再次/三次出现、前次单选、单选不变、平概率、不同units、现金及预算、标签变化、跨cutoff、错误概率和旧评估seed。
- r/fundamentals_repeated_double.R：repeated_double_summary复用原汇总和风险实现，强制完整配对、等额及相同组数；对应testthat文件验证正常和错误合同。
- scripts/run_repeated_double.py：全部冻结后才读取本轮结算；320个BASE原计划和结算逐项复现。
- scripts/check_repeated_double.py：独立重建640计划的支持、物理票、units、共享场景、回执、返奖以及新增/失去命中组；不调用新规划和结算函数。票级0.65只一次。
- tests/test_fundamentals_n7_single.py新增归档fixture案例；归档只复现报告，不是原数据模型全链重跑。
- 新增函数不拟合历史参数；cutoff与实现闭包均复用src/temporal_learning。输入/冻结计划/结算/代码哈希绑定。

## 复现与验证

依赖沿用config/compression_breadth_runtime.json；安装在环境准备阶段。

```sh
$PY scripts/run_repeated_double.py --parent data/derived/fundamentals_417/compression-bridge-v1 --output <新目录>
$PY scripts/check_repeated_double.py --study <新目录>
$PY -m pytest tests/test_fundamentals_repeated_double.py tests/test_fundamentals_compression_bridge.py tests/test_fundamentals_compression_breadth.py tests/test_fundamentals_n7_single.py tests/test_fundamentals_n7_baseline.py tests/test_fundamentals_n7_twocover.py tests/test_fundamentals_n7_c2_relax.py tests/test_fundamentals_n7_diversity.py -q
$PY scripts/check_cutoff_governance.py
Rscript --vanilla -e 'for(f in c("repeated-double","compression-bridge","compression-breadth","n7-c2-relax")) testthat::test_file(paste0("tests/testthat/test-fundamentals-",f,".R"),stop_on_failure=TRUE)'
quarto render quarto/71_repeated_double.qmd --execute-dir . --execute --no-cache
$PY scripts/prepare_n7_single_fixture.py --fixture tests/fixtures/repeated_double_report.json.gz --output <新归档目录>
quarto render quarto/71_repeated_double.qmd --execute-dir . --execute --no-cache -P study:<新归档目录> -P archived_report:true
```

本地97项相关Python测试、63项受影响R断言、cutoff静态检查及独立640计划核验通过。全仓R套件未执行，范围为受影响分析接口。完整研究和归档QMD均要求执行、无缓存、错误致命。v1保留为未验收草稿；v2补强预算与实际units元数据后完整重跑，所有数值结果与v1一致，未改写旧回执。

独立CI工作流compression-breadth.yml增加本轮测试和QMD71归档渲染；共享工作区其他会话改动不纳入提交。Codex review与远端CI验收状态另行追加。

## 最终本地审核及交付

实现已提交并推送为453dac25。Codex final review无可操作P1/P2；审核者实际运行新增3项Python测试、独立640计划核验及新增10项R断言，并检查HTML含七张完整表和640结果行。待提交文件的隔离快照另通过97项Python测试、63项受影响R断言、cutoff检查及归档渲染；实际、归档、隔离归档三份HTML表行数均为1/8/8/8/8/48/640。实现闭包原始字节和检查日志保存在本地研究目录。

[远端CI](https://github.com/algotradinglife/beijing-lot/actions/runs/34479521989)已触发，交付记录时仍运行中，不能记为通过；本轮本地验证和Codex审核通过，不进行合并或Issue关闭。
