# v3.3.3 Phase 1 基线审计

日期：2026-07-11
对应卡片：`t_8b6b7373`
结论：Phase 1 验收通过，正式策略参数未变；Phase 2 可以在该冻结基线上开展主押实验。

## 1. 已完成修复

### 1.1 唯一决策核心

- API 的 `_gpt_fixed_chain_decision` 通过统一输入适配调用 artifact 生成器使用的
  `structured_decision_for_payload`。
- API 与 artifact 不再各自维护一套 v3.3.3 押/保/停规则。
- 增加 parity 测试，覆盖选择码、主押、保护、停牌、判断、置信与决策链。
- 原 API 实现保留为明确命名的 legacy 函数，不再进入运行路径。

### 1.2 开赛前 artifact 锁定

- artifact cutoff 定义为该期最早开赛时间。
- API 的策略、看板、详情和结算路径只选择 cutoff 之前生成的同版本最新 artifact。
- 响应增加 `artifact_generated_at`、`artifact_cutoff_at` 和 `pre_kickoff_valid`。
- 补齐 v4.2.0004 legacy alias，只用于公平观察对照，不改变默认策略。

26073 线上验证：v3.3.3 锁定 artifact 生成时间为 `2026-07-07 21:36:12`，首场
cutoff 为 `2026-07-07 23:50:00`，10 场均为 `pre_kickoff_valid=true`。7 月 8 日和
7 月 10 日的赛后 artifact 不再进入正式比较。

### 1.3 结算与复盘口径

- 无真实票池结算时，`total_stake/total_payout/pnl/roi` 返回 `null`，并设置
  `financials_status=unavailable_no_ticket_settlement`。
- 比赛赛果数量与票腿结算分离：无票池时 `n_legs_total/n_legs_hit=0`，比赛结果使用
  `match_settlement_count`，SP 诊断使用 `match_result_sp_sum`。
- 复盘增加 `total/settled/reviewed/complete/status` 范围，不再用部分复盘代表整期。

26073 线上验证：10 场已结算、4 场已复盘、状态为 `partial`，无票池财务字段全部为
`null`。

### 1.4 停牌与前端语义

- `stop_flag` 只表示不可出票。
- v3.3.3 在有有效选择码时的低 q 风险停牌改为 `advisory_stop_flag=true`，不再被前端
  清空选择；真实无选择或执行 skip 仍为不可出票。
- 前端复盘明确显示已复盘/已结算范围，并将无票池字段标为复盘口径，不伪装成真实收益。
- 旧 API 未提供完整性字段时按完整复盘处理，保持前端向后兼容。

## 2. 验证结果

| 验证 | 结果 |
|---|---|
| `py_compile`：API 与 structured core | 通过 |
| 决策 API、release/freeze、structured core 测试 | `49 passed` |
| 前端 Vitest（`VITE_DATA_MODE=mock`） | `19 passed` |
| 前端 TypeScript 与 Vite production build | 通过 |
| `pytest -q tests` | `471 passed, 3 skipped, 3 failed` |
| 线上重启与 health/operations smoke | 通过 |
| 线上 26073 artifact/settlement contract | 通过 |

`pytest -q tests` 的 3 个失败均位于未修改的旧 WebUI：两个空 SQLite 夹具缺少
`settlements` 表，一个旧票生成夹具未生成 ticket。根目录直接执行 `pytest` 还会误收集
`notebooks/draw_correction_test.py`，该文件读取不存在的 macOS 绝对路径。上述问题不影响
Phase 1 相关 49 项测试，但应独立建卡治理测试基线。

## 3. 残余风险与后续约束

- 旧 artifact 没有显式 `generated_at`，锁定逻辑兼容使用文件 mtime；新 artifact 应逐步写入
  manifest 时间戳并以其为主。
- 共享核心目前物理定义仍位于 `scripts/`，功能上已唯一；后续可迁入 `src/`，迁移必须保持
  parity golden 不变。
- 没有合法开赛前 artifact 的历史期会明确显示正式版本不可用，不允许回退到赛后结果。
- Phase 2 只能改变主押排序，必须冻结覆盖集合和成本，以隔离主押优化的真实贡献。
