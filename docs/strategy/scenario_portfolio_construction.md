# 场景组合 / 宏观状态覆盖 — 押状态而非押单腿 — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban t_000a05cc）
**状态**: 设计稿，待评审 → 转 writing-plans
**关联**:
- 代码：`src/combo_optimizer/`（diversity_lambda / cross_n_lambda / max_combos 的现有票池构造）、`src/webui/services.py`（`select_current_issue` / `assign_kickoff_buckets` / `q_buckets` / `leg_concentration_pct`）、`src/sp_drift/panel.py` + `drift_stats.py`（分桶特征源）、`src/sp_drift/replay.py`（`replay_policy` 回测不变量）
- 研究：`docs/research/q_persistence_analysis.md`（单腿 q 无可提取 edge）、`docs/research/sp_drift_phase4.md` + `sp_drift_forward.md`（SP 漂移 / GATE-FT）
- 姊妹文档（分工见 §10）：
  - `docs/strategy/joint_q_correlation_edge.md`（joint_q **度量**：腿间相关性如何改变 P(全中)）
  - `docs/strategy/regime_timing_strategy.md`（**时间维**状态选择器：选哪个 preset / 是否空仓）
  - `docs/strategy/walk_forward_strategy_evaluation.md`（评估骨架）
  - `docs/strategy/low_mid_sp_high_n_experiment.md`、`single_match_probability_calibration.md`、`inplay_sp_timing_filter.md`

---

## 1. 背景与动机

`q_persistence_analysis.md` 的结论是硬约束：**单腿 q 在任何切口（整体 / 联赛 / 选项）都是围绕 ~0.82 的 iid 噪声，无可利用的趋势或持续性**（lag-1 自相关 ≈ 0，联赛级跨段相关 −0.745，逆向均值回归方向真实但中心 0.82 < 1 仍不可盈利）。也就是说——**靠「挑出好的单腿」择时这条路是死的**。

但「单腿不可择」不等于「组合不可构造」。本设计转向一个**结构不同的假设**：某些比赛日整体处于一个**共同宏观状态**（主队强势日、低赔热门日、冷门日、杯赛混乱日、某联赛集体偏差……），同状态下多条腿的结果不是独立的。如果能识别这些状态，就可以让**每张组合票代表一个状态假设**（"押今天是主队强势日"），而不是把 top-q 单腿盲目串起来。

**核心可行性前提（护栏，不可省）**：北单的结构地板始终在——
- 抽水 `RETURN_RATE = 0.65`（`src/combo_optimizer/types.py`、`services.py::_q_stat`）。
- SP 漂移乘法：命中腿计划 SP→结算 SP 约 **−16.6%**（`sp_drift_phase4.md`），串 4 关时 `0.836⁴ ≈ 0.49` 的乘法侵蚀。

在独立假设下，把腿串起来**只会让 P(全中) = ∏ p_i 越来越小**，组合 EV = `0.65 × ∏(p_i × SP_i)`，每多一关乘一次 < 1 的因子。**因此「押状态」要值得做，唯一的理由是：状态本身让 `P(全中)` 显著高于各腿独立概率之积（正向共振），其增益要足以抵过 0.65 × 漂移的地板。** 这是本设计的可行性闸门，不是锦上添花。

```
组合可行   ⟺   P(全中 | 状态)  >  ∏ p_i              （正向共振）
            且   0.65 × E[∏ SP | 全中 ∧ 状态] × P(全中|状态)  >  1   （过盈亏平衡线）
```

若状态带来的是腿间**正相关但无概率增益**（只是"同涨同跌"），那它只会放大尾部：要么全中、要么全灭，方差暴涨而均值不动甚至更差——这是**有害相关**，必须与"有利共振"严格区分（§4）。

---

## 2. 设计原则

