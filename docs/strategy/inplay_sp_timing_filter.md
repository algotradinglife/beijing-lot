# 临场 SP / 资金流择时过滤 — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban `t_d597b4ef`）
**状态**: 设计稿（不含实现代码；仅本文档，不改其他文件）
**关联**:
- 代码：`src/webui/services.py`（`kickoff_bucket_label` / `assign_kickoff_buckets` / `generate_bucketed_plans` / `maybe_haircut_snapshots` / `q_buckets` / `select_downweight_leagues` / `passes_concentration_guard` / `select_current_issue`）、`src/sp_drift/panel.py`（`minutes_to_kickoff` / `build_snapshot_panel` / `decision_view`）、`src/sp_drift/replay.py`（`replay_policy` / `Policy` / `apply_band_haircut`）、`src/sp_drift/forward.py`（`HAIRCUT_MAP` / `WINDOW_MTK` / `run_forward`）
- 数据：`data/beidan_live.db`（`snapshots` / `matches` / `settlements`）
- 既有研究：`docs/research/sp_drift_phase0.md`、`sp_drift_phase1.md`、`sp_drift_phase4.md`、`sp_drift_forward.md`、`docs/superpowers/specs/2026-06-11-sp-drift-optimization-design.md`、`2026-06-13-sp-drift-forward-test-design.md`
- 姊妹文档（计划中，本文为其前置）：`regime_timing_strategy.md`、`low_mid_sp_high_n_experiment.md`、`single_match_probability_calibration.md`、`walk_forward_strategy_evaluation.md`

---

## 1. 背景与动机

北单 SP 随资金流实时变化。当前实盘 autoplan 用**全 7 天窗口**（`kickoff_window_hours=0`，即不按"距开赛多久"过滤），其结果是**承受不利 SP 漂移**：命中腿的计划 SP（决策时观测）平均 **4.05**，结算 SP（真实赔付）平均 **3.36**，即 **−16.6%** 的不利漂移；整体 q≈0.838。Phase 1 分析（2026-06-14）把这 −16.5% 归因为两部分：**band-selection**（我们偏好的高赔档本身系统性下修）+ **early-decision**（决策太早，离开赛还有十几小时，SP 尚未收敛）。`vol_pct` 维度（成交占比）被验证为 dead（无预测力）。

朴素的"收紧窗口"方案已被否决（见 §2）。本文档不再纠结单一全局窗口值，而是设计一套**临场择时过滤 + 按 kickoff bucket 分批执行**的机制，回答三件事：

> **什么时候买、什么时候等、什么时候放弃。**

核心张力：
- **太早买** → 吃 early-decision 漂移；
- **太临场买** → 单一 bucket 候选池不足（autoplan 饿死，达不到 N 腿 / 并发场次 / 多样性约束）。

设计目标是在这条张力曲线上，用**每张票各自的临场状态**（而非全局开关）来分别决定买 / 等 / 弃，并在候选不足时优雅降级（降 N、降 stake、空仓），而非整盘放弃或硬扛漂移。

## 2. 关键已知结论（必须纳入，避免重复踩坑）

- **`kickoff_window_hours` 是同时性过滤，不是择时**：实盘该参数语义为"只纳入距现在 N 小时内开赛的比赛"。要凑齐一个全局 plan 需 **≥30 场同时在池**；N=4 时窗口太紧 → 在池场次不足 → **autoplan 饿死**；N 放大到能凑够场次时 → 窗口太松 → **漂移不降**。**没有任何单一窗口值能两全**，故 2026-06-13 试过 3h 后于 P1（2026-06-14）改回 0。
- **kickoff bucket 分批是绕过此约束的正确方向**：`generate_bucketed_plans` 已实现"按 kickoff 把当期切成若干 bucket，每 bucket 独立出一个 issue+bucket 小计划"。这样**每个 bucket 自己临近开赛时才决策**，不要求全期同时在池——但代价是**单 bucket 候选更少**，故必须**结合降 N / 降 stake / 空仓**才不会再次饿死。
- **haircut 已实现但默认关**：`maybe_haircut_snapshots`（`haircut_enabled` config 门控，默认 0）在 EV/Kelly sizing 前把每腿 SP 按冻结的 GATE-1 band map 向期望结算值收缩（长赔档缩水 → 减小/归零 stake）。其上线由 forward-test（GATE-FT）裁决，**本设计复用它，不重造**。
- **forward-test 框架已就位**：`src/sp_drift/forward.py` 的 C0/C1/C2 三 arm（C1/C2 用 180min=3h 的 MTK 代理窗口，C2 叠加冻结 `HAIRCUT_MAP`），`replay_policy` 在不同 MTK 上做 simulated decision、用真实 `winning_sp` 结算——**正是本设计的实验工具**。GATE 3 方向性 Go 的 OOS forward-test 周计时器在跑。

