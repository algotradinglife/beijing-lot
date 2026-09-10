# 决策链冲突处理：固定规则历史诊断

入口：`quarto/61_decision_chain_conflicts.qmd`。
输出：`data/derived/fundamentals_417/decision-chain-conflict-v1`。
治理：开始工作前读取实时 #417（OPEN、PI Review、无 blockedBy/blocking）；
本地研究交付不等同于 Issue 关闭、策略推广或生产变更。

## 研究合同

用户确认比分保护整体负收益，本轮继续不买比分；也不把双选扩成全包。
冻结前一研究 `integration-weight-v3` 已验收输入，让平1.1.0、高净球同一前32期模型，
高净球权重0.5。当前让平权重0.5，其源、版本、原始cutoff与实现存档有哈希绑定。
不调用fit、不重训练、不按本轮收益选择阈值或专家。

冲突：固定市场q的第一方向不在当前p的前二内。p/q均为北单让球方向；
q来自赛前欧赔+大小球的比分映射，估算SP=1/q，独立于专家权重。
并列按W,D,L。固定四个arm：保持；冲突时让平降到0.25；冲突时退回0；冲突时跳过。
只变让平，未必能消除由其他模型因素形成的冲突。零权重仍含高净球专家。

沿用概率+集中策略：最多6组不重叠7串1、每场双选、每组128注、每注2元，
每期上限1,536元，返奖系数0.65仅在票级一次。跳过从剩余候选重新排名补位，
剩余不足7场不买。余额留现金，不追加倍数或比分保护。
第五个arm `SKIP_MATCHED_CURRENT` 保留当前方案前K组（K由跳过后的组数决定），
保证逐期与跳过方案实际投入一致。不是同本金下注比例优化，也不是全局最优分组。

40期2313个市场可用候选：TRAINING24=原训练32期中的有时钟24期；
VALIDATION8=100305—100312；TEST8=100313—100319及100401。
2359个端点中46个因市场门控排除，原始原因完整沿用。
训练/验证/测试命名沿用旧研究，全部为已经揭示的历史回顾，不是新留出验证；
旧的已接受/完场样本范围含事后可用性选择，不能授予前瞻资格。
逐场相对时钟也不证明同一张票在同一购买时刻能执行。

这不是旧v3.3.3/v4.2原样复测。旧策略还有情报、战力、q保护、全包和停标签；
本次只抽取“模型与市场冲突后处理”思想，保持当前输入和票据口径。

## 结果

|方案|训练24 ROI|验证8 ROI|测试8 ROI|测试最大回撤（元）|
|---|---:|---:|---:|---:|
|保持0.5|−14.93%|98.22%|33.75%|2,165.25|
|冲突降到0.25|−10.12%|75.54%|23.38%|2,971.70|
|冲突退回0|−1.53%|84.93%|13.58%|4,435.51|
|冲突跳过|−25.99%|93.61%|61.59%|2,894.14|
|与跳过等投入CURRENT|−14.76%|102.53%|40.27%|2,165.25|

测试CURRENT投入11,008元、净收益3,715.11元；跳过投入10,496元、净收益6,465.00元。
等投入CURRENT净收益4,227.11元，跳过相对它多2,237.89元，但回撤增加728.89元。
跳过在训练和验证均不胜等投入CURRENT，不能根据测试8期ROI推广。

原双选命中率，冲突/非冲突：训练69/117=58.97% vs839/1144=73.34%；
验证42/73=57.53% vs374/499=74.95%；测试39/67=58.21% vs302/413=73.12%。
风险信号方向一致，处理方式收益不一致。测试冲突降0.25可把39/67提高到43/67，
退回0提高到44/67，但串关整体回报反而下降；单场覆盖改善不等于组合收益改善。
表格保留所有候选与实际入选命中，未把跳过的场次从诊断分母中抹掉。

结论：不新增默认冲突跳过/降权，不恢复比分保护。保留风险标签供下一批新数据验证。

## 函数、截止与来源清单

|层|调用/文件|约束与自动化覆盖|
|---|---|---|
|旧预测与投射|上游 `integration-weight-v3` 的候选、端点、receipt|固定诊断证据；不重新fit；source与模型hash核对|
|取固定权重|既有 `select_integration_weights`|无标签精确schema、固定q、原共享Cutoff；既有对应pytest|
|冲突路由|`src/fundamentals_decision_chain.py::route_decision_chain`|精确schema、身份唯一、cutoff完整、参数/输入/来源/实现闭包回执；新pytest|
|选场票据|既有 `rank_double_candidates`、`n7_baseline_plan`|原逐场Cutoff、同COVERAGE/C0E0/UNIT；既有pytest|
|等投入组数|`limit_decision_chain_plan`|显式Cutoff，父计划seal，0组允许，不读取标签；新pytest|
|结算|既有 `settle_n7_baseline`|先200份计划与freeze receipt落盘，后读已保存R/SQLite三份审计，最终SP仅用于结算|
|统计|`r/fundamentals_decision_chain.R::decision_chain_tables` 调用既有 `integration_weight_summary`|不学习；逐期ROI、分区CNY回撤、未投现金、冲突/入选命中；11条testthat断言|

没有新增历史学习或缓存；不需要重新选训练窗/ESS/标签可用代理。不能把“不学习”
解释为上游输入已通过前瞻准入。所有新决策函数显式接收共享Cutoff，不复制时间框架。
独立checker不调用新路由函数或票据规划函数，重建冲突、所有Top2、排序、分组、
128个结果组合和返奖，并验证CURRENT逐期与上轮0.5完全一致。
CLI测试改变最终比分方向/SP后，支持、路由、票据保持不变；即使结算文件不存在，
全部计划已先冻结。源文件变动或覆写研究目录失败关闭。

## 复现与验收

在仓库根目录，显式选择项目Python与已配置R库。无需安装新依赖。

```sh
"$PROJECT_PYTHON" scripts/prepare_decision_chain_inputs.py --source data/derived/fundamentals_417/integration-weight-v3 --output <new-study>
"$PROJECT_PYTHON" scripts/run_decision_chain_comparison.py --study <new-study> --audit-source data/derived/fundamentals_417/integration-weight-v3
"$PROJECT_PYTHON" scripts/check_decision_chain_comparison.py --study <new-study> --reference data/derived/fundamentals_417/integration-weight-v3/results.json
quarto render quarto/61_decision_chain_conflicts.qmd --execute-dir . --execute --no-cache -P study:<new-study>
```

新函数测试在 `tests/test_fundamentals_decision_chain.py`、`tests/test_decision_chain_entry.py`、
`tests/testthat/test-fundamentals-decision-chain.R`。CI新增对应Python/R测试、
cutoff治理扫描及QMD离线归档渲染。归档fixture标记只验证报告呈现，不声称重新执行专家。
具体命令、运行记录、Codex review与最终hash封存见输出目录的验收文件。
