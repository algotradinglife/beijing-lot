# #419逻辑的40期等额诊断

入口：`quarto/69_compression_breadth.qmd`。用户要求QMD/R交付，因此本轮采用可执行QMD，不新增Jupyter笔记本。实现参考Issue #419，但本轮不是该Issue的完整因果跨年验收，不关闭Issue，不更新生产默认，不改#210/#218。

## 合同

当前40期2010年已揭示数据，原各期预算合计55,040元；每个实验方案实际投注均精确匹配原预算。将#419的一组256元基准按当前原组数等比例扩展。原baseline是CURRENT全双选、Top2概率集中分组，不是此前C2追加投注方案。冻结让平1.1.0与同一高净胜球专家，权重各0.5；p来自比分分布投射及专家整合，q来自欧赔＋大小球市场映射，SP代理为1/q。最终SP仅用于结算。

深度r=0/1/2/3。压缩规则TOP1、RETENTION、ABS_LOSS、VALUE_RETENTION、RANDOM。比较REPEAT原组重复下注、QUALITY按压缩后联合概率选组、UNION贪心新增模型覆盖、RANDOM同质量池随机选组。随机压缩和随机组合使用三个固定种子，全部报告，共114个策略×40期=4560计划。固定种子0仅作主表视图，不是根据收益筛选。

每期固定512不同七场候选，含原组、循环窗口、固定种子均匀抽样。每种压缩规则和深度下，按压缩后联合质量取前128候选。QUALITY/UNION/RANDOM共享这个池；规则变化时质量池可变化。不是所有七场组合的全局最优，没有硬复用／两组重叠上限；以联合覆盖和持仓集中度评估相关性。REPEAT明确是无新增覆盖的对照，重复物理票按units合并，不伪造独立组数。

UNION用1024个共享场次情景选择，评估另用8192情景、独立种子。不同场次独立是模型假设；同一场在各组必须共享赛果。只有OR并集概率作为整体命中概率。每组精确联合概率、模拟哈希、压缩ledger、p/q、cutoff与代码闭包均绑定。三种随机种子仅为敏感性，不是样本外置信区间。

## 接口与测试映射

`src/fundamentals_compression_breadth.py`：
- breadth_candidates：验证Cutoff和输入，固定候选池，明确有限搜索边界。
- compression_surface：确定单选角色、支持位掩码、概率和价值保留比例、分层ledger，返回完整seal。
- breadth_scenarios：以每场一次赛果产生候选命中矩阵，返回seed/shape/sha256/surface identity。
- compression_breadth_plan：按同额预算选择，完整票据枚举与重复单位合并，绑定设计情景。
- breadth_metrics：独立评估流的并集概率/模拟标准误及付费持仓HHI。
这些函数均有显式Cutoff，无历史拟合、数据写入或网络副作用。导入只定义函数。settle_breadth_bundle在单次审计上下文内缓存相同组的权威settle_n7_baseline结果，绑定cutoff和输入身份，合计各组返奖；已逐项与settle_n7_single对照测试，不重写票级支付公式。

Python测试`tests/test_fundamentals_compression_breadth.py`覆盖全部规则×深度×组合方式、完整支持、同额、重复合并、共享事件模拟、独立评估种子、身份篡改、错误预算、质量池不足、无效参数、标签变化不改计划与归档恢复。独立检查器不调用新规划/结算函数，重建压缩选择、情景矩阵、贪心追加、票据及单次0.65返奖。

R函数`compression_breadth_summary`汇总同额基准提升、10万元资金路径、净收益最大期剔除、增益最大期剔除、亏损连期、5/10/20窗口、回撤与恢复、返奖集中度。`compression_leg_strata`按固定边界描述压缩概率、保留比例、熵、分歧、让球及方向。对应R测试`tests/testthat/test-fundamentals-compression-breadth.R`。持仓是嵌套观测，报告期数，不将组数或重复持仓当独立样本量。

## 复现与证据

使用项目Python运行：
```
scripts/run_compression_breadth.py --parent data/derived/fundamentals_417/n7-compression-v1 --output <新目录>
scripts/check_compression_breadth.py --study <新目录>
```
第一阶段冻结全部计划和模型评估后，第二阶段才读取同一R/SQLite权威结算审计。此前已见过这些历史结果，不构成前瞻冻结或可交易时间证明。2010年单年度不能检验剔除最大年份后的稳定性。所有实际输出与审计绑定在研究目录，原始数据仍保留，不随代码推送。

