# 预测 final_SP / SP 过程模型 — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban `t_dd1fa5e2`）
**状态**: 设计稿（不含实现代码；仅本文档，不改其他文件）
**关联**:
- 代码：
  - `src/sp_drift/panel.py`（`minutes_to_kickoff` / `build_snapshot_panel` / `decision_view(panel,mtk_target)` / `attach_final_and_settlement`）
  - `src/sp_drift/drift_stats.py`（`drift_metrics`：`drift_bias`/`residual_drift` / `drift_by_mtk_bucket` / `sp_band` / `drift_by_cell` / `winners_vs_all_bias` / `vol_imbalance_predictivity`）
  - `src/sp_drift/replay.py`（`replay_policy(panel, live_db, niche_config, Policy(mtk_target,haircut))` / `apply_band_haircut` / `actuals_from_db`）
  - `src/sp_drift/forward.py`（`HAIRCUT_MAP` / `WINDOW_MTK=180` / `FORWARD_START=2026-06-13` / `build_arms` / `check_stopping_rule` / `run_forward`）
  - `src/webui/services.py`（`maybe_haircut_snapshots`（config `haircut_enabled` 门控，默认 0）/ `generate_plan` 的 EV·sizing 接入点 / `compute_q_drift` / `q_buckets`）
  - `src/combo_optimizer`（`RETURN_RATE=0.65`，`Candidate.edge = p_hat × SP × 0.65 − 1`）
- 数据：`data/beidan_live.db`（`snapshots` 796,542 行 / `matches` / `settlements` 1,891 行）
- 既有研究：`docs/research/sp_drift_phase0.md`、`sp_drift_phase1.md`、`sp_drift_phase4.md`、`sp_drift_forward.md`、`q_persistence_analysis.md`、`sp-bias-and-kelly.md`
- 姊妹文档（同目录设计稿，明确分工见 §0）：
  - `docs/strategy/inplay_sp_timing_filter.md`（临场择时；本文是其**预测内核**）
  - `docs/strategy/single_match_probability_calibration.md`（单场 `p` 校准；本文负责 `E(final_SP)`，两者相乘成 EV）
  - `docs/strategy/walk_forward_strategy_evaluation.md`（统一样本外评估框架；本文回测遵从其判据）

---

## 0. 这份文档是什么 / 分工

**研究对象切换**：从「预测赛果 `q`」改为「预测结算赔率过程 `E(final_SP | 当前状态)`」。

最终 EV 公式从「用当前 SP」改为「用预测的结算 SP」：

```
EV_leg = p × E(final_SP) × 0.65 − 1        （期望版）
EV_leg = p × SP_conservative × 0.65 − 1    （保守分位版，见 §5）
```

**分工边界（务必遵守，避免与姊妹文档重叠）**：

| 文档 | 负责 | 不负责 |
|------|------|--------|
| **本文** `final_sp_process_model.md` | 预测 `final_SP / current_SP` 的过程模型、haircut、tail、把 final_SP 分布接入 EV | 单场赛果概率（交给校准文档）、买/等/弃的调度执行（交给临场文档） |
| `single_match_probability_calibration.md` | 单场 `p`（赛果概率）的校准 | SP 漂移过程 |
| `inplay_sp_timing_filter.md` | 据预测结果做**买/等/弃**的调度、kickoff bucket 分批、降 N/降 stake/空仓 | 漂移**预测**本身（调用本文产出） |
| `walk_forward_strategy_evaluation.md` | 统一 OOS 评估纪律（预注册、停止规则、GATE） | 具体策略内核 |

一句话：**本文产出 `E(final_SP)` 与其分位，校准文档产出 `p`，临场文档用 `p × E(final_SP)` 做调度，评估文档裁决上线。**

---

## 1. 背景与核心论据

### 1.1 为什么这是最该做的结构性方向

最近实盘 ROI **−50 ~ −70%**。拆解亏损来源：

