# 单场概率预测与校准层 — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban t_6b5ba80f）
**状态**: 设计稿，待评审 → 转 writing-plans
**关联**:
- 现有代码：`src/phase5a/filter.py`（`NicheConfig` / `p_hat_train` 现状）、`src/phase5a/planner.py`、`src/combo_optimizer/types.py`（`Candidate`、`RETURN_RATE=0.65`）、`src/webui/services.py`（`q_buckets` / `_q_stat` / `collect_settled_legs` / `compute_q_drift`）、`src/sp_drift/`（`forward.py` 的 `HAIRCUT_MAP`、`replay.py` 的 `winning_sp` 结算真值）
- 数据：`data/beidan_live.db`（`snapshots`：北单 SP + 欧赔 `eu_h/eu_d/eu_a`；`settlements`：`result_code` / `winning_sp` / 结算均欧赔 `avg_eu_h/avg_eu_d/avg_eu_a`）
- 姊妹文档：`regime_timing_strategy.md`、`low_mid_sp_high_n_experiment.md`、`inplay_sp_timing_filter.md`、`walk_forward_strategy_evaluation.md`（均为本目录下规划中的姊妹设计稿）

---

## 1. 背景与动机

当前每条候选腿的概率 `p_hat` 来自 `NicheConfig` 的 **niche 规则匹配**（`src/phase5a/filter.py`）：按 `(option, sp_band, league_tier, handicap_class, comp_type)` 命中第一条规则，取其静态 `p_hat_train` 作为先验。这套 `p_hat` 有三个结构性问题：

1. **静态**：`p_hat_train` 是离线训练快照，不随单场强弱、欧赔、近期表现变化；同一 niche 桶内所有比赛共享一个数字。
2. **乐观**：近期实盘对真实命中率和 SP 漂移过度乐观。命中腿计划 SP 4.05 → 结算 3.36（**−16.6%**）；`compute_q_drift` 的实盘整体 **q≈0.838（负 EV）**。`p_hat` 偏高直接抬高了 `edge = p_hat × SP × 0.65 − 1`，让本应被否的腿进了池子。
3. **不分层校准**：niche 桶粗，没有「小样本回归到市场概率」的机制，也没有按联赛/选项/SP 桶的事后校准回路。

**关键经济学事实（必须贯穿全文）**：目标是**提升 `p_final` 质量以服务 EV，而非追表面命中率**。

- `q = p × SP`，北单 `RETURN_RATE = 0.65`。
- break-even q：**N2≈1.240, N3≈1.154, N4≈1.114, N5≈1.090**（腿数越多，单腿 break-even q 越低，因为联合 EV 摊到每腿）。
- 买低 SP 热门能**提高命中率**，但同时**压低 q**（SP 小）和**长期收益**。一个把所有概率往「安全热门」推的模型会让命中率好看、却让 EV 变负。因此评估**只看 hit rate 是错的**，必须看**按 q 桶 / SP 桶的 realized ROI**。

**本设计的范围**：在现有 niche `p_hat_train` 之上，叠加一个**市场概率底座 + 轻量模型 + 分层校准 + 融合**的概率层，产出校准后的 `p_final` 与对应 `q_final`，接进 planner 的 EV 与 sizing。

**非目标（YAGNI）**：
- 不做深度学习 / xG 级别的进球模型；MVP 用 Elo/SPI 量级的轻量特征。
- 不在本稿写实现代码、不改任何现有文件；只产出设计。
- 不引入实盘真钱 A/B；上线门槛走 walk-forward + 纸面 forward-test（见 §9，复用 `src/sp_drift/forward.py` 的预注册门槛范式）。

---

## 2. 数据源（已盘点 DB，标注可用性）

