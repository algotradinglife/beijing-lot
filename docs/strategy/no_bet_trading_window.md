# No-bet 作为一级动作 + 可交易窗口检测 — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban t_208514b5）
**状态**: 设计稿，待评审 → 转 writing-plans
**关联**:
- 代码：`src/auto/autoplan.py`（现有 skip 门 + `auto_log`）、`src/webui/services.py`（`passes_concentration_guard`、`q_buckets`/`_q_stat`、`select_downweight_leagues`、`select_current_issue`、`generate_bucketed_plans`、`maybe_haircut_snapshots`、`collect_settled_legs`）、`src/webui/db.py`（`auto_get`/`auto_pause`/`auto_resume`/`auto_log`、`get_config`/`set_config`）、`src/sp_drift/forward.py`（`check_stopping_rule` 入/退条件范式）
- 研究：`docs/research/q_persistence_analysis.md`（q 无时间结构）、`docs/research/sp_drift_forward.md`（GATE-FT pending）
- 姊妹文档：
  - `docs/strategy/regime_timing_strategy.md`（动态择时选择器，已含 `SKIP` 动作）—— **分工见 §10**
  - `docs/strategy/posterior_ev_decision.md`（用 P(EV>0) 作入场门，规划中）
  - `docs/strategy/walk_forward_strategy_evaluation.md`（walk-forward 评估骨架）

---

## 1. 背景与动机

### 1.1 默认状态应当是「不下注」

本次会话的两条关键证据，把「每期强行出票」这个隐含默认彻底推翻：

1. **实盘整体 q ≈ 0.838（负 EV），且 q 无可利用的时间结构**（`docs/research/q_persistence_analysis.md`）。
   - q 的工程定义见 `src/webui/services.py:_q_stat`：`q = RETURN_RATE × Σ(命中腿 SP) / n`，即每腿已实现回报倍数，`RETURN_RATE = 0.65`（北单抽水后回报率）。q < 1 即负 EV。
   - 「无时间结构」意味着：**不能靠『最近几期 q 高就预测下期 q 高』来择时**。q 的自相关接近 0，过去的好/坏不延续。因此不存在「跟着 q 趋势加仓」的可利用结构 —— 唯一稳健的默认是**不下注**，只在**当期候选池里直接观测到可验证错价**时才出手。

2. **结构性地板：两道墙**。任何下注的期望必须先翻过它们：
   - **抽水墙**：`RETURN_RATE = 0.65`，即 −35% 的硬性回报折扣。
   - **SP 漂移墙**：命中腿平均计划 SP 4.05 → 结算 SP 3.36（约 −16.6%），不利漂移远多于有利。串 4 关时漂移乘法 `0.836⁴ ≈ 0.49`。
   - 二者叠加：默认 EV ≈ `0.65 × 0.49 ≈ 0.32`。**一张「平均牌」的期望只有本金的三分之一**。

**核心判断**：在这样的地板上，「每期都下注」是系统性失血。edge（若存在）只在少数局部窗口出现 —— 那些**错价幅度大到能同时翻过抽水墙和漂移墙**的时刻。系统应从「每期优化下注额」转为「识别可交易窗口；多数时候空仓等待」。

### 1.2 把零散 skip 收编成显式状态机

现状不是「没有 no-bet」，而是 **no-bet 散落在 `autoplan.py` 里的多道失败式 skip 门**，每道各写各的 `auto_log`，没有统一的状态语义，也没有「为什么这一窗口不可交易」的结构化记录。本设计**不新造逻辑**，而是把这些 skip 升格为一个**显式状态机 + no-bet 一级动作**。

现有可复用 skip 门（全部位于 `src/auto/autoplan.py`，逐一收编进 §3 的特征/§4 的状态机）：

| 现有 skip 门 | 常量/函数 | 当前触发 | 收编后归属 |
|---|---|---|---|
| 薄期次 | `MIN_OPEN_MATCHES = 30`（`thin_issue`） | 当期可下注场次 < 30 | §3 候选池数量特征 → `no-bet(thin_issue)` |
| 候选过少 | `MIN_CANDIDATES = 5`（`low_candidates`） | dedupe 后票数 < 5 | §3 候选池数量 → `no-bet(low_candidates)` |
| 下注额过低 | `MIN_STAKE = 500`（`low_stake`） | total_stake < 500 | §3 资金/Kelly 信号 → `no-bet(low_stake)` |
| 集中度护栏 | `passes_concentration_guard`（`concentration_guard`） | 合格腿过少 或 单腿占比过高 | §3 集中度特征 → `no-bet(concentration)` |
| 无可下注期次 | `select_current_issue() is None` | 无可下注 issue | §3 → `no-bet(no_issue)` |