1. **抽水地板（一次性 −35%）**：北单 `RETURN_RATE = 0.65`，即任何下注先扣 35%。这是固定成本，不可消除，只能靠正 edge 覆盖。
2. **SP 漂移沿串关腿成倍放大（乘法杀手）**：命中腿平均漂移 **−16.6%**（计划 SP `4.05` → 结算 SP `3.36`）。串 4 关时，漂移按腿相乘：

   ```
   0.836⁴ ≈ 0.49
   ```

   即**中奖票实际只按计划赔率的约一半派彩**。漂移对单腿是减法，对串关是**乘法**——这正是 final_SP 预测要解决的核心。

> 关键洞察：把 EV 建立在「计划时观测的 current_SP」上，等于系统性高估每一腿的赔付，再被串关相乘放大。**正确做法是把 EV 建立在「预测的 final_SP」上。**

### 1.2 为什么不是继续做赛果 q 择时

`docs/research/q_persistence_analysis.md`（n=504 腿、10 期）已证明单腿赛果 `q` **无可利用的时间结构**：

- 整体 lag-1 自相关 **−0.20**（标准误 ≈0.32，与 0 不可区分）；
- 联赛级早期 q 与晚期 q 相关 **−0.745**（均值回归方向真实但…）；
- 逆向回测：低 q 桶 **0.756** vs 高 q 桶 **0.480**——方向真实但**均 < 1.0**，回归中心 0.82 本身就在盈亏平衡线下，**逆向只是亏得少，不是赚**。

结论：赛果 q 的负 EX 基底无法靠择时翻正。**换框到「预测 SP 过程」是合理的**——SP 漂移有方向性结构（band-selection + early-decision，见 §2），是可建模、可对冲的。

---

## 2. SP 漂移的两层机制（Phase 1 已定性，本文要量化）

Phase 1（2026-06-14）把 −16.5% 拆为：

- **band-selection**：我们偏好的高赔档（longshot）本身系统性下修。`HAIRCUT_MAP` 已捕捉到这一层的桶级 `drift_bias`：

  | SP 桶 | 冻结 `drift_bias` | 含义 |
  |-------|------------------|------|
  | `<3.5` | **+0.33** | 热门反而上漂（被抛售/对冲）|
  | `3.5-4.5` | **−0.09** | 轻微下修 |
  | `4.5-5` | **−0.21** | 中度下修 |
  | `5-8` | **−0.36** | 重度下修 |
  | `>8` | **−0.81** | 极端下修（长尾砍价）|

  （来源：`src/sp_drift/forward.py: HAIRCUT_MAP`，GATE-1 冻结值，OOS 测试期不得重估。）

- **early-decision**：决策离开赛太久（实盘中位决策点约 18h-out，`kickoff_window_hours=0`），SP 尚未收敛。漂移**随 MTK 增大而加剧**——这是 `drift_by_mtk_bucket` 要量化的维度。

- **`vol_pct` 维度已被验证 dead**：成交占比无预测力（`vol_imbalance_predictivity` 历史结果）。**且当前数据库 `vol_pct_*` / `pool_total` 全 NULL**（见 §3），故资金占比/成交热度特征**整体推迟到 v2**。

> 本文的建模任务 = 把上述两层机制从「全局桶级常数」升级为「条件期望 `E(final_SP | 状态)`」，并扩展到 tail / haircut / 砍价风险，且**在全部腿上估计**（避免幸存者偏差，见 §7）。

---

## 3. 数据字段（实测，务必采用）

实测 `data/beidan_live.db`（2026-06-23）：

### 3.1 可用字段