1. **押状态，不押单腿**：每张票编码一个**可证伪的状态假设**；票的合理性来自"该状态今天成立"的判断，而非"这几条腿 q 高"。
2. **正向共振是唯一买点**：仅当离线证据显示某状态下 `P(全中) > ∏ p_i` 且能跨过 `0.65 ×` 地板时，才允许构造该状态票。无共振 → 不构造（等价空仓）。
3. **有利共振 vs 有害相关分离**：状态用于**提升联合命中概率**时是资产；状态只是**让腿同向波动**时是负债（放大全军覆没）。两者用不同度量门控（§4、§5）。
4. **离线标注先行 + shrinkage**：样本极薄（504 腿 / 10 期，状态级更稀疏），任何状态级 q/命中率必须收缩到全局先验，禁止用稀疏格的点估计直接下注（§7）。
5. **只用决策时可见信息**：状态标注只能用 `decision_ts` 之前已结算数据 + 当期候选池快照（含决策时 SP / 欧赔），对齐 `replay.py` 的"决策 SP qualify、真实 SP 结算"不变量。
6. **复用既有护栏**：`passes_concentration_guard`（MIN_QUALIFIED_LEGS=13 / MAX_CONCENTRATION_PCT=60%）、`select_current_issue`（单期次锁定）、`WEEKLY_STAKE_CAP_FRAC=0.25`、`PER_COMBO_STAKE_CAP_FRAC=0.005`，全部保留为状态层之下的硬过滤。

---

## 3. 状态枚举（State Definitions）

状态 = 在 `decision_ts` 对"当期比赛日整体环境"的一个**离散、可前向计算**的刻画。按下列维度构造，**每个维度只用决策时可见或已结算的数据**。数据可用性已核对（见 §3.6）。

### 3.1 维度与数据源

| 维度 | 特征 | 数据源（已核对列名） |
|------|------|----------------------|
| 选项方向 | 票的统一选项（胜/平/负偏好） | leg `selection ∈ {3,1,0}`；`q_buckets().by_option` |
| SP 桶 | 腿 SP 落在 `<3.5 / 3.5-4.5 / 4.5-5 / 5-8 / >8` | `drift_stats.sp_band(sp)`（`_SP_EDGES`） |
| 联赛类型 | tier / comp_type（联赛 vs 杯赛） | `panel.classify_league` / `classify_comp_type`；`q_buckets().by_league` |
| 让球 | 让球分级 | `panel.classify_handicap(handicap_line)`（`hcp_class`） |
| 赛程窗口 | kickoff 时段桶（同日同批集中度） | `services.assign_kickoff_buckets` / `kickoff_bucket_label` |
| 欧赔/北单偏离 | 欧赔隐含概率 vs 北单 SP 隐含概率的差 | snapshots `eu_h/eu_d/eu_a`；settlements `avg_eu_h/avg_eu_d/avg_eu_a`（~99.9% 覆盖） |
| 资金分布（**v2，无数据**） | 选项 vol% 份额 / 池总额 | `vol_pct_*` / `pool_total` 列存在但**全 NULL** → 标 v2，本设计不依赖 |

### 3.2 状态枚举（初始集合，离线标注用）

每个状态是一个**布尔/分级谓词**，对一个期次（或一个 kickoff 桶）求值：

| 状态码 | 名称 | 谓词（决策时可计算） |
|--------|------|----------------------|
| `HOME_STRONG` | 主队强势日 | 当期"胜(3)"选项中低 SP（`sp_band ≤ 3.5-4.5`）腿占比高，且欧赔隐含主胜概率普遍高于北单隐含 |
| `AWAY_STRONG` | 客队强势日 | 对称：低 SP "负(0)" 腿占比高（北单"负"= 客胜方向）+ 欧赔确认 |
| `FAV_LOWSP` | 低赔热门日 | 当期合格腿 SP 普遍落在 `<3.5/3.5-4.5`（热门密集），让球多为浅盘 |
| `UPSET` | 冷门日 | 高 SP（`5-8/>8`）腿占比高，欧赔与北单对热门方向**分歧大**（市场犹豫） |
| `CUP_CHAOS` | 杯赛混乱日 | `comp_type = 杯赛` 腿占比高（轮换 / 单场淘汰 → 方差大、可预测性低） |
| `EU_NB_DIVERGE` | 欧赔-北单偏离日 | `|p_eu − p_nb|` 的池均值超阈（北单定价系统性偏离欧赔，潜在结构偏差） |
| `LEAGUE_SKEW:<lg>` | 特定联赛集体偏差 | 某联赛当期腿数达标且其历史状态 q 显著偏离全局（**仅诊断/收缩后用**，受 §7 约束） |
| `NEUTRAL` | 无显著状态 | 上述均不触发 → 默认，**不构造状态票** |