独立CI工作流`.github/workflows/compression-breadth.yml`避免纳入其他会话的共享工作流改动。版本在`config/compression_breadth_runtime.json`声明；依赖仅在环境设置时安装，函数与QMD不安装依赖。归档报告恢复使用`restore_compression_breadth_fixture.py`，严格允许四个文件、哈希核验、不可覆盖；归档模式不声称原数据或模型重放。

本轮只报告历史诊断信号，不以单一ROI挑选部署方案；任何正面结果仍需另外冻结的新期验证。完成比较后按用户授权提交、推送，不自动合并。

初审发现pool/surface未绑定原cutoff、模拟seed/draw元数据未与矩阵一起封存两项P2，已补强并添加跨cutoff复用、seed/draw/shape改动和矩阵篡改回归。v1保留为未验收记录；v2由修复后的实现重新生成，未迁移旧计划或重写旧回执。

## 40期结果与本地验证

各方案实际投入均为55,040元。原全双选净收益10,754.90元、ROI 19.54%、最大回撤19,895.50元。
TOP1压一场后原组重复两倍：净收益40,585.22元、ROI 73.74%、回撤13,728.01元；压一场按压缩后概率扩组：31,181.03元、56.65%、6,886.46元。
各自剔除相对原方案增益最大的一期后，同期配对净增益仍为20,701.45元及7,930.25元。
但概率扩组在已暴露VALIDATION8分区净亏4,483.42元，不能据总收益宣称稳定。
TOP1压两场按QUALITY仅净赚615.46元，按UNION净亏10,697.99元，后者模型并集概率均值虽高于基准仍未改善经济结果。
这些规则不等于此前保留原C2组再花剩余现金的追加规则；本轮重新选组、全部同额花完。

验证命令（`PY`指配置声明的项目解释器，R库在环境设置阶段提供）：

```
$PY -m pytest tests/test_fundamentals_compression_breadth.py tests/test_fundamentals_n7_single.py tests/test_fundamentals_n7_baseline.py tests/test_fundamentals_n7_twocover.py tests/test_fundamentals_n7_c2_relax.py tests/test_fundamentals_n7_diversity.py -q
$PY scripts/check_cutoff_governance.py
Rscript --vanilla -e 'testthat::test_file("tests/testthat/test-fundamentals-compression-breadth.R",stop_on_failure=TRUE);testthat::test_file("tests/testthat/test-fundamentals-n7-c2-relax.R",stop_on_failure=TRUE)'
$PY scripts/check_compression_breadth.py --study data/derived/fundamentals_417/compression-breadth-v2
quarto render quarto/69_compression_breadth.qmd --execute-dir . --execute --no-cache
$PY scripts/restore_compression_breadth_fixture.py --fixture tests/fixtures/compression_breadth_report.json.gz --output <新归档目录>
quarto render quarto/69_compression_breadth.qmd --execute-dir . --execute --no-cache -P study:<新归档目录> -P archived_report:true
```

89项Python测试、34项R断言及cutoff静态治理通过；独立枚举核对4560计划通过。真实输入与归档报告均执行成功，HTML包含4560行逐期策略结果，全部主表、1356行分层及ROI图已检查。
全仓R测试没有执行：本轮验证限定于新增函数及受影响的共享投注接口；其他会话修改不纳入本次验收。
工作区数据目录保存原始初审、修复复审和最终审核证据；归档fixture允许CI重放报告，不等价于原始采集和模型重放。远端CI状态在推送后另核验，不将本地通过冒充远端通过。

最终Codex审核：无P1/P2；独立重算全部456行汇总一致。另有P3元数据提示：压缩计划保留基准模板的`shape=C0E0`及`group_budget_cny=432`，这两个字段不描述最终压缩支持或实际组成本。读取压缩结果必须使用`single_count`、各leg的`support`、`group_cost_cny`与完整ticket/units；当前报告、独立检查和结算均使用这些实际字段，数字不受影响。本轮冻结产物不就地改写，后续接口版本应消除模板字段歧义，当前产物仅作已登记诊断证据。
待提交树的独立文件快照（不含其他会话工作区修改）亦通过89项Python、34项R断言和归档QMD执行；该验证使用当前已安装依赖，不能替代远端全新安装CI。
