# joint_q / 共振概率：从单腿无 edge 到组合非独立性 edge — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban `t_b82b28f3`）
**状态**: 设计稿
**关联**:
- 直接前置（论据）：单腿 q 无可利用时间结构 `docs/research/q_persistence_analysis.md`（grand-mean q=0.838、整体 lag-1≈0、联赛级跨段相关 −0.745、逆向也过不了盈亏平衡线）
- 度量 vs 构造的姊妹分工：场景组合构造 `docs/strategy/scenario_portfolio_construction.md`（**待写**——本稿是「度量」，它是「构造法」，见 §0.2）
- 组合级后验 EV 决策 `docs/strategy/posterior_ev_decision.md`（**待写**——joint_q 给出组合状态的点估计与 CI，它把这套估计接进后验下注规则）
- 评估纪律总纲 `docs/strategy/walk_forward_strategy_evaluation.md`（本稿的 walk-forward 验证遵从其接口/判据/OOS 切片约定）
- 结构性逆风（可行性前提的来源）：`docs/research/sp_drift_phase4.md`、`docs/research/sp_drift_forward.md`、`[[sp-drift-study]]`
- 可复用基建：`src/webui/services.py`（`collect_settled_legs`/`q_buckets`/`_q_stat`/`leg_concentration_pct`/`select_current_issue`）、`src/combo_optimizer/`（`Candidate`/`Combo`/`combo_math`/`builder`）、`src/backtest_combo/settler.py::settle_plans`、`src/sp_drift/replay.py::replay_policy`、`scripts/analyze_q_persistence.py`

---

## 0. 这份文档是什么 / 不是什么

### 0.1 是 / 不是

**是**：定义一个组合级的回报度量 `joint_q` 与一套「先识别可押的组合状态/族、再在族内选票」的 planner 接入方案，并给出统计检验与 walk-forward 验证设计。核心问题：**单腿 q 已被证明无 edge（见 q_persistence），但若各腿并非独立——存在共同隐变量让 `P(A∩B∩C…)` 偏离 `Πp_i`——组合层可能仍有可提取的结构。** 本稿要把这个「可能性」变成一个可证伪的实验。

**不是**：不写实现代码、不改其他文件，本次只产出这一份设计稿。不是「场景组合的构造法」（那是姊妹文档 `scenario_portfolio_construction.md` 的职责）。不是真钱 A/B。

### 0.2 与场景组合文档（`scenario_portfolio_construction.md`）的分工

两份文档共用「组合非独立性」这一主题，但严格分工，避免重叠：

| | 本稿 `joint_q_correlation_edge` | 姊妹稿 `scenario_portfolio_construction` |
|---|---|---|
| 角色 | **度量层（measurement）** | **构造层（construction）** |
| 回答 | 「某个组合状态/族的真实组合回报是多少？腿间是正相关（隐藏风险）还是负相关（可利用）？这个数字过没过结构墙、统计上稳不稳？」 | 「给定一个已识别为可押的状态，怎么把当期可用的票拼成一个组合投注组合（portfolio）——选哪几条腿、几张票、各下多少、怎么控相关与并发？」 |
| 产物 | `joint_q` 指标、组合族枚举法、腿间相关检验、shrinkage 后的状态 EV 估计与 CI | 选票/拼票/分仓/并发控制规则，diversity_lambda / cross_n_lambda / max_combos 的场景化设定 |
| 依赖方向 | 上游：提供「哪些状态值得押」的度量结论 | 下游：消费本稿的度量结论，把状态落成具体票 |

一句话：**本稿告诉你「在哪押」，场景组合告诉你「怎么押」。** 本稿的 §6 planner 接入只画到「识别可押族 → 把候选票交给构造层」为止，不规定构造层的内部算法。

---

## 1. 可行性前提（必须先过这一关，否则后面全是噪声）

