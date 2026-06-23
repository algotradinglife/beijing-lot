# 后验概率决策框架：用 `P(EV>0 | data)` 替代单点 q

**日期**: 2026-06-23
**作者**: Claude（承接 kanban `t_6716253d`）
**状态**: 设计稿（不含实现，仅设计）
**关联（动机）**: [[q_persistence_analysis]] —— 点估计 q 不可信的实证
**关联（校准层）**: [[single_match_probability_calibration]] —— `p_final` 是输入，本框架是其决策层
**关联（入场门）**: `no_bet_trading_window.md`（计划中）—— `P(EV>0)` 用作入场闸门
**关联（组合级）**: `joint_q_correlation_edge.md`（计划中）—— 组合相关性下的联合后验
**关联（评估）**: [[walk_forward_strategy_evaluation.md]] —— walk-forward 对比框架

---

## 0. 一句话

不要问「点估计 q 是否过阈值」，而问「在当前样本和先验下，这个腿 / 组合族 / 策略 **EV 为正的后验概率** 是否足够高」。点估计 q 在小样本里是噪声；后验概率把样本量、先验锚点、不确定性一并编码进决策。

---

## 1. 为什么需要后验：q 持续性分析是直接证据

[[q_persistence_analysis]]（`scripts/analyze_q_persistence.py`，504 已结算腿、10 期 26051–26065）量化地证明了「点估计 q 不可交易」：

1. **联赛级 q 早 / 晚段相关 = −0.745**（n=11 联赛）。早期好的联赛后期普遍变差、早期差的反弹。若按点估计 q 降权，会精确踢掉正要反弹的联赛（解放者杯：早期 q=0.00 → 晚期 1.57）。
2. **逆向回测 0.756 vs 0.480**（上期低 q 桶 vs 上期高 q 桶，各 ~75 腿，gap +0.276）。**这 +0.276 大半是小样本回归均值的机械假象**：上期 q 高多半运气好必回落，低多半运气差必回升。纯噪声也会产生此图案，而纯噪声不可交易。
3. **整体 q 在任何切口（整体 / 联赛 / 选项）都是围绕 grand-mean ≈ 0.82 摆动的 iid 噪声**，lag-1 自相关全为 0~负。

结论：**点估计 q 阈值（无论全局口径还是近期口径）都在追噪声**。正确做法是把每个桶的 q 当作带不确定性的后验分布来对待，对薄样本桶强 shrinkage 回归到先验，只有当「EV>0 的后验概率高」时才允许加重注。

> 注意：q 持续性分析里 `select_downweight_leagues`（`src/webui/services.py`）正是当前的「点估计阈值」实现（`q < 0.7` 且 `n ≥ 8` 就拉黑），它应被本框架的后验判据替代。

---

## 2. 关键陷阱：回归中心是 0.82 < 1.0 —— 先验必须锚在「负 EV」

最危险的失败模式：后验显示某桶「EV>0 的概率 90%」，但那只是小样本好运。因为：

- **全样本回归中心 grand-mean q ≈ 0.82 < 1.0**（系统性负 EV 基底）。
- 因此**先验的均值应锚在「负 EV」（q₀ < 1）而非「公平」（q=1）**。把先验锚在公平，等于默认每个桶无罪推定为可盈利，会把噪声好运误判为 edge。

盈亏平衡（break-even，`RETURN_RATE = 0.65`）：

- **单腿**：`q = 0.65 × p × SP ≥ 1` ⟺ `p × SP ≥ 1/0.65 ≈ 1.538`。等价 `edge = p×SP×0.65 − 1 ≥ 0`（见 `src/combo_optimizer/types.py::Candidate.edge`）。
- **组合（N 腿，独立近似）**：`0.65 × Π(pᵢ×SPᵢ) ≥ 1`。N=4 每腿对称时需 `raw p × SP ≥ (1/0.65)^(1/4) ≈ 1.114`（见 `combo_math.break_even_per_leg_edge`）。

**设计取向**：后验框架的默认零假设是「这个桶净亏（EV ≤ 0）」，要靠数据把后验推过 break-even 才下注。这与 sp_drift 的预注册判据范式一致（`src/sp_drift/forward.py::check_stopping_rule`：要求 margin 才 "go"）。

---

## 3. 后验表达（数学定义）

记 `RR = RETURN_RATE = 0.65`。我们对「实现回报倍数 q」的后验建模分三层。

### 3.1 单腿层：Beta-Binomial

把一个桶（联赛 × 选项，或 niche 规则）的命中建模为伯努利。设该桶平均报价 `SP̄`（或逐腿 SP），命中概率 `p`。

