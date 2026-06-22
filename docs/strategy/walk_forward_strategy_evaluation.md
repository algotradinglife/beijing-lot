# 策略实验评估框架（统一 walk-forward / forward-test）— 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban t_3cd1a618）
**状态**: 设计稿
**关联**:
- forward-test 现状：`src/sp_drift/forward.py`、`src/sp_drift/replay.py`、`scripts/run_sp_drift_forward.py`、`data/derived/sp_drift/forward_ledger.csv`、`docs/research/sp_drift_forward.md`、systemd `beidanlot-sp-forward.timer`、spec `docs/superpowers/specs/2026-06-13-sp-drift-forward-test-design.md`、`docs/research/sp_drift_phase4.md`
- 复用基建：`src/webui/strategies.py`（REGISTRY S1–S11）、`src/webui/services.py`（`q_buckets`/`_q_stat`/`collect_settled_legs`/`passes_concentration_guard`/`select_downweight_leagues`/`generate_bucketed_plans`）、`src/sp_drift/panel.py`
- 四份姊妹文档（本框架是其总纲，下游 spec 待写）：
  - 动态择时 `docs/strategy/regime_timing_strategy.md`
  - 中低 SP 高 N `docs/strategy/low_mid_sp_high_n_experiment.md`
  - 单场预测校准 `docs/strategy/single_match_probability_calibration.md`
  - 临场过滤 `docs/strategy/inplay_sp_timing_filter.md`

---

## 0. 这份文档是什么 / 不是什么

**是**：把上面四个候选策略方向放进**同一套样本外评估纪律**的框架/总纲。它定义统一的策略接口、数据字段、指标定义、统计稳健性门槛、决策规则、产物与 CLI 草案，使「该不该把某策略升为生产默认」成为一个**事前冻结判据 + 样本外验证**的决定，而不是看几条近期结果拍脑袋。

**不是**：不是实现代码、不是某一策略的具体 spec、不写真钱 A/B。本稿**只产出这一份设计文档**，不改其他文件。四份姊妹文档各自细化自己的候选腿生成、参数空间与先验，但都**遵从本框架的接口与判据**。

**为什么要它**：现有 `sp_drift/forward.py` 已经把「预注册停止规则 + OOS 切片 + 多 arm 对照 + 幂等 ledger + GATE-FT verdict」这套纪律跑通了（见 `sp_drift_forward.md`）。但它是为单一研究（SP 漂移）硬编码的（FORWARD_START、HAIRCUT_MAP、C0/C1/C2 三 arm 写死在模块里）。本框架把这套纪律**泛化为可复用的实验运行器**，让四个方向共享同一套基建与同一把尺子。

---

## 1. 数据切分（rolling train / validation / test）

### 1.1 时间轴与切片定义

足彩按**期次（issue）**发行、按**开赛时刻（kickoff_ts）**结算。两者都可用作时间轴：

- `issue`：离散周期，适合「按周滚动」。
- `kickoff_ts`：连续北京时间 naive ISO 串，字典序比较即时序比较（沿用 `forward.forward_panel` 的约定）。**结算口径以 kickoff 为准**——只有「在切片边界之后开赛且已结算」的比赛才计入 OOS（防止用未来信息）。

三段切分（rolling，逐周右移）：

| 段 | 用途 | 数据范围 | 谁能看 |
|----|------|----------|--------|
| **train** | 估计/拟合策略内部参数（如校准曲线、band drift_bias、league q 先验） | `[T0, T_val)` | 策略自己 |
| **validation** | 在 train 之外选超参 / 阈值（grid、Kelly 分数、N 权重、窗口长度） | `[T_val, T_test)` | 选参逻辑 |
| **test (OOS / forward)** | 冻结后唯一评判，事前不可见 | `kickoff_ts > FORWARD_START` 且已结算 | 仅最终评判 |