| 表.字段 | 含义 | 覆盖率（实测）| 备注 |
|---------|------|--------------|------|
| `snapshots.sp_3/sp_1/sp_0` | 北单 SP（胜/平/负）| 高 | 面板 `sp`，按 selection 展开 |
| `snapshots.snapshot_ts` | 快照时间 | 全 | **UTC**（尾 `Z`）|
| `snapshots.eu_h/eu_d/eu_a` | 欧赔（主/和/客）| **100.0%** | 做「北单 SP vs 去水欧赔偏离」特征 |
| `matches.kickoff_ts` | 开赛时间 | — | **北京时间**（naive，无 tz）|
| `matches.league / handicap_line / issue / match_idx` | 联赛/让球/期号/场序 | 高 | 分桶维度 |
| `settlements.result_code` | 赛果（0/1/3）| — | join key |
| `settlements.winning_sp` | **真实结算 SP（赔付真值）** | — | 漂移的因变量来源；replay 结算用它 |
| `settlements.avg_eu_h/avg_eu_d/avg_eu_a` | 结算均欧赔 | **95.24%** | 「SP 偏离欧赔」标签侧 |

`snapshots` 共 **796,542** 行，`settlements` **1,891** 行。

### 3.2 当前缺失（标 v2 / 待 collector 打通）

| 字段 | 状态 | 影响 |
|------|------|------|
| `snapshots.vol_pct_3/1/0` | **全 NULL（0.0%）** | 资金占比特征**无数据源** |
| `snapshots.pool_total` | **全 NULL（0.0%）** | 成交热度/砍价风险**无数据源** |

> 因此「资金占比、成交热度导致的砍价风险」**作为 v2 特征**，须等 collector 打通 `vol_pct` / `pool_total` 后再做。本文 MVP（§4）**不依赖这两类字段**，仅用 SP 序列 + 欧赔偏离 + 桶维度。

### 3.3 时区与冻结 SP 注意事项

- `snapshot_ts` 是 UTC，`kickoff_ts` 是北京时间（UTC+8）。`panel.minutes_to_kickoff` 已正确处理两者时差。
- collector **开赛后仍 poll**（SP 被冻结），故面板必须保留 `mtk > 0`（`build_snapshot_panel` 已做：`panel["mtk"] > 0`）。**所有训练/评估只用 pre-kickoff 快照。**

### 3.4 SP 过程特征清单（建模输入 X）

按 `(match_id, selection, 决策快照)` 一行，从 `decision_view(panel, mtk_target)` 起算：

| 特征 | 来源 | v1/v2 |
|------|------|-------|
| `open_sp` | 该腿最早快照的 SP（开盘）| v1 |
| `current_sp` | 决策时 SP（`decision_view` 的 `sp`）| v1 |
| `slope_1h / 3h / 6h` | 决策点回看 1h/3h/6h 的 SP 斜率（log-ratio / Δt）| v1 |
| `mtk` | 决策点距开赛分钟（`decision_mtk`）| v1 |
| `sp_band` | `drift_stats.sp_band(current_sp)` | v1 |
| `eu_deviation` | 北单 current_sp 相对去水欧赔隐含赔率的偏离：`current_sp / (eu_sel × 去水因子) − 1` | v1 |
| `mtk_implied_odds` | 同一选项的 MTK 派生赔率（去水欧赔→隐含 SP，做锚）| v1 |
| `league_bucket / hcp_class / comp_type` | `panel` 已有分类列 | v1 |
| `vol_pct_self` | 该腿自身成交占比 | **v2（NULL）** |
| `pool_total / 热度` | 总成交，砍价风险 | **v2（NULL）** |

去水因子：把欧赔 `avg_eu` 的隐含概率归一去掉 booker margin（overround），得到「公平赔率」，再与北单 SP 比，刻画北单相对国际市场的定价偏离。

---

## 4. 预测目标与模型 MVP

### 4.1 预测目标（因变量 Y）

以「决策快照」为基准，目标全部以**比率形式**（与 `drift_metrics` 一致：`ratio = final_sp / decision_sp`）：

| 目标 | 定义 | 用途 |
|------|------|------|
| `E[final_SP / current_SP]` | 期望漂移比率（signed）| 期望版 EV（§5）|
| 绝对 drift | `E[final_SP − current_SP]` | 派彩缩水的绝对量 |
| **下修概率** `P(ratio < 0.98)` | 不利漂移概率（对应 `unfavorable_share`）| 跳过/降权决策 |
| **tail haircut** `P(ratio < 0.5)` 及尾部条件期望 | 极端砍价的尾风险 | 长尾 longshot 的 EV 截断 |
| 砍价风险（v2）| 高成交热度→临场被砍的条件下修 | v2，待 `pool_total` |