- 似然：`hits ~ Binomial(n, p)`，数据来自 `services.py::collect_settled_legs` → `_q_stat`（给出 `n, hits, avg_sp`）。
- 先验：`p ~ Beta(α₀, β₀)`，**锚在市场隐含概率打折后的负 EV 点**。
  - 市场隐含命中率 `p_mkt = 1/(SP̄ × RR_implied)`，但更稳的锚是 niche 规则的 `p_hat_train`（`src/phase5a/filter.py`，训练集校准命中率）或 `league_quality.json` 的联赛 q。
  - 锚点取 `p₀ = p_hat_train × shrink_to_negative`，其中 `shrink_to_negative` 使 `q₀ = RR × p₀ × SP̄ ≈ 0.82`（grand-mean），即默认负 EV。
  - 先验强度 `α₀+β₀ = κ`（伪计数，例如 κ=20~40 等价 20~40 条虚拟腿），控制 shrinkage 力度。薄样本（n < κ）时后验主要听先验。
- 后验：`p | data ~ Beta(α₀ + hits, β₀ + n − hits)`。

由 p 的后验导出 q 与 EV 的后验。单腿 `q = RR × p × SP̄`（SP̄ 视为已知常数时，q 的后验是 p 后验的线性变换）：

```
EV_leg = RR × p × SP̄ − 1
P(EV_leg > 0 | data) = P(p > 1/(RR × SP̄) | data)
                     = 1 − BetaCDF(1/(RR × SP̄); α₀+hits, β₀+n−hits)
```

### 3.2 组合族层：联合后验

一个「组合族」= 同一参数策略产出的 N 腿 parlay 的集合。两条路径：

- **解析（独立近似）**：组合 EV `= RR × Π pᵢ × Π SPᵢ − 1`（`combo_math.combo_ev`）。把每腿 `pᵢ` 的 Beta 后验独立抽样，蒙特卡洛得到 `Π pᵢ` 的后验，再算 `P(EV_combo > 0)`。
  - ⚠️ 独立假设是近似（`types.py::Combo` 注释已警示：组合内共享腿强相关）。组合相关性专门见 `joint_q_correlation_edge.md`。
- **层级模型（推荐主路径）**：联赛 / 规则共享一个上层超先验，桶级 `pᵢ` 部分汇聚（partial pooling）。这正面解决「联赛级 q 早晚相关 −0.745」的回归均值问题——层级 shrinkage 把异常热 / 异常冷的桶都拉回群体均值，自动不被单期好运 / 坏运牵着走。

  ```
  μ_global ~ Normal(logit(p_anchor), τ₀)         # 全局锚（负 EV）
  θ_league ~ Normal(μ_global, σ_league)          # 联赛偏移
  p_bucket = sigmoid(θ_league + 选项/SP 协变量)
  hits_bucket ~ Binomial(n_bucket, p_bucket)
  ```

### 3.3 策略级：实现回报的后验

策略级直接对「逐期实现回报率 r_t」建模（结算 PnL / stake），用层级正态或 t 分布（厚尾防极端期）：

```
r_t ~ StudentT(ν, μ_strat, σ_strat)
μ_strat ~ Normal(0, s₀)          # 锚在 0（盈亏平衡 ROI），保守
```

`P(strategy EV > 0) = P(μ_strat > 0 | r_{1..T})`。数据来自 `services.py::equity_series` / `db.list_settlements`。

---

## 4. 决策规则

对每个候选桶 / 组合 / 策略，计算三个后验量并组合成动作：

1. **正 EV 后验概率门**：`P(EV > 0 | data) > x`。
   - 建议 `x = 0.80`（实盘重注），`x = 0.60`（小注 / 试探），`x ≤ 0.60` → 仅 shadow。
2. **回撤风险门**：`P(drawdown over horizon > D) < y`。由 q / EV 后验抽样路径模拟得分布；`D` 例如 30%，`y = 0.10`。对接 `compute_stats` 的 `max_drawdown` / `current_dd`。
3. **期望对数增长（Kelly 目标）**：`E[log growth | posterior] > 0`。对后验抽样，每抽样算该样本下的 Kelly 增长率，取期望。只有期望对数增长为正才进场。

**组合判据（伪代码）**：

```
def decide(bucket_posterior, x=0.80, y=0.10, D=0.30):
    p_ev   = P(EV > 0 | bucket_posterior)
    p_dd   = P(maxDD > D | bucket_posterior)        # 模拟得到
    g_log  = E[log_growth | bucket_posterior]       # 后验期望对数增长
    if p_ev > x and p_dd < y and g_log > 0:
        return "BET_FULL"      # 用保守分位数定注（见 §6）
    if p_ev > 0.60 and p_dd < y:
        return "BET_SMALL"
    return "SHADOW"            # 只记账、不实盘
```

---

## 5. 小样本处理：shrinkage + shadow-only