**纪律**：参数在 train+validation 上确定后**冻结**（写进实验配置），test 段一律不得回看重估。这正是 `forward.py` 把 `HAIRCUT_MAP` 冻结、注释「forward 期间不得据 forward 数据重估」的做法。

### 1.2 最近 regime 短窗 + 长期先验如何结合

足彩样本薄（赛季中每周比赛少、N=4 命中稀疏，见 `sp_drift_forward.md` 风险节），纯短窗噪声大、纯长窗对 regime 切换迟钝。框架统一用**收缩（shrinkage）混合**：

```
θ_used = w · θ_short + (1 − w) · θ_prior
w = n_short / (n_short + k)          # k = 先验等效样本数（伪计数）
```

- `θ_short`：最近 regime 短窗（如近 N 周 / 近 M 场）的估计。
- `θ_prior`：长期先验（全历史，或上一稳定 regime）。
- 短窗样本越多，越往短窗靠；样本薄时自动退回先验（Bayesian shrinkage，见 §4.3）。

各策略声明各自的 `θ`（择时声明 regime 标签、校准声明概率映射、SP 高 N 声明 q 先验、临场过滤声明窗口残余漂移），但**收缩公式与 k 的来源由框架统一规定并记录在实验配置里**，避免每个方向各搞一套口径。

### 1.3 Walk-forward 滚动协议

```
for cutoff in 每周一(systemd timer):
    train      = 数据[: cutoff − val_weeks − test_weeks]
    validation = 数据[cutoff − val_weeks − test_weeks : cutoff − test_weeks]   # 仅训练期选参用
    test_slice = 数据[kickoff_ts > FORWARD_START 且已结算]                      # 累计 OOS
    每个策略在冻结参数下重放 test_slice → 追加 ledger → 评判
```

实操上沿用现有「每次运行写当前累计 OOS 快照」的 ledger 模式（`forward.append_ledger` 幂等、同 run_date 覆盖），ledger 因此天然是各策略累计指标的时间序列。

---

## 2. 统一策略接口

### 2.1 契约

每个策略是一个**纯函数 / 可调用对象**，输入同一候选腿集，输出 tickets + stake + diagnostics，且**必须支持空仓（no-bet）作为合法动作**。形态对齐现有 `replay.Policy` + `replay_policy`（已是「qualify/size 在决策 SP、结算在真实 winning_sp」的原型）。

```
StrategyResult = {
    "tickets":    [Ticket, ...],     # 可为空 → 空仓（合法、需被指标体系正确计入）
    "stake":      float,             # 本期总投注（=0 即空仓）
    "diagnostics": {                 # 策略自报，用于审计与归因
        "n_candidate_legs": int,     # 输入候选腿数
        "n_qualified_legs": int,     # 通过 qualify 的腿数
        "ev_by_leg":   {...},        # 决策 SP 下的 per-leg EV
        "reason_skip": str | None,   # 空仓原因（EV 不足 / 集中度守卫 / 样本薄）
        "params_hash": str,          # 冻结参数指纹（可复现 + 实验记录键）
        "strategy_id": str,          # 见 §2.3
    },
}

def run_strategy(
    candidate_legs: CandidateLegs,   # 同一候选腿集（§2.2）
    bankroll: float,                 # 滚动 bankroll（框架管理）
    config: StrategyConfig,          # 冻结参数（实验配置文件 → §6）
) -> StrategyResult
```

**约束**：
- 三个口径分离（沿用 replay 不变式）：**qualify 在决策 SP** → **size 在决策 SP（可 haircut 调整）** → **settle 在真实 winning_sp**。这是「决策太早 → 缩水赔付」能显示为已实现亏损的关键，不可省。
- 空仓是一等动作：stake=0、tickets=[]、diagnostics.reason_skip 给原因；指标体系（§3）须把空仓周正确计入 turnover=0、不污染 hit_rate 分母。
- 框架管理滚动 bankroll、weekly_stake_cap、跨期累计；策略只决定「本期这批候选腿 → tickets/stake/diag」。