| 数据 | 来源 | 可用性 | 备注 |
|------|------|--------|------|
| 北单 SP（计划时） | `snapshots.sp_3/sp_1/sp_0` | ✅ 已有 | 决策快照；随时间漂移 |
| 北单成交量占比 | `snapshots.vol_pct_3/1/0` | ✅ 已有 | SP-drift 研究结论：**vol% 作为漂移信号已判 dead**，本层不作为校准特征（可留作诊断） |
| 池规模 | `snapshots.pool_total` | ✅ 已有 | 可作市场流动性/置信度权重 |
| **欧赔（计划时）** | `snapshots.eu_h/eu_d/eu_a` | ✅ **已有，覆盖 99.9%**（794510/794518 行） | **本设计据此构造 `p_market` 底座**；此前文档标注「待确认」——经本次盘点确认已落库 |
| 北单结算 SP（真值） | `settlements.winning_sp` | ✅ 已有 | 校准/评估的 realized SP；`src/sp_drift/replay.py` 已用 |
| 比赛结果 | `settlements.result_code`（3/1/0）、`fthg/ftag` | ✅ 已有 | 校准标签（命中真值） |
| **结算均欧赔** | `settlements.avg_eu_h/avg_eu_d/avg_eu_a` | ✅ **已有，覆盖 95%**（1792/1879 行） | 收盘欧赔，可作 `p_market` 的收盘版与漂移特征 |
| 让球线 | `LiveSnapshot.handicap_line`（经 `classify_handicap`） | ✅ 已有 | `h0/h1/h2plus/h_unknown` |
| 联赛 / 杯赛-国际赛 | `classify_league` / `classify_comp_type` | ✅ 已有 | `league_tier` / `cup/league/intl` |
| 赛程密度、休息天数 | ⚠️ **待接入** | ❌ 需新数据源 | 需要球队赛程表（外部源）；MVP 标为可选特征，缺失时退化为不可用 |
| Elo / SPI 评分 | ⚠️ **待接入** | ❌ 需外部/自建 | MVP 可用「欧赔隐含强度」自举一个轻量 Elo（见 §4.1），避免外部依赖 |

**结论**：欧赔与结算真值齐备，足以支撑「市场底座 + 校准」MVP。赛程/休息/外部 Elo 为**第二批可选特征**，不阻塞 MVP。

---

## 3. 市场概率底座（`p_market`）

### 3.1 devig（去抽水）

欧赔 `(eu_h, eu_d, eu_a)` 的隐含概率含 overround（庄家抽水）。原始隐含：

```
r_h = 1/eu_h,  r_d = 1/eu_d,  r_a = 1/eu_a
overround = r_h + r_d + r_a          # >1，越大抽水越重
```

去抽水生成归一概率（MVP 用**比例法 / basic normalization**）：

```
p_market(3) = r_h / overround
p_market(1) = r_d / overround
p_market(0) = r_a / overround
```

- **devig 方法分层**：MVP 用比例法；第二批可加 **Shin** 或 **power/odds-ratio** 法（对长尾更准），按联赛择优（用 §8 的 logloss 评估各法）。
- **北单 SP 也可 devig**：北单是 parimutuel，`1/(SP × 0.65)` 是含 35% rake 的「市场隐含概率」。可生成 `p_beidan_implied(opt) = 1/(SP_opt × 0.65)`，三选项归一。但北单池小、漂移大，**`p_market` 以欧赔为主，北单隐含概率作为对照/一致性检查**（见 §3.3）。

### 3.2 记录的诊断量

每条候选记录：
- `overround_eu`：欧赔抽水（市场效率诊断）。
- `p_market_open` / `p_market_close`：计划时欧赔 vs 结算均欧赔（`avg_eu_*`）的 devig 概率；二者之差是**欧赔漂移**特征。
- `p_beidan_implied`：北单 SP 隐含概率（归一后）。

### 3.3 市场一致性（market consistency）

记录欧赔市场与北单市场的分歧：

```
consistency = 1 - 0.5 * Σ_opt | p_market(opt) - p_beidan_implied(opt) |   # 1=完全一致
```

低一致性（北单 SP 显著偏离欧赔）往往伴随**北单 SP 后续向欧赔回归**——这与 SP-drift 研究方向一致，是融合时**给 `p_market` 加权**的依据。

---

## 4. 轻量模型（`p_model`）— MVP

### 4.1 MVP 特征集（按可用性排序）

