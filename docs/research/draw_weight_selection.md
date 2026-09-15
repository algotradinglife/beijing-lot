# 校正强度与条件信息的收敛测试

已有284期BASE/TOTAL冻结预测前10期用作强度选择预热，274期22439场配对。28个10期块，候选权重0/.25/.5/.75/1，按此前可用历史的三分类Brier选取；平手小权重。只用既有预测、共享prior标签读取和共享context的归一化long component（等历史权重）；近期component不用于该选择。原概率模型自身仍是此前50/50动态校正，区别明确。

固定同强度BASE/TOTAL对照在0.25/0.5/1，分别与RAW和历史选择版本比较。固定预测与选择预测均在打开目标结算前冻结，v1试运行修正固定对照冻结顺序后由v2替代；未用目标标签选权重。

|版本|Brier↓|Log loss↓|Top2|
|---|---:|---:|---:|
|RAW|.6460418|1.0689747|73.5505%|
|BASE固定25%|.6459632|1.0688487|73.4525%|
|TOTAL固定25%|.6459820|1.0688807|73.4302%|
|BASE历史选择|.6460663|1.0690164|73.4391%|
|TOTAL历史选择|.6460475|1.0689838|73.4525%|

同25%/50%强度下TOTAL未胜过BASE；历史选择均只到0或25%，整体proper scores未胜过RAW。固定25%BASE改善很小且回撤前变差，Top2少22场，不宣称稳定升级。结论维持RAW，停止当前强校正与继续分档寻优，保留大小球作诊断。

R函数draw_weight_fit/predict在r/draw_weight_selection.R，对应tests/testthat/test-draw-weight-selection.R。QMD198为完整执行，199为结论。显式cutoff、原预测receipt、标签hash、实现hash和选择score表封存；独立重放重算候选损失、权重和预测。无下注收益声明；历史代理不构成前瞻验收。

验证：`testthat::test_file("tests/testthat/test-draw-weight-selection.R",stop_on_failure=TRUE)`13断言PASS，含未来标签/预测及伪造时点变动不改变选择与预测。项目Python `scripts/check_cutoff_governance.py` PASS；QMD198/199干净进程使用声明参数、`--no-cache`渲染。独立R重放28个模型的候选损失、选择权重、44878条选择预测及9版本评分PASS。最终v2与试运行v1的预测/选择/评分CSV逐字节一致；v1非验收版本。未运行无关全仓测试，未启用远端CI。
