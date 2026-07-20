# v3.3.3 Phase 3 保护裁剪 Forward 协议

日期：2026-07-12
候选：`phase3_drop_switched_ev_home_protection`
版本：`v0.1.0000`
执行：`execution_enabled=false`

## 固定规则

候选仅在以下条件同时成立时，从 paper 副本删除保护码 `3`：

1. 正式主押与最高 q/EV 方向不同；
2. 最高 q/EV 方向为 code `3`；
3. code `3` 已位于正式覆盖集合中且不是主押。

候选不改变 `shadow_selection_codes`、Active 快照或下注计划。让球平保护和其他来源的 code `3` 保护不受影响。

## Artifact 字段

每场 structured artifact 输出：

- `phase3_protection_experiment_id`
- `phase3_protection_experiment_version`
- `phase3_protection_baseline_codes`
- `phase3_protection_candidate_codes`
- `phase3_protection_triggered`
- `phase3_protection_removed_code`
- `phase3_protection_reason`
- `phase3_protection_execution_enabled`

## 样本锁定

`scripts/monitor_v3_3_3_phase3_protection_forward.py` 同时扫描整期和 operational 分段 artifact。

- 只接受 `shadow_arm=active_v3.3.3`、exact experiment ID/version 且 execution disabled 的行。
- 每场只保留 `artifact mtime < kickoff` 的最后一份 artifact。
- 开赛后生成的 artifact 不能覆盖该场已锁定样本。
- draft、v4.2、旧版本字段和未携带候选的 artifact 全部排除。
- 未结算行进入 sampled ledger；赛果和 winning SP 齐全后进入 settled ledger。

## 评审门槛

全部满足后状态才从 `collecting` 变为 `ready_for_review`：

| 门槛 | 要求 |
|---|---:|
| 触发期数 | >= 5 |
| 已结算有效触发 | >= 30 |
| 覆盖变化 | >= -2pp |
| 平均深度下降 | >= 0.05 |
| profit proxy | 不劣于 baseline |
| 执行隔离 | 所有样本 `execution_enabled=false` |

`ready_for_review` 不自动修改 release。进入 Phase 4 前仍需固定 N、相同分段、预算和随机种子的配对组合实验。

## 展示与运行

- `live_artifact_refresh_loop.py` 每轮更新 Phase 3 monitor；失败只记录状态，不阻断正式 artifact。
- API `/api/strategies/lab` 通过 `forward_experiments` 返回只读摘要。
- “策略实验”页显示样本、触发、已结算触发、覆盖/深度/profit 变化和门槛通过数。
- 详细数据位于 `results/phase3_protection_forward/`。

## 异常告警

从候选启用时间 2026-07-12 15:03 起，monitor 每轮审计：

| 告警 | 严重度 | 条件 |
|---|---|---|
| `artifact_fields_missing` | bad | 未来场次已有 Active artifact，但缺少 exact Phase 3 字段 |
| `prekick_sample_missing` | bad | 未来场次没有可锁定的赛前 Active artifact |
| `execution_enabled` | bad | exact 候选出现非零执行标志 |
| `settlement_stalled` | warn | 已锁定样本开赛超过 180 分钟仍无赛果或 winning SP |

摘要缺失或在仍有未完赛场次时超过 15 分钟未更新，也会由 Operations API 生成 `phase3_forward_*` 告警。“运行状态”的待处理事项以“策略监控”分类展示；历史期次不触发实时 monitor 告警。

## 首次 Smoke

2026-07-12 15:03 的 26074 operational artifact：

- 65/65 行携带 exact candidate ID/version；
- `execution_enabled=1` 为 0 行；
- 正式 `shadow_selection_codes` 与候选 baseline 不一致为 0 行；
- 全 artifact 触发 9 行；开赛前未来样本锁定 29 行，其中触发 5 行；
- 当前未结算，monitor 状态 `collecting`。