这是框架的核心防御。数据薄是常态（504 腿、10 期、联赛级每段 5–13 腿），后验 / CI 是刚需不是锦上添花。

- **强 shrinkage 到先验**：薄样本桶（`n < κ`）的后验由先验主导，先验锚在「市场概率打折后的负 EV」（§2、§3.1）。一个 n=5、q=1.5 的桶，shrink 后后验均值会被拉回 ~0.9，`P(EV>0)` 远达不到 0.80 → 不重注。这机械地杜绝「小样本好桶被误认 edge」。
- **回归到市场 / 全局先验的层级**：桶 → 联赛 → 全局。桶薄就听联赛，联赛薄就听全局（grand-mean ≈ 0.82）。
- **shadow-only 闸门**：`n < n_min`（例如 `n_min = κ`，或 `P(EV>0)` 未过 `x`）的桶**只允许 shadow**：照常生成下注、记账、计入校准与 walk-forward，但**不投真钱**。只有后验把概率推过门、且样本够厚，才允许实盘重注。
- **错杀保护**：因为先验锚在负 EV，薄样本下的「误放」（把烂桶当好桶）被压住；而「错杀」（把真 edge 当噪声）通过 shadow 通道仍在持续累积证据，一旦样本变厚、后验过门即转实盘，不会永久埋没。

---

## 6. 与 Kelly 的关系：用后验**保守分位数**，不用乐观均值

当前 `combo_optimizer/sizer.py::size_one_combo` 用点估计 `p`（`p_hat`）算 `kelly_fraction_full(joint_p, payout)`，再乘 `kelly_fraction = 1/16`。点估计 p 在小样本偏乐观 → Kelly 系统性过注。

改造：**把 Kelly 的 p 换成后验的保守分位数，而非后验均值**。

```
# 现状（乐观）：
f_star = kelly_fraction_full(p_hat, payout)

# 改造（保守）：
p_lo   = posterior_quantile(p | data, q=0.25)     # 后验下四分位
f_star = kelly_fraction_full(p_lo, payout)
stake  = bankroll × kelly_fraction × f_star       # kelly_fraction=1/16 不变
```

- 取后验 **25 分位（或 10 分位）** 作为 Kelly 输入 `p`，等价于「对自己估计的不确定性收税」：样本越薄、后验越宽，p_lo 离均值越远、注越小，自然趋向 shadow。
- 这与「fractional Kelly」叠加：分位数收一道，`1/16` 再收一道。组合 / per-N Kelly（`generate_plan` 的 `kelly_n2..n5`）同样换成各自后验分位。
- 当 p_lo 使 `f_star = 0`（`kelly_fraction_full` 在非 +EV 时返回 0），自动不下注——与 §4 的 `P(EV>0)` 门一致收敛。

---

## 7. 动态更新

按 issue（期次）更新后验，近期样本加权但避免过度反应（直接回应 q 持续性分析「别追噪声」的结论）。

- **逐期贝叶斯更新**：每结算一期，把该期 legs 并入似然，后验自然递推。无需重训。
- **近期加权但克制**：用**指数遗忘 / 时间衰减伪计数**而非硬窗口。给历史伪计数一个衰减因子 `λ_decay`（例如半衰期 = 6 期），使近期样本权重略高，但**衰减必须温和**——q 持续性分析显示 q 是 iid 噪声、lag-1 ≈ 0，近期并不比全局更有预测力，激进遗忘 = 追噪声。
- **层级模型天然抗过度反应**：partial pooling 把单期异常拉回群体，比硬性「近期窗口」稳得多。这正是 §3.2 选层级模型的理由。
- **预注册更新规则**：衰减参数、先验强度 κ、阈值 x/y 在上线前冻结，不在样本里调参（对齐 `check_stopping_rule` 的预注册范式）。

---

## 8. 评估指标

walk-forward 对比「后验决策」与「点估计 q 阈值」，用 [[walk_forward_strategy_evaluation.md]] 的滚动 train/test 框架。

| 指标 | 定义 | 目标 |
|------|------|------|
| **后验校准** | 把 `P(EV>0)` 分桶，看每桶实际 EV>0 的频率是否对齐预测概率（可靠性图 + ECE） | ECE 低；对角线 |
| **下注覆盖率** | 实盘下注桶数 / 全部候选桶数；shadow 占比 | 覆盖率不崩（避免后验过保守到不下注） |
| **错杀成本** | shadow 桶里事后被证明 EV>0 的、本可赚而未赚的 PnL | 量化「过保守」代价 |
| **误放成本** | 实盘下注桶里事后 EV<0 的净亏 | 量化「过激进」代价 |
| **walk-forward ROI / maxDD / Sharpe** | 后验决策 vs `select_downweight_leagues` 点估计阈值，逐折对比 | 后验 ≥ 点估计，且 maxDD 更小 |
| **回归均值免疫度** | 用 q 持续性分析的早 / 晚段切分，验证后验是否不再被早期异常桶牵着走（对照 −0.745 相关） | 后验决策的早晚段下注不应复现 −0.745 的反持续坑 |