**第一批（DB 现成，MVP 必做）**：
1. `p_market(3/1/0)`（计划时 devig 概率）——模型的最强单特征，等于「市场基线 + 残差学习」。
2. 让球线类 `handicap_class`（`h0/h1/h2plus/h_unknown`）。
3. `league_tier`、`comp_type`（`cup/league/intl`）。
4. SP band 与 `option`（沿用 niche 桶维度，保证可与现状对比）。
5. **欧赔漂移**：`p_market_close − p_market_open`（需结算欧赔；训练期可用，实时打分时只有 open，故此特征仅用于**校准/评估**或滞后特征）。
6. **SP 漂移先验**：`HAIRCUT_MAP` 给出的 band 级 `drift_bias`（`src/sp_drift/forward.py`：`{<3.5:+0.33, 3.5-4.5:−0.09, 4.5-5:−0.21, 5-8:−0.36, >8:−0.81}`）。这是**结算 SP 相对计划 SP 的期望偏移**，让模型知道长尾 band 的 SP 会缩水。

**第二批（待接入数据，可选）**：
7. **轻量 Elo / 主客场强度**：用历史 `result_code` 自举一个 Elo（主队 +η 主场修正），或直接用「欧赔隐含强度差」作为代理，避免外部依赖。
8. 攻防进球率（需进球数据 `fthg/ftag` 累积——DB 已有结果，可自建球队滚动进/失球率）。
9. 赛程密度 / 休息天数（需外部赛程表，**待接入**）。

### 4.2 MVP 模型形态

- **形态**：以 `p_market` 为基线的**残差/收缩模型**，不是从零学概率。
  - 起步用**逻辑回归**（label = `result_code` 是否等于该 option，特征如上），或更稳的**分桶查表 + 收缩**（每个 niche 桶用历史命中率，向 `p_market` 收缩，见 §5.1）。逻辑回归与查表二选一由 §8 评估定夺；**MVP 默认查表+收缩**（样本小、可解释、不易过拟合）。
  - 输出三选项原始分数后做 **softmax / 归一**，得到 `p_model(3/1/0)` 且三者和为 1。
- **为什么不直接用 niche `p_hat_train`**：现状 `p_hat_train` 是孤立先验、无市场锚、无收缩。`p_model` 把它升级为「市场基线 + 历史残差 + 收缩」，并保留 niche 桶维度以便平滑迁移。

---

## 5. 校准方法

校准把模型/市场输出的「名义概率」对齐到「真实命中频率」。分三层叠加：

### 5.1 Beta-Binomial 收缩（小样本 → 回归市场概率）

每个分层桶 `b`（见 §5.4）有历史 `n_b` 场、`k_b` 次命中。用 Beta 先验 `Beta(α_b, β_b)`，先验**均值锚定到市场概率** `p_market`：

```
α_b = κ * p_market_bar_b
β_b = κ * (1 - p_market_bar_b)         # κ = 先验强度（伪样本数，超参，按桶/全局调）
p_shrunk_b = (k_b + α_b) / (n_b + α_b + β_b)
```

- `n_b` 小 → `p_shrunk_b ≈ p_market`（**小样本回归到市场概率**，正是验收要求）。
- `n_b` 大 → `p_shrunk_b ≈ 经验命中率`。
- `κ` 控制信任市场 vs 信任经验的速度；MVP 全局 `κ` 起步（如 20–50），后续按联赛分层调。

### 5.2 Isotonic / Platt（单调校准曲线）

在收缩后概率之上，做**保序回归（isotonic regression）**或 **Platt scaling（逻辑回归式 sigmoid 重映射）**，把「预测概率 → 实测命中率」拉成单调对齐：

- **isotonic**：非参、单调、对校准曲线弯折更鲁棒；样本够时首选。
- **Platt**：两参（A、B），小样本更稳；样本薄的联赛/选项用 Platt。
- 选择规则：桶样本 `n ≥ N_iso`（如 200）用 isotonic，否则 Platt；阈值由 §8 评估定。

### 5.3 叠加顺序

```
p_model_raw  --(5.1 Beta 收缩，锚 p_market)-->  p_shrunk
p_shrunk     --(5.2 isotonic/Platt)-->          p_model_cal     # 最终的「模型校准概率」
```

`p_market` 自身也过一遍 isotonic（市场未必完美校准），得 `p_market_cal`。

### 5.4 分层维度（stratified calibration）

校准器**按层独立拟合**，复用现有桶维度，保证与 niche/诊断口径一致：

