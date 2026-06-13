# SP 漂移上线前 Forward-Test — 设计稿

**日期**: 2026-06-13
**作者**: brainstorming（承接 GATE 3）
**状态**: 设计稿，待评审 → 转 writing-plans
**关联**: [SP 漂移优化 spec](2026-06-11-sp-drift-optimization-design.md)、`src/sp_drift/replay.py`、`docs/research/sp_drift_phase4.md`（GATE 3）

---

## 1. 背景与动机

GATE 3 反事实重放（in-sample，~5.5 周）显示：决策时机是巨大杠杆（uniform 18h-out 0/290 命中 → 1h-out 12 命中），把漂移按档计入 EV 的保守 haircut 变体 ROI **+11.6%**（扣 35% 房费后为正）。**但样本太薄、个位数命中、haircut 用同期 in-sample 估计——量级不可信。** 在投真钱放大前，必须用**样本外（forward-dated）**数据验证方向与符号是否成立。

实盘已先行把 `kickoff_window_hours` 由 0 改为 3（2026-06-13，default profile）。本 forward-test 与之并行，**纸面**验证「时机 + haircut」组合，给出 GATE-FT go/no-go：是否值得做下一步「真实落地」（haircut 进 live planner + 真钱小额）。

## 2. 目标（Goal）

构建一个**调度化纸面 forward-test 框架**：在 `FORWARD_START` 之后开赛并结算的比赛上，按预注册规则逐周评估 3 个策略 arm 的 what-if 真实 PnL，到达预注册停止条件时给出 GATE-FT 结论。

**终点**：forward ledger + 周报 + GATE-FT 判定。**纯纸面，不下真钱，不改 live planner。**

**非目标（YAGNI）**：
- 不把 haircut 接进 live planner / combo EV（那是 GATE-FT 通过后「真实落地」spec 的事）。
- 不做真钱 A/B。
- 不动 default profile 的实盘配置（除已做的 window=3h）。

## 3. 验证标准（预注册，事前固定）

为避免事后挑数，以下全部**事前冻结**：
- **OOS 边界**：`FORWARD_START = 2026-06-13`（北京日期）。只计 `kickoff_ts > FORWARD_START` 且已结算的比赛。GATE 1/3 估计用的是 ~06-11 前数据，故此切片为真正样本外。
- **haircut map 冻结**（GATE 1 实测每档 drift_bias）：`{"<3.5": +0.33, "3.5-4.5": -0.09, "4.5-5": -0.21, "5-8": -0.36, ">8": -0.81}`。**forward 期间不得据 forward 数据重估。**
- **停止规则**：C2 累计 **≥200 组合** 或 forward 窗 **≥12 周**，先到先停；**提前止损**：C2 纸面 MaxDD > 50% → 立即判 No-go。
- **GATE-FT 成功判据**：OOS 切片上同时满足 — (a) C2 ROI > 0；(b) C2 ROI − C0 ROI ≥ +5pp（margin）；(c) C1 ROI − C0 ROI ≥ +5pp（时机方向成立）→ **Go-for-real**。任一不满足且 C2 ROI ≤ 0 → **No-go**。介于之间 → 继续跑到停止条件或判「不确定」。

## 4. 三个 Arm（全纸面，复用 `replay_policy`，结算用真实 winning_sp）

| Arm | mtk_target | haircut | 隔离的变量 |
|-----|-----------|---------|-----------|
| **C0 对照** | `baseline_decision_mtk`（~18h，复现历史行为） | 无 | — |
| **C1 仅窗口** | 180（3h） | 无 | 决策时机 |
| **C2 全处理** | 180（3h） | 冻结 band map | 时机 + haircut |

三个 arm 共用：`NicheConfig.load()`、N=4、kelly=1/16、起始 bankroll=100,000、combo_ev_threshold=0.05（即 `replay.Policy` 的默认 + 上述 `mtk_target`/`haircut`）。

> **保真度说明**：replay 的 `mtk_target=180` 是「在距开赛 180 分钟时的快照 SP 上决策」，是 live「只纳入 3h 内开赛的比赛」窗口过滤的**近似代理**（二者都把决策推到临近开赛，但选快照的方式略不同）。本纸面 test 接受此近似；真实落地 spec 再用 live 路径验证。

## 5. 架构与代码边界

复用既有 `src/sp_drift/replay.py`（`replay_policy`、`Policy`、`apply_band_haircut`），仅新增一个 forward 编排层：

