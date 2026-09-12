# 结算工具发布验收（#430）

日期：2026-09-13。范围是历史五玩法采集/重放/汇集/SQLite 重建、
审定缺失比分 SP 修正、外置目录保护与 R 读取。未修改实际结算数值。

## 已执行检查

- 项目 Python `-m pytest tests/test_nowscore_history* tests/test_nowscore_issue_inventory.py tests/test_nowscore_settlement.py tests/test_nowscore_archive.py tests/test_nowscore_replay.py tests/test_settlement_sp* tests/test_settlement_storage.py tests/test_fundamentals_census.py tests/test_fundamentals_capture.py tests/test_fundamentals_pipeline.py -q`：293 passed，零跳过。
- Python 测试显式提供 `QUARTO_BIN`，包含三次干净历史报告渲染及 HTML 表格检查。
- `Rscript tests/testthat.R`：全部通过，零跳过。先用 `scripts/materialize_fundamentals_pipeline_fixture.py` 创建集成 bundle，并显式设置 `FUNDAMENTALS_PIPELINE_TEST_BUNDLE`、`FUNDAMENTALS_PYTHON`、`BEIJING_LOT_VENV_PYTHON`、`R_LIBS_USER`。
- `python scripts/check_cutoff_governance.py`：PASS。
- `quarto/10_settlement_external_storage.qmd`：外置盘现有库只读渲染通过；合成库和带前导零期号的 JSON 参数渲染通过。
- 实际 exFAT 挂载盘上的独立临时合成库：新库生成、SQLite 备份、SP 更新和重复执行通过；测试目录结束后清理，实际历史数据库未写入。
- 最终 `codex review`：PASS，无剩余可操作缺陷。首轮发现的主队/客队 ID 字段回退、严格空开奖页识别、原始报告误接收更正库三项均已修复并增加回归测试。

## 函数与测试映射

| 实现 | 对应测试 |
|---|---|
| nowscore_issue_inventory | test_nowscore_issue_inventory.py、test-nowscore-inventory.R |
| nowscore_history_plan/capture/assembly | 同名 test_nowscore_history_*.py（包括命令入口） |
| nowscore_settlement、nowscore_replay | test_nowscore_settlement.py、test_nowscore_archive.py、test_nowscore_replay.py |
| settlement_sp_supplement/update | test_settlement_sp_supplement.py、test_settlement_sp_update.py（包括更新入口） |
| settlement_storage | test_settlement_storage.py |
| nowscore_query.R、nowscore_history_report.R | test-nowscore-query.R、test-nowscore-history-report.R |

数据库生成保持来源原始值；SP 修正需明确审定清单并保留原值。
历史证据没有授权新的前瞻可用性或学习流程。GitHub CI 再执行独立环境检查。

## GitHub 执行环境限制

PR #431 的 Actions run 34704248699 没有启动 runner。GitHub 注释明确指出账户付款失败或 spending limit 限制；无远程测试日志，不能计为 CI 通过。仓库未报告必需状态检查。本次自动化验收证据为以上实际执行的本地检查和独立 Codex review；远程 CI 需账户额度恢复后重新执行。