- **联赛**（`league` / `league_tier`）——`q_buckets().by_league` 已能算 realized hit_rate/q，可直接作校准训练样本。
- **选项**（`option` 3/1/0）——`q_buckets().by_option` 同上；draw（option=1）历史规则缺失，分层后能单独建。
- **SP 桶**（沿用 niche band 与 `HAIRCUT_MAP` 的档位边界 `<3.5 / 3.5-4.5 / 4.5-5 / 5-8 />8`，保证与漂移研究对齐）。

层太细会样本枯竭 → 用**层级回退（hierarchical backoff）**：`(league × option × sp_band)` 不足 `n_min` 时回退到 `(league_tier × option × sp_band)`，再回退到 `(option × sp_band)`，最终回退到 `p_market`。回退本质上由 §5.1 的收缩自然实现（薄桶 → 市场）。

---

## 6. 融合公式（`p_final`）

把三路概率融合为最终单腿概率：

```
p_final(opt) = w_market * p_market_cal(opt)
             + w_model  * p_model_cal(opt)
             + w_recent * p_recent(opt)
```

随后**重新归一**使 `Σ_opt p_final = 1`。

- **`p_recent`**：近期实盘/近窗校准信号——直接复用 `src/webui/services.py` 的 `collect_settled_legs` + `q_buckets`/`_q_stat`，给出按 (league, option) 的近 N 场 realized hit_rate。它是「最近真实命中率」的低延迟估计，用于纠正模型/市场的近期系统性偏差（正是当前「过度乐观」要修的）。薄样本时同样向 `p_market` 收缩。
- **权重动态调整**：`w_*` 按**近期各路自身的预测表现**自适应（inverse-loss weighting）：

```
w_source ∝ 1 / (recent_logloss_source + ε)     # 对 market/model/recent 三路分别在最近窗口算 logloss
然后归一 w_market + w_model + w_recent = 1
```

近期 `p_model` 若 logloss 变差（如 regime 切换），其权重自动让位给 `p_market`。MVP 可先用**固定权重**（如 `0.5/0.35/0.15`）跑通，再开启动态权重（避免一上来就引入不稳定性）。
- **下界保护**：当 `p_recent` 样本 `< n_min` 或某路缺失时，其权重置 0 并把质量重分配给 `p_market`（市场永远在线，作兜底）。

### 6.1 与 SP 漂移的耦合

`q_final` 用的 SP 应是**漂移修正后的期望结算 SP**，而非计划 SP（否则 q 仍乐观）：

```
SP_eff(opt) = SP_plan(opt) + drift_bias(band)        # drift_bias 来自 HAIRCUT_MAP（frozen）
q_final(opt) = p_final(opt) * SP_eff(opt) * RETURN_RATE
```

这与 `src/webui/services.py:maybe_haircut_snapshots` 的 haircut 路径同源（同一 `HAIRCUT_MAP`），保证概率层与 SP 层一致。**注意**：haircut 在实盘仍默认 OFF（GATE-FT 未通过，见 `docs/research/sp_drift_forward.md`）；本层在 `q_final` 内部用 `SP_eff` 评估，是否把 haircut 接进实盘下单仍受 GATE-FT 约束，二者解耦。

---

## 7. 接入现有 planner

### 7.1 候选结构扩展

现有 `Candidate`（`src/combo_optimizer/types.py`）为 frozen dataclass：`match_id, selection, p_hat, sp`，其 `edge = p_hat × SP × 0.65 − 1`。**接入方案（设计层，不改码）**：

- 在 `QualifiedCandidate`（`src/phase5a/filter.py`）上新增携带字段（或在新模块产出一个扩展候选）：
  - `p_market`、`p_model`、`p_recent`、`p_final`、`q_final`、`sp_eff`、`overround_eu`、`market_consistency`。
- **`Candidate.p_hat` 由 `p_final` 喂入**（而非 niche `p_hat_train`）。这样 `edge`、`Combo.ev`、sizing 全部自动改用校准概率，**无需改 combo_optimizer 的数学**——只是换了喂进去的 `p_hat`。
- niche `p_hat_train` 降级为**回退先验**：当概率层因数据缺失无法产出 `p_final` 时，退回 `p_hat_train`（保证不回归、可灰度）。

### 7.2 EV 与 sizing

