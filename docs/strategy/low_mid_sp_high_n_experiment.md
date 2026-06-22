# 中低 SP + 高 N 是否优于高 SP 串 — 研究方案设计

| 元信息 | 值 |
|--------|----|
| 日期 | 2026-06-23 |
| 作者 | Claude（承接 kanban `t_8ed3c34f`） |
| 状态 | 设计稿（spec，未实现） |
| 主题 | 用中低 SP 腿（依赖 q 而非 SP 高低）+ 更高 N 构票，是否优于当前偏好的高 SP 串 |

**关联代码**

- `src/sp_drift/replay.py` — `replay_policy` / `Policy(n_legs,…)` / `apply_band_haircut`（任意 N 的反事实重放；qualify/sizing 用决策 SP，结算用真实 `winning_sp`）
- `src/sp_drift/forward.py` — forward-test 框架（C0/C1/C2 arm、`HAIRCUT_MAP`、`build_arms`、停止规则 `check_stopping_rule`、ledger）。**本课题的 MVP 落点**
- `src/webui/services.py` — `q_buckets` / `_q_stat`（按 league/option 算 q）、`passes_concentration_guard`、`leg_concentration_pct`、mix 路径（per-N weights/kelly/lambda、`cross_n_lambda`）
- `src/webui/strategies.py` — `REGISTRY`（S2/S10 纯高 N 示例；S7 纯 N=3；S9 跨 N 多样化）
- `src/phase5a/filter.py` — `NicheConfig`（`p_hat_train`、q 门槛、`league_quality.json`、`drift_block_rules`）
- `src/phase5a/planner.py` — `build_weekly_plan(…, n_legs, kelly_fraction, max_combos, diversity_lambda, combo_ev_threshold, top_k, cross_n_*)`

**姊妹文档**（并行规划，路径待建）

- `docs/strategy/regime_timing_strategy.md`
- `docs/strategy/single_match_probability_calibration.md`
- `docs/strategy/inplay_sp_timing_filter.md`
- `docs/strategy/walk_forward_strategy_evaluation.md`
- 并行课题：`docs/research/sp_drift_phase4.md`（决策时机是巨大杠杆；haircut 后保守 ROI +11.6%，样本薄）

---

## 1. 背景与假说

### 1.1 现象

当前策略偏好把 SP≈4.0–4.5 的高 SP 腿串在一起。近期即使单腿命中，回报与命中也偏弱。按实盘票粗分（2026-05-22 之后）：

| 票的平均 SP 桶 | 实盘 ROI（粗估） |
|----------------|------------------|
| avg SP 3–4 | ≈ −47% |
| avg SP 4–5 | ≈ −77% |

高 SP 桶反而更差。这与"SP 越高赔率越大、EV 越好"的直觉相反。

### 1.2 为什么不能用 SP 高低判 EV

北单 `RETURN_RATE = 0.65`，定义每腿的"期望回报倍数"

```
q = p × SP
```

其中 `p` 是该腿真实命中概率，`SP` 是结算赔率。整票（N 腿）期望回报近似 `(mean q)^N × 0.65`（各腿命中独立、乘积结算）。**EV 由 q 决定，不由 SP 决定**：SP 高若 p 没相应高，q 反而塌。实盘高 SP 桶差，正是 SP 高但 p 跟不上、且高 SP 腿更易 SP-drift 下跌（见 `sp_drift_phase4.md`），结算 `winning_sp` 缩水。

### 1.3 高 N 降低每腿 break-even 门槛

整票 +EV 要求 `(mean q)^N × 0.65 > 1`，即每腿 break-even

```
q* = (1 / 0.65)^(1/N) = 0.65^(-1/N)
```

| N | break-even q* |
|---|---------------|
| 2 | 1.240 |
| 3 | 1.154 |
| 4 | 1.114 |
| 5 | 1.090 |
| 7 | 1.064 |

N 越高，每腿 q 只需略高于 1 即可整票 +EV。这给"用一堆 q 稳定略 >1 的中低 SP 腿、靠高 N 摊薄门槛"提供了理论入口——**前提是 q 真的稳定 ≥ q\***，而非靠少数高 SP 腿的方差撑场面。

### 1.4 核心假说