在投入任何样本之前，必须诚实地把「组合非独立性 edge 要大到多少才有意义」算清楚。北单的结构性逆风是**乘法叠加**的，共振 edge 必须翻过两道墙：

### 1.1 两道结构墙

1. **抽水 0.65 地板**：北单 parimutuel 返奖率 0.65（`RETURN_RATE`，`src/combo_optimizer/types.py`）。每张组合票赢的时候只拿回 `0.65 × Π winning_sp`，35% 被抽走。这是乘法地板，**不随腿数变化**（rake 只收一次，见 `settler.settle_combo`：`payout = RETURN_RATE; for leg: payout *= sp`）。

2. **SP 漂移 haircut（乘法）**：决策时刻看到的计划 SP 高于结算 winning_sp，4 腿组合实现回报相对计划缩水约 `0.836⁴ ≈ 0.49`（来自 sp_drift 研究的逐腿漂移系数）。每多一腿就再乘一次 < 1 的系数，组合越长缩得越狠。

### 1.2 边际门槛推导

单腿盈亏平衡需要 `p × SP × 0.65 = 1`。组合 N 腿在**独立**假设下盈亏平衡需要 `Πp_i × ΠSP_i × 0.65 = 1`。把组合实际全中概率写成 `P(全中) = ρ × Πp_i`，其中 `ρ = P(A∩B∩…)/Πp_i` 是**非独立性放大因子**（ρ>1 正向共振/负相关于「同时败」、ρ<1 同向正相关）。则组合 EV：

```
combo_EV + 1 = ρ × Πp_i × ΠSP_i × 0.65 × (SP漂移缩水)
```

对一个单腿恰好盈亏平衡（`p_i×SP_i×0.65^{1/N}=1`，即组合在独立+无漂移下 EV=0）的族，要让 4 腿组合在漂移后回正，需要：

```
ρ ≥ 1 / (SP漂移缩水) ≈ 1 / 0.49 ≈ 2.04
```

**即：共振放大因子 ρ 必须 ≳ 2（全中概率比独立乘积高一倍以上），4 腿组合才可能仅靠非独立性翻过 SP 漂移墙。** 这是一个**极高**的门槛——意味着腿间要有强到几乎确定性的共同隐变量（如「同一天所有低赔热门要么集体兑现、要么集体爆冷」）。

**可行性结论（前置门槛）**：
- 若数据里 ρ 的可识别上界（即便是最极端的组合族）远不到 2，本课题应**直接判死**，不进入 MVP。§5 的第一个检验就是估 ρ 的分布与上界。
- 缩短腿数能降低门槛：N=2 时 SP 漂移缩水 ≈ `0.836²≈0.70`，需要 `ρ≥1.43`；N=3 需要 `ρ≥1.71`。**因此本课题天然偏好短组合（N=2/3），而非现有默认 N=4。** 这点要在 §6 planner 接入与场景组合文档里贯穿。

### 1.3 双面性：负相关=edge，正相关=隐藏风险

现有结算与 EV 逻辑（`combo_math.joint_probability`、`Combo.joint_p`、`services` 里的 `0.65×Πq` 心智模型）**默认独立**。但若腿间其实是**正相关**（同日同向偏差：同一批热门一起兑现或一起爆冷），那 `P(全中)` 会**低于** Πp_i（ρ<1），组合票更容易全军覆没——这是 **downside，不是 edge**。

因此本稿的检验必须**对称地**同时回答两面：
- **ρ>1（负相关 / 反向共振）= 可利用**：组合比独立模型以为的更容易全中 → 在这些状态加注短组合。
- **ρ<1（正相关 / 同向共振）= 隐藏风险**：组合比独立模型以为的更容易全灭 → 在这些状态**减注或退出**，并修正现有独立 EV 的高估。

注意：即便最终没找到可利用的 ρ>1，**找到稳定的 ρ<1 区域本身也是有价值的产物**（防御性地修正现有独立假设导致的系统性 EV 高估）。

