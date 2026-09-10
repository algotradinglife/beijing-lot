# #419旧／新压缩策略的单因素与交互诊断

入口：`quarto/70_compression_bridge.qmd`，输出：`data/derived/fundamentals_417/compression-bridge-v1`。

## 合同与图状态

现场读取#419 native blockedBy/blocking/parent/subIssues/type/project字段，当前无原生依赖，Issue开放。本轮仅40期2010年已暴露诊断，不满足该Issue完整因果跨年合同；不关闭、不合并、不改生产。使用QMD是用户明确交付要求，优先于Issue正文的Jupyter形式。所有阶段保留同一冻结模型、p/q、期次、每期预算（合计55,040元）；不重训、不新增赛季。按2元单位，完整票级0.65仅一次；不买比分。

## 设计

旧结果SINGLE_1/SINGLE_2与前次D1/D2 TOP1 QUALITY直接复用并重新结算，金额与命中逐项复现。共同候选池=前次固定512七场集合∪旧两种深度全部七场组；不同深度共用池。32因子组合=2深度×是否保留旧不重叠前缀×TOP2/COMPRESSED目标×STRICT2/2/FREE限制×HOLD/REPEAT_BEST余款。4个直接对照，共36策略×40=1440计划。

TOP2补组log目标及1e−10排名惩罚延续旧规则；COMPRESSED按压缩后联合概率选组。候选组顺序选择，不宣称全局最优。STRICT约束不同七场组，每场最多两组、两组最多重叠两场。现金加倍仅改变完整组的物理票units，重复单位不增加独立组或并集覆盖。最大概率组的选择不用最终SP。TOP1压缩固定，未重新选择压缩阈值或专家参数。

共同池、原计划、cutoff、输入与transitive代码哈希都在冻结回执；全量计划封存后本轮才读取权威审计。已暴露标签不冒充前瞻未知。1024设计/8192独立评估情景共享同场赛果，不同场次独立是模型假设。无训练、调参、时间分区或缓存工具的新实现；统一通过src/temporal_learning的Cutoff及provenance。

## 主要观察

旧一场净收益21,173.79元、两场21,686.87元，完全复现。按旧前缀→改目标→放开限制→取消前缀→前次512池的固定路径：

- 一场：21,173.79→21,173.79→44,268.63→24,050.99→31,181.03元。
- 两场：21,686.87→21,408.65→17,267.72→911.43→615.46元。

两场下降主要对应取消原不重叠分组（本路径减少16,356.29元）。归因依赖改变顺序，完整64组ALL40配对对照报告所有上下文；不是唯一因果分解，也不把同一期的票当独立样本。

仅把旧两场方案剩余现金加到最高概率组：净收益59,876.59元，预算回报108.79%，回撤4,491.49元，相对旧方案增益38,189.72元；剔除增益最大期100303后配对增益10,417.93元。一场同样处理现金反而少1,536元。此观察不是新默认，更不是未来收益承诺。相对各自OLD，和前次相对原全双选的配对基准不同，不能混用ex-largest数值。

## 模块／测试映射

- `bridge_surface`：扩展共同池并绑定旧计划；`bridge_plan`：四因素纯规划与完整票据；`bind_bridge_reference`：原票不变接入共享模型情景。位于src/fundamentals_compression_bridge.py。
- Python测试tests/test_fundamentals_compression_bridge.py覆盖两深度全部16组合、现金不改支持/并集、完整笛卡尔票、严格重叠、封存身份/跨cutoff错误、标签变异不改计划、单次0.65与权威结算对照。
- R `compression_bridge_summary`：预算/投注双分母、配对OLD提升、最大期剔除、回撤、亏损连期、5/10/20期窗口；`compression_bridge_contrasts`：其他因素固定的逐期配对及ex-largest增量。tests/testthat/test-fundamentals-compression-bridge.R覆盖19断言，含分母差异、缺失配对、重复和summarise列覆盖回归。
- CLI scripts/run_compression_bridge.py只编排冻结及结算；scripts/check_compression_bridge.py不调用新规划/结算函数，独立重建候选池、全部因素选择、TOP1支持、物理票、现金、联合覆盖、持仓HHI及返奖。
- 归档复用scripts/prepare_n7_single_fixture.py；新增fixture参数由test_fundamentals_n7_single.py验证1440行。归档只重放报告，不代表原始采集或模型重放。

## 验证与复现

```
$PY scripts/run_compression_bridge.py --old data/derived/fundamentals_417/n7-compression-v1 --recent data/derived/fundamentals_417/compression-breadth-v2 --output <新目录>
$PY scripts/check_compression_bridge.py --study <新目录>
$PY -m pytest tests/test_fundamentals_compression_bridge.py tests/test_fundamentals_compression_breadth.py tests/test_fundamentals_n7_single.py tests/test_fundamentals_n7_baseline.py tests/test_fundamentals_n7_twocover.py tests/test_fundamentals_n7_c2_relax.py tests/test_fundamentals_n7_diversity.py -q
$PY scripts/check_cutoff_governance.py
Rscript --vanilla -e 'testthat::test_file("tests/testthat/test-fundamentals-compression-bridge.R",stop_on_failure=TRUE)'
quarto render quarto/70_compression_bridge.qmd --execute-dir . --execute --no-cache
$PY scripts/prepare_n7_single_fixture.py --fixture tests/fixtures/compression_bridge_report.json.gz --output <新归档目录>
quarto render quarto/70_compression_bridge.qmd --execute-dir . --execute --no-cache -P study:<新归档目录> -P archived_report:true
```

依赖在config/compression_breadth_runtime.json固定。上轮远端CI缺少导入链matplotlib导致测试收集失败，本轮补齐matplotlib/nbformat/nbclient/pyarrow/PyYAML，并用隔离Python环境只安装声明依赖执行检查。独立工作流compression-breadth.yml增加新路径、测试及归档QMD；其他会话尚未提交的fundamentals-census.yml扩展不纳入当前commit，HEAD中的该工作流并不运行这些新测试。

所有本地独立核验和审核证据置于研究输出目录；远端CI须另记实际状态。全仓R套件未执行，范围限定新增函数和受影响投注接口。无风险阈值拟合、默认策略晋升或历史分区重命名。

## 分区限制与最终本地复审

两场方案余款加倍的增益集中在原TRAINING24（净收益53,309.77元，对照10,000.05元）；VALIDATION8净收益8,354.98元，比对照少2,240元；TEST8净亏1,788.15元，比对照少2,880元。不能用全40期高收益自动晋升此策略。QMD的原24/8/8表提供全量对应数字。

最终Codex审核在f8a26f2c上无P1/P2：独立核对1440计划、160旧/新直接对照、144汇总、256因素上下文、16600个HTML数值和640个现金配对。重复资金不改变支持或覆盖已核验。审核明确回撤上升和单年度暴露限制。待提交代码的独立快照在仅安装已声明Python依赖的隔离环境中93项测试通过；受影响R合计53断言（新桥接19、前次20、C2计14）及归档渲染通过。原数据、完整实现快照、初审与最终审核均保存在本地研究目录。

远端CI已通过：[f8a26f2c](https://github.com/algotradinglife/beijing-lot/actions/runs/34475713652)。验证93项Python测试、53项受影响R断言、cutoff检查及QMD68/69/70三份归档报告渲染；修复了上一轮缺少传递导入依赖造成的收集失败。此CI绑定实现提交；后续仅追加本验收说明。
