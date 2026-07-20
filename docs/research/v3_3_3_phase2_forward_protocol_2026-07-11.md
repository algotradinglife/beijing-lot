# v3.3.3 Phase 2 Forward 采样协议

日期：2026-07-11
实验 A：`phase2_probability_first_within_coverage` / `v0.1.0000`
实验 B：`phase2_handicap_gated_probability_first` / `v0.2.0000`
实验 C：`phase2_seasonal_league_soft_tiebreak` / `v0.1.0000`
执行状态：`execution_enabled=false`

## 1. 目的

在不修改正式 `active_v3.3.3`、不增加保护深度的前提下，持续比较原主押与
probability-first 主押。两个候选都只能在正式选择集合内部重排，因此组合覆盖和成本保持不变。

- v0.1：所有盘口均采用覆盖集合内 probability-first。
- v0.2：仅平手盘和主队让 1 采用 probability-first；其他盘口保留 v3.3.3 主押。
- 联赛 v0.1：只使用同一自然年、更早期次的严格赛前 active snapshot 已结算残差；有效样本至少 30 场、原覆盖内前两名概率差不超过 2pp 时，最多施加 1pp 收缩调整。
- 联赛标签只进入诊断分层，不参与两个候选的主押选择。

联赛实验不改变覆盖集合、保护深度或资金权重。历史 one-hot 联赛标签在 2016-2025
的 155,007 场 OOS 上整体恶化，因此该实验只检验“当前赛季短期残差是否可作为极弱 tie-break”，
不复活固定联赛规则。

v0.2 来自首轮开发样本的盘口分层观察，因此其历史 `+9.7pp` 只作描述，不能视为独立验证；
v0.2 的有效 forward 样本从同时携带两个预注册实验版本的新 artifact 开始。

## 2. 预注册边界

- 只接受首场开赛前生成的 `active_v3.3.3` structured artifact。
- artifact 必须同时携带完全匹配的三个 experiment id 和 version，保证候选使用同一批样本。
- 只结算数据库已有正式 `result_code` 和 `winning_sp` 的比赛。
- 旧 artifact、赛后重算、缺少实验字段的文件和 v4.2 派生产物全部排除。
- 同一期存在多个合法 artifact 时，选择首场开赛前生成的最后一份。
- artifact 生成时间暂使用文件 mtime；后续 schema 增加显式时间戳后应切换为显式字段。

26073/26074 的开赛前 artifact 早于本实验预注册，未携带实验字段，因此 forward 累计从 0
开始；不得用赛后重新生成的文件补齐。

## 3. 晋级门槛

| 条件 | 门槛 |
|---|---|
| 已结算 forward 场数 | 至少 300 场 |
| 独立期数 | 至少 5 期 |
| 候选主押命中提升 | 至少 +2pp |
| 覆盖集合 | 逐场完全一致 |
| 主押二元 Brier | 相对基线恶化不超过 0.01 |

任一候选达到全部门槛后，监控器只将总状态改为 `ready_for_review`，不得自动修改 release、默认版本或
资金分配。A/B/C 等级还必须在扩大样本后表现出合理单调性，才能单独进入资金权重评审。

## 4. 自动化

生成器在每份新 structured artifact 中写入：

- 三个候选各自的主押和重排后选择码；
- 是否相对基线切换；
- 主押概率和领先间距；
- A/B/C 等级；
- 赛后候选主押命中；
- 固定的 `execution_enabled=0`。

联赛实验还写入 `effective_n`、逐结果收缩调整、是否通过 30 场/2pp 门槛和信号来源。
历史残差只读取当前期号之前、同自然年、生成时间不晚于开赛时间的 active snapshot。

`scripts/live_artifact_refresh_loop.py` 每轮调用
`scripts/monitor_v3_3_3_phase2_forward.py`。只有累计样本签名变化时才重写输出，避免每五分钟
产生无意义文件变更。

运行产物位于：

- `results/phase2_primary_forward/summary.json`
- `results/phase2_primary_forward/settled_rows.csv`
- `results/phase2_primary_forward/report.md`

手动复核命令：

```bash
.venv/bin/python scripts/monitor_v3_3_3_phase2_forward.py
```

## 5. 初始状态

2026-07-11 三候选冷启动结果为 `collecting`，`artifact_count=0`、`rows=0`。这是预期状态，证明旧期
和赛后 artifact 没有被错误补入 forward 样本。
