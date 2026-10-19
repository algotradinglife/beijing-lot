# 复用与验收入口

以下路径相对 beijing-lot 仓库根；先核实当前函数签名与测试。不要在 skill 里另建解析器、结算选项域或时间工具。示例报告和脚本是查找入口，不保证其默认输入永远最新。

|用途|现有入口|
|---|---|
|跨期异常与人工裁决记录|docs/research/fundamentals-data-quality-register.md|
|采集/解析结果整理|src/fundamentals_issue_pages.py、src/fundamentals_issue_report.py|
|主源整合|src/fundamentals_pilot.py 的 pilot_tables|
|全量盘口核验与方向转换|src/fundamentals_scope_market.py、src/fundamentals_market_orientation.py；r/fundamentals_scope_market.R|
|大小球解析|src/fundamentals_titan_total.py 的 parse_titan_total_html|
|日期对齐|src/temporal_learning/roster_clock.py 的 roster_clock_alignment|
|部分日期报价窗口与行顺序|src/temporal_learning/partial_clock.py 的 diagnostic_monthday_quotes|
|验证清理 release、基本面和盘口可用性|src/fundamentals_clean_validation.py|
|准备派生输入|scripts/prepare_clean_validation.py|
|裁决层与归档示例|quarto/26098_135_official_clock_20261019.qmd；src/fundamentals_audit_bundle.py（归档发布，不是业务表裁决消费者）|
|SQLite 只读结算查询|r/nowscore_query.R 的 query_nowscore_settlement|
|稀疏查询全选项按 1 裁决|src/nowscore_query_adjudication.py 的 apply_query_all_one；config/day_status_all_one.json|
|盘口顺序/日期清理展示|quarto/74_new48_quote_source_order.qmd|
|人工结算有效表展示|quarto/75_day_status_settlement_adjudication.qmd|

## 执行与验证

- 从项目配置选择 Python、R 库与 Quarto，显式传路径；不要复制其他机器的绝对路径。reticulate 绑定项目 venv 可执行文件，不要通过解析可执行文件符号链接丢失虚拟环境。
- manifest 必须绑定输入哈希、传递实现身份、参数、原 cutoff 与生成时间。新输出使用独立 release；未验收中间结果不能替代已验收输入。
- 函数变更匹配 tests/ 下 pytest 或 tests/testthat/ 测试：覆盖原始数据不变、精确修正范围、重复执行、来源元数据、空/错误输入，以及午夜边界和截止前后等相关边界。
- 常用对应测试入口：tests/test_roster_clock_alignment.py、tests/test_fundamentals_clean_validation.py、tests/test_fundamentals_titan_total.py、tests/test_nowscore_query_adjudication.py。按实际修改选择，不用例行无关全量测试替代针对验证。
- 执行项目 Python 的 `-m pytest`；R 用 `Rscript tests/testthat.R`。涉及截止/学习治理时运行 `scripts/check_cutoff_governance.py`，历史学习工具只来自 packages/beidan/inst/python/beidan_backend/temporal_learning；旧客户端时序入口不能用于新历史学习。
- QMD 输入通过参数声明，干净进程执行、绕过 cache/freeze，错误致命；检查 HTML 中表格结构、首行、单位和排除计数。报表运行不自动写 SQLite；不依赖 RStudio 全局对象。
- 用户要求 Codex review 验收。对本次明确变更及契约审查，修复发现后复审；报告实际运行命令和证据。审查环境缺依赖不能说独立测试通过，执行者测试与审查结果分别陈述。
- 清理报告只报告已验证的清理结果；未重跑的预测、命中率、每期收益/ROI/回撤不能借用旧数字冒充更新结果。

## 维护 skill

仓库 `skills/beijing-lot-data-cleaning/` 为可版本管理的源，用户技能目录中的同名目录为安装副本。修订时同步两处并运行 skill-creator 的 quick_validate.py；不要覆盖其他技能。技能文件变更无需重跑数据 QMD，但实际数据/函数变更仍须上述验收。