| 模块 | 职责 | 单一目的 |
|------|------|----------|
| `src/sp_drift/forward.py` | `forward_panel(panel, min_kickoff)` 过滤 OOS 面板；`run_forward(panel, live_db, arms, run_date) -> list[dict]` 跑各 arm；`append_ledger(rows, ledger_path)` 追加；`check_stopping_rule(ledger_df, treat_arm="C2") -> dict` 判停止/止损 | forward 编排 |
| `scripts/run_sp_drift_forward.py` | 接真实 db → 跑 → 追加 ledger → 写 `docs/research/sp_drift_forward.md` + 分 arm 累计权益图 + 停止状态 | 报告入口 |
| `tests/sp_drift/test_forward.py` | `forward_panel` 过滤、`append_ledger` 幂等追加、`check_stopping_rule` 三种触发的确定性测试 | 测试 |
| systemd `beidanlot-sp-forward.{service,timer}` | 每周一跑报告、追加 ledger（spec 记录，部署时建；DEPLOY.md 第五节同款模式） | 调度 |

**接口约定**：
- `forward_panel(panel, min_kickoff)`：返回 `panel[panel["kickoff_ts"] > min_kickoff]`（kickoff_ts 是 naive 北京 ISO 串，字典序比较即可）。
- `run_forward` 内部对每个 arm 调 `replay_policy(forward_panel(...), live_db, cfg, policy)`，把返回的指标 + `run_date` + `arm` 名组成行。
- Ledger 为 append-only CSV；每次运行写「当前累计快照」一行/arm（同一 run_date 重跑则覆盖该 run_date 的行，保持幂等）。

## 6. Ledger schema

`data/derived/sp_drift/forward_ledger.csv`，列：

```
run_date, arm, forward_start, n_combos, n_hits, total_stake, total_pnl, roi, max_dd, final_bankroll
```

- **字段映射**：`n_combos` = `replay_policy` 返回的 `n_tickets`（一个 `TicketPlan` = 一个组合，含税拆票后仍记为一个组合）；`n_hits`/`roi`/`max_dd`/`total_stake`/`total_pnl`/`final_bankroll` 直接取自 `replay_policy` 返回的同名键。
- 一行 = 某 run_date 某 arm 在「FORWARD_START 至今的 OOS 切片」上的累计结果。
- 随周数增长，ledger 是各 arm 累计 ROI/命中/DD 的时间序列（供画图与停止判定）。

## 7. 停止规则与 GATE-FT 逻辑

`check_stopping_rule(ledger_df)` 取最新 run_date 的各 arm 行，按 §3 预注册规则返回：
```
{ "stop": bool, "reason": "n_combos>=200" | "weeks>=12" | "maxdd_stop" | "running",
  "verdict": "go" | "no_go" | "uncertain" | "pending",
  "c0_roi", "c1_roi", "c2_roi", "c2_n_combos", "weeks_elapsed", "c2_max_dd" }
```
- weeks_elapsed = (最新 run_date − FORWARD_START) / 7 天。
- verdict 仅当 stop=True 或触发止损时给 go/no_go/uncertain；否则 pending。
- 报告把 verdict + 各 arm 累计 ROI/命中/DD + 权益图 + 「距停止还差多少」一并呈现。

## 8. 数据流

```
collector → snapshots(beidan_live.db)
   → panel.build(rebuild) → forward_panel(kickoff > FORWARD_START)
      → replay_policy(C0/C1/C2)  [复用 qualify→build_plan→settle-on-winning_sp]
         → append_ledger → check_stopping_rule → 周报 + 图
```

## 9. 风险与局限

| 风险 | 处理 |
|------|------|
| forward 初期样本极小（赛季中每周比赛少，N=4 命中稀疏） | 停止规则用「200 组合 OR 12 周」双闸，避免过早下结论；报告显式标注样本量与命中数 |
| haircut 用 in-sample 冻结值 | 这正是 forward 要检验的——冻结即诚实 OOS；不得据 forward 重估 |
| 纸面 PnL 忽略真实摩擦（售罄/凑整/SP 末段再动） | 标注为乐观上界；GATE-FT 通过后真实落地 spec 再校验 |
| MTK=180 代理 vs live 窗口过滤 | §4 注明；真实落地用 live 路径复核 |
| 自身下注反身性 | 纸面不下注，无反身性；真实落地阶段再评估 |
| 多重比较（3 arm + 每周看） | 判据事前冻结（§3）；不在 forward 期间改判据或 arm |

## 10. 交付物清单

- `src/sp_drift/forward.py` + `tests/sp_drift/test_forward.py`（全绿）
- `scripts/run_sp_drift_forward.py` + 首次运行的 `docs/research/sp_drift_forward.md` + 权益图
- `data/derived/sp_drift/forward_ledger.csv`（随周增长）
- systemd `beidanlot-sp-forward.{service,timer}`（每周一）+ DEPLOY.md 增补一节
- 到达停止条件时的 GATE-FT 结论；**Go → 写「真实落地」spec；No-go → 记录负结果并重审玩法/N/SP**