> **H1**：在相同决策时机 / 相同 Kelly 下，以 q 与 q 稳定性为准筛中低 SP 腿、用更高 N（5/6/7）构票，长期 ROL（log wealth）与 Calmar 优于当前偏高 SP 的 N=4 串。
>
> **H0（零假设 / 必须能被"skip"否决）**：高 N 摊薄不足以补偿整票命中率的指数下跌，中低 SP 高 N 并不优于现状，甚至该直接 skip（不下注）。

判 H1 成立的硬条件见 §8。

---

## 2. 候选定义：以 q 为准，不以 SP 为准

候选筛选**第一公民是 q，不是 SP**。SP 上下限只作为"避免落入已知 drift 黑洞"的护栏，不作为选优依据。

### 2.1 单腿过滤规则（leg filter）

| 维度 | 字段 / 来源 | 设计取值（网格见 §6） |
|------|------------|------------------------|
| q 下限 | `q_final = p_final × SP`（`p_final` 见下） | `q_min ∈ {1.05, 1.08, 1.10, 1.12}` |
| q 稳定性 | 同 niche 桶历史 q 的方差 / 样本量 | 桶内 `n ≥ n_min`（如 8）；剔除 q 波动过大的桶 |
| p 下限 | `p_final`（niche `p_hat_train`，见 `filter.py`） | `p_min ∈ {0.20, 0.25, 0.30}`（越高越偏中低 SP） |
| SP 桶 | 决策 SP 分档（对齐 `drift_stats.sp_band`：`<3.5 / 3.5-4.5 / 4.5-5 / 5-8 / >8`） | 主网格锁 `<3.5` 与 `3.5-4.5`；高 SP 桶仅作对照 |
| SP 上限 | `sp_hi` | `sp_max ∈ {3.5, 4.0, 4.5}`（卡掉长尾高 SP） |
| 是否允许平局 | option `1`（平） | 两组：允许平 / 不允许平（现 niche 规则结构上**几乎无平局规则**，见 `diagnostic_legs`，需单独考查） |
| drift 护栏 | `NicheConfig.drift_block_rules` + `league_blacklist` | 沿用现有，不放松 |

**关键点**：

- `q_final` 用**决策时刻**的 `p_final × SP_decision`。但结算永远用真实 `winning_sp`（`replay.py` 不变量），所以"决策时 q 看着够、结算 SP 缩水导致 q 塌"的损失会真实体现为亏损。
- 可叠加 `apply_band_haircut`：把决策 SP 朝预期结算值打折后再算 q（C2 arm 思路），让高 SP 桶在 EV/sizing 阶段先缩水。
- q 稳定性优先于 q 绝对值：宁要 q=1.10±0.03 的桶，不要 q=1.20±0.30 的桶——后者整票方差会被 N 放大。

### 2.2 q 的度量口径

复用 `services._q_stat` / `q_buckets`：按 league 与 option 聚合已结算腿，给出 `n / hits / hit_rate / avg_sp / q`，其中

```
q = RETURN_RATE × (Σ 命中腿 SP) / n
```

这是**已实现 q**，与决策时 `p_hat × SP` 的"期望 q"对照，可量化决策口径与实盘口径的偏差，作为候选桶是否可信的依据。

---

## 3. 组合构造（N=4/5/6/7）

复用 `build_weekly_plan` / mix 路径。每个 N 的构造参数：

| 参数 | 字段 | 设计 |
|------|------|------|
| 腿数 | `n_legs` | 4 / 5 / 6 / 7（`replay.Policy.n_legs` 支持任意 N；mix 路径目前枚举 N∈{2,3,4,5}，扩到 6/7 需在 `generate_plan` 的 `per_n_params` 增项——MVP 不做，先用 replay 直接跑） |
| 组合上限 | `max_combos` | 随 N 升高调高（候选少时高 N 组合数爆炸/枯竭都可能）：`{N4:100, N5:150, N6:200, N7:200}` |
| 多样化 | `diversity_lambda` | N 越高越要分散，`λ ∈ {0.5, 1.0}`；跨 N 用 `cross_n_lambda`（如 0.5）避免同一腿在不同 N 票里重复 |
| 单腿频率上限 | `leg_concentration_pct` ≤ `MAX_CONCENTRATION_PCT(=60%)` | 高 N 下更严：目标 ≤ 40% |
| 合格腿下限 | `passes_concentration_guard`（`MIN_QUALIFIED_LEGS=13`） | 高 N 至少需 `n_legs + 余量` 个独立合格腿，否则该 N 跳过 |
| Kelly | `kelly_fraction` | 见 §4 降档 |
| combo EV 门槛 | `combo_ev_threshold` | 默认 0.05；高 N 下因 q* 降低可保持或略松 |

