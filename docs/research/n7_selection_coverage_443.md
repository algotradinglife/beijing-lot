# #443 选组与覆盖预声明

本轮为已暴露 200 期的固定规则回顾诊断，不重训概率，不作未见数据验收。
欧赔与大小球映射用于冻结概率和估算 SP；北单实际 SP 只在全部计划冻结之后结算。
两者支付机制差异不作为本轮校正对象。

## 固定比较矩阵

固定 25% 累计概率在 256 元内可达的准入条件，比较以下九个策略：

- 固定深度、先开组 × 三种排序。
- 可变深度、先开组 × 三种排序。
- 可变深度、开组和加深竞争 × 三种排序。

三种排序是：新增各组累计概率之和/新增资金；联合至少中一组概率增量/新增资金；估算净收益增量/新增资金。
估算收益仅排序，不要求估算净收益为正；无合法动作时保留现金。
不进行倍投，不引入撤减、交换或 #427 的完整资金重分配。
可变深度/先开组/联合概率是 #441 DEPTH 对照。

每项在 512、768、1024 元预算及 42501、42502、42503 种子运行，共 16200 个计划。
深度全集仍包含 25% 和 30% 两种原准入规则产生的深度，再叠加原固定深度网格，防止改变对照候选集。
固定 N=7、2 元单位、票级一次 0.65 结算系数，初始资金 100000 元。
分配使用 256 个模型世界，独立概率评估使用 5000 个世界及种子偏移 1000000。

## 交付与边界

统一报告所有策略和种子、投入、净收益、ROI、命中/盈利期数、回撤、50 期分段、去掉最大 1/3/5 期收益后的表现。
不依据当期结算切换策略。本轮是固定候选 24 组之内的排序与覆盖研究，不能代表候选池扩大后的表现。
运行器复用 shared R 分配器和 src/temporal_learning 的冻结输入绑定；完整计划先于结算写入，独立进程重建分配与模型指标。
配置、源码、输入和输出哈希写入凭证；函数测试、回放、干净 QMD 渲染和 Codex review 全部通过后提交 PR。

## 可复现入口

当前运行器统一使用 `policies` 表，每行包含唯一 `id`、`mode`、`objective`、`allocation_order`。
`mode` 为 BREADTH 或 DEPTH；`objective` 为 coverage_sum、any_hit 或 expected_net；
`allocation_order` 为 OPEN_FIRST 或 COMPETE。BREADTH 没有加深动作，因此只保留 OPEN_FIRST，避免重复策略。
完整配置随 `plans-frozen.json$config` 留存；其余输入显式包含 catalog、rank_dir、repository_root、python、output_dir，不能从目录年龄推断输入。

依次执行（从仓库根目录，使用已配置的项目 Python/R 环境）：

```sh
Rscript scripts/run_n7_funding_modes.R /absolute/path/config.json
Rscript scripts/replay_n7_funding_modes.R /absolute/path/study /absolute/path/study/allocation-replay.json
/path/to/project/python scripts/check_n7_funding_modes.py /absolute/path/study /absolute/path/study/independent-check.json
quarto render quarto/151_n7_selection_coverage.qmd --execute-dir . --execute \
  -P study_dir:/absolute/path/study -P output_dir:/absolute/path/new-report-directory
```

研究输出目录和报告目录必须不存在，避免覆盖已有冻结证据。
报告只接受与当前计划和结算字节匹配的独立检查凭证。
`n7_selection_report_inputs()` 负责输入凭证检查；`n7_selection_overlap()` 描述买入组合的场次复用与组间重叠；
`n7_sweet_union_summary()` 复用统一资金、ROI、命中、回撤与去极值核算。
上述描述函数不参与选组或历史拟合。