> 状态是**互斥/半互斥的标签**：一个期次可同时带多个状态标签（如 `FAV_LOWSP` ∧ `HOME_STRONG`），但**票池构造时每张票绑定单一主状态**（§5），避免一张票同时押两个未必同向的假设。

### 3.3 状态特征向量（前向可计算）

对每个 `decision_ts`，由候选池快照 + 历史已结算腿组装：

```
state_features(decision_ts) = {
  # 池结构（决策时 snapshot）
  sp_profile:        {band -> 合格腿占比}            # drift_stats.sp_band 分桶
  option_profile:    {3/1/0 -> 合格腿占比}           # 选项方向分布
  comp_profile:      {联赛/杯赛 -> 占比}             # classify_comp_type
  hcp_profile:       {让球分级 -> 占比}              # classify_handicap
  kickoff_buckets:   assign_kickoff_buckets(...)     # 同批集中度
  eu_nb_gap:         mean(|p_eu - p_nb|)             # eu_* vs SP 隐含概率
  # 历史状态级表现（已结算，shrinkage 后）
  state_q_hat:       {state -> 收缩后 q}             # §7
  state_hit_hat:     {state -> 收缩后命中率}
  state_joint_lift:  {state -> P(全中) / ∏p_i 的估计} # §4 共振度量
}
```

### 3.4 北单 SP 隐含概率 vs 欧赔隐含概率

- 北单隐含：`p_nb(sel) ≈ 1 / (SP_sel × RETURN_RATE)`（含抽水，与 `services.compute_q_drift` 的 `1/(sp*0.65)` 一致）。
- 欧赔隐含：对 `eu_h/eu_d/eu_a` 去 overround 归一得 `p_eu`。
- 偏离 `eu_nb_gap = mean(|p_eu − p_nb|)` 是 `EU_NB_DIVERGE` 的触发量，也是 `UPSET`（分歧大）的辅助信号。

### 3.5 与时间维状态（regime）的边界

`regime_timing_strategy.md` 的 regime 是**纵向**问题——"现在整体环境好不好、该用哪个 preset、要不要空仓"。本文档的状态是**横向**问题——"在一张票内部，押哪个共同状态、票池如何按状态分层"。两者可叠加：regime 决定**是否下注 + 全局 Kelly preset**，本设计决定**下注时票池里各状态怎么配**。

### 3.6 数据可用性结论

- ✅ 可用：`league` / `handicap_line` / `kickoff_ts` / `result_code` / `winning_sp`（matches+settlements）；`eu_h/eu_d/eu_a`（snapshots，~99.9%）、`avg_eu_*`（settlements）。→ 选项 / SP 桶 / 联赛类型 / 让球 / 赛程窗口 / 欧赔偏离 状态**全部可标注**。
- ❌ 不可用：`vol_pct_*` / `pool_total` **全 NULL** → 一切"资金类状态"（公众份额、池规模）**无数据源，标 v2**，本设计不构造此类状态。

---

## 4. 风险收益：共振 vs 相关（核心论证）

### 4.1 状态如何改善 joint probability

设一张 N 腿票全绑同一状态 `S`。独立基线 `P_indep = ∏ p_i`。状态票真实命中：

```
P(全中 | S) = P_indep × Lift(S)
Lift(S) = P(全中 | S) / ∏ p_i        # > 1 = 有利共振；< 1 = 有害（异向）
```