- `qualify_candidates` 之后插入一个**概率层 transform**：对每条 `QualifiedCandidate` 计算 `p_market/p_model/p_recent → p_final`，并用 `SP_eff` 算 `q_final`；把 `p_final` 写入 `Candidate.p_hat`。
- planner / `build_weekly_plan` / Kelly sizing 全部沿用现有路径（它们读 `p_hat` 与 `sp`），EV 与 stake 自然基于 `p_final`。
- **break-even q 门槛**：腿入池前用 `q_final ≥ break_even_q(N)`（N2≈1.240/N3≈1.154/N4≈1.114/N5≈1.090）做硬过滤，替代/叠加当前的 niche 匹配。这把「只看命中率」改成「按 EV 门槛」，直击当前 q≈0.838 负 EV 的根因。

### 7.3 灰度开关

DB config 增加 `prob_layer_enabled`（默认 OFF），OFF 时完全等价现状（`p_hat = p_hat_train`），ON 时走概率层。与现有 `haircut_enabled` / `mix_enabled` 同范式，可独立灰度与回滚。

---

## 8. 评估指标与脚本接口

**核心原则：不只看 hit rate。** 一个把概率推向低 SP 热门的模型 hit rate 升、q 降、ROI 负——必须用下列指标组合识别。

### 8.1 概率质量（越低越好，hit rate 之外的硬指标）

- **Brier score**：`mean((p_final − y)²)`，`y∈{0,1}`。
- **Logloss**：`−mean(y·log p + (1−y)·log(1−p))`；对过度自信惩罚重。
- **Calibration curve + ECE**（Expected Calibration Error）：把 `p_final` 分箱，比较每箱预测均值 vs 实测命中率；ECE = 加权平均绝对差。**这是「校准好不好」的主指标**。
- 三路分别评（`p_market_cal` / `p_model_cal` / `p_final`），确认融合确有增益、且优于单用市场。

### 8.2 经济价值（最终裁判）

- **按 q 桶的 realized ROI**：把腿按 `q_final` 分桶（如 `<1.0 / 1.0–1.09 / 1.09–1.15 / >1.15`，边界对齐 break-even），各桶算真实 ROI。期望：高 q 桶 ROI 显著为正、低 q 桶为负 → 证明 `q_final` 有排序力。
- **按 SP 桶的 realized ROI**：沿用 `HAIRCUT_MAP` band，看是否仍把钱压在漂移大的长尾（应被压缩）。
- **命中率仅作诊断**，与 ROI 并列展示，绝不单独作为通过条件。

### 8.3 评估脚本接口（设计，待实现）

提议新增 `src/prob_calib/eval.py`（**本稿不实现**），接口草案：

```python
def evaluate_prob_layer(
    panel,                 # 计划时快照面板（含 SP、欧赔），同 sp_drift.replay 的 panel
    live_db_path,          # data/beidan_live.db，取 result_code / winning_sp / avg_eu_*
    calibrators,           # §5 拟合好的分层校准器
    fusion_weights,        # §6 的 w_market/w_model/w_recent（或动态策略）
    *,
    oos_start: str,        # walk-forward 的 OOS 边界（同 forward.py 的 FORWARD_START 范式）
) -> dict:
    """对每条 (match, option) 算 p_market/p_model/p_recent/p_final/q_final 与真值，
    返回 Brier/logloss/ECE + calibration curve 数据 + 按 q桶/SP桶的 realized ROI。
    复用 webui.services.q_buckets/_q_stat 算实测 hit_rate/q。"""
```

- **数据复用**：训练/评估样本直接来自 `collect_settled_legs` + `settlements`（`result_code`/`winning_sp`/`avg_eu_*`），无需新采集。
- **walk-forward**：拟合校准器只用 OOS 边界**之前**的数据，评估在边界**之后**，杜绝信息泄漏（细节见姊妹文档 `walk_forward_strategy_evaluation.md`）。

---

## 9. 模型 MVP、校准流程、上线门槛

### 9.1 MVP 范围（最小可跑）

1. `p_market`：欧赔比例法 devig（§3.1）+ overround/consistency 诊断。
2. `p_model`：**分桶查表 + Beta 收缩锚市场**（§4.2 默认形态），特征用第一批（市场概率 + handicap + tier + comp_type + SP band + option）。
3. 校准：Beta-Binomial 收缩（§5.1）+ isotonic/Platt（§5.2），按 (league_tier × option × sp_band) 分层 + 层级回退。
4. 融合：**固定权重**起步（`0.5/0.35/0.15`），`p_recent` 用 `collect_settled_legs` 近窗 hit_rate。
5. `q_final` 用 `SP_eff`（HAIRCUT_MAP 修正），break-even q 硬门槛。
6. 评估脚本（§8.3）跑出 Brier/logloss/ECE + q桶/SP桶 ROI。
7. planner 接入走灰度开关（§7.3），默认 OFF。

