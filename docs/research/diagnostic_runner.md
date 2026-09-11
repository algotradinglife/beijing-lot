# 可维护的类别诊断入口

入口：`scripts/diagnose_fundamentals.R`。分析实现复用
`r/fundamentals_category_diagnostics.R`；导出/读取接口位于
`r/fundamentals_diagnostic_runner.R`；通用报告模板为
`quarto/92_diagnostic_runner.qmd`。

## 一次运行

在仓库根目录、已安装项目 R 依赖和 Quarto 的环境中执行：

```sh
Rscript scripts/diagnose_fundamentals.R \
  data/derived/fundamentals_417/category-diagnostics-v2 \
  data/derived/fundamentals_417/my-diagnosis-001
```

输出目录必须是新目录，父目录必须存在。默认导出后执行 QMD，
在该目录生成 `report.html`；每次复查使用新的输出目录。
Quarto 不在 PATH 时，设置 `QUARTO_PATH` 为可执行文件绝对路径。
脚本可从其他目录调用；输入输出相对路径按调用时目录解释。

- `--help`：使用说明。
- `--no-render`：仅输出表格、QMD 和来源记录。
- `--archived`：只接受恢复后带 archive.json 的校验归档；
  这是归档展示，不是模型重放或前瞻使用许可。

默认模式要求输入原始绑定仍可验证。仓库内已保存的归档可以离线恢复：

```sh
python scripts/prepare_n7_single_fixture.py \
  --fixture tests/fixtures/category_diagnostics.json.gz \
  --output data/derived/fundamentals_417/my-category-archive
Rscript scripts/diagnose_fundamentals.R \
  data/derived/fundamentals_417/my-category-archive \
  data/derived/fundamentals_417/my-archive-diagnosis --archived
```

## 输入和输出契约

输入是经过来源校验的已结算 N7 类别诊断包，包含
`results.json`、`plans-frozen.json`，数据字段为
`factors/features/legs/audit/rows`。每期只能有一条原对照方案记录。
字段类型、主键、概率、支持方向及关联关系由已有诊断函数校验。
此入口不直接接收任意 SQLite 或任意策略结果目录；新数据须先按同一契约打包。

| 输出 | 内容 |
|---|---|
| summary.csv | 类别、概率分箱、让球深度、联赛、历史支持量等的实际与预期命中率 |
| observations.csv | 三种统计口径的逐场支持、市场概率与基线概率 |
| original_groups.csv | 原组别错误数和差一场未中情况 |
| original_issues.csv | 逐期命中和未中归因 |
| diagnostics.json | 同一组表格的结构化结果 |
| receipt.json | 输入和实现散列、生成时间、环境版本、实际期数和未中期数 |
| report.qmd / report.html | 可复核的通用报告及渲染结果 |

统计切片统一为 ALL / MISSED / HIT，不再把48/25/23写死在函数内。
原 category-diagnostics-v1 保存为历史证据；QMD91和归档夹具更新为v2，
仅变更标签及实现绑定，没有重训练或改变投注方案。

输出先写入私有暂存目录，成功后一次发布。导出失败清理自身暂存目录；
已有输出不会覆盖。若渲染失败，已导出的表保留且进程返回失败。
可以进入该输出目录后，重新执行：

```sh
quarto render report.qmd --execute-dir /绝对路径/仓库 \
  --execute --no-cache --output report.html \
  -P diagnostics:/绝对路径/输出目录
```

读取函数验证导出文件和当前绑定代码；代码更新后旧导出会拒绝重渲染，
应重新诊断生成新目录。来源散列保留在回执，独立移动导出目录不能替代
原绑定代码的存在。HTML用于查看，不作为新的拟合或选场输入。
本轮是结算后描述，不改变赛前概率、不自动屏蔽类别、不新增专家。

## 测试和验收

`run_category_diagnostics` / `read_category_diagnostic_output` 对应
`tests/testthat/test-fundamentals-diagnostic-runner.R`：
验证两期子集的通用计数、跨目录和空格路径调用、帮助/错误参数、
不渲染模式、拒绝覆盖、缺失父目录、篡改检测以及写入失败回滚。
`category_diagnostics` 对应原有同名 testthat 测试。

本地检查：

```sh
Rscript -e 'for (f in c("diagnostic-runner","category-diagnostics","missed-issues","pure-report")) testthat::test_file(paste0("tests/testthat/test-fundamentals-",f,".R"),stop_on_failure=TRUE)'
python -m pytest tests/test_fundamentals_n7_single.py -k category_diagnostics -q
python scripts/check_category_diagnostics.py
python scripts/check_cutoff_governance.py
```

R相关测试45项断言通过（15+11+13+6），未运行整个仓库的R/Python测试；
此次未改动其他业务模块。CI增加相同入口测试和归档完整渲染。
完整48期输入已在 diagnostic-cli-v3 生成报告；
归档执行另保存在 diagnostic-cli-archive-v1。原QMD91重新执行。
这些输出位于 data/derived/fundamentals_417，原快照未覆盖。
独立复算1,568个分层行通过；归档测试1通过；cutoff governance通过。
现场与归档输出的diagnostics.json完全一致；通用HTML均含6张表，
完整分层表1,799行，原QMD91含8张表。对应日志：
diagnostic-runner-tests.log、diagnostic-cli-v3.log、
diagnostic-cli-archive-v1.log、category-v2-render.log。

本工作属于#419的描述性诊断支持，不解除#421依赖，也不声称完成截止时点治理验收。

## Codex独立审核

本次只读Codex审核无阻塞或新增可操作缺陷。审核独立验证两种运行的
输入/实现/输出散列、全部1,799个分层与明细重算、HTML表数量，
以及归档结果载荷未变。审核受只读沙箱限制未重跑R测试或渲染；
上述45项断言和完整渲染由执行方完成。审核文本位于
data/derived/fundamentals_417/diagnostic-runner-review.txt。
执行方另以在线GitHub读取确认#419仍被开放的#421阻塞；不关闭Issue。