注意：`drift_metrics` 现成给出 `drift_bias`（signed E[ratio−1]）、`residual_drift`（E|ratio−1|）、`favorable/stable/unfavorable_share`，可直接作为桶级标签。

### 4.2 四个建模层级（按复杂度递增，MVP 从 M0/M1 起）

| 模型 | 描述 | 优点 | 缺点 | 角色 |
|------|------|------|------|------|
| **M0 分桶 haircut** | 复用 `HAIRCUT_MAP`：按 `sp_band` 取桶级 `drift_bias` 常数。`apply_band_haircut` 已实现 | 已上线、零新代码、可解释 | 桶粗、忽略 MTK 与 slope、无分位 | **基线（已有）** |
| **M1 多维分桶 + Bayesian shrinkage** | 桶维度扩展到 `(sp_band × mtk_bucket × league_bucket)`，每桶 `drift_bias` 用经验贝叶斯向全局先验收缩，小样本桶回归到 M0 | 抗小样本、仍可解释、自然给出分位 | 维度组合爆炸需 shrinkage 兜底 | **MVP 主推** |
| **M2 quantile regression** | 对 `ratio` 直接回归条件分位 `Q_τ(ratio | X)`，X = §3.4 特征。τ ∈ {0.1, 0.25, 0.5} | 直接产出**保守分位**（§5），刻画 tail | 需特征工程、校准检验 | **MVP 次推（接 EV 的分位入口）** |
| **M3 轻量树（LightGBM / 单棵浅树）** | 梯度提升回归 `ratio` 或分位，吃全部 §3.4 特征 + 交互 | 自动抓非线性/交互（如 slope×mtk）| 黑盒、易过拟合薄样本、需更强 OOS 纪律 | **v1.5，仅当 M1/M2 残差仍有结构时** |

**取舍原则**：当前 `settlements` 仅 1,891 行（每选项展开后腿数有限），**样本薄**。优先 **M1（Bayesian shrinkage 抗薄样本）+ M2（分位接 EV）**；M3 树模型**先不做**，留待样本累积且 M1/M2 出现系统残差时再引入，并必须过 §6 的 OOS 纪律。

### 4.3 MVP 范围

- **In**：M0 基线对照、M1 多维分桶 shrinkage、M2 quantile regression（至少 `Q_0.25`）、`eu_deviation` 特征、tail 下修概率。
- **Out（v2）**：所有 `vol_pct` / `pool_total` 特征、M3 树、砍价热度模型。

---

## 5. 把 final_SP 分布接入 EV（核心接入点）

### 5.1 现状

`Candidate.edge = p_hat × SP × 0.65 − 1`，其中 `SP` 是**当前 SP**——这正是高估来源。EV/Kelly sizing 在 `src/webui/services.py: generate_plan` 内，经 `maybe_haircut_snapshots(snaps, haircut_enabled)`（默认 OFF）调 `apply_band_haircut`。

### 5.2 接入方案（两种，互斥可切换）

**方案 A — expected final payout（期望版）**：
```
SP_used = current_SP × (1 + E[ratio−1 | X]) = E(final_SP | X)
edge = p × SP_used × 0.65 − 1
```
即把 `apply_band_haircut` 的桶级 `band_bias` 升级为 M1/M2 的条件期望。`apply_band_haircut` 的签名（`sp × (1 + band_bias[band(sp)])`）天然兼容——把 `band_bias` 从全局 map 换成 per-leg 预测即可，**不改下游 sizing**。

**方案 B — conservative quantile（保守版，推荐）**：
```
SP_used = Q_τ(final_SP | X)        # τ=0.25，M2 输出
edge = p × SP_used × 0.65 − 1
```
用**条件低分位**代替期望，对长尾砍价更稳健——宁可低估赔付、放弃边缘腿，也不让被高估的 longshot 进串关。对串关的乘法放大效应，保守分位提供安全边际。

