# #533：预算驱动 Block 8 本地验收

本次交付是预算驱动的串场构建工程基线，入口仍为 `quarto/26098_walkthrough.qmd`。不预设购买组数，不宣称概率目标已优化收益或全局最优。

## 行为与边界

- `parlay_budget_state` 扣除本期真实历史购票，按整注计算可用预算。
- `parlay_generate_candidates` 在合格比赛池内生成候选，报告穷尽/抽样状态。
- `parlay_coverage_frontier` 保留合法结构空间，给出未经条件归一化的覆盖曲线。
- `parlay_allocate_portfolio` 比较新开组与加深组的下一注，执行历史复用、重叠、单组单结构和物理票去重。
- `parlay_plan_summary(result)` 展示实际已购票覆盖、结构空间、排名深度、资金与 SP 可用性；G01 等仅为展示标签。
- `parlay_build_plan` 仍衔接保存、结算、诊断与跨决策账本；公开配置删除固定 `n_groups` 和旧预设函数。

DSH 完成核心与整合初稿；整合轮连续无输出后停止其明确归属的 headless 进程，由 Codex 子代理修复接口并验收。不得把 DSH 进程退出本身当作正确性证据。

## 函数与测试映射

| 范围 | 测试 | 通过断言 |
|---|---|---:|
| 预算、搜索、覆盖曲线、分配及内部校验 | package `test-parlay-budget-allocation.R` | 172 |
| 实际购买覆盖与展示 | package `test-parlay-plan-summary.R` | 23 |
| 公共配置及完整构建 | package `test-parlay-block8-build-plan.R` | 39 |
| 保存/读取、不可覆盖 | package `test-parlay-storage.R` | 21 |
| 状态与可见性 | package `test-n7-match-status.R` / `test-n7-match-status-acceptance.R` | 109 / 27 |
| 估值、资金、冻结、结算、诊断、历史账本 | package `test-n7-pipeline-value.R` | 311 |
| 6/7/8 场、空输入及历史宽度 | package `test-parlay-variable-legs.R` | 73 |
| 原 QMD 第6–8块 | repository `test-26098-walkthrough.R` | 15 |
| 公开接口与端到端验收脚本 | repository `test-parlay-interface-regressions.R` / `test-parlay-public-flow.R` | 17 / 106 |

合计 913 条断言，最终对应专项均无失败或 warning。旧状态测试拒绝北京时间的断言已按现有明确时区合同改为：北京时间转换保持瞬间，未支持时区仍拒绝。没有用跳过测试代替修复。

测试在仓库根目录使用 `R_LIBS="$PWD/r_lib" TMPDIR="$PWD/.run-control/tmp"`，加载当前源码后逐文件执行：

```sh
Rscript -e 'devtools::load_all("packages/beidan", quiet=TRUE); testthat::test_file("packages/beidan/tests/testthat/test-parlay-budget-allocation.R", reporter="summary", stop_on_failure=TRUE)'
```

同一命令中的路径分别替换为表中实际测试路径。没有运行全仓入口 `Rscript tests/testthat.R`：此次为受影响函数及调用方的定向验收，不声称全仓测试通过。未参与 CI。

## 真实快照执行

输入：`inputs/26098_walkthrough/{schedule,markets,settlements}.rds`，原历史冻结文件 `plans/26098-20260926-121805.rds`。原始观察时间未改写。

明确复核时点：2026-09-26 17:51:58 Asia/Shanghai。验证副本 `.run-control/533-validation.qmd` 与原 QMD 仅参数不同：`refresh_schedule=FALSE`、`refresh_markets=FALSE`、`replay_decision_at` 指定上述时间；默认交互文档仍用实际当前时间，保留用户的采集开关。该历史回放不能冒充当前新方案。

```sh
BEIDAN_PROJECT_DIR="$PWD" R_LIBS="$PWD/r_lib" TMPDIR="$PWD/.run-control/tmp" \
XDG_CACHE_HOME="$PWD/.run-control/cache" DENO_DIR="$PWD/.run-control/deno" \
RETICULATE_PYTHON="$PWD/.venv/bin/python" \
quarto render .run-control/533-validation.qmd --to html --execute --no-cache
```

干净进程执行，QMD 明确 `error:false, cache:false, freeze:false`。HTML 含 11 张表、0 个 `cell-output-error`。逐项核验了预算、搜索诊断、2组汇总、192张票明细和进度表：

- 146场赛程；20场市场采集；19场准入、57行概率。
- 候选总空间50388，固定种子搜索128组，明确非穷尽。
- 1024元整期预算、2元单价；自动购192注、384元，未用640元。
- 两组均为3222221，各96注、192元；无条件累计概率分别0.1037016与0.1452598。
- 当前约束每场最多复用一组，未用资金合法；并非预设2组或384元。
- 没有完整赛前SP，目标为预计命中票数，EV不可用。两组累计概率不作为联合命中概率相加。
- 未自动保存、未下注。独立历史冻结方案仍80张待结算、0张已结算，不声称真实结算全流程完成。

第一次 HTML 检查发现同一代码块中多个 `kable()` 未显式打印而丢失表格，已修 Block8 的实际输出并重渲染检查。汇总原先格式化全部候选票，已缩小为实际购买票以减少等待。既有 skill 的“检查真实表格内容”要求足以覆盖此类问题，不能只看渲染退出码。

## 本地安装

```r
devtools::document("packages/beidan")
pak::local_install("packages/beidan", lib="r_lib", upgrade=FALSE, ask=FALSE)
```

已在独立 R 进程验证安装包来自仓库 `r_lib/beidan`，六个新接口均导出、旧 `parlay_allocation_configs` 不再导出，summary 仅接收 `result`。

## 审阅与证据

核心首轮发现并修复：预算状态与实际历史脱钩可超支、概率目标接受错误排序、伪换组内比赛绕过复用约束。每项均有反例回归，第二轮核心 review 无剩余可操作发现。

最终整合 `codex review` 结论：**No actionable defects found within the requested #533 scope**；独立复跑八份包测试及 QMD 15 条断言通过。补充审阅覆盖随后优化的购买票格式化、QMD 显式表格输出和旧公开验收脚本适配，结论亦为 **No actionable defects found in the scoped supplementary changes**。

审阅命令原文、结论与审阅时源码/传递 R 实现、输入和渲染副本 SHA-256 见 `533-block8-hashes.json`。完整本地日志分别 `.run-control/533-core-review.log`、`533-core-review2.log`、`533-final-review.log`、`533-supplement-review.log`。最终补入验收文字未改执行代码。结果表摘录保存在 `533-block8-render-tables.json`。

本地验收完成；工作区含其他任务修改和本地历史，本记录不代表代码已提交、推送或合并，也不关闭 #533。