---

## 2. 指标定义

### 2.1 `joint_q`（组合级实现回报倍数）

对齐单腿 q（`_q_stat`：`q = RETURN_RATE × Σ(命中腿 SP)/n`）的定义，把它抬到组合级。给定一个**组合族** F（同一构造规则下的一批 N 腿组合，详见 §4），逐个组合按真实 winning_sp 结算（`settle_plans` 口径：全中才赔，赔率用结算 winning_sp）：

```
joint_q(F) = E_combo∈F[ realized_payout_per_yuan ]
           = (1/|F|) × Σ_combo [ 1{全中} × Π winning_sp(命中腿) × 0.65 ]
```

- `joint_q = 1` 为盈亏平衡，`< 1` 净亏。
- **结算口径必须用 winning_sp（结算价），不是计划 SP**——这样 SP 漂移自动计入，与 `replay.replay_policy`/`settler` 一致。

### 2.2 与「单腿 q 乘积」的区别（核心）

现框架的组合 EV 简化为 `0.65 × Πq_i − 1`，它**默认独立**：把组合回报当成各腿独立回报的乘积。`joint_q` 与它的差，正是非独立性：

```
独立基线（independent_q）  = 0.65 × Π( q_i / 0.65 )       # 各腿 q 反解出 p×SP 再连乘，rake 收一次
                          ≈ 0.65^{1-N} × Π q_i

joint_q（实测组合回报）    = §2.1 的直接组合结算

非独立性增益 Δ = joint_q − independent_q
共振放大因子 ρ̂ ≈ joint_q / independent_q   （§1 的可行性门槛就盯这个 ρ̂）
```

- `Δ > 0 / ρ̂ > 1`：组合实际比「各腿独立」赚得多（负相关/反向共振，可利用）。
- `Δ < 0 / ρ̂ < 1`：组合实际比独立模型赚得少（正相关/同向共振，隐藏风险）。

**关键澄清**：`independent_q` 不能简单写成「`Πq_i`」——单腿 q 已含一次 rake（0.65），N 腿连乘会把 rake 收 N 次，与组合只收一次不符。基线必须先把各腿 q 反解回 `p_i×SP_i`，连乘后再乘**一次** 0.65。这是本指标最容易写错的地方，实现时务必对齐 `combo_math.combo_payout_per_yuan`（`joint_sp × RETURN_RATE`，rake 一次）。

### 2.3 辅助量

- `hit_rate(F)`：组合全中率（直接观测 `P(全中)`）。
- `independent_hit_rate(F) = mean(Π p̂_i)`：独立假设下的预测全中率。
- `ρ̂ = hit_rate / independent_hit_rate`：用全中率直接估的放大因子（比用 q 估更干净，因为不掺 SP 漂移；推荐主用这个估 ρ，用 §2.1 的 joint_q 估「钱」）。
- `n_combos(F)`、`n_distinct_legs(F)`、`leg_concentration_pct`（复用 `services.leg_concentration_pct`，监控族内是否其实是少数腿撑起的伪样本）。

---

## 3. 数据

- 主库 `data/beidan_live.db`：`matches` / `snapshots` / `settlements`，含 `issue`/`league`/`kickoff_ts`/`result_code`/`winning_sp`，欧赔 `eu_*` 覆盖 ~99.9%（可作 regime/方向的协变量）。
- 已结算腿来源：`services.collect_settled_legs`（每条腿带 `league/selection/sp/hit`）+ `settlements.winning_sp`（结算价，用于 joint_q 的真实赔付）。
- **样本硬约束**：504 条已结算腿、仅 10 期（26051–26065）。组合级样本比单腿**更稀疏**——任何按状态切分的组合族很容易只剩个位数组合。**这是本课题的头号风险**，shrinkage / 最小门槛 / bootstrap（§5.3）是硬性前提，不是可选项。
- 时间轴：与 walk_forward 文档一致，**结算口径以 kickoff_ts 为准**（字典序=时序），OOS 只计「切片边界之后开赛且已结算」的组合。