### 2.2 候选腿集（CandidateLegs）—— 四策略共用输入

为让四个方向可比，框架在调用任何策略前先组装统一的候选腿集（由 `panel.build` + `decision_view` + settlement 真值拼成）：

```
CandidateLeg = {
    "match_id", "issue", "match_idx", "league", "kickoff_ts",
    "selection",            # "3" 主胜 / "1" 平 / "0" 客胜（沿用现有编码）
    "handicap_line",
    "decision_sp",          # 决策 MTK 时刻快照 SP（decision_view 产出）
    "decision_mtk",         # 该 SP 距开赛分钟数
    "winning_sp",           # 结算真实 SP（settlements，仅评判用，策略 qualify 不得读）
    "result_code",          # 结算真值（"3"/"1"/"0"）
    "sp_band",              # drift_stats.sp_band(decision_sp) 分档
    "league_q_prior",       # 长期 q 先验（q_buckets/_q_stat 口径，含收缩）
}
```

各策略只是对**同一份 CandidateLeg 列表**做不同的 qualify/size：
- 动态择时：按 regime 标签调权 / 调 N 混合 / 决定空仓。
- 中低 SP 高 N：按 `sp_band` 选低中档 SP、抬高 N。
- 单场校准：用校准后的胜率覆盖隐含概率算 EV。
- 临场过滤：按 `decision_mtk` / 窗口残余漂移过滤腿。

### 2.3 策略标识（可复现 + 实验记录）

复用 `webui/strategies.py` 的 `REGISTRY`（S1–S11）与 `match_strategy`/`apply_strategy`：每次实验记录 `strategy_id`（S1–S11 或 `custom` + 描述串）+ `params_hash`，使「上周跑的是哪条策略」精确可查、ledger 行可归因、复现命令可直接 `apply_strategy(sid)`。新方向若不在 REGISTRY，登记为命名 arm（如 `R0/R1/R2`，对齐现有 `C0/C1/C2` 对照设计）。

---

## 3. 指标体系

所有指标在 **OOS test 切片**上、按 ledger 累计计算。分两类：**净值/风险**与**校准/质量**。

### 3.1 净值与风险（来自 `aggregate_equity` + 扩展）

| 指标 | 定义 | 现成来源 |
|------|------|----------|
| **真实 ROI** | `total_pnl / total_stake`（结算用 winning_sp） | `aggregate_equity` |
| **log wealth** | `Σ log(bankroll_t / bankroll_{t−1})`，几何增长率 | 由 equity 序列扩展 |
| **max drawdown** | `max((peak − bankroll)/peak)` | `aggregate_equity.max_dd` |
| **streak** | 最长连胜/连负期数（命中/未命中游程） | 由 weeks 序列扩展 |
| **turnover** | `total_stake / 平均 bankroll`；空仓周计 0 | 由 stake 序列扩展 |
| **hit rate** | 命中组合 / 总组合（空仓周不计分母） | `n_hits / n_combos` |
| **SP drift 后收益** | 决策 SP 下的「纸面 EV」与真实 winning_sp 结算 PnL 之差，按 sp_band 拆 | replay 不变式 + `apply_band_haircut` |

### 3.2 校准与预测质量

| 指标 | 定义 | 现成来源 |
|------|------|----------|
| **EV 校准** | 决策 SP 隐含的 per-leg EV vs 实际实现 q（多档分桶比较） | `_q_stat.q`（= RETURN_RATE × Σ命中腿SP / n）、`q_buckets` 分 league/option |
| **Brier** | `mean((p̂ − y)²)`，y∈{0,1} 为腿是否命中 | 由 calibration 策略预测概率 + result_code |
| **logloss** | `−mean(y·log p̂ + (1−y)·log(1−p̂))` | 同上 |
| **realized q vs 阈值** | 分 league/option 的 q 是否 ≥ 守卫阈值 | `select_downweight_leagues`（min_n + q_threshold） |

