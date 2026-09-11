# 四版本相关性

入口 quarto/110_double_source_correlations.qmd；读取已验收 double-source-v1 的48期192行，严格按期号配对，包括未下注的零净收益，不对累计资金曲线求相关。没有新函数、学习、票据或模型变更。

|配对|Pearson净收益|Spearman净收益|中奖期phi|共同命中|仅前者|仅后者|均未中|
|---|---:|---:|---:|---:|---:|---:|---:|
|U3基线—U3市场|0.785|0.523|0.605|12|7|2|27|
|U3基线—U6基线|0.933|0.690|0.739|16|3|3|26|
|U3基线—U6市场|0.748|0.523|0.559|13|6|4|25|
|U3市场—U6基线|0.845|0.529|0.605|12|2|7|27|
|U3市场—U6市场|0.888|0.870|0.867|14|0|3|31|
|U6基线—U6市场|0.843|0.677|0.737|15|4|2|27|

六组Pearson均为明显正相关，当前没有相关性很低的组合。U3基线与U6市场为六组最低，但0.748仍高；不能把“六组最低”解释为能明显降低回撤。两基线版本0.933，说明改变复用上限仍保留很强的收益同向性。部分Spearman较低，说明收益排序相似程度弱于金额线性相关，但不据此断言由某个大额期造成。

U6市场相比U6基线新增2个命中期、失去4个命中期；共同15期，均未中27期。两个市场版本U3命中的14期都在U6命中期内。中奖不等于盈利，低相关不等于组合收益或回撤必然改善。

## 验证

- R直接使用stats::cor和tidyr严格配对，无新增项目函数；QMD执行192行完整笛卡尔键契约及48期重合计数断言。
- numpy.corrcoef/scipy.stats.spearmanr独立复算六对金额相关性、排名相关性、中奖phi与重合计数，通过。
- 源和归档分别新进程 `quarto render quarto/110_double_source_correlations.qmd --execute-dir . --execute --no-cache`；归档显式指定study/output/archived_report参数。
- CI复用已存在double_source.json.gz，无新增数据采集。未运行全仓测试或宣称远端CI通过。
- 同期观察相关性属于已暴露历史回顾，不用于自动择策/分配；#419仍受#421阻塞。

补充核验：两次独立进程生成的correlations.csv逐字节一致，HTML三表4/4/6行且无执行错误，source/report provenance哈希全部匹配。

独立Codex review：无可执行发现。审核者读取实时419/421关系，在Rscript --vanilla执行分析块，另用NumPy/SciPy核对源/归档全部六对相关性、计数及文档；未重跑渲染（quarto不在其PATH）、全仓测试或远端CI。主任务已使用显式Quarto路径完成两次新进程渲染。日志 data/derived/fundamentals_417/double-source-correlations-review.txt。