---

## 4. 组合族枚举方法

「组合族（family）」= 一条**状态谓词**定义的、同期内可枚举的 N 腿组合集合。目标是构造一组互不相同、各自对应一个**可能的共同隐变量**的族，逐族估 ρ̂ 与 joint_q。

### 4.1 状态维度（笛卡尔积过粗，需先验剪枝）

| 维度 | 取值（示例） | 数据来源 | 隐变量假设 |
|------|------|------|------|
| regime | 低赔热门日 / 冷门日 / 混合（按当期 median SP 或欧赔隐含概率分布分档） | `snapshots.eu_*` / `sp_*` | 「整盘热门/冷门情绪」共同驱动 |
| 联赛结构 | 同联赛多腿 / 跨联赛 / 同国别 | `matches.league` | 同联赛同日裁判/天气/赛程疲劳共同偏差 |
| 选项组合 | 全主胜(3) / 全客胜(0) / 混合 / 含平(1) | `selection` | 「主场优势」或「客队强势」的当日系统性偏 |
| SP 桶 | 全低 SP / 全中 SP / 全高 SP / 混合（沿用 `drift_stats.sp_band`） | `sp` / `winning_sp` | 同赔率带的漂移与兑现同步 |
| 让球 | 同向让球 / 反向 / 平手盘 | `handicap_line`（`classify_handicap`） | 盘口设置的系统性偏 |
| kickoff bucket | 同时段开赛（复用 `kickoff_bucket_label` / `assign_kickoff_buckets`） / 跨时段 | `kickoff_ts` | 同时段比赛信息/情绪同步 |
| 热门/冷门方向 | 全押热门（低 SP 一侧） / 全押冷门 / 混合 | `sp` 相对同场其他选项 | 「整日热门是否集体兑现」——§1.3 最核心的共振假设 |

### 4.2 枚举与剪枝法

1. **不取全笛卡尔积**（维度爆炸 + 样本秒空）。改用**单维 + 双维**族：先逐个维度切（如「regime=低赔热门日」这一族里所有 N 腿组合），再只对**有先验的双维交互**（如「低赔热门日 × 全押热门方向」「同联赛 × 同向让球」）做交叉。
2. 族内组合枚举复用 `combo_optimizer.builder.enumerate_combos`（同期 `C(K, n_legs)`），但**这里不按 EV 过滤/排序**——要的是该状态下的**无偏组合总体**来估 ρ̂，不是选高 EV 的票（选 EV 会引入选择偏差，污染相关估计）。
3. 优先 **N=2/3**（§1.2 门槛更低、组合样本更多），N=4 仅作对照。
4. 每族登记 `n_combos`、`n_distinct_legs`、`leg_concentration_pct`；族内 `n_combos < 门槛`（见 §5.2）或 concentration 过高的，**只报告、不下结论**。

### 4.3 起点代码

`scripts/analyze_q_persistence.py` 是现成的「逐期×状态聚合 + 分桶 + 看 q」的脚手架。joint 检验脚本可在其基础上：把「逐腿聚合」替换为「逐组合枚举 + `settle_plans` 结算」，把「单腿 q」替换为 §2 的 `joint_q` / `ρ̂`，把分桶键替换为 §4.1 的状态谓词。

---

## 5. 统计检验

### 5.1 腿间相关检验（正/负两面，§1.3）

逐族估并报告：

