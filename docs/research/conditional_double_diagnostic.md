# #419 重叠双选条件替换：固定概率差门槛

入口quarto/72_conditional_double.qmd；输出data/derived/fundamentals_417/conditional-double-v2。
实时#419图：OPEN，无blockedBy/blocking、parent/subIssues、issueType或Project条目。不关闭、不合并。

## 研究合同

在上一轮不重选组、不增加资金的框架中，固定p2−p3≤0.02/0.05/0.10才替换；1.0为无条件对照。
门槛在运行前声明，不拟合、不进一步细扫或按结果逐期路由。概率是比分投射加冻结专家后的让球p，不是原始欧赔。
只在前序任何组出现过、本次双选的场次应用；保留Top1，把Top2改为Top3。单选不改、首现不改、第三次及以后仍用同一规则。
差值含等号，1e−12浮点容差；0只放行并列。平概率W/D/L排序。
不重新计算分组/角色，不调用专家训练；原模型让平1.1.0及高净球各0.5，原市场q来自欧赔＋大小球。

固定原不重叠前缀及HOLD余款；两压缩深度×两选组目标×两重叠约束，8环境×4门槛×BASE/ADJUSTED×40期=2560计划。
报告去重共同BASE后1600行。各策略40期分配55,040元；同环境各门槛投入、现金、units严格一致。
票级0.65仅一次，结算复用settle_breadth_bundle；不买比分。

40期皆已暴露，保留24/8/8原标签仅供诊断，不冒充新样本外或#419跨年因果验收。
每次阈值运行先封存全部640计划和独立实际支持场景，再打开结算；没有结果反馈改变门槛。
阈值、cutoff、模型、源及传递实现哈希绑定回执；沿用shared temporal_learning，未新增学习工具。

## 观察

原压两场TOP2/STRICT上下文：

|规则|净收益元|预算回报率|最大回撤元|相对不替换增益元|
|---|---:|---:|---:|---:|
|差≤2个百分点|25,175.37|45.74%|4,446.85|3,488.50|
|不替换|21,686.87|39.40%|3,248.79|0.00|
|差≤5个百分点|16,590.78|30.14%|4,446.85|-5,096.10|
|差≤10个百分点|11,764.22|21.37%|7,312.65|-9,922.65|
|无条件替换|16,572.80|30.11%|9,129.52|-5,114.07|

2点门槛四个STRICT环境均增加收益，但四个FREE均下降，不能脱离分组限制使用。
以上2点收益增加3,488.50元，剔除最大增益期后只余669.16元，且回撤增加；训练24期−605.61、验证8期+3,091.38、测试8期+1,002.72元。
其平均model_union由0.59951微降至0.59871，实际收益改善不能解释成模型命中概率提高。
10点在两场FREE的正增益剔除最大增益期后转负。不默认启用任何门槛，不宣称最优。

## 复用与测试

- 修改replace_repeated_double_tail增加合法的max_gap策略参数及second_third_gap ledger；evaluate_fixed_supports与其他投注函数不改。
- tests/test_fundamentals_repeated_double.py共5测试覆盖两个深度、阈值0/2/5/10/100、通过集合单调性、13点等号及略低边界、并列、非法参数、不触发时票/场景不变，以及原有单选/金额/跨cutoff验证。
- 旧C3函数保持原实现，由tests/test_fundamentals_n7_diversity.py回归保护。首轮文本替换误加校验被完整回归抓出；v1标记未验收并保存旧字节，修复后v2四次完整重跑，不改写旧回执。
- runner仅增加--max-gap参数，独立checker按绑定门槛重建支持、逐组票、units、场景及结算。
- 不新增R函数：QMD循环调用已有repeated_double_summary；检查四个BASE逐项完全一致，报告去重BASE。
- 四份两文件归档fixture复用prepare_n7_single_fixture；已有test_fundamentals_n7_single新增4例。归档只重放报告，不代表模型全链重放。

## 验证命令

PY为config/compression_breadth_runtime.json声明依赖的项目解释器；R依赖在环境准备时安装。

    $PY scripts/run_repeated_double.py --parent data/derived/fundamentals_417/compression-bridge-v1 --output <新目录> --max-gap 0.02
    $PY scripts/check_repeated_double.py --study <新目录>
    $PY -m pytest tests/test_fundamentals_repeated_double.py tests/test_fundamentals_compression_bridge.py tests/test_fundamentals_compression_breadth.py tests/test_fundamentals_n7_single.py tests/test_fundamentals_n7_baseline.py tests/test_fundamentals_n7_twocover.py tests/test_fundamentals_n7_c2_relax.py tests/test_fundamentals_n7_diversity.py -q
    $PY scripts/check_cutoff_governance.py
    Rscript --vanilla -e 'for(f in c("repeated-double","compression-bridge","compression-breadth","n7-c2-relax")) testthat::test_file(paste0("tests/testthat/test-fundamentals-",f,".R"),stop_on_failure=TRUE)'
    quarto render quarto/72_conditional_double.qmd --execute-dir . --execute --no-cache

其余阈值同命令使用0.05、0.10、1.0，均写入全新目录。归档4子目录按gap02/gap05/gap10/gapall恢复后，QMD传study父目录及archived_report:true。
CI专用compression-breadth.yml包含相关测试和QMD68–72归档渲染，不包含其他会话的共享workflow变更。
全仓R套件不执行，限定受影响接口。最终审核/远端状态另记，不把未完成CI当通过。

## 最终本地验收

Codex final review无剩余P1/P2，审核实际执行41项Python检查、10项R断言、cutoff检查、4×640独立重放及全新QMD渲染。
隔离待提交快照103项相关Python测试、63项受影响R断言、cutoff检查、归档渲染全部通过。
实际报告、归档报告和隔离归档的表行数均为4/40/40/40/120/1600，无执行错误。
四个门槛v2数值与修复前v1完全一致；无条件640行逐项复现上一轮，四个BASE完整一致。
实现字节、源绑定和检查日志保存于本地输出目录。远端CI在推送后触发，未完成前不计为通过。