- **`Lift > 1`（有利共振，可利用）**：状态成立时，各腿同向更易一起兑现（例："主队强势日"下多场主胜的共同驱动——主场优势、客队疲劳、裁判倾向等系统因子同时推高）。此时 `P(全中)` 高于独立积，组合 EV 被抬升。这是**唯一**能抵消 `0.65 × 漂移` 地板的来源。
- **`Lift < 1`**：状态使腿**互斥/异向**（例某状态让"今天要么主队赢要么大冷门"）→ 串起来反而更难全中，应避免。

> **joint_q 文档是这里的度量供给方**：`Lift(S)`、腿间相关结构、`P(全中)` 的估计与置信区间，由 `joint_q_correlation_edge.md` 定义和计算；本文档**消费**这个度量来决定"该状态值不值得构造票"。分工见 §10。

### 4.2 双刃：有利共振 vs 有害相关

| | 有利共振（资产） | 有害相关（负债） |
|---|------------------|------------------|
| 概率效应 | `P(全中) > ∏p_i`（Lift>1） | `P(全中) ≈ ∏p_i` 或更低，但**方差暴涨** |
| 收益分布 | 均值抬升，尾部右移 | 均值不动/下降，全中/全灭两极化 |
| 机制 | 共同正向系统因子 | 仅"同涨同跌"，无概率增益 |
| 处置 | 构造该状态票 | **禁止**——退化为一张高方差彩票 |

**关键陷阱（来自本会话发现）**：若状态本质是"**同日同向偏差**"（例整个联赛今天集体被高估），则腿间正相关会让组合**更易全军覆没**——状态判断一旦错，N 腿同时崩。这正是"押状态"的 downside：把 N 个独立小赌注换成 1 个相关大赌注，**赢家诅咒同时作用于所有腿**（呼应 `q_persistence_analysis.md` §4"最近异常热的联赛崩到 0.48"）。

### 4.3 控制"状态判断错误导致全军覆没"

1. **票间状态分散**：票池不押单一状态——按 §5 在 ≥3 个**半互斥**状态间分配票数与注额，单状态失效不致全灭。
2. **状态内 N 上限 + 降 Kelly**：相关性越高的状态，N 越要小（少串关减少乘法侵蚀与共同失效面），Kelly 越要低（沿用 preset 的 per-N kelly，不另放松）。
3. **Lift 置信门控**：仅当 `Lift(S)` 的**收缩后下界 > 1**（不是点估计）才构造该状态票（§7）。
4. **状态命中后验回撤刹车**：连续状态判断错误（状态票全灭）触发降档/空仓，复用 `compute_stats().current_dd` 的回撤底线。

---

## 5. 组合构造算法（票池按状态分层）

### 5.1 与现有 diversity 的区别

现有 `src/combo_optimizer/builder.py` 的 `_greedy_diverse` 用 `score = c.ev − diversity_lambda × Σ leg_count[l]`（按**单腿出现频率**惩罚），`cross_n_lambda` 跨 N 再罚一次。其目标是**降低任一单腿在票池中的频率**（防集中）。

**本设计不同**：不是把单腿摊薄，而是**按状态把票池分层配置**——

| | 现有 diversity_lambda / cross_n_lambda | 本设计：状态分层 |
|---|----------------------------------------|------------------|
| 惩罚对象 | 单腿出现频率（leg_count） | 单状态的票数 / 注额份额超配 |
| 目标 | 没有哪条腿出现太频繁 | 没有哪个**状态假设**暴露太重 |
| 多样性单位 | 腿 | 状态 |
| 暴露控制 | `leg_concentration_pct ≤ 60%`（腿级） | 单状态注额占比 ≤ 上限（状态级，新增） |
| 与共振关系 | 无（纯防集中） | 主动利用 `Lift>1` 的状态、回避 `Lift<1` |

**接入点**：状态分层是 `build_combos` 的**上游配额层**——先按状态把 bankroll 分成几桶，每桶内**复用** `build_combos`（含 diversity_lambda 防单腿过频）。即"状态间用配额、状态内用现有 diversity"。不改 builder 内核。

### 5.2 票池构造算法（伪代码）