### 5.3 接入点（不改本文，仅记录给实现 spec）

- 计算入口：`generate_plan` 中 `maybe_haircut_snapshots` 调用处（services.py L567 一带）。
- 替换内核：`apply_band_haircut` 的 `band_bias` 由静态 `HAIRCUT_MAP` → 改为 per-leg `E(final_SP)` 或 `Q_τ`。
- **结算真值不变**：replay/真盘仍按 `settlements.winning_sp` 结算（`actuals_from_db`）——这保证「决策用预测 SP、结算用真实 SP」的 invariant 不被破坏。

### 5.4 break-even 锚（评估时对照）

`q = p × SP`，`RETURN_RATE = 0.65`。各 N 的单腿 break-even q：**N2≈1.240, N3≈1.154, N4≈1.114, N5≈1.090**。接入 final_SP 后，应检验「按预测 SP 重算的 EV」是否把不达 break-even 的 longshot 正确剔出。

---

## 6. 购买策略（本文只给信号，调度归临场文档）

本文产出三类**腿级信号**，供 `inplay_sp_timing_filter.md` 做买/等/弃调度：

| 信号 | 由本文模型给出 | 临场文档据此动作 |
|------|---------------|-----------------|
| **提前买** | `E[ratio] ≥ 0`（如 `<3.5` 桶 +0.33，预期上漂）且分位稳定 | 可在 bucket 早期锁定 |
| **等临场** | `E[ratio] < 0` 但绝对值小 + slope 未收敛 | 推迟到 MTK 更小的快照再决策（漂移随 MTK 缩小而收敛）|
| **直接跳过** | 下修概率 `P(ratio<0.98)` 高 **或** tail `P(ratio<0.5)` 非零 **或** 保守分位下 `edge < 0` | 该腿弃选，不进候选池 |

> 边界：本文**不**实现 bucket 分批、降 N、降 stake、空仓——那些是临场文档的调度逻辑。本文只回答「这一腿的 final_SP 会怎样、保守 EV 是多少」。

---

## 7. 评估设计

### 7.1 必须避免幸存者偏差（重点）

现有 `sp_drift_stats` / 实盘 −16.5% 只看**命中腿**（winning legs），有**幸存者偏差**：命中腿往往是被市场买热（下修）的腿，故漂移偏负被放大。

**本文规定：所有漂移估计在全部腿上做**，用 `attach_final_and_settlement` 收齐每个 `(match, selection)` 的 `decision_sp → final_sp`（无论命中），而非只看 `is_winner`。

`drift_stats.winners_vs_all_bias(legs)` 已现成给出该 gap：返回 `all_bias / winners_bias / bias_gap`。**评估报告必须同时列 all-legs 与 winners-only，并报告 `bias_gap`**，以量化幸存者偏差幅度，确认模型是在无偏的全样本上训练/评估。

### 7.2 评估指标

| 指标 | 定义 | 工具 |
|------|------|------|
| **SP 预测误差** | `E|predicted_final − actual_final|`、按桶的 RMSE / MAE on `ratio` | 新（M1/M2 残差）|
| **分位校准** | 实际落入 `Q_τ` 以下的频率 ≈ τ（pinball / coverage）| 新（M2）|
| **haircut 后 EV 校准** | 用预测 SP 重算 edge 后，realized ROI 是否与预测 EV 对齐（reliability）| `replay_policy` |
| **按 MTK 的真实 ROI** | `drift_by_mtk_bucket` + `replay_policy` 在不同 `mtk_target` 的 OOS ROI | 现成 |
| **全腿 vs 命中腿 bias gap** | §7.1 | `winners_vs_all_bias` |

### 7.3 回测框架（复用 forward-test 纪律）

复用 `src/sp_drift/forward.py` 的 OOS 机制，遵从 `walk_forward_strategy_evaluation.md`：

