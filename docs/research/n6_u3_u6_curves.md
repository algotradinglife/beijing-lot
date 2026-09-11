# 两个六串一效率方案与原U3/U6曲线

用户指定EXTRA_PROB、EXPECTED_NET_768、U3_ORIGINAL、U6_ORIGINAL四方案。
48期100402—100607，各自100000元初始资金，沿用现有逐期实际投入、余额留现金，
无复投、重排、合并或新增策略。不同方案累计投入不同，图不代表同等投入比较。

QMD：quarto/107_n6_u3_u6_curves.qmd。复用read_pure_baseline_report验证两个源报告，
missed_strategy_summary/strategy_equity_curves计算资金及历史峰值回撤；未新增项目函数。
默认来源n6-efficiency-v1和high-hit-filter-v1；参数允许已有归档报告回放。
输出data/derived/fundamentals_417/n6-u3-u6-curves-v1中的equity/drawdown PNG和PDF、
summary.csv、curves.csv、provenance.json，记录输入/代码哈希、参数和生成时刻。
报告文字定义回撤正数，图向下显示负数，汇总表报告正的最大回撤。

|策略|净收益元|最大回撤元|期末资金元|
|---|---:|---:|---:|
|EXTRA_PROB|8078.58|4437.61|108078.58|
|EXPECTED_NET_768|9408.08|4059.71|109408.08|
|U3_ORIGINAL|19946.49|2057.14|119946.49|
|U6_ORIGINAL|24713.37|4416.06|124713.37|

R函数无修改，运行三个对应testthat文件：pure-report、equity-curves、missed-summary，
stop_on_failure=TRUE。R_LIBS_USER明确指向项目r_lib，TMPDIR使用项目临时目录。
Quarto1.10.18，--execute-dir . --execute --no-cache，新进程执行、错误致命。
CI加入恢复n6_efficiency/high_hit_filter夹具及参数化报告渲染。
全体策略仍是已暴露历史诊断，不宣称#421验收、远程CI通过或前瞻收益。
本轮不更改默认策略、Issue生命周期或原始数据。

验收：三个既有R函数测试文件通过；最终QMD现场和归档均新进程执行通过。
独立核对每方案49点（含起始点）、期末资金与最大回撤、输入/代码哈希，196点CSV完全一致；
两张2640×1320 PNG和两份PDF有效。执行方实际查看两张PNG，中文/图例/坐标无裁切或重叠。
独立Codex review无可执行缺陷，复核同48期192行、金额与回撤、来源哈希和CI接线；
审核者未重复函数测试、渲染或视觉检查。原文位于
data/derived/fundamentals_417/n6-u3-u6-review.txt。无关全仓测试及远程CI未运行。