| 检验 | 量 | 判读 |
|------|------|------|
| 全中率对比 | `hit_rate` vs `independent_hit_rate` | ρ̂>1 反向共振（可利用）；ρ̂<1 同向共振（风险） |
| 同日方向共振 | 「当期已结算腿里 主胜命中数」的实际分布 vs 二项独立分布 | 实际尾部更胖（极端同中/同灭多）= 正相关 |
| 客胜共振 | 同上，selection=0 | 同上 |
| 低赔热门日 | 热门腿命中的 pairwise φ 系数 / 条件命中率 | φ>0 = 热门集体兑现/集体爆冷（正相关风险） |
| 冷门日 | 同上，冷门一侧 | |
| 联赛同向偏差 | 同联赛多腿命中的组内相关（intra-class correlation） | ICC>0 = 同联赛同日共偏 |

具体统计量：对「同期同向 K 腿里命中数」用**二项过散/欠散检验**（实际方差 vs `np(1-p)`）；对成对腿用 **φ 系数 / Cramér's V**；对同组多腿用 **ICC**。所有检验都给点估计 + bootstrap CI（§5.3）。

### 5.2 避免样本稀疏

- **最小样本门槛**：族内 `n_combos ≥ 30` 且 `n_distinct_legs ≥ 8` 才出 ρ̂/joint_q 的**结论**；不足者标 `thin`，只报告点估计 + 宽 CI，不进决策。门槛对齐 q_persistence 的诚实口径（504 腿、逆向桶各 ~75 腿已属薄）。
- **层级 shrinkage（经验贝叶斯）**：族级 ρ̂ 向**全局 ρ̂**收缩，收缩强度按族内有效样本：`ρ̂_shrunk = w × ρ̂_family + (1−w) × ρ̂_global`，`w = n_eff / (n_eff + k)`。这正是 q_persistence §4 警告的「小样本回归均值是机械产物」的正面用法——用 shrinkage 主动把伪信号压回全局，只有信号强到顶住收缩才留存。`n_eff` 用 `n_distinct_legs`（不是 `n_combos`，因组合间共享腿、强相关，组合数高估了独立信息量）。
- **bootstrap 置信区间**：**按 leg 重采样（cluster bootstrap），不是按 combo**——组合共享腿，按 combo 重采样会假性收窄 CI。重采样腿池 → 重新枚举族内组合 → 重算 ρ̂/joint_q，取 1000 次的 2.5/97.5 分位。

### 5.3 决策判据（事前冻结，遵从 walk_forward 总纲）

某族判为「可利用（加注）」需**同时**满足：
1. `n_combos ≥ 30 且 n_distinct_legs ≥ 8`（过薄一票否决）；
2. shrinkage 后 `ρ̂_shrunk` 的 bootstrap 95% CI 下界 `> 1`；
3. **过结构墙**：`ρ̂_shrunk` 下界 ≥ §1.2 对应腿数的门槛（N=2:1.43 / N=3:1.71 / N=4:2.04），即 joint_q 的 CI 下界 > 1；
4. 在 walk-forward OOS 切片上复现（§7），不是只在样本内。

某族判为「隐藏风险（减注/退出）」：shrinkage 后 `ρ̂_shrunk` 的 CI 上界 `< 1`（稳定正相关）。

---

## 6. Planner 接入

现框架的 planner（`services.generate_plan` → `combo_optimizer.builder`）逻辑是「**rank 单腿候选 → 枚举 EV 高的组合**」，全程默认独立。joint_q 的接入把它改成**两段式**：

```
第 0 段（状态识别，本稿/joint model 提供）：
  对当期 snapshots，先判定当前盘面落在哪些「已验证可押」的状态/族
  （regime / 方向 / SP 桶 / 联赛结构 …，用 §5.3 冻结的族白名单）。
  → 若落在 ρ̂<1 风险族 → 该状态下减注或不押（修正独立 EV 高估）。
  → 若落在 ρ̂>1 可利用族 → 标记为可押状态，附带该族的 joint_q 点估计与 CI。

第 1 段（族内选票，交给场景组合文档 scenario_portfolio_construction）：
  在可押状态内，按场景组合的构造法拼短组合（偏好 N=2/3）、分仓、控并发与相关。
  本稿不规定第 1 段的内部算法，只把「可押族 + 其 joint_q 估计」作为接口交出去。
```