> **枯竭风险**：`replay` 已验证 N=2 在现有 EV/qualify 机器下"饿死"（~1 票/周）。N 越高对"足够多 q≥q\* 的独立合格腿"的需求越大，候选池一旦不够，高 N 票数会塌。`max_combos` 与合格腿下限须联动监控。

---

## 4. 高 N 的代价与风控

| 代价 | 机制 | 对策 |
|------|------|------|
| 整票命中率指数下跌 | `hit = Π p_leg`；实盘 N=4 整票命中 ≈ 2.8%，N 越高越低 | 接受更低命中、更靠长尾大额命中；用 log wealth 而非 ROI 主判 |
| 长连亏（losing streak） | 命中率低 → 连续 miss 周期长 | 监控最长 miss streak；预登记 streak 上限作停止条件 |
| 方差放大 | 高 N 把每腿 q 的方差按乘积放大 | 要求 q 稳定（§2）、强制分散（§3）、Kelly 降档 |
| 分散要求 | 少数腿撑多张票 = 伪分散 | `leg_concentration_pct` ≤ 40%、`cross_n_lambda` 跨 N 去重 |
| Kelly 过激 | 高 N + 高方差下满 Kelly 会爆 | **Kelly 降档**：N 越高 `kelly_fraction` 越小，如 `{N4:1/16, N5:1/16, N6:1/32, N7:1/32}`；整体周投注 cap `weekly_stake_cap_frac=0.25` 不变 |

---

## 5. Walk-forward 对比设计

三类策略同框对比，**同决策时机、同结算口径**（`replay_policy` 不变量），用 walk-forward（逐 issue 滚 bankroll，`replay_policy` 已逐 issue 结算）：

| 臂 | 含义 |
|----|------|
| **A. 现状高 SP 串** | 当前偏好：N=4，偏 3.5–4.5 SP，现有 niche 规则 |
| **B. 中低 SP 高 N** | §2 候选 + §3 高 N（N=5/6/7 各一组，或 mix） |
| **C. skip** | 不下注（现金）——H0 的物化对照，B 必须显著优于 C 才有意义 |

历史 + 实盘两段：

- **历史段（in-sample 探索）**：用全 panel 跑 §6 网格，定 B 的最优参数。**仅用于探索，不作上线依据**（防过拟合）。
- **实盘 / OOS 段（walk-forward 验证）**：用 `forward.py` 的 `forward_panel`（`kickoff_ts > FORWARD_START`）滚动验证锁定参数，逐周追加 ledger。

> 与 `sp_drift_phase4` 一致的告诫：baseline 用统一 MTK 比实盘更早，**A 的绝对 ROI 不能与实盘直接比**；三臂须在**同一 MTK、同一 panel 切片**下比，只看相对差。

---

## 6. 实验网格

| 维度 | 取值 |
|------|------|
| N | 4（对照基线）, 5, 6, 7 |
| q_min | 1.05, 1.08, 1.10, 1.12 |
| p_min | 0.20, 0.25, 0.30 |
| sp_max | 3.5, 4.0, 4.5 |
| 允许平局 | 否 / 是 |
| diversity_lambda | 0.5, 1.0 |
| cross_n_lambda | 0（关）, 0.5 |
| kelly（按 N 降档） | N4:1/16, N5:1/16, N6:1/32, N7:1/32 |
| max_combos（按 N） | N4:100, N5:150, N6:200, N7:200 |
| haircut | 关 / 开（`HAIRCUT_MAP`，C2 思路） |
| 决策时机 MTK | 与 A 同（统一），不在本课题内调（时机课题见 `sp_drift_phase4`） |

全网格仅在历史段跑；OOS 只验证锁定的少数组合，避免多重检验。

---

## 7. 输出指标

每臂 / 每参数组合输出（`aggregate_equity` + 扩展）：