```text
function build_scenario_portfolio(db, live_db_path, decision_ts, bankroll):
    # 0. 单期次锁定 + 候选池（复用 services 前段）
    snaps = load_open_matches(live_db_path)
    issue = select_current_issue(snaps)                  # 跨期次绝不混
    if issue is None: return EMPTY, "no_issue"
    pool = [s for s in snaps if s.issue == issue]

    # 1. 标注当期状态 + 取每个状态的共振度量（shrinkage 后）
    feats  = state_features(decision_ts)                 # §3.3
    states = active_states(feats)                        # 触发的状态标签集合
    # 仅保留“可利用”状态：收缩后 Lift 下界 > 1 且能过 0.65 地板
    usable = [S for S in states
              if lift_lower_bound(S, feats) > 1.0
              and breaks_even(S, feats)]                 # §4.1 闸门
    if not usable: return EMPTY, "no_resonant_state"     # 等价空仓

    # 2. 状态间配额：按 Lift 强度 × 置信度分配 bankroll，单状态封顶
    weights = normalize({S: lift_score(S) for S in usable})
    weights = cap_per_state(weights, max_state_frac)     # 单状态注额上限（状态级反集中）

    # 3. 每状态内：用绑定该状态的腿子集，复用现有 builder
    tickets = []
    cross_used = set()
    for S in sorted(usable, key=weights.get, reverse=True):
        legs_S = legs_matching_state(pool, S, feats)     # 该状态的合格腿（同向、同桶）
        N_S    = n_for_state(S)                          # 相关性越高 → N 越小
        plan_S = build_weekly_plan(                      # 复用 phase5a → combo_optimizer
                    legs_S, bankroll=bankroll*weights[S],
                    n_legs=N_S, kelly_fraction=kelly_for(S),
                    diversity_lambda=DIV_LAMBDA,         # 状态内仍防单腿过频
                    cross_n_lambda=CROSS_LAMBDA,
                    weekly_stake_cap_frac=WEEKLY_STAKE_CAP_FRAC)
        for t in plan_S.tickets:
            t["state"] = S                               # 每张票标注其状态假设
        tickets += plan_S.tickets

    # 4. 既有护栏（腿级，状态层之下）
    ok, why = passes_concentration_guard(
        n_qualified_legs=len(unique_legs(tickets)),
        concentration_max_pct=leg_concentration_pct(tickets))
    if not ok: return EMPTY, why                          # MIN=13 / MAX=60%
    return tickets, "scenario_portfolio"
```

### 5.3 状态互斥/半互斥约束

- **一票一状态**：每张票只绑一个主状态（`t["state"]`），不在一张票里混押两个假设。
- **腿不跨状态重复暴露**：同一 `(match_id, selection)` 腿原则上只进一个状态桶（取其最强归属状态），避免"换个状态标签重复押同一腿"——这是与单纯 diversity 的关键差异（diversity 只看频率，不看是不是同一暴露被包装成多状态）。
- **半互斥状态可共存**：如 `FAV_LOWSP` 与 `HOME_STRONG` 可同时配票（它们半独立），但 `UPSET` 与 `FAV_LOWSP` 互斥（不可同期都重配）。

---

## 6. 风险底线（硬约束，复用 services 常量）

| 底线 | 阈值 | 来源 | 触发 |
|------|------|------|------|
| 候选腿不足 | `MIN_QUALIFIED_LEGS = 13` | `passes_concentration_guard` | EMPTY |
| 腿级集中度 | `MAX_CONCENTRATION_PCT = 60%` | `passes_concentration_guard` / `leg_concentration_pct` | EMPTY |
| 单状态注额上限（新增） | `max_state_frac`（建议 0.40） | 本设计 §5.2 | 截断到上限 |
| 共振未达标 | `Lift 下界 ≤ 1` 或 过不了 0.65 地板 | §4.1 闸门 | 该状态不构造 |
| 周投入上限 | `WEEKLY_STAKE_CAP_FRAC = 0.25` | `build_weekly_plan` | 截断 |
| 单组合上限 | `PER_COMBO_STAKE_CAP_FRAC = 0.005` | planner 内生效 | 已生效 |
| Kelly 上限 | preset per-N kelly ≤ 全局 `1/16` | preset / `services` | 拒绝该状态配置 |
| 回撤刹车 | `current_dd ≥ 0.25` | `compute_stats().current_dd` | 降档/空仓 |