> q 是该项目已实现的「per-leg 实现回报倍数」口径（`_q_stat`），把它作为 EV 校准的实证锚点，避免再造一套概率口径。校准类指标（Brier/logloss）主要服务**单场校准**方向；净值类对四个方向都适用。

### 3.3 空仓的正确计入

- 空仓周：stake=0、turnover=0、不进 hit_rate 分母、equity 横走（log wealth 贡献 0）、不计 streak。
- 但**空仓本身要被审计**：diagnostics.reason_skip 入实验记录，便于回答「策略是因为没机会还是因为参数过紧而长期空仓」。一个长期空仓→ROI 看似不亏的策略，不得据此升为默认（§5 决策规则显式拦截）。

---

## 4. 统计稳健性（避免小样本拍脑袋）

足彩 OOS 初期样本极小（`sp_drift_forward.md` 现状：1.3 周、C2 仅 1 命中）。框架对所有「升级/降权」判定加统计闸门。

### 4.1 最小样本门槛（事前冻结）

沿用并泛化现有预注册停止规则：

- **组合数闸**：累计组合 ≥ `MIN_COMBOS`（现 200）。
- **周数闸**：forward 窗 ≥ `MAX_WEEKS`（现 12），先到先停。
- **止损闸**：纸面 MaxDD > `MAXDD_STOP`（现 50%）→ 立即 No-go。
- **校准类**：每桶 ≥ `min_n`（现成 `select_downweight_leagues` 用 8）才纳入 q/Brier 评判，否则 warn-only。

样本未达门槛时，**只允许方向性结论（directional Go / shadow），不允许加注**（与 MEMORY 中「样本薄时方向性 Go 而非加注」一致）。

### 4.2 置信区间与 bootstrap

- **小样本 CI**：ROI / hit_rate 用 bootstrap（按期次或按组合重采样 ≥ 2000 次）给 95% CI；命中率二项区间用 Wilson。
- **arm 对比**：C_x − C0（或 R_x − R0）的 ROI 差用配对 bootstrap 给差值 CI；GATE 通过要求**差值 CI 下界 > margin**（现 margin=5pp 的硬阈值升级为「CI 下界 > 0 且点估计 ≥ margin」）。
- 报告须画出 arm 累计 ROI 带 CI（扩展现有 `sp_drift_forward_roi.png` 的画法）。

### 4.3 Bayesian shrinkage

- 分 league/option/band 的 q、hit_rate 用 §1.2 的收缩公式向先验收缩，伪计数 k 由全历史定。薄样本桶自动退回先验，防止「某联赛 3 场全中 → q 虚高 → 误升权」。
- 单场校准的概率同样向「市场隐含 + 历史基率」收缩，再算 Brier/logloss。

### 4.4 多重比较

- 多 arm × 每周看 = 多重比较风险。处理：**判据全部事前冻结**（OOS 边界、阈值、margin、停止规则），forward 期间不得改判据或加 arm（沿用 spec §3/§9）。
- 若同一框架并行评估四个方向（= 多族实验），对「升为生产默认」这一最强决策施加更严门槛（如 Bonferroni 式提高 margin 或要求两段独立 OOS 复现），并在实验配置里登记同时在跑的族数。

---

## 5. 决策规则（升级 / shadow / 降权 / 停用）

判据事前冻结，verdict 由框架按 ledger 自动给出（泛化 `check_stopping_rule`）。四档动作：

| verdict | 触发条件（OOS、达样本门槛后） | 动作 |
|---------|-------------------------------|------|
| **go → 生产默认** | ROI > 0 **且** 对 C0/R0 的 ROI 差 CI 下界 > 0 且点估计 ≥ margin **且** 风险闸（MaxDD < 止损线）通过 **且** 非长期空仓伪正 | 升为 default profile，写下游落地 spec |
| **shadow / 小资金** | 方向成立（差值点估计 > 0）但 CI 含 0，或样本未达门槛 | 仅 shadow 记录或最小资金试跑，不改默认；继续累计到停止条件 |
| **降权** | ROI/q 显著低于对照但未到止损（如 `select_downweight_leagues`：n≥min_n 且 q<阈值） | 临时降权 / 联赛黑名单（现成机制），保留观察 |
| **no_go / 停用** | ROI ≤ 0 且差值不成立，**或** 触发 MaxDD 止损 | 停用该策略，记负结果并重审玩法/N/SP（沿用 spec §10） |

