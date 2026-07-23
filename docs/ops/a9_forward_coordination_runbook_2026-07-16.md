# A9 前瞻保护腿比较器生产协调运行手册

日期：2026-07-16

状态：`production_coordinator_ready_research_only`。本流程只协调研究侧
`S13_A9_SIMPLE_RUNNER_FORWARD_V1`，不启用策略、不生成票据、不写生产数据库，
也不修改 API、前端、采集器或 release manifest。

## 目标与边界

生产侧只负责两件事：

1. 标准三市场 overlap 锁定后，发布不可变 `A9_INPUT_READY` 事件包；
2. 在最早停售前至少 10 分钟校验事件并调用研究侧 freeze，之后只路由路径、
   摘要和状态。

研究侧拥有 freeze/status/settle 产物。生产协调器只能读取其
`SHA256SUMS`、manifest 和状态输出，不能传递选码、保护深度、预算、阈值或正式
执行参数。

## 固定路径

共享协调根：

```text
/home/drwho1985/workspace/soccer/beijing-lot/results/coordination
```

单期事件路径：

```text
results/coordination/a9/<issue>/A9_INPUT_READY_v1/
  manifest.json
  SHA256SUMS
```

生产编排通知保存在同一期 `.orchestration/notifications/` 下；研究 snapshot 和
settlement 仍只写研究 worktree 的 `results/strategy_parallel/`。

## 发布流程

overlap 锁定步骤必须显式调用：

```bash
.venv/bin/python scripts/a9_forward_coordinator.py publish \
  --issue ISSUE \
  --overlap-dir /absolute/path/to/locked/overlap
```

发布器会先完整校验 overlap 的 `SHA256SUMS`，再从 `overlap_matrix.csv` 推导：

- `issue_rows`、`eligible_rows` 和覆盖率；
- 排除场次；
- eligible cohort 的最早停售时间；
- overlap `SHA256SUMS` 的 SHA-256。

事件先在同一父目录的私有临时目录完成写入、校验和 fsync，再原子 rename 到正式
路径。`event_id=A9:<issue>:<overlap SHA256SUMS SHA-256>`。重复 event_id 返回既有
事件；同一期不同 digest 会拒绝覆盖。

## 协调流程

`beidanlot-a9-coordinator.timer` 每分钟扫描一次有效事件。每个事件依次执行：

1. 重新校验事件包和 overlap 的所有摘要；
2. 获取 event_id 对应的进程锁；
3. 检查距离最早停售是否仍有至少 10 分钟；
4. 调用研究 worktree 的 A9 freeze；
5. 校验研究 snapshot 的 issue、overlap digest、paper-only 标志和 `SHA256SUMS`；
6. 只输出 `event_id`、产物绝对路径、SHA-256、状态和距停售秒数。

错过时间窗时只发布 `FREEZE_EXPIRED`，不调用研究侧。已有相同 event_id 的研究
snapshot 会校验后复用，不会创建第二份。

结算必须显式触发：

```bash
.venv/bin/python scripts/a9_forward_coordinator.py settle --issue ISSUE
```

协调器先调用研究侧 status。只有 `settled_rows == frozen_rows` 且
`settlement_ready=true` 才调用 settle；部分结算只发布
`SETTLEMENT_REJECTED`，不生成结算产物。

## Dry-run 验收

2026-07-16 已在完全隔离的 `tmp_path` 非实时夹具根完成五项生产侧验收：

| 验收项 | 预期 | 结果 |
| --- | --- | --- |
| 坏事件摘要 | freeze 前拒绝 | 通过 |
| 重复 event_id | 只生成一个 snapshot | 通过 |
| 距停售不足 10 分钟 | `FREEZE_EXPIRED`，无 snapshot | 通过 |
| 部分结算 | `SETTLEMENT_REJECTED`，无 settlement | 通过 |
| 非实时夹具成功链路 | publish -> freeze -> settle | 通过 |

生产侧测试：

```bash
.venv/bin/pytest -q tests/scripts/test_a9_forward_coordinator.py
```

研究侧 A9 原有四项测试也必须保持通过。第一期 live 事件仍然是
`research_paper_nonselectable`，任何结果都不能直接提升为正式策略。

## 调度与排障

安装或刷新 user units：

```bash
scripts/install_decision_dashboard_systemd.sh
systemctl --user status beidanlot-a9-coordinator.timer
systemctl --user status beidanlot-a9-coordinator.service
```

默认研究根为：

```text
/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-strategy-beijing-lot-model-betting-20260712
```

可在 `~/.config/beidanlot/a9_coordination.env` 通过 `A9_RESEARCH_ROOT` 覆盖。研究
worktree 或其 A9 CLI 不存在时，systemd condition 会跳过扫描，不会回退到生产
策略或其他脚本。