> 注意：当前 `auto_pause/auto_resume`（`src/webui/db.py`）是**全局开关**——暂停后什么都不跑。它解决「系统性停机」，**不等于**按窗口的 no-bet。本设计的 no-bet 是**每个 decision_ts 独立判定**的一级动作：系统持续运行、持续评估窗口，只是大多数窗口的输出是「不下注」。两者正交：`auto_pause` 仍是人工急停。

---

## 2. 设计原则

1. **no-bet 是一级动作，不是失败状态**。它与「下注」平级，是状态机的合法稳态输出。负 EV 期空仓的期望（0）严格优于下注（≈ 0.32 本金的失血）。`auto_log` 里 no-bet 不再用 `level=warn/error`，统一 `level=info` + 结构化 `reason`。
2. **默认即空仓（fail-closed）**。状态机的初始/缺省态是 `no-bet`。只有**明确检测到可交易窗口**才升档下注。任一信号缺失或样本不足 → 留在 no-bet，而非「证据不足所以照常下注」。
3. **只用 decision_ts 之前已结算的数据 + 当期候选池快照**（walk-forward）。所有「近期 q」类特征严禁用事后数据。详见 `walk_forward_strategy_evaluation.md`。
4. **空仓不是惩罚，恢复要谨慎**。空仓期**不追单、不因错过期数抬 Kelly、不报复性加仓**（§5）。恢复下注需**连续信号**确认，避免单期噪声把系统拉回失血状态。
5. **可复盘**。每次决策——尤其是 no-bet——必须在 Dashboard/周报里回放「**为什么没买**」，附触发特征的实测值。空仓而无记录 = 不可复盘（§6）。
6. **复用既有护栏**。`passes_concentration_guard`、`select_downweight_leagues`、`select_current_issue`、NicheConfig 黑名单/`league_q_min`、`maybe_haircut_snapshots` 全部保留，作为状态机之下的硬过滤层。

---

## 3. 可交易窗口定义

**可交易窗口** = 在 `decision_ts` 时刻，当期候选池里存在「错价幅度足以翻过抽水墙 + 漂移墙」的下注机会。用下列**可观测、可前向计算**的特征向量刻画。所有特征只用 decision_ts 之前已结算的腿 + 当期快照。

### 3.1 特征表

| 特征 | 定义 | 来源 / 复用 | no-bet 触发方向 |
|---|---|---|---|
| **近期 q（per-leg）** | rolling window 内已结算腿的 `_q_stat.q` | `collect_settled_legs` + `_q_stat`（services.py） | `q_recent < q_skip` → no-bet |
| **近期 q 样本量** | 上述 window 的腿数 n | `_q_stat.n` | `n < min_q_n` → 视作信号不足 → no-bet（fail-closed） |
| **joint_q（组合层）** | 候选组合的 `q^N` 是否过 break-even（`q^N ≥ 1/RETURN_RATE`） | 由 per-leg q + N 推导（见 §3.2 break-even 表） | `joint_q < 1`（组合负 EV）→ no-bet |
| **SP drift（漂移负担）** | 当期候选腿按 SP band 的预期漂移负担（`HAIRCUT_MAP`） | `maybe_haircut_snapshots` / `src/sp_drift/forward.py:HAIRCUT_MAP` | 漂移后 EV 翻不过 break-even → no-bet |
| **候选池数量** | 当期可下注场次数 / dedupe 后候选票数 | `_count_open_matches`（autoplan）、`generate_plan` 票数 | `< MIN_OPEN_MATCHES` 或 `< MIN_CANDIDATES` → no-bet |
| **集中度** | 合格腿数 + 单腿最高占比 | `passes_concentration_guard`（services.py） | guard 不过 → no-bet |
| **联赛黑名单** | 触发降权/黑名单的联赛 | `select_downweight_leagues` + NicheConfig 黑名单/`league_q_min` | 候选池被黑名单清空到不足 → no-bet |
| **MTK（决策→开赛时距）** | decision_ts 到 kickoff 的小时数 | `kickoff_bucket_label` / `WINDOW_MTK=180`（forward.py） | 距开赛过远（漂移未定型）→ 可选降档/no-bet（保守） |
| **资金热度** | 候选池规模 + 期望 stake 相对 bankroll 的占比 | `total_stake` vs bankroll；`MIN_STAKE` | `total_stake < MIN_STAKE` → no-bet（窗口太薄不值得操作开销） |

