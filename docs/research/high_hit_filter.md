# 高命中六串一的零让球Top2分歧排除

## 范围与结论

48期100402—100607的已暴露回顾诊断。用户要求在历史41期命中的
H1_R050_N6_C1_RETENTION上排除让球为0且原基线/市场Top2集合不同的场次。
排除发生在候选池阶段，再完整重建原七场来源组，最后删一场并压一场为六串一。
不排除全部零让球，不增加首选一致/50%门槛或主流联赛限制，不改默认策略。

过滤511/2561场，保留2050场。新旧均48期下注，每期预算1024元，组价64元。
控制组的48期源组和最终六串逐场持仓、票据、投入、现金和组数精确复现。

|指标|原六串一|过滤后|
|---|---:|---:|
|命中期|41/48（85.42%）|37/48（77.08%）|
|盈利期|22|14|
|组数 / 命中组|746 / 121|730 / 104|
|实际投入元|47744|46720|
|净收益元|11357.61|1916.14|
|投入ROI|23.79%|4.10%|
|预算ROI|23.11%|3.90%|
|最大回撤元|5251.49|9442.55|
|最长连续未中|2|3|

少投入1024元却少赚9441.47元；最大回撤上升4191.07元。
新增命中100520，但该期仍亏损；失去100406、100502、100508、100515、100601。
命中不等于盈利。剔除配对增益最大100421后净增益为−12590.66元。
不支持把当前过滤规则直接迁移到这套高命中策略。

重建候选组也会改变其余场次的搭配和单选位置，结果不能解释为被过滤场次本身
具有因果优势；只说明该完整过滤变体在本样本不如对照。

## 与原U3/U6的相关性

对齐同48期逐期净收益，包括不下注期0收益。

|六串一|对U3 Pearson / Spearman|对U6 Pearson / Spearman|
|---|---:|---:|
|原方案|0.125 / 0.342|0.166 / 0.401|
|过滤后|0.160 / 0.235|0.144 / 0.368|

过滤没有明显改善线性收益相关性，牺牲收益且扩大回撤。
它与U3共同命中16期、独有21期，U3独有3期；与U6共同17期、独有20期，U6独有2期。
低相关不等于组合收益改善，本轮没有叠加或增加预算。

## 复现入口与契约

- `src/fundamentals_high_hit_filter.py::high_hit_n6_plan`：单期无标签预测表与显式cutoffs；
  排除开关、1024/2/.65和候选/场景种子参数显式传入。返回封存源组、六串计划及排除账本。
  输入p由调用方提供大让球市场校正，函数不拟合或读写文件；少于七个保留候选失败关闭。
- 复用候选过滤、原n7单选、breadth/bridge、rescue_shape、fixed_n67_wallets和权威结算。
  没有复制时间切分、缓存、标签可用性或结算实现。
- `scripts/high_hit_filter.py freeze --study NEW`先生成192计划；`settle`随后读取绑定审计。
- `scripts/check_high_hit_filter.py --study STUDY`独立核验2238组的Cartesian票据、单选/删场、
  ID/盘口、复用上限、资金和一次0.65结算，不改写计划或结果。
- `quarto/105_high_hit_filter.qmd`使用R展示汇总、48期明细、相关性、收益与回撤图。
  原始study为`data/derived/fundamentals_417/high-hit-filter-v1`，初始资金100000元。
- `tests/fixtures/high_hit_filter.json.gz`保存报告文本和哈希，可通过已有
  `prepare_n7_single_fixture.py`恢复，`archived_report:true`仅回放报告。

192计划封存后才开启本轮结算。receipt绑定原cutoff、源/代码闭包、参数、原组证据、
报告代码与结算指针。旧历史来源保留为带哈希的证据清单，不验证为当前前瞻接口；
历史时间代理不能证明当时真实可用性，全部historical_admission=false。
未变更任何原始数据、模型、既有默认策略或GitHub生命周期。

## 验收

新增函数由test_fundamentals_high_hit_filter.py覆盖：开关、输入不变、重复确定性、
完整组合、预算/复用、空/小候选池、非法常量、标签拒绝、cutoff身份隔离、报告恢复。
下游既有函数运行对应回归测试。脚本主入口由48期封存/结算/独立重放覆盖；
报告使用现有受测R汇总函数。CI增加Python测试与夹具恢复后干净Quarto执行，
现有cutoff治理保持启用。最终测试、渲染和Codex审核记录见验收补记。

实时Issue Graph：#419 OPEN，blockedBy #421；#421 OPEN，blocking #419且parent #419；
两者ProjectItems为空。本轮不满足或绕过#421跨年因果验收，不关闭Issue或合并PR。

### 执行方验收补记

- 项目Python：`/home/drwho1985/.codex/validation-envs/compression-bridge/bin/python`。
  `-m pytest tests/test_fundamentals_high_hit_filter.py tests/test_fundamentals_candidate_exclusion.py tests/test_fundamentals_rescue_shapes.py tests/test_fundamentals_compression_bridge.py tests/test_fundamentals_market_blend.py tests/test_fundamentals_missed_portfolio.py -q`：38 passed。
- 上述Python执行`scripts/check_high_hit_filter.py --study data/derived/fundamentals_417/high-hit-filter-v1`：
  PASS，192计划、2238组；`scripts/check_cutoff_governance.py`：PASS。
- R使用`R_LIBS_USER=/home/drwho1985/workspace/algotradinglife/beijing-lot/r_lib`、
  项目`pure-baseline-checks-v1/tmp`临时目录，testthat::test_file(stop_on_failure=TRUE)
  逐一运行pure-report、equity-curves、missed-summary、hit-improvement四个测试文件，通过；
  日志`data/derived/fundamentals_417/high-hit-filter-r-tests.log`。
- Quarto1.10.18现场和离线夹具各执行一次：
  `quarto render quarto/105_high_hit_filter.qmd --execute-dir . --execute --no-cache`；
  离线追加`-P study:data/derived/fundamentals_417/high-hit-filter-archive-v1 -P archived_report:true`。
  全新进程、禁用缓存、错误致命，两次通过。四张表分别4/2/4/192行、两图、无错误单元；
  两份HTML表格文本逐项相同。图像查看工具受沙箱挂载配额阻碍，未声称像素级视觉审核。
- 未运行无关全仓R/Python测试；未声称远程CI已通过或完成#421验收。

### 独立Codex审核

`codex review -`：无可执行发现。审核者成功读取实时Issue Graph，独立通过111项Python测试、
check_high_hit_filter及cutoff治理，复核全部48期原组/控制重现、96份N6支持与组合映射、
现场/夹具/离线文本绑定及收益/回撤总数。原文：
`data/derived/fundamentals_417/high-hit-filter-review.txt`。
审核者自身R环境缺少jsonlite，未独立重跑R/Quarto；执行方已用明确项目R库完成四文件测试
和现场/离线全新渲染，不将两者混称为独立R审核。未授权合并或关闭Issue。