关键验收：在 504 腿薄样本下，后验决策应在**不增加 maxDD** 的前提下，至少不输给点估计 q 阈值，且**校准 ECE 明显更优**、薄样本桶不再被误重注。

---

## 9. 数据表字段

后验状态需持久化（建议 webui DB 新增表 `posterior_state`，每 issue 一版快照，便于 walk-forward 回放与审计）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `bucket_id` | TEXT | 桶键，如 `联赛|选项` 或 `niche_rule_name` |
| `level` | TEXT | `leg` / `combo_family` / `strategy` |
| `issue` | TEXT | 更新到哪一期（北单期次） |
| `n` | INT | 累计似然样本腿数（来自 `_q_stat.n`） |
| `hits` | INT | 命中数（`_q_stat.hits`） |
| `avg_sp` | REAL | 平均报价（`_q_stat.avg_sp`） |
| `prior_alpha` / `prior_beta` | REAL | Beta 先验伪计数（锚在负 EV） |
| `prior_anchor_p` | REAL | 先验锚命中率（来自 `p_hat_train` / `league_quality.q`） |
| `post_alpha` / `post_beta` | REAL | 后验参数 |
| `post_mean_q` | REAL | 后验均值 q（诊断用，**不直接定注**） |
| `p_ev_gt0` | REAL | `P(EV>0 | data)` |
| `p_lo_25` | REAL | 后验 p 的 25 分位（Kelly 输入） |
| `p_dd_gt_D` | REAL | 回撤风险后验 |
| `e_log_growth` | REAL | 后验期望对数增长 |
| `decision` | TEXT | `BET_FULL` / `BET_SMALL` / `SHADOW` |
| `lambda_decay` | REAL | 本期所用时间衰减因子（可审计） |
| `updated_ts` | TEXT | ISO 时间戳 |

`shadow_ledger`（错杀 / 误放成本核算，复用 `forward.py::append_ledger` 的 append-only + 幂等范式）：`run_date, bucket_id, decision, would_be_stake, realized_pnl_if_bet, on_book(bool)`。

---

## 10. MVP（最小可行）

只做单腿 Beta-Binomial + `P(EV>0)` 闸门 + 后验分位 Kelly + shadow 账本，先在 walk-forward 离线证明它不输点估计 q。

1. **后验计算函数**（纯函数，可单测）：输入 `_q_stat` 输出（`n, hits, avg_sp`）+ 锚 `p_hat_train`/`league_quality.q` + 先验强度 κ，返回 `(post_alpha, post_beta, p_ev_gt0, p_lo_25)`。先验锚到 `q₀ ≈ 0.82`。
2. **决策闸门**：`decide()`（§4 简化版，先只用 `p_ev_gt0 > x`），输出 `BET_FULL / BET_SMALL / SHADOW`。
3. **接管下注**：在 `services.py` 用本框架替换 `select_downweight_leagues`（黑名单 → 后验降权 / shadow），Kelly 输入从 `p_hat` 换成 `p_lo_25`。
4. **shadow 账本**：薄样本桶照常算注但只记账，落 `shadow_ledger`。
5. **walk-forward 对比脚本**：滚动期次，后验决策 vs 点估计 q 阈值，输出 §8 的校准 / ROI / maxDD / 错杀 / 误放表。复用 q 持续性分析的早晚段切分验证回归均值免疫。

**MVP 不做**：层级 / 组合联合后验（§3.2 推荐主路径，列为下一迭代）、回撤后验模拟（§4 门 2）、期望对数增长门（§4 门 3）—— 先用单腿 `P(EV>0)` 跑通闭环。

---

## 11. 验收清单

- [ ] 数学定义齐全：单腿 Beta-Binomial、组合 / 层级、策略级、break-even、Kelly 保守分位（§2/3/6）。
- [ ] 伪代码：`decide()`（§4）、后验分位 Kelly（§6）。
- [ ] 数据表字段：`posterior_state` + `shadow_ledger`（§9）。
- [ ] 小样本 / 动态更新策略明确：shrinkage、shadow-only、温和时间衰减（§5/7）。
- [ ] 评估指标含后验校准、覆盖率、错杀 / 误放成本、walk-forward vs 点估计 q（§8）。
- [ ] MVP 范围界定（§10）。
- [ ] 与 q 持续性分析、单场校准、Kelly sizer、forward 预注册范式交叉引用闭合。
