# 三单选七串一：复用与赛果变化

交付：`quarto/67_n7_reuse_diversity.qmd`。沿用已揭示40期和原预算55,040元；冻结专家，不重训练。回顾分区为TRAINING24、VALIDATION8、TEST8，不作为新测试或可交易证明。

每组3单选、4双选，16基本票×2元；先不重叠、再逐组MILP补组，复用上限2/3/4/6、任意两组交集≤2。不能购买完整组则保留现金。组内单选角色按最高Top1概率；固定支持与p/(1+已有方向覆盖次数)多样化支持同组同额比较。方向变化不改原p或市场q，不是概率校准。

第一轮高上限会重选补组，因此另做事后NESTED对照：从CAP2固定计划依次提高3/4/6，保留所有旧组，只追加。NESTED多样化使用相同组序；原有组的多样化支持也保持不变。两轮分别冻结后使用同一R/SQLite审计结算；不声称此前未见结果。

复用接口：
- `n7_single_plan(..., cutoffs, max_uses, single_count=3, ...)`：生成固定方向计划。
- `diversify_n7_outcomes(base, cutoffs, rule)`：原分组内的确定性方向多样化。
- `extend_n7_reuse_plan(base, frame, cutoffs, max_uses)`：原组前缀不变的增量补组。
- 结算复用`settle_n7_single`，报告复用R的`integration_weight_summary`。

对应测试：`tests/test_fundamentals_n7_single.py`、`tests/test_fundamentals_n7_diversity.py`；相邻调用回归`tests/test_fundamentals_n7_selection_variants.py`。独立枚举`check_n7_reuse_diversity.py`核对支持、完整票、约束、原组前缀、返奖、覆盖与预算。所有规划接口使用共享Cutoff，未增加历史拟合或时间治理实现。

运行初始研究：`scripts/run_n7_reuse_diversity.py --parent data/derived/fundamentals_417/n7-compression-v1 --output <新目录>`；增量对照：`scripts/run_n7_reuse_extension.py --parent <初始研究目录> --output <初始研究目录>/nested-v1`。使用项目Python；不可覆盖已冻结目录。独立检查分别对两个目录传`--study`。

QMD声明`study`和`nested`。正常渲染校验真实绑定文件；CI通过两个gzip归档和`prepare_n7_single_fixture.py`恢复报告数据，必须显式`archived_report:true`，仅验证报告，不冒充模型重放。

本轮不自动升级默认策略。验收和数字以研究目录的日志、冻结回执、报告和Codex review为准；本地检查通过不等于远程CI已经运行。