> 状态层**只会更保守**，绝不放松腿级护栏；`Lift` 门控不达标即等价空仓。

---

## 7. 离线标注 + Shrinkage（样本薄的硬约束）

样本：504 已结算腿 / 10 期。按状态切分后**每格极稀疏**（部分状态可能 <30 腿）。约束：

1. **状态 q / 命中率 / Lift 一律收缩**：`q_hat(S) = w·q_S + (1−w)·q_global`，`w = n_S / (n_S + k)`（经验贝叶斯，`k` 在标定期冻结）。`q_global = 0.82`（`q_persistence_analysis.md` grand-mean）。**禁止用稀疏格点估计直接下注**。
2. **Lift 用下界，不用点估计**：`lift_lower_bound(S)` 取收缩后估计的置信下界（bootstrap over issues）。这直接回应 `q_persistence_analysis.md` §4 的"小样本回归均值假象"——只有下界稳定 > 1 才认。
3. **时间因果**：状态标注与 `state_q_hat` 只用 `decision_ts` 之前已结算腿（沿用 `collect_settled_legs` 的天然过去性），禁止用当期/未来结果回标状态。
4. **预注册阈值并冻结**：`max_state_frac / k(shrinkage) / lift 显著性 / eu_nb_gap 触发阈 / N_for_state` 在标定期一次确定后冻结，对齐 `sp_drift/forward.py` 风格（`MIN_COMBOS=200 / MAX_WEEKS=12 / MARGIN=0.05`）。
5. **方向优先于量级**：与 regime 选择器同理——只在状态的**方向**（Lift 符号 + 下界）上行动，不押稀疏样本的精确量级（GATE 3 教训）。

---

## 8. 评估指标

| 指标 | 定义 | 来源 |
|------|------|------|
| 状态命中率 | 每状态绑定票的全中率 vs 该状态独立基线 | `settle_plans` / `winning_tickets_for_plan` |
| 状态内 joint_q | `0.65 × E[∏ SP \| 全中] × P(全中\|S)`，按状态分组 | joint_q 文档度量 + `_q_stat` |
| Lift 实现值 | 事后 `P(全中\|S) / ∏ p_i`，与事前下界对比 | joint_q 文档 |
| 跨状态相关性 | 不同状态票 PnL 的相关矩阵（应低 → 分散有效） | `equity_series` 派生 |
| 收益分布 | 每状态 PnL 直方图 / 分位（看是否两极化=有害相关） | settlements_log |
| 回撤 | `max_drawdown` / `current_dd` | `compute_stats` |
| 空仓率 | `no_resonant_state` 触发占比（坏区应高） | regime/scenario 决策记录 |
| 状态分层 vs 现有 diversity | 同样本 ROI / maxDD / Sharpe 对照 | `replay_policy` |

**判据**：状态分层组合的 ROI ≥ 现有 diversity 票池**且** maxDD 不劣；状态命中率显著高于该状态独立基线（Lift>1 被实盘/回放确认）；跨状态相关性低（分散真实有效）。任一不达标 → 否决该状态或全盘退回 diversity。

---

## 9. 实验计划（预注册、可证伪）