> **MTK 说明**：当前 `kickoff_window` 在 sp_drift 研究中实测「无窗口值能改善漂移」（已 revert 到 0，见 MEMORY）。因此 MTK **不作为正向择时信号**，只作为**保守降档的可选门**：距开赛过远时漂移尚未定型，证据更弱，默认更倾向 no-bet。这与 `inplay_sp_timing_filter.md` 的落地侧互补，不重叠。

### 3.2 break-even 锚点（判 joint_q 是否过墙）

组合需满足 `q^N ≥ 1/RETURN_RATE = 1/0.65 ≈ 1.538`，等价 per-leg 阈值：

| N | break-even per-leg q |
|---|---|
| 2 | ≈ 1.240 |
| 3 | ≈ 1.154 |
| 4 | ≈ 1.114 |
| 5 | ≈ 1.090 |

可交易窗口要求**漂移调整后**的 per-leg q 仍站在对应 N 的 break-even 之上（含安全边际 `q_go`）。这是「错价翻过两道墙」的可操作判据。

### 3.3 窗口可交易性判据（综合）

一个窗口判为 **可交易** 当且仅当（全部满足）：

```
q_recent ≥ q_go                                  # 近期 per-leg q 留出 break-even 之上的边际
n_recent ≥ min_q_n                               # 样本量达标，否则 fail-closed
joint_q_after_haircut ≥ 1/RETURN_RATE            # 漂移调整后组合仍正 EV
candidate_pool 通过 thin/low_candidates/low_stake # 池足够厚
passes_concentration_guard == True               # 不是集中赌注伪装成多票
league_blacklist 清理后候选仍充足                  # 黑名单未把池掏空
```

任一不满足 → **no-bet**，并记录**首个失败的判据**作为 `reason`（§6 日志字段）。

---

## 4. 状态机

### 4.1 四个状态

| 状态 | 含义 | 下注行为 |
|---|---|---|
| `risk-on` | 检测到可交易窗口，证据充分 | 正常 `generate_plan` + place，按 preset 的 per-N Kelly 全额 |
| `half-size` | 窗口边际可交易 / 信号刚跨门但样本偏薄 | place，但 stake 砍半（Kelly 系数 × 0.5），降低单期方差 |
| `shadow-only` | 窗口看似可交易但未达连续信号 / 处于恢复观察期 | **生成计划但不 place**（影子下注），仅记录用于复盘与连续信号确认，**不动用真金** |
| `no-bet` | 默认稳态，无可交易窗口 | 不 place（`generate_plan` 可跑用于诊断，但产物不落地） |

> `shadow-only` 复用 autoplan 现有机制：`generate_plan` 已会 upsert 计划 + 写 JSON；`mark_placed` **不调用**即为影子（对照 autoplan 当前在 low_candidates skip 时 `delete_plan` 清理 —— shadow 不清理，保留供复盘 + 连续信号判定）。

### 4.2 状态转移图

```text
                 ┌──────────────────────────────────────────────┐
                 │                                              │
                 ▼                                              │
            ┌─────────┐  连续 K_up 期可交易 + joint_q 过墙   ┌──────────┐
   (默认)──▶│ no-bet  │ ───────────────────────────────────▶ │ risk-on  │
            └─────────┘                                       └──────────┘
              ▲  │  ▲                                          │   │
              │  │  │ 单期可交易但未达连续门                     │   │ 单期不可交易
              │  │  └──────────────┐                           │   ▼
   任一硬底线  │  │                 │                      ┌───────────┐
   触发(强制)  │  ▼                 │      边际/样本薄      │ half-size │
              │ ┌────────────┐      └──────────────────────┤           │
              └─┤shadow-only │◀────────────────────────────┘           │
                └────────────┘   连续 K_down 期不可交易       └───────────┘
                  影子观察，恢复需连续信号                          │
                                                                  │ 连续不可交易
                                                                  ▼
                                                              回 no-bet
```