接入要点：
- **不再只 rank 单腿**：单腿 q 无 edge（q_persistence 已证），rank 单腿是死胡同。改为先识别组合状态，再在状态内选票。
- **EV 计算从独立改为 joint**：候选组合的 EV 用该族 shrinkage 后的 `ρ̂` 修正——`combo_EV = ρ̂ × joint_p_independent × payout − 1`，而非现在的纯独立 `Combo.ev`。这需要在 `combo_math` / sizing 层引入一个按状态查表的 ρ̂ 因子（实现时再定，本稿只定接口语义）。
- **偏好短组合**：planner 的 N 选择从默认 N=4 转向 N=2/3（§1.2 门槛），与场景组合文档协同。
- **复用** `select_current_issue`（单期约束，组合绝不跨期）、`leg_concentration_pct`（族内伪样本监控）、`generate_bucketed_plans`（kickoff bucket 维度的天然切分）。

---

## 7. 验证：walk-forward 三方对照

遵从 `walk_forward_strategy_evaluation.md` 的统一接口与 OOS 切片纪律（rolling train/val/test，结算以 kickoff_ts 为准，预注册停止规则，幂等 ledger，GATE verdict）。本课题的特化是**三个 arm 同切片对照**：

| arm | 模型 | 实现路径 |
|-----|------|------|
| **A0 no-bet** | 不下注（基线，0 回报 0 方差） | 空计划 |
| **A1 independent-q** | 现框架：独立 EV、`0.65×Πq`、N=4、rank 单腿 | 现 `replay_policy` 原样 |
| **A2 joint model** | 本稿：状态识别 + ρ̂ 修正 EV + 偏好短组合 + 风险族退出 | `replay_policy` + 按 §6 注入 ρ̂ 查表 |

- 回测引擎复用 `src/sp_drift/replay.py::replay_policy`：它已经做到「决策时刻 qualify/size、按真实 winning_sp 结算、逐 issue 滚 bankroll」，**天然支持 joint vs independent 的同口径对照**（只需把 A2 的 EV/选票逻辑替换进 `build_weekly_plan` 调用前的候选构造）。
- 指标：每 arm 报 `roi / total_pnl / max_dd / n_tickets / n_hits`（`aggregate_equity` 已给），外加组合级 `joint_q` 实测 vs 预测、ρ̂ 实测 vs 训练期估计的漂移。
- **判 A2 胜出（升生产）**：A2 的 OOS ROI 的 CI 下界 > A1，且 > A0（即真为正 EV，不只是相对没那么亏）；否则维持 A1 / 退回 A0。诚实预期：鉴于 §1 的高门槛，**最可能的结论是「ρ 区域有但翻不过结构墙 → A2 不胜 A0」**，此时本课题的产物退化为「§5.3 的风险族白名单」（防御性修正 A1 的 EV 高估），仍有价值但不构成独立盈利策略。

---

## 8. MVP 拆解

按「能最快证伪」排序，前 2 步若不过即判死，省掉后续：

- **MVP-0｜可行性体检（最高优先，门槛守卫）**：在全样本上估**全局 ρ̂**（`hit_rate` vs `independent_hit_rate`，按 §2.3 用全中率直接估）及其 cluster-bootstrap CI。
  - **杀手判据**：若全局 ρ̂ 的上界连「最宽松的 N=2 门槛 1.43」都够不到，且无任何单维族的点估 ρ̂ 接近门槛 → **直接判死本课题**，只留 MVP-1 的风险族扫描作为防御性副产物。