## 3. 数据源现状（务必先确认，部分字段缺失）

实测 `data/beidan_live.db / snapshots`（794,518 行）字段可用性：

| 字段 | 含义 | 可用性 | 用途 |
|------|------|--------|------|
| `snapshot_ts` | 快照 UTC 时间（尾 `Z`） | ✅ 全量 | 算 MTK；面板须保留 MTK>0（collector 开赛后仍在 poll → 冻结 SP，须剔除） |
| `kickoff_ts`（in `matches`） | 开赛北京时间（UTC+8，无 tz 后缀） | ✅ | bucket 标签、MTK |
| `sp_3 / sp_1 / sp_0` | 北单 SP（胜/平/负） | ✅ | 决策 SP、drift |
| `eu_h / eu_d / eu_a` | 欧赔（主/平/客） | ✅ 794,510/794,518≈100% | **北单 SP vs 欧赔偏离** 特征 |
| `vol_pct_3/1/0` | 成交占比 | ⚠️ **全 NULL（0 行非空）** | 成交占比/资金集中度——**当前无数据源，特征不可用，需先打通采集** |
| `pool_total` | 资金池总量 | ⚠️ **全 NULL** | 资金集中度——同上，缺失 |
| `result_code / winning_sp`（in `settlements`） | 结算结果 / 真实赔付 SP | ✅ | replay 结算真值 |

> **关键结论（必须在落地前解决）**：`vol_pct` / `pool_total` 列虽存在但**实盘采集全为 NULL**。因此所有依赖"成交占比 / 资金集中度 / 资金过热"的特征与触发规则，**当前没有真实数据支撑**，必须标注为 **待确认数据源**：要么先在 collector 打通这两列的采集，要么在 v1 用**欧赔偏离 + SP 自身漂移速度**作为"资金流"的代理。`vol_pct` 此前还被 Phase 1 验为预测力 dead，故即便补齐采集也需重新验证其增益。
>
> 本设计据此分层：**v1 只用已验证可得的字段**（SP 漂移 + 欧赔偏离 + kickoff bucket）；资金流类特征列为 **v2（数据就绪后）**。

## 4. 特征（择时信号）

对当期每个候选腿 `(match, selection)`，在某决策 MTK 上计算下列特征。可得性按 §3 分层标注。

### 4.1 SP 漂移类（v1，已可得）
- **开盘→当前 SP 变化**：`sp_now / sp_open − 1`。`sp_open` = 该 (match,selection) 最大 MTK 的快照 SP（开盘代理）；`sp_now` = `decision_view(panel, mtk_target)` 选出的决策快照 SP。
- **近 1h / 3h / 6h 滚动漂移**：`sp(mtk) / sp(mtk+60) − 1` 等三档；衡量"近端 SP 还在不在动 / 往哪动"。下修加速 = 危险信号。
- **漂移速度 / 加速度**：相邻快照 SP 变化率，判定 SP 是否已**收敛**（速度趋 0 → 可买）还是仍在快速下修（→ 等或弃）。