### 4.3 进入 / 退出条件（借鉴 `check_stopping_rule` 的预注册范式）

参照 `src/sp_drift/forward.py:check_stopping_rule`——**阈值预注册、不在过程中改、判定只看最新窗口**。所有阈值进 `db.set_config`，标定方式见 §7。

**升档（no-bet → risk-on）**：需**连续信号**，不靠单期：
```
连续 K_up 期（默认 2）窗口判为可交易
  AND joint_q_after_haircut ≥ 1/RETURN_RATE（组合过墙）
  AND n_recent ≥ min_q_n（样本达标）
```

**进入 half-size（no-bet/shadow → half-size）**：单期可交易但边际：
```
窗口可交易 但 (q_recent 仅略高于 q_go 边际带内 OR n_recent 介于 [min_q_n_low, min_q_n) 样本偏薄)
```

**进入 shadow-only**：看似可交易但未达连续门，或处于恢复观察期：
```
单期可交易 但 连续期数 < K_up（升档证据不足）
  OR 刚从 no-bet 出来需先影子观察 recover_obs 期
```

**降档 / 退回 no-bet**：
```
连续 K_down 期（默认 1，即立即退）窗口不可交易 → 退回 no-bet
  OR 任一硬底线触发（§4.4）→ 强制 no-bet（不被「窗口看似好」覆盖）
```

### 4.4 硬底线（先于一切，触发即强制 no-bet）

复用现有护栏，任一触发**直接 no-bet**，不进上面的连续信号逻辑：
- `select_current_issue() is None`（无可下注期次）
- 候选池 < `MIN_OPEN_MATCHES` / 票数 < `MIN_CANDIDATES` / stake < `MIN_STAKE`
- `passes_concentration_guard` 不过
- 回撤底线：滚动 max_dd 超阈（借鉴 `forward.py:MAXDD_STOP`，作为状态机层的强制降档）

---

## 5. 资金管理（空仓期纪律）

空仓不是「等待出手的蓄力」，不得演变为报复性下注。规则：

1. **不追单**：错过的期数不补。no-bet 期的「机会成本」记为 0（§7 评估里单列），**不转化为下期加仓的理由**。
2. **不因错过期数抬 Kelly**：Kelly 系数恒由当前 preset 决定（见 `regime_timing_strategy.md` §4「选择器不另调 Kelly」），**空仓时长不进入 Kelly 计算**。连续空仓 10 期，恢复时 Kelly 与空仓 0 期完全相同。
3. **恢复需连续信号**：no-bet → risk-on 必须经 `K_up` 连续可交易期（§4.3），中间可经 `shadow-only` 影子观察确认信号稳定。**禁止单期反弹直接全额下注**。
4. **空仓期 bankroll 冻结语义**：空仓不触发 `record_settlement`（无周结算），peak/active 不变。利润锁仓（`PROFIT_LOCK_*`，services.py）只在实际结算时触发，与空仓正交。
5. **half-size 是方差闸门，不是折中下注**：仅在边际窗口用于压低单期方差，**不**作为「证据不足但又不甘心空仓」的安慰性动作——边际不足时应 shadow-only 或 no-bet，而非 half-size。

---

## 6. 日志字段 / Dashboard / 周报（可复盘「为什么没买」）

### 6.1 日志字段（扩展现有 `auto_log` details，写入 `auto_mode_log`）

每个 decision_ts **都写一条**（含 no-bet），统一 `kind="window_decision"`、`level="info"`：

```json
{
  "decision_ts": "2026-06-23T12:00:00Z",
  "issue": "2026xxx",
  "state": "no-bet",                  // risk-on | half-size | shadow-only | no-bet
  "action": "skip",                   // place | place_half | shadow | skip
  "reason": "joint_q_below_floor",    // 首个失败判据；可交易时为 "tradeable"
  "features": {
    "q_recent": 0.84, "n_recent": 41,
    "joint_q_after_haircut": 0.46, "break_even_q": 1.114,
    "n_open": 62, "n_candidates": 7, "total_stake": 1200,
    "concentration_max_pct": 38.0, "n_qualified_legs": 9,
    "blacklisted_leagues": ["X联"], "mtk_hours": 14.5,
    "consec_tradeable": 0, "consec_no_bet": 5
  },
  "thresholds": { "q_go": 1.05, "q_skip": 0.95, "min_q_n": 30, "k_up": 2 }
}
```