- **MVP-1｜风险族扫描（防御性，几乎确定有产出）**：逐 §4.1 单维族估 shrinkage 后 ρ̂，标出 CI 上界 < 1 的**正相关风险族**。这些直接喂回现框架，修正独立 EV 高估——即便 MVP-0 判死，这步也值得做。
- **MVP-2｜可利用族识别**（仅当 MVP-0 没判死）：双维交互族 + §5.3 全套判据，产出「可押族白名单 + 各族 joint_q/ρ̂ 估计与 CI」。
- **MVP-3｜replay 三方对照**：在 `replay_policy` 上跑 A0/A1/A2（§7），出样本内对照表。
- **MVP-4｜walk-forward OOS**：接入 walk_forward 总纲，OOS 切片复现，出 GATE verdict。
- **MVP-5｜planner 接入**（仅当 MVP-4 通过）：按 §6 把状态识别 + ρ̂ 查表接进 `generate_plan`，把族内选票交棒给 `scenario_portfolio_construction`。

---

## 9. 实验表结构（产物 schema）

### 9.1 族级表 `joint_family_stats`

| 列 | 含义 |
|----|------|
| family_id | 状态谓词的稳定标识（如 `regime=hot_low \| dir=fav \| N=3`） |
| dims | 触发的维度键值（JSON） |
| n_legs | 组合腿数 |
| n_combos / n_distinct_legs / concentration_pct | 样本规模与伪样本监控 |
| hit_rate / independent_hit_rate / rho_hat | 全中率、独立预测、放大因子点估 |
| rho_shrunk / rho_ci_lo / rho_ci_hi | shrinkage 后 ρ̂ 及 cluster-bootstrap 95% CI |
| joint_q / indep_q / delta | 组合实现回报、独立基线、非独立性增益 |
| joint_q_ci_lo / joint_q_ci_hi | joint_q 的 bootstrap CI（与结构墙门槛比） |
| barrier_threshold | §1.2 对应腿数的 ρ 门槛（1.43/1.71/2.04） |
| verdict | `exploit` / `risk` / `thin` / `neutral`（按 §5.3） |

### 9.2 walk-forward 对照表 `joint_walkforward_ledger`

| 列 | 含义 |
|----|------|
| slice_id / train_range / oos_range | 滚动切片（kickoff_ts 边界） |
| arm | `A0_nobet` / `A1_indep` / `A2_joint` |
| roi / total_pnl / max_dd / n_tickets / n_hits | `aggregate_equity` 口径 |
| joint_q_oos_pred / joint_q_oos_real | 训练期估计 vs OOS 实测（看 ρ̂ 是否漂移） |
| verdict | GATE：A2 是否胜 A1 且胜 A0 |

---

## 10. 风险与诚实声明

1. **结构墙极高**：ρ≳2（N=4）的门槛意味着腿间要近乎确定性共同隐变量，先验上不太可能。**最可能结局是判死或退化为防御性风险族修正**，文档不预设它能盈利。
2. **样本是头号约束**：504 腿 / 10 期，组合族秒空。所有「可利用」结论都将带宽 CI，MVP-0 很可能因样本不足而无法把 ρ̂ 的 CI 收到门槛之上——届时结论是「在此样本量下无法证实」，与 q_persistence §6 同调，不是「证伪了 edge」。
3. **正相关是默认风险面**：体育同日同向偏差先验上更可能是**正相关**（ρ<1，热门集体表现）。这意味着本课题的现实主力产出更可能是 §1.3 的**下行修正**而非上行 edge——这恰恰是现框架独立假设的盲区，仍值得做。
4. **选择偏差**：族枚举若混入 EV 排序会污染相关估计（§4.2），实现时务必用无偏组合总体估 ρ̂、只在 planner 接入阶段（§6）才引入 EV。
5. **ρ̂ 的非平稳性**：相关结构可能随 regime/季节漂移，训练期估的 ρ̂ 未必在 OOS 成立——§7 的 `joint_q_oos_pred vs real` 列就是盯这个漂移；若漂移大，即便样本内显著也不可生产化。