**反拍脑袋硬约束**：
- 升级**只**能在样本门槛 + CI 闸 + 冻结判据全过时发生；近几周好看不构成升级理由。
- 长期空仓导致的「不亏」不得当作 go（§3.3）。
- 升级前后判据不可改；要改判据须开新实验、重置 OOS 边界。

---

## 6. 产物

| 产物 | 路径 / 形态 | 说明 |
|------|-------------|------|
| **实验配置文件** | `experiments/<exp_id>.yaml`（建议） | 冻结：FORWARD_START、arm 定义、策略参数、margin、停止规则、收缩 k、并行族数、params_hash |
| **结果 ledger** | `data/derived/<exp_id>/forward_ledger.csv` | 泛化现有 `forward_ledger.csv`，列见 §6.1，append-only + 幂等 |
| **图表** | `docs/research/figures/<exp_id>_*.png` | arm 累计 ROI（带 CI）、equity、校准曲线、q 分桶 |
| **周报摘要** | `docs/research/<exp_id>_forward.md` | 泛化现有 `sp_drift_forward.md`：各 arm 累计表 + verdict + 距停止差距 + 局限声明 |
| **复现命令** | CLI（§7） | 一条命令重跑某 exp 的某 run_date，结果应幂等一致 |

### 6.1 Ledger schema（泛化现有）

现有列 `run_date, arm, forward_start, n_combos, n_hits, total_stake, total_pnl, roi, max_dd, final_bankroll`，扩展为：

```
exp_id, run_date, arm, strategy_id, params_hash, forward_start,
n_candidate_legs, n_combos, n_hits, total_stake, total_pnl,
roi, log_wealth, max_dd, max_streak, turnover, hit_rate,
brier, logloss, roi_ci_low, roi_ci_high, verdict
```

- 老列保持兼容（`sp_drift` 实验仍可读）；新列对不产出该指标的策略填 NaN。
- 一行 = 某 exp 某 arm 在「FORWARD_START 至今 OOS 切片」上的累计快照（同 run_date 重跑覆盖）。

---

## 7. CLI 草案

泛化 `scripts/run_sp_drift_forward.py`（现为单实验硬编码）为多实验运行器。命令仅为草案，本稿不实现：

```bash
# 列出已注册实验（读 experiments/*.yaml）
beidan-wf list

# 跑一个实验的当前 run_date：组装候选腿集 → 各 arm 重放 OOS → 追加 ledger → 出报告+图+verdict
beidan-wf run <exp_id> [--run-date YYYY-MM-DD] [--rebuild-panel]

# 只看状态/判定，不重跑（读 ledger → check_stopping_rule 泛化版）
beidan-wf status <exp_id>

# 复现校验：对某 run_date 重跑，断言 ledger 行幂等一致
beidan-wf verify <exp_id> --run-date YYYY-MM-DD

# 周报（systemd 每周一调用，沿用 beidanlot-sp-forward.timer 同款模式，每实验一个 timer）
beidan-wf report <exp_id>
```

- `run` 内部：`panel.build` → 组装 CandidateLegs → 对配置里每个 arm 调 `run_strategy` → `aggregate_equity` + 校准指标 → bootstrap CI → `append_ledger` → verdict → 写报告/图。
- 复用现有 `NicheConfig.load()`、`baseline_decision_mtk`、`append_ledger` 幂等逻辑、matplotlib 出图。
- 每实验一个 `experiments/<exp_id>.yaml` + 一个 systemd timer，互不干扰；判据冻结在 yaml 里。