第二批（MVP 通过后）：动态融合权重、Shin devig、自举 Elo/攻防率、赛程密度（待接入数据）。

### 9.2 校准流程（pipeline）

```
settlements + snapshots(欧赔/SP)
   → 构造样本 (collect_settled_legs 风格，含 result_code / winning_sp / avg_eu_*)
   → 按 OOS 边界切 train / test（walk-forward）
   → train 上：拟合分层 Beta 收缩 + isotonic/Platt 校准器
   → test 上：算 p_market/p_model/p_recent → 融合 p_final → q_final
   → evaluate_prob_layer：Brier/logloss/ECE/calibration curve + q桶/SP桶 ROI
   → 产出报告（docs/research/ 下，对齐 sp_drift_forward.md 体例）
```

### 9.3 上线门槛（预注册，事前冻结）

仿 `src/sp_drift/forward.py` 的 GATE-FT 范式，事前固定，避免事后挑数：

- **校准质量门**（OOS 切片）：`p_final` 的 **ECE 严格优于** 现状 `p_hat_train` 基线，且 `p_final` 的 **logloss ≤ `p_market_cal` 的 logloss**（即融合不能比单用市场更差）。
- **经济门**：按 q 桶 realized ROI **单调**（高 q 桶 ROI > 低 q 桶 ROI），且**最高 q 桶 ROI > 0**；整体 OOS ROI ≥ 现状基线 ROI + margin（如 +5pp，对齐 forward.py 的 `MARGIN=0.05`）。
- **样本门**：OOS test 样本 `≥ N_min`（如 ≥ 300 腿，量级对齐 forward.py 的 `MIN_COMBOS=200`）后才判定；不足则继续累积或判「不确定」。
- **风控门**：纸面/灰度阶段 MaxDD 不破 50%（对齐 `MAXDD_STOP=0.50`）。
- **灰度路径**：纸面 → walk-forward 通过 → planner 灰度开关 ON（小额）→ 监控 `compute_q_drift` 的实盘 q 回到 ≥ break-even → 全量。任一门不过即回滚开关（默认 OFF，零成本回退）。

---

## 10. 风险与开放问题

- **概率层与 SP 漂移耦合**：`q_final` 用 `SP_eff` 依赖 frozen `HAIRCUT_MAP`，而 GATE-FT 尚未通过（`docs/research/sp_drift_forward.md`）。若漂移修正方向被 forward-test 推翻，`q_final` 需相应调整——二者应作为**联合门槛**评估。
- **过拟合分层校准**：层多 × 样本薄 → 校准器自身过拟合。靠 Beta 收缩 + 层级回退 + walk-forward 评估缓解；`κ` / `N_iso` / `n_min` 等超参须在 OOS 上选，不可在 test 上调。
- **`p_recent` 的延迟与噪声**：近窗 hit_rate 样本小、滞后；动态权重可能追噪。MVP 用固定低权重（0.15）+ 薄样本收缩到市场。
- **欧赔时点对齐**：`snapshots.eu_h/d/a` 是采集时点欧赔，与北单 SP 采集时点未必同步；devig 概率的时效需在 `p_market_open` 口径里界定（用最接近决策时刻的快照）。
- **draw（option=1）样本稀**：当前 niche 无 draw 规则，分层后 draw 桶薄 → 强依赖收缩到市场；评估须单独看 option=1 的校准曲线。
- **赛程/Elo 待接入**：第二批特征依赖外部数据，缺失时模型退化为「市场 + niche 残差」，须确认 MVP 在无这些特征时仍达门槛。

---

> 设计稿，不含实现。下一步：评审 → `superpowers:writing-plans` 拆分实现计划（先 `src/prob_calib/` 的 devig + 分层校准 + 评估脚本，planner 接入走灰度开关，全程 walk-forward / 纸面验证，不动实盘配置）。