- **OOS 切片**：`forward_panel(panel, FORWARD_START="2026-06-13")`，只评 kickoff 在此之后的腿（lexicographic 比较，naive 北京时间）。
- **invariant**：`replay_policy` 在决策 MTK 上用预测 SP qualify/size，用 `winning_sp` 结算——**决策用预测、结算用真值**。
- **多 arm 对照**（沿用 `build_arms` 形态，新增本文 arm）：
  - C0：control，当前 SP，无 haircut（现状）；
  - C1：window-only（`WINDOW_MTK=180`）；
  - C2：window + 冻结 `HAIRCUT_MAP`（M0 基线）；
  - **C3（本文新增）**：M1/M2 预测 `E(final_SP)` 或 `Q_τ` 接入。
- **幂等 ledger**：`append_ledger` 按 `run_date` 去重；systemd 周计时器 `beidanlot-sp-forward.timer` 已在跑。
- **预注册停止规则**：`check_stopping_rule`，`MIN_COMBOS=200` / `MAX_WEEKS=12` / `MAXDD_STOP=0.50` / `MARGIN=0.05`。

### 7.4 上线阈值（GATE，预注册冻结）

C3 升为生产默认须**同时**满足：

1. **SP 预测优于 M0**：C3 的 ratio MAE 显著低于 M0 桶级常数（OOS）。
2. **EV 校准过关**：预测 EV 与 realized ROI 的 reliability 斜率落在 [0.8, 1.2]，无系统高估。
3. **OOS ROI 边际**：`roi(C3) > 0` 且 `roi(C3) − roi(C0) ≥ MARGIN(0.05)`（沿用 GATE-FT verdict 逻辑）。
4. **风险闸**：`max_dd(C3) ≤ MAXDD_STOP(0.50)`。
5. **无偏性**：训练/评估用全部腿（§7.1），并报告 `bias_gap`。
6. **样本量**：`n_combos ≥ MIN_COMBOS(200)` 或 `weeks ≥ MAX_WEEKS(12)` 才裁决。

满足→把 `haircut_enabled` 切到「M-prediction」模式（替换 `apply_band_haircut` 内核，§5.3）；不满足→保持 C0/M0，继续 OOS 累积。

---

## 8. 实施路线（给后续 writing-plans，本文不写代码）

| 阶段 | 内容 | 依赖 |
|------|------|------|
| P0 | 在 `attach_final_and_settlement` 之上构建**全腿** drift 训练集（含 `eu_deviation`、slope、mtk）| 现有 panel |
| P1 | M1 多维分桶 + Bayesian shrinkage，OOS 对 M0 | P0 |
| P2 | M2 quantile regression（`Q_0.25`），分位校准 | P0 |
| P3 | C3 arm 接入 `replay_policy` / forward ledger，跑 OOS | P1/P2、forward.py |
| P4 | GATE 裁决（§7.4）→ 决定是否切 `haircut_enabled` 预测模式 | P3 |
| v2 | collector 打通 `vol_pct`/`pool_total` 后，加资金占比/砍价热度特征 + M3 树 | collector |

---

## 9. 风险与开放问题

- **样本薄**：`settlements` 1,891 行，多维分桶易过拟合——M1 shrinkage 是兜底，M3 树暂缓。
- **`vol_pct`/`pool_total` 全 NULL**：资金流维度整层缺失，砍价风险只能等 v2，当前用 `eu_deviation` 做替代锚。
- **欧赔去水因子**：overround 归一方法需定标（按主和客三向还是双向）；`avg_eu` 95.24% 覆盖，缺失腿需回退到桶级 M0。
- **漂移非平稳**：`HAIRCUT_MAP` 是历史冻结值，市场结构若变（如北单返奖率调整），需重估——但 OOS 测试期内**不得**重估（预注册纪律）。
- **保守分位 vs 期望的取舍**：方案 B 更稳但可能过度保守饿死候选池——交给临场文档在调度层平衡。