- **GATE-S0（离线状态标注）**：对历史 10 期每期 / 每 kickoff 桶标注 §3 状态标签，产出 `state × outcome` 表。**判据**：状态可稳定标注（覆盖率、互斥性合理），且至少一个状态的 `Lift 下界 > 1`（收缩后）。无任何状态过闸 → 早停，结论"无可利用共振"，方向证伪。
- **GATE-S1（离线回放对照）**：用 `replay.py::replay_policy` 跑三臂——`scenario_portfolio` vs 固定 `diversity`（现有 builder）vs `always-skip`，walk-forward（每 `decision_ts` 只用过去数据标状态）。**判据**：scenario 全期 ROI ≥ diversity，且坏区（2026-05-22 后切片）ROI ≥ always-skip。冻结 §3/§5/§7 阈值。
- **GATE-S2（影子模式）**：每期记录状态标注 + 假想票池 + what-if PnL，不改实盘（实盘仍跑现行策略）。运行 ≥ 8 期或 ≥ 200 已结算腿（对齐 `forward.py` MIN_COMBOS）。**判据**：影子 PnL ≥ 实盘基线，状态命中后验与事前 Lift 一致。
- **GATE-S3（小额真钱）**：通过 S2 后，限动作于"已验证过闸的状态"，bankroll 折半，单状态封顶。**停止规则**：`current_dd > 0.50` 立即停（对齐 MAXDD_STOP）。

每个 GATE 产出 `docs/research/scenario_portfolio_*.md`（ledger + equity 图 + go/no-go/uncertain verdict），不事后改阈值。

---

## 10. 最小可行版本（MVP）

MVP = **离线标注 + 离线回放**，纯只读，零真钱。按依赖顺序：

1. **M1 状态标注器**（纯函数，复用现有）：`annotate_states(panel, decision_ts) -> {issue: [state_labels]}`，调 `panel.build_snapshot_panel` + `drift_stats.sp_band` + `classify_*` + `assign_kickoff_buckets` + eu_* 偏离计算。无新算法，只组装。
2. **M2 共振度量 + shrinkage**：`state_lift(states, settled_legs)` → 收缩后 `q_hat / Lift 下界`（§4、§7）。度量公式向 `joint_q_correlation_edge.md` 对齐/复用。带单测（构造 Lift>1 / <1 / 样本不足用例）。
3. **M3 状态分层票池**：`build_scenario_portfolio`（§5.2），状态间配额 + 状态内复用 `build_weekly_plan`/`build_combos`。**不改 builder 内核**。
4. **M4 回放对照**：接 `replay_policy` 跑 scenario vs diversity vs skip（GATE-S1）。
5. **M5 报告**：产出 GATE-S0/S1 的 `docs/research/scenario_portfolio_*.md`。

MVP 完成判据：10 期状态可稳定标注、至少一个状态 Lift 下界 > 1（或明确证伪）、回放对照可复现。**M1–M5 全不调用 place，零真钱风险。**

YAGNI（MVP 不做）：
- 不做资金类状态（`vol_pct/pool_total` 全 NULL，标 v2）。
- 不改 `build_combos` / planner 内核（只在其外做状态配额与门控）。
- 不引入在线 bandit / 自动权重（样本太薄，同 regime 文档 §5.1 结论）。
- 不接临近开赛 SP 落地（属 `inplay_sp_timing_filter.md`）。
- 不动 `kickoff_window_hours`（保持 0，已知无窗口值两全）。

---

## 11. 与姊妹文档的分工

| 文档 | 关系 / 分工 |
|------|-------------|
| `joint_q_correlation_edge.md` | **度量供给方**：定义并计算 `Lift(S)`、腿间相关结构、`P(全中)` 及其置信区间。本文档**消费**这些度量来决定"哪个状态值得构造票"。joint_q = "腿间相关性如何改变联合命中"；本文档 = "按状态把票池构造/分层出来"。 |
| `regime_timing_strategy.md` | **纵向 vs 横向**：regime 是时间维状态选择（这一期用哪个 preset / 是否空仓）；本文档是票池内状态覆盖（下注时各状态如何分层配票）。两者叠加：regime 决定是否下注 + 全局 Kelly，本文档决定票池内部结构。 |
| `walk_forward_strategy_evaluation.md` | 提供 §7/§9 的 walk-forward 评估骨架；本文档是其上的"状态驱动组合"消费者。 |
| `q_persistence_analysis.md` | 提供本文档的出发点（单腿 q 无 edge → 转押状态）与护栏（grand-mean 0.82、小样本回归均值假象 → shrinkage + Lift 下界）。 |
| `single_match_probability_calibration.md` | 改善 `p_i`，直接抬升 Lift 估计与状态命中率的信号质量。 |