### 4.2 北单 SP vs 欧赔偏离（v1，已可得）
- 把欧赔 `(eu_h, eu_d, eu_a)` 去 vig 归一为隐含概率 `p_eu`，对应北单 SP 的隐含概率 `p_sp = RETURN_RATE / sp`（`RETURN_RATE` 复用 services 常量）。
- **偏离** `dev = p_sp − p_eu`（或 `sp / (RETURN_RATE/p_eu) − 1`）。北单 SP 显著高于欧赔隐含（dev<0，赔率虚高）→ 大概率会向欧赔收敛、临场下修 → 这是 −16.6% 漂移的**前瞻预警**，是 v1 最有价值的资金流代理。

### 4.3 资金流 / 集中度（v2，数据待打通）
- **成交占比** `vol_pct_sel`、**资金集中度**（某选项占该场资金的比例 / 全场 `pool_total`）、**资金过热**（短时成交占比骤升）。
- **状态**：`vol_pct` / `pool_total` 实盘全 NULL（§3），**当前不可用**。列为 v2，待 collector 补齐采集且重验预测力后启用。

### 4.4 时点 / 画像类（v1，已可得）
- **kickoff bucket**：`kickoff_bucket_label(kickoff_ts, bucket_hours)`，复用既有实现，作为分批调度键，也作为 drift 画像的分组维度（不同时段漂移规律可能不同）。
- **MTK**：`minutes_to_kickoff(snapshot_ts, kickoff_ts)`，决策时点。
- **联赛 / 选项 drift 画像**：复用 `panel` 的 `league_bucket` / `hcp_class` / `comp_type` 与 `selection`，统计各组的历史平均不利漂移（对接 `q_buckets` / `select_downweight_leagues` 的口径），作为先验。某联赛/某选项历史 drift 大 → 该腿先验降权。

## 5. 临场过滤触发规则（买 / 等 / 弃）

对每个候选腿，在其所属 bucket 的决策时点求一个 **drift-haircut 后的 SP**（复用 `apply_band_haircut`），再叠加下列**临场 gate**。规则输出三态：**BUY（纳入并按 haircut 后 SP 定 EV/size）/ WAIT（本轮跳过，留到该 bucket 更临近开赛的下一轮重评）/ SKIP（本期放弃该腿）**。

| 触发条件 | 信号（§4） | 动作 | 理由 |
|----------|-----------|------|------|
| **SP 下修中 / 未收敛** | 近 1h 漂移 < 0 且漂移速度未趋 0 | **WAIT** | SP 还在跌，早买必吃漂移；等收敛或等更临场 |
| **SP 已收敛** | 近 1h 漂移速度 ≈ 0 | **BUY**（按 haircut 后 SP） | 漂移风险已释放，可锁价 |
| **欧赔偏离过大（虚高）** | `dev < −阈值`（北单 SP 远高于欧赔隐含） | **降权 / SKIP** | 该腿大概率向欧赔下修；haircut 已缩，偏离仍过大则直接弃 |
| **资金过热**（v2） | 成交占比短时骤升 / 集中度过高 | **降权 / WAIT** | 热钱推高赔率不可持续；数据就绪前不启用 |
| **候选腿 q 恶化** | `select_downweight_leagues` 命中（live q<阈值 且 n 足） | **该联赛/选项 SKIP（临时黑名单）** | 复用既有 live-q 监控，实测劣化即停 |
| **临场流动性不足** | 该 bucket 决策时点 BUY 腿数 < `MIN_QUALIFIED_LEGS` | **降级（见 §7）** | 候选池薄 → 降 N / 降 stake / 空仓，而非硬凑 |
| **集中度护栏** | `passes_concentration_guard` 不过 | **SKIP 该 plan / 降 stake** | 复用既有多样性护栏，避免过度押单一腿 |

> **与既有 haircut 的关系**：haircut（`maybe_haircut_snapshots`）是**连续的价格修正**（按 band 把 SP 向期望结算值缩，进 EV/Kelly），本节 gate 是**离散的时点决策**（买/等/弃）。二者叠加：先 haircut 修价、再 gate 决定是否纳入及何时纳入。haircut 仍受 `haircut_enabled` 门控、由 GATE-FT 裁决；本设计不改其门控逻辑。

### 5.1 主策略的 SP 稳定性优先原则

