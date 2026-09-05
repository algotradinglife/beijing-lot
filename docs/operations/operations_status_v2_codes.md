# Operations Status v2 状态码

`GET /api/issues/<issue>/operations` 的 `schema_version` 为
`operations_status_v2`。旧的 `issue_status`、`runtime`、`sources`、
`snapshots`、`review`、`workflow`、`versions` 和 `warnings` 在兼容期内保留；
`warnings` 只是 canonical `alerts` 的兼容投影，不是第二套判断。

## 通用状态

| 状态 | 含义 | 操作原则 |
|---|---|---|
| `ok` | 当前检查通过 | 无需动作；不等于策略、执行或收益准备度 |
| `running` | 任务正在运行 | 等待完成并再次检查 |
| `due` | 已到计划动作或等待计划窗口 | 检查 `next_due_at` 与自动恢复预期 |
| `partial` | 部分覆盖或部分成功 | 查看影响范围与下一动作 |
| `stale` | 超过该来源自己的 SLA | 检查采集器最近尝试、进程和覆盖 |
| `failed` | 检查或执行失败 | 按告警诊断引用处理 |
| `missing` | 必需事实或产物缺失 | 不能按正常处理 |
| `blocked` | 下游能力被明确阻断 | 先关闭阻断项 |
| `not_applicable` | 当前期、阶段或能力不适用 | 不触发异常 |

未知状态必须在前端显示为 `未知状态（原值）` 并使用失败色，不能静默显示为正常。

## Segment 冻结时间线

| 状态 | 含义 |
|---|---|
| `scheduled` | 冻结窗口尚未到达，系统预计按计划尝试 |
| `frozen` | 对应不可变包和校验摘要可用 |
| `missed` | 已错过前瞻窗口；不得事后伪造成前瞻冻结 |
| `unavailable` | 契约或其中一种必需证据不可用 |
| `verification_failed` | 包、ledger、身份或 hash 校验失败 |

定时 exact-N、p40/p42 research freeze 和用户即时生成使用不同身份。
即时生成始终 `research_evidence_eligible=false`，状态页不得记录或推断用户线下购买。

## 告警字段

每条 `alerts[]` 都有稳定 `alert_id`，并包含：

- `domain`、`severity`、`status`；
- 用户可读 `detail`、`impact`、`next_action`；
- 首次、最近、最近成功与下次计划时间；
- 受影响 segment、match、market 和 source；
- 自动恢复预期、重试次数、受控诊断引用；
- 对数据展示、研究冻结、即时生成和结算的阻断标记。

顶部阻断数、警告数和“待处理事项”必须直接使用同一 `alerts` 列表。

## 公共诊断边界

异常、数据库错误和健康探针错误属于不可信自由文本。Operations API 会将其中
的 HTTP(../ops/S) URL、Authorization/Bearer、token、API key、password、cookie
及绝对文件路径替换为脱敏标记。运行时兼容字段只暴露状态白名单，不透传原始
command、diagnostics 或 URL 快照。

可导航的受控引用必须由后端写入结构化 `links[]`，不能通过异常文本传递。