- **ROI** = `total_pnl / total_stake`
- **log wealth / CAGR**：`Σ log(1 + 周收益率)`（**主判据**，高 N 长尾分布下比 ROI 稳健）
- **max drawdown**（`max_dd`）
- **Calmar** = CAGR / max_dd
- **命中分布**：整票命中率（`n_hits / n_tickets`）、命中票 payout 分布、单腿 hit_rate（按 SP 桶 / option / league，复用 `q_buckets`）
- **亏损 streak**：最长连续 miss 周期数 / 票数
- **SP drift 后 EV**：决策 q（`p_hat × SP_decision`）vs 已实现 q（`_q_stat`）之差，量化"决策时看着够、结算缩水"的损失
- **票数 / 周（枯竭监控）**：每 issue 实际生成票数，防 N 过高导致饿死

---

## 8. 预期风险与"是否进入小资金 forward test"的判据

### 8.1 主要风险

1. **过拟合**：网格大、命中稀疏，历史段易挑出幸运组合。对策：OOS 只验证少量锁定参数；主看 log wealth 而非 ROI 峰值。
2. **样本太薄不可据此选 N**：已用 replay 做过 N=2/3/4 快速对比，**稳的结论只有"低 N 命中频率高一个数量级"（N3≈7% vs N4≈1.3%）**；ROI 样本太薄，**不可据此选 N**。N=2 在现有机器下会饿死（~1 票/周）。
3. **枯竭**：高 N 需要足够多 q≥q\* 的独立合格腿；池子不够则票数塌、统计失效。
4. **方差**：高 N 长尾，少数大额命中即可翻盘 ROI，单看 ROI 会被噪声主导。

### 8.2 进入小资金 forward test 的判据（pre-registered）

复用 `forward.py` 停止规则 / GATE-FT 的结构（`MIN_COMBOS=200`、`MAX_WEEKS=12`、`MAXDD_STOP=0.50`、`MARGIN=0.05`），针对本课题登记：

进入小资金 forward test（GATE：directional-go），须**全部**满足：

1. 历史段：某中低 SP 高 N 组合（B）的 **log wealth / CAGR > 现状高 SP 串（A）**，且 **B 的 ROI > skip（C，=0）**；
2. B 相对 A 的 ROI margin ≥ `MARGIN(0.05)`，且方向在多个相邻参数（q_min / sp_max 邻格）上一致（非单点幸运）；
3. B 的 max_dd 未触 `MAXDD_STOP(0.50)`，最长 miss streak 在登记上限内；
4. B 票数充足（不枯竭，避免 N=2 式饿死），样本足以让 §7 指标可读。

否则判 **no-go / skip**（H0 不能被否决，维持现状或直接 skip）。

---

## 9. MVP：把 N=3 / N=5 paper arm 加进 forward 框架

> **不在本文档实现。** 以下是 MVP 落点，作为后续 kanban 任务。

`forward.py::build_arms` 目前只有 C0/C1/C2（围绕决策时机 + haircut）。本课题最小可行验证 = **在同一 forward 框架内加 N 维度的 paper arm**，与现有 N=4 臂并排滚 ledger：

- 新增 `Policy(n_legs=3)` 与 `Policy(n_legs=5)` 臂（`replay.Policy.n_legs` 已支持任意 N），先与 C0（现状 N=4）同 MTK、同 kelly 跑，**纯 paper、零资金**；
- ledger 复用 `append_ledger` / `LEDGER_COLS`，每臂一行，逐周累积 `n_combos / n_hits / roi / max_dd`；
- 停止规则复用 `check_stopping_rule` 思路（按 N 臂登记 margin）；
- 为什么先 N=3/5 而非 6/7：mix 路径现仅枚举 N∈{2,3,4,5}；N=6/7 需扩 `generate_plan` 的 `per_n_params`，留作第二步。replay 侧可直接跑任意 N 作离线探索。

MVP 通过（OOS 上某高 N 臂 log wealth 稳定 ≥ N=4 且不枯竭）后，再按 §8.2 决定是否进小资金 forward test。

---

## 10. 不做什么 / 边界

- 不调决策时机 MTK（属 `sp_drift_phase4` / `inplay_sp_timing_filter` 课题，本课题统一固定）。
- 不放松 `drift_block_rules` / `league_blacklist`。
- 不靠单点历史 ROI 选 N（样本太薄，见 §8.1.2）。
- 不在本设计稿写实现代码 / 不改其他文件。