新增一条资金分层原则：**主策略不追最高名义 SP，而优先选择温和、可解释、预期不剧烈漂移的 SP；高 SP / 高漂移腿只进入小资金尾仓或观察池。**

理由：

- 串关收益按腿相乘，单腿 SP 下修会被 N 放大；主仓承受高漂移腿，相当于在出票前就放大负滑点。
- Phase 1 已显示 SP 档位漂移强烈分层：`<3.5` 平均上漂，`3.5-4.5` 小幅下修，`4.5-5` 下修明显，`5-8` 与 `>8` 是主漂移雷区。
- 主策略的目标应是降低死票与极端回撤，冷门右尾收益交给尾仓；二者不要混在同一个 eligibility 规则里。

落地上给每条候选腿增加一个 `sp_stability_score`，只用于决定这条腿是否能进入**主策略池**，不替代 `p/confidence/q`：

```text
sp_stability_score =
  f(
    sp_band,
    predicted_final_sp_ratio,      # E(final_SP/current_SP) 或 Q0.25(final_SP/current_SP)
    residual_drift_bucket,
    recent_slope_1h_3h,
    eu_deviation,
    tail_downshift_risk
  )
```

建议分层：

| 层级 | 条件口径 | 用途 |
|------|----------|------|
| **主仓 core** | 温和 SP；预测 final_SP ratio 接近 1 或上漂；近 1h/3h 斜率收敛；欧赔偏离不大；tail 下修风险低 | 允许进入主策略组合，confidence 决定覆盖深度 |
| **主仓 watch** | q/confidence 好，但 SP 稳定性一般；预测轻微下修或尚未收敛 | WAIT 或降 stake，临近重评 |
| **尾仓 only** | 高 SP / 高 residual drift / 高 tail 下修风险，但赛果模型有冷门信号 | 只允许小资金冷门尾仓，且避免与主策略同腿重叠 |
| **skip** | 保守 final_SP 后 edge≤0，或欧赔偏离/下修概率过大 | 不买 |

这会把原先一个混合问题拆开：

- `confidence`：决定多注下注时的覆盖深度；
- `q` / `edge_after_final_sp`：决定是否值得下注；
- `sp_stability_score`：决定进入主仓、等待、尾仓，还是跳过。

后续评估口径：在 `replay_policy` / bucket 回测里新增一个 arm，比较「原主策略」vs「主策略只收 stable SP 腿」vs「stable 主策略 + cold tail」的 ROI、profit、MaxDD、死票率；结算仍必须用真实 `winning_sp`，不能用 `final` 快照代替。

## 6. 分批执行（bucket 调度方案）

直接在 `generate_bucketed_plans` 之上设计调度，**不重写它**。

- **分批键**：`kickoff_bucket_label(kickoff_ts, bucket_hours)`。`bucket_hours` 为调度参数（候选）：小 bucket → 更临场、漂移更小，但每批候选更少；大 bucket → 反之。需在 §9 实验里扫描确定。
- **每 bucket 一个小计划**：`generate_bucketed_plans` 已实现"当期 → 按 bucket 切 → 每 bucket 复用 `generate_plan`（继承单 issue pin、anti-double-bet、集中度护栏、stake 逻辑）→ 出 issue+bucket plan id"。本设计在每 bucket 内部接入 §5 的临场 gate 与 §7 的降级。
- **滚动重评（解决 WAIT）**：一个 bucket 不是一次性决策。随时间推进，到该 bucket 临近开赛的"决策窗"时再跑一轮：上一轮 WAIT 的腿在新 SP 上重评，可能转 BUY 或 SKIP。这样**避免单一全局 plan 一次性覆盖整期**——每个 bucket 在它自己合适的临场时点各自成交。
- **决策时点选择**：每个 bucket 的决策 MTK 取该 bucket 内比赛"临近但仍有足够候选"的点（与 §9 的 MTK 实验联动确定）。collector 开赛后仍 poll，故面板与决策一律只用 MTK>0 的快照（`build_snapshot_panel` 已强制）。