> 复用现状：autoplan 现有每道 skip 已写 `auto_log(..., details=dict(reason=...))` + `set_config("auto_last_plan_status", "skipped_*")`。本设计把 `reason` 标准化为 §3.3 判据枚举，并强制**可交易时也写一条**（现状只在 skip 时写，导致「为什么买了/没买」记录不对称）。`set_config` 新增 `window_state` 键，Dashboard 直读当前态。

### 6.2 Dashboard 展示

- **当前窗口卡片**：大字显示当前 `state`（risk-on/half-size/shadow-only/no-bet）+ 一句话 reason + 触发特征的实测 vs 阈值。
- **空仓计数**：连续空仓期数 `consec_no_bet`、本周空仓/下注期数比。
- **窗口时间线**：近 N 期的 state 序列（色块：绿=risk-on / 黄=half-size / 灰=shadow / 白=no-bet），鼠标悬停看当期 reason + features。
- **影子台账**：shadow-only 期的假想下注及其（事后结算的）假想 PnL，用于验证「当时空仓是对的」。

### 6.3 周报字段（接 `docs/research/` 周报风格）

| 字段 | 含义 |
|---|---|
| 本期窗口状态 + reason | 当周各 decision_ts 的 state 与首因 |
| 空仓期数 / 下注期数 | 本周分布 |
| 机会成本 | 空仓期影子台账的假想 PnL（正=躲过亏损 / 负=错过盈利） |
| 升/降档事件 | 触发了哪些转移，连续信号是否满足 |
| 触发最多的 no-bet reason | top reason 排序（指向最该改进的瓶颈：池薄？q 低？漂移？） |

---

## 7. 评估（把 no-bet 纳入 walk-forward）

借 `walk_forward_strategy_evaluation.md` 的骨架 + `forward.py` 的 ledger/arm 范式（`append_ledger` / `LEDGER_COLS` / `check_stopping_rule`）。

### 7.1 对照臂（arms）

| 臂 | 含义 |
|---|---|
| `A_ALWAYS` | 基线：每期强行下注（现状默认行为） |
| `A_NOBET` | 本设计：状态机择窗，多数期 no-bet |
| `A_NOBET_HALF` | 本设计 + half-size 闸门启用 |

每臂在同一 OOS 切片上 replay（`forward_panel` 只取 `kickoff_ts > FORWARD_START`），逐期产 ledger 行。

### 7.2 对比指标

- **资金曲线 / final_bankroll**：A_NOBET 是否优于 A_ALWAYS（核心假设：躲过负 EV 期 → 终值更高）。
- **max_dd**：空仓应显著降回撤。
- **turnover**（下注期数 / 总期数）：量化「出手有多稀」。
- **机会成本**：A_NOBET 在 no-bet 期的影子 PnL 之和。**负机会成本**（即影子下注本会亏）= no-bet 决策正确的直接证据。
- **per-window hit**：可交易窗口判定的精度（被判可交易的期，实际 ROI 是否真为正）。

### 7.3 预注册停止规则（仿 `check_stopping_rule`）

```
MIN_DECISIONS = 200        # 累计 decision_ts 数（不是下注数，空仓也计）
MAX_WEEKS     = 12.0
MARGIN        = 0.05       # A_NOBET final_bankroll 相对 A_ALWAYS 的优势边际
verdict: go      if A_NOBET 终值优势 ≥ MARGIN 且 max_dd 改善
         no_go   if A_NOBET 终值 ≤ A_ALWAYS（择窗未带来价值）
         uncertain otherwise
```

阈值**预注册、过程中不改**（同 `forward.py` HAIRCUT_MAP/GATE-FT 纪律）。

---

## 8. 阈值候选（初始值，待 §7 walk-forward 标定）

```
# 窗口可交易性
q_go         = 1.05     # per-leg q，break-even 之上安全边际
q_skip       = 0.95     # 低于此一律 no-bet
min_q_n      = 30       # q_recent 最小腿数（fail-closed 门）
min_q_n_low  = 15       # 介于 [low, min_q_n) → half-size（样本偏薄）

# 连续信号
k_up         = 2        # no-bet → risk-on 需连续可交易期数
k_down       = 1        # 连续不可交易即退回 no-bet
recover_obs  = 1        # 升档前 shadow-only 观察期

# 资金 / 池（沿用 autoplan 现有常量，集中到 config）
min_open_matches = 30   # MIN_OPEN_MATCHES
min_candidates   = 5    # MIN_CANDIDATES
min_stake        = 500  # MIN_STAKE
maxdd_stop       = 0.50 # 借 forward.py:MAXDD_STOP

# 漂移
return_rate  = 0.65
break_even_joint_q = 1.538   # = 1/RETURN_RATE
haircut_map  = forward.py:HAIRCUT_MAP   # 冻结的 GATE-1 per-band 漂移
```