---

## 8. 首批实验清单

四个方向各登记为一个实验，共用 §2 接口、§3 指标、§4 闸门、§5 决策规则。每个实验都设**对照 arm（X0 = 复现历史行为，无该策略处理）** + 一个或多个**处理 arm**，对照设计对齐现有 C0/C1/C2。

| exp_id | 方向 / 姊妹文档 | 候选腿处理（vs 对照 X0） | 关键 OOS 指标 | 备注 |
|--------|----------------|--------------------------|----------------|------|
| `regime_timing` | 动态择时 `regime_timing_strategy.md` | 按 regime 标签调 N 混合权重/Kelly，或触发空仓 | ROI、log wealth、turnover、空仓占比 | 须验「空仓不是过紧伪正」（§3.3/§5） |
| `low_mid_sp_high_n` | 中低 SP 高 N `low_mid_sp_high_n_experiment.md` | 按 `sp_band` 选低/中档 SP + 抬高 N | ROI、hit rate、max_dd、SP drift 后收益 | 高 N 命中稀疏，样本门槛尤其关键 |
| `single_match_calib` | 单场校准 `single_match_probability_calibration.md` | 用校准胜率覆盖隐含概率重算 EV/qualify | Brier、logloss、EV 校准、ROI | train 段拟合校准曲线，OOS 段冻结 |
| `inplay_filter` | 临场过滤 `inplay_sp_timing_filter.md` | 按 `decision_mtk`/窗口残余漂移过滤腿 | ROI、SP drift 后收益、turnover | 注意运营口径差（见下）|

**继承 sp_drift 的两个教训（写进每个实验的局限节）**：
1. **运营口径差**：replay 的「每场各取距开赛 N 分钟的池化 SP」≠ 实盘「距现在 N 小时内开赛的同时性过滤」。`inplay_filter` 与 `regime_timing` 的临场类处理量化的是**理想临近决策上界**，落地需运营机制复核（参见 `sp_drift_forward.md` 的 P1 权衡结论：N=4 需 ≥30 场同时在池，任何窗口值都无法两全）。
2. **纸面 PnL 是乐观上界**：忽略售罄/凑整/SP 末段再动。go 仅意味着「值得进 shadow / 小资金真实落地 spec」，不等于直接放大真钱。

---

## 9. 与现有 sp_drift forward-test 的关系

本框架是 `sp_drift/forward.py` 的**超集泛化**，不推翻它：

- `sp_drift` 现有实验可视为本框架的实例 `exp_id=sp_drift`（arm=C0/C1/C2，verdict 逻辑即 `check_stopping_rule`）。
- 泛化点：FORWARD_START/arm/参数/margin 从模块常量移到 `experiments/<exp_id>.yaml`；ledger 加 exp_id + 校准/CI 列；运行器接受 exp_id；CI/shrinkage 显式化。
- 不变量保留：append-only 幂等 ledger、OOS 切片用 `kickoff_ts >` 过滤、qualify/decision-SP + settle/winning-SP 不变式、预注册停止规则、样本薄只方向性 Go。

---

## 10. 风险与局限

| 风险 | 处理 |
|------|------|
| OOS 初期样本极小 | 双闸（组合 OR 周数）+ CI 下界判定 + 薄样本只方向性 Go |
| 多方向并行 = 多重比较膨胀 | 判据事前冻结；升默认这一最强决策加严 margin / 要求两段 OOS 复现（§4.4） |
| 校准/收缩引入新自由度（k、桶切法） | k 与桶切法写进冻结配置，OOS 不得调；改则开新实验重置边界 |
| 运营口径差（临场类） | 量化为理想上界；落地前用 live 路径复核（§8 局限） |
| 长期空仓伪正 | §3.3 审计 reason_skip；§5 升级规则显式拦截 |
| 自身下注反身性 | 纸面阶段无；真实落地阶段单独评估 |