## 7. 与 high-N 策略结合（候选不足时的降级阶梯）

单 bucket 候选天然比全期少，§2 已警示"仍受单 bucket 候选不足限制 → 需结合降 N"。降级阶梯（按 bucket 内 BUY 腿数 `k` 决定）：

1. **k ≥ N_target**：正常出 N=N_target（默认 4）的组合，正常 stake。
2. **MIN_QUALIFIED_LEGS ≤ k < N_target**：**降 N** 到 `k`（或预设下限，如 3），并**降 stake**（按 N 缩水程度缩 per-combo cap，组合更短、命中概率结构变化，需相应降注），保持集中度护栏。
3. **k < MIN_QUALIFIED_LEGS**：**空仓**该 bucket（不强凑），把资金留给同期更健康的 bucket 或后续 issue。

与 high-N 的接口：N_target、stake cap（`PER_COMBO_STAKE_CAP_FRAC` / `WEEKLY_STAKE_CAP_FRAC`）均复用 services 现有常量与 `generate_plan` 的 stake 逻辑；降级只是按 bucket 的 BUY 腿数动态下调 N 与 cap，不新增并行 sizing 路径。空仓 bucket 不消耗周 stake cap，使资金自然向候选充足的 bucket 集中。

## 8. 数据表 / 字段（用于 UI / 周报 / 审计）

每张已成交票（或每个 bucket 决策记录）落一行决策审计，字段：

| 字段 | 来源 | 说明 |
|------|------|------|
| `plan_id` / `bucket_label` | `generate_bucketed_plans` 的 issue+bucket id | 定位批次 |
| `match_id` / `selection` / `league` | snapshot / plan leg | 腿标识 |
| `decision_ts`（UTC） / `mtk` | `minutes_to_kickoff` | **购买时点 + MTK** |
| `sp_open` / `sp_decision` | panel（开盘代理 / 决策快照） | 漂移基准 |
| `drift_1h / 3h / 6h` | §4.1 | 近端漂移 |
| `eu_implied_p` / `sp_implied_p` / `dev` | §4.2 | 欧赔偏离 |
| `vol_pct` / `concentration`（v2） | §4.3 | 资金流（待数据） |
| `q_before` / `q_after_haircut` | `apply_band_haircut` 前后 | **haircut 前后 q** |
| `sp_haircut` | haircut 后决策 SP | 进 EV 的价 |
| `gate_action` | §5 | BUY / WAIT / SKIP + reason |
| `winning_sp`（结算后回填） / `hit` | `settlements` | 真实赔付，算实现 drift = `winning_sp/sp_decision−1` |

## 9. 实验设计（回测 / forward 验证）

复用既有工具，**先纸面，后真钱小额**。

### 9.1 同一候选 × 不同 MTK 的 simulated decision（核心实验）
- 工具：`replay_policy(panel, live_db, niche_config, Policy(mtk_target=...))`。
- 做法：对同一 OOS 候选池，扫 `mtk_target ∈ {18h(baseline), 360, 180, 90, 45, ...}`，每点跑两版：**haircut 前**（`haircut=None`）与 **haircut 后**（`HAIRCUT_MAP`）。
- 比较：**drift-haircut 后的 ROI**（结算用真实 `winning_sp`，所以"决策太早→赔付缩水"会真实计入 PnL）。产出 ROI–MTK 曲线，定位"漂移已大幅释放、候选尚未饿死"的甜区 MTK，反哺 §6 的决策时点与 §6 的 `bucket_hours`。
- 注意：这是 `decision_view` / `replay` 既有路径，**不需要新建实验代码**，只需扫参数。

### 9.2 bucket 调度回测
- 在 OOS 面板上模拟 §6+§7：按候选 `bucket_hours` 分批、每 bucket 按 §5 gate + §7 降级出计划，滚动重评，逐 issue 滚 bankroll。对比"全局单 plan（现状）" vs "bucketed + 临场 gate"的 ROI / MaxDD / 周成交腿数（验证是否饿死）。