全部以 `db.set_config` 键持久化，命名前缀 `window_`（如 `window_q_go`），与 regime 选择器的 config 键不冲突。

---

## 9. 实验计划

1. **影子先行（shadow-first）**：先让状态机在生产里**只跑 shadow-only**（永不动真金），收集 ≥ 4 周窗口判定 + 影子台账，验证日志/Dashboard 闭环与判据可解释性。
2. **离线 walk-forward**：在历史面板上 replay §7.1 三臂，产 ledger，跑停止规则。**门槛**：A_NOBET 终值优势 ≥ MARGIN 且 max_dd 改善 且机会成本为负（躲过亏损）。
3. **阈值标定**：仅用离线切片标定 §8 阈值，**冻结后**才上线，禁事后调参。
4. **灰度上线**：通过门槛后，先开 `half-size` 上限（真金但半仓）跑 ≥ 4 周，再放开 `risk-on` 全额。
5. **回退闸**：上线后若实盘 max_dd > `maxdd_stop` 或机会成本转正（频繁错过盈利期），强制回 shadow-only 复审。

### 9.1 MVP 最小拆解
- **M1**：把 autoplan 的 5 道 skip 收编为统一 `evaluate_window()`，输出 `(state, action, reason, features)`，每期都写标准化 `auto_log`（含可交易期）。**纯日志，行为不变**——只是把现有 skip 标准化 + 补「为什么买了」的记录。
- **M2**：加 `shadow-only` 状态 + 影子台账（不动真金）。
- **M3**：加连续信号转移（K_up/K_down）+ half-size。
- **M4**：Dashboard 窗口卡片 + 周报字段 + §7 walk-forward 三臂评估。

---

## 10. 与 `regime_timing_strategy.md` 的分工

两份文档都谈「空仓」，但**层次不同，互补不重叠**：

| 维度 | `regime_timing_strategy.md`（择时选择器） | 本文档（no-bet 窗口） |
|---|---|---|
| 核心问题 | **下注时，选哪个策略**（S1–S11 中挑一个 preset） | **是否构成可交易窗口**（下注 vs 不下注，及半仓/影子的中间态） |
| 空仓的角色 | `SKIP` 是动作空间里的**一个动作**，与 S1–S11 平级 | no-bet 是**默认稳态 + 完整状态机**（risk-on/half-size/shadow-only/no-bet）的核心 |
| 输出 | 选中的 preset（含 SKIP） | 窗口状态 + 下注规模档位 + 「为什么没买」结构化记录 |
| 关注点 | regime 标签（GREEN/AMBER/RED）→ 选 edge 来源 | 窗口可交易性判据 + 空仓期资金纪律 + 复盘日志 |

**契约**：本文档的 `evaluate_window()` 是 regime 选择器的**前置门**。调用顺序：

```text
evaluate_window()  →  no-bet ?  ──是──▶ 不调用选择器，直接空仓（写窗口日志）
                          │否
                          ▼
            regime_timing_strategy.select_action()  →  在可交易窗口内选 S1–S11 preset
```

即：**先判「这期到底能不能交易」（本文档），能交易才问「用哪个策略」（regime 文档）。** regime 文档的 `SKIP` 动作与本文档的硬底线一致，由本文档统一拥有判定与日志，regime 选择器不再重复实现 skip 逻辑——它假定被调用时窗口已可交易。

`posterior_ev_decision.md`（规划中）将提供 `P(EV>0)` 作为 §3.3 里 `joint_q ≥ 1/RETURN_RATE` 的**贝叶斯版入场门**：把硬阈值升级为「后验 P(EV>0) ≥ 阈值」，给薄样本期更稳健的不确定性处理。届时本文档 §3.3 的 joint_q 判据替换为后验门，状态机其余部分不变。

---

## 复盘（本期）

> 待状态机上线后，每期在此追加：窗口状态、reason、影子台账机会成本。设计稿阶段留空。