### 9.3 Forward 验证（对接 GATE-FT）
- 复用 `src/sp_drift/forward.py` 框架与已跑的周计时器：C0（baseline，~18h，无 haircut）/ C1（3h 窗口）/ C2（3h+haircut）。本设计的 bucket+gate 变体作为**新 arm（如 C3）** 加入同一 ledger，遵循已冻结的预注册口径（`FORWARD_START=2026-06-13`、冻结 `HAIRCUT_MAP`、≥200 组合或 ≥12 周停止、MaxDD>50% 止损、C? 对 C0 ≥+5pp margin 判 Go）。
- **数据缺口前置**：v2 资金流特征要进 forward arm，**必须先打通 `vol_pct`/`pool_total` 采集并重验预测力**，否则该 arm 不可信，维持 v1（SP 漂移 + 欧赔偏离）口径。

## 10. UI / 周报展示

- **每张票一行**（数据源即 §8 表）：购买时点（`decision_ts` 本地化）、**MTK**、**SP drift**（`sp_decision→winning_sp` 实现漂移 %，结算后回填）、**haircut 前后 q**（`q_before` / `q_after_haircut`）、`gate_action`。
- **bucket 视图**：每 issue 下按 bucket 列出（决策 MTK、BUY/WAIT/SKIP 腿数、是否触发降 N / 空仓），让"哪个时段批次饿死 / 漂移大"一目了然。
- **drift 画像**：对接 `q_buckets`（by_league / by_option）展示各组实现 q 与平均不利漂移，标红被 `select_downweight_leagues` 黑名单的联赛/选项。
- **周报衔接**：与 `docs/research/sp_drift_forward.md` 的 forward ledger / 权益图同框，新增"临场 gate 命中分布"与"降级触发次数"两张小图。

## 11. 与既有机制的衔接小结（避免重复造轮子）

| 需求 | 复用的既有实现 | 本设计新增的"设计"（非代码） |
|------|----------------|------------------------------|
| 分批 | `generate_bucketed_plans` / `assign_kickoff_buckets` / `kickoff_bucket_label` | bucket 内临场 gate + 滚动重评调度 + `bucket_hours` 选参 |
| 价格修正 | `maybe_haircut_snapshots` / `apply_band_haircut`（`haircut_enabled` 门控） | 在 haircut 后叠加买/等/弃离散 gate |
| 候选不足 | `passes_concentration_guard` / `generate_plan` stake 逻辑 / `MIN_QUALIFIED_LEGS` | 按 bucket BUY 腿数的降 N / 降 stake / 空仓阶梯（§7） |
| 劣化止损 | `q_buckets` / `select_downweight_leagues` | 接入临场 gate 作为 SKIP 触发 |
| MTK 决策 | `panel.decision_view` / `minutes_to_kickoff` | 决策时点选参、面板 MTK>0 约束沿用 |
| 实验 | `replay_policy(Policy(mtk_target,haircut))` / `forward.py` C0/C1/C2 | MTK 扫描甜区、bucket arm（C3）接入同一 GATE-FT ledger |

## 12. 开放问题 / 风险

1. **`vol_pct` / `pool_total` 全 NULL**（§3）——资金流特征当前无数据，v1 必须靠欧赔偏离代理；v2 须先补采集。这是最大缺口。
2. **单 bucket 饿死**仍是结构风险——降 N 到 3、空仓多 bucket 是否会让整期成交量过低、统计功效不足，需 §9.2 量化。
3. **欧赔偏离的有效性未验**——`dev` 作为漂移前瞻预警是合理假设，但需在 OOS 上验证其与实现漂移的相关性（可作为 `single_match_probability_calibration.md` 的输入）。
4. **滚动重评的实现成本**——每 bucket 多轮决策需调度器支持多次触发同一 issue+bucket，需确认与 anti-double-bet（同腿不重复下注）兼容。
5. **haircut 仍未过 GATE-FT**——本设计依赖 haircut 但其上线未定；v1 可在 `haircut_enabled=0` 下仅用 §5 离散 gate（买/等/弃）先行，待 GATE-FT 通过再叠加连续修价。
