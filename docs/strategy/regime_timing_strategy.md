# 动态择时 / 局部最优策略选择器 — 设计稿

**日期**: 2026-06-23
**作者**: Claude（承接 kanban t_7f4b283a）
**状态**: 设计稿，待评审 → 转 writing-plans
**关联**:
- 代码：`src/webui/services.py`、`src/webui/strategies.py`（REGISTRY S1–S11）、`src/sp_drift/forward.py`、`src/phase5a/filter.py`
- 研究：`docs/research/sp_drift_phase4.md`（GATE 3）、`docs/research/sp_drift_forward.md`（GATE-FT pending）
- 姊妹文档（4 份，并行设计）：
  - `docs/strategy/low_mid_sp_high_n_experiment.md`（低/中 SP 高 N 实验）
  - `docs/strategy/single_match_probability_calibration.md`（单场概率校准）
  - `docs/strategy/inplay_sp_timing_filter.md`（临近开赛 SP 时机过滤）
  - `docs/strategy/walk_forward_strategy_evaluation.md`（walk-forward 评估框架）

---

## 1. 背景与动机

实盘在 **2026-05-22 之后明显转坏**。当前固定 custom 参数把「历史 edge」当成常数，但 edge 不是常数：

- **q 定义** = `p_final × SP` = 已实现回报代理。北单 `RETURN_RATE = 0.65`（见 `src/niche_analysis/sp_native.py`、`src/phase5a/filter.py` 的 `return_rate`）。`src/webui/services.py:_q_stat` 里 q 的工程实现为 `RETURN_RATE × Σ(命中腿 SP) / n`，即每腿已实现回报倍数。q < 1 即负 EV。
- **各 N 的每腿 break-even q**（组合 q 需满足 `q^N ≥ 1/RETURN_RATE`，等价 per-leg 阈值）：

  | N | break-even per-leg q |
  |---|----------------------|
  | 2 | ≈ 1.240 |
  | 3 | ≈ 1.154 |
  | 4 | ≈ 1.114 |
  | 5 | ≈ 1.090 |
  | 7 | ≈ 1.064 |

  N 越大，每腿 q 门槛越低——这正是「低/中 SP 高 N」方向的理论依据（姊妹文档 `low_mid_sp_high_n_experiment.md`）。
- **SP 漂移**：命中腿平均计划 SP **4.05** vs 结算 SP **3.36**（约 **−16.6%**），不利漂移远多于有利。实盘整体 **q ≈ 0.838 < 1（负 EV）**。
- **GATE 3 / GATE-FT**：决策时机（从 ~18h-out 移到临近开赛）是巨大杠杆，但样本薄、量级不可信，forward-test 仍 pending（`docs/research/sp_drift_forward.md`）。

**核心判断**：固定全局最优参数在一个非平稳市场里必然滞后。用户明确——**局部时期最优可接受，不需要全局最优**。本设计提出一个**按近期 regime 选择策略（含空仓）的择时选择器**，把「edge 是常数」这个错误假设换成「edge 随 regime 变化，且我们只在能识别出有利 regime 时下注」。

**当前状态**：auto 暂停，生产默认已切到低风险 **S9（跨 N 多样化 30/40/30，K=1/32，max=200，cross_n_lambda=0.5）**。本选择器以 S9 为「保守锚点」，向上仅在证据充分时切换，向下随时退到 skip。

---

## 2. 设计原则

1. **不追全局最优**：不存在一组「永远最好」的参数。目标是**在每个时期挑当期数据支持的较优策略**，并在没有任何策略有正 edge 时**空仓**。
2. **空仓是一等公民**：`skip / no-bet` 与 S1–S11 平级，是选择器的合法输出，不是异常。负 EV 时空仓的期望收益（0）严格优于下注。
3. **只用当期之前的数据**（walk-forward）：选策略所用的全部指标，必须只基于 `decision_ts` 之前已结算的腿。严禁用事后最优参数。详见 §6 与姊妹文档 `walk_forward_strategy_evaluation.md`。
4. **风险底线先于收益**：任一底线触发即强制空仓或降档，不被「选择器觉得这个 regime 好」覆盖。
5. **可解释**：每次决策必须能在周报里回放「为什么选了这个策略/为什么空仓」，附触发的指标值。
6. **复用既有护栏**：`passes_concentration_guard`、`select_downweight_leagues`、`select_current_issue`、NicheConfig 黑名单/q_min，全部保留，作为选择器之下的硬过滤层。

---

## 3. Regime 定义

Regime = 在 `decision_ts` 时刻，对「当前可下注环境是否有利」的刻画。用以下**可观测、可前向计算**的特征向量描述（全部只用 decision_ts 之前的已结算数据 + 当期候选池快照）：

### 3.1 近期已实现表现（lookback，rolling window）
来源：`collect_settled_legs` + `_q_stat` / `q_buckets`（`src/webui/services.py`）。

| 特征 | 定义 | 来源 |
|------|------|------|
| `q_recent` | 最近 N 条已结算腿的 q（`_q_stat(legs)['q']`） | `_q_stat` |
| `q_recent_n` | 该窗口腿数（样本量，用于置信度门控） | `_q_stat` |
| `hit_rate_recent` | 最近窗口命中率 | `_q_stat` |
| `avg_sp_settled` | 最近命中腿平均结算 SP | `_q_stat` |
| `q_by_league` | 分联赛 q（识别局部坏区） | `q_buckets().by_league` |
| `q_by_option` | 分选项（胜/平/负）q | `q_buckets().by_option` |
| `downweight_leagues` | 当前应临时降权/拉黑的联赛 | `select_downweight_leagues(min_n=8, q_threshold=0.7)` |

窗口建议**双窗**：`N_legs ∈ {最近 30 腿, 最近 60 腿}`，同时辅以**时间窗**（最近 N 期 issue，建议 4 期与 8 期），取「腿数达标且时间不过期」者。短窗灵敏、长窗稳，两者背离时降档（见 §5 状态机）。

### 3.2 当期候选池结构（snapshot，下注前可见）
来源：`diagnostic_legs` / `generate_plan` 的池统计、`leg_concentration_pct`、HHI。

| 特征 | 定义 | 来源 |
|------|------|------|
| `current_issue` | 当前应下注期次 | `select_current_issue` |
| `n_open_matches` | 当期开放比赛数 | `load_open_matches` |
| `n_qualified_legs` | 通过 niche 规则的合格腿数 | `diagnostic_legs.qual_count` / plan 字段 |
| `concentration_max_pct` | 单腿最大票面占比 | `leg_concentration_pct` |
| `hhi` / `effective_n_legs` | 候选集中度（HHI 及其倒数） | `generate_plan` 已算 |
| `qual_by_option` | 合格腿按胜/平/负分布 | `diagnostic_legs.qual_count` |
| `league_spread` | 候选覆盖的不同联赛数 | 派生 |

### 3.3 SP 漂移 / 时机维度
来源：`src/sp_drift/forward.py`（`HAIRCUT_MAP`、arm 框架）、`compute_q_drift`。

| 特征 | 定义 | 来源 |
|------|------|------|
| `sp_drift_recent` | 最近命中腿（计划 SP − 结算 SP）/ 计划 SP | 派生（基线 −16.6%） |
| `q_drift` | 最近 90 天实盘 q vs baseline 0.71 | `compute_q_drift` |
| `band_haircut_load` | 候选腿按 `HAIRCUT_MAP` 加权后的预期漂移负担 | `HAIRCUT_MAP` |
| `pool_sp_profile` | 候选腿 SP 桶分布（`<3.5/3.5-4.5/4.5-5/5-8/>8`） | `kickoff_bucket_label` 同款分桶逻辑 |

> 注：`sp_drift/forward.py` 的 window 是「期内每场各取距开赛 180min 的 SP」的池化口径，与实盘 `kickoff_window_hours`（距现在 N 小时同时性过滤）**不等价**（见 `sp_drift_forward.md` 运营口径差）。本设计的 regime 维度**只用漂移的方向与负担作为降档/空仓信号**，不依赖临近决策的精确落地——后者属姊妹文档 `inplay_sp_timing_filter.md`。

### 3.4 Regime 标签（派生，供人读 + 状态机用）
把上述特征压成一个**离散标签**（便于周报与状态机阈值）：

- `GREEN`（有利）：`q_recent ≥ q_go` 且样本量达标 且 漂移负担正常 且 池结构健康。
- `AMBER`（中性/不确定）：指标混合，或短长窗背离，或样本不足。
- `RED`（不利）：`q_recent < q_skip`，或漂移负担过重，或池结构触发护栏。

阈值（初始，待 walk-forward 标定，见 §7）：

```
q_go    = 1.05    # per-leg q，留 break-even 之上的安全边际（N=3 阈 1.154，N=4 阈 1.114）
q_skip  = 0.95    # 低于此一律空仓
min_q_n = 30      # q_recent 的最小腿数，不足则视作 AMBER（样本不足）
```

---

## 4. 策略候选（动作空间）

选择器在每个 `decision_ts` 从下列离散动作中选一个。S 编号对应 `src/webui/strategies.py` 的 REGISTRY，可直接 `apply_strategy(db, sid)` 落地（写入 `mix_enabled` + per-N weights/kelly/lambda + max_combos + league_q_min + cross_n_lambda）。

| 动作 | 含义 | 对应 REGISTRY / 实现 |
|------|------|----------------------|
| `SKIP` | 空仓，不生成计划 | 不调用 `generate_plan`（或生成后不 place） |
| `LOW_N2N3` | 低风险、小 N、低 Kelly | S1「稳健」(0.30/0.40/0.30, K=1/32) 或 S7「纯 N=3」 |
| `S9_ANCHOR` | 当前生产默认锚点 | **S9 跨 N 多样化**（30/40/30, K=1/32, max=200, cross_n_lambda=0.5） |
| `CURRENT_N4` | 当前 N=4 主力 | S3/S4/S8 一类 N=4 偏重 preset |
| `LOWMID_SP_HIGH_N` | 低/中 SP + 高 N | S2/S10/S11（含 N=5）+ `league_q_min` 门控；详见姊妹 `low_mid_sp_high_n_experiment.md` |

约束：
- **动作只能在已注册 preset 中选**（保证可复现、可 round-trip via `match_strategy`）。若需要新 preset，先加进 REGISTRY 再纳入动作空间，不允许选择器临时合成参数。
- 每个动作天然带各自的 per-N Kelly 上限；选择器**不另调 Kelly**，只在 preset 之间切换 + 叠加全局风险底线（§5）。

---

## 5. 策略选择逻辑

### 5.1 方案对比：状态机 vs contextual bandit

| 维度 | 规则状态机（MVP 选型） | Contextual bandit |
|------|------------------------|-------------------|
| 可解释性 | 高（阈值即理由，直接进周报） | 低（权重难解释） |
| 数据需求 | 低（几十条腿即可起步） | 高（北单每期样本极稀，命中个位数，bandit 极易过拟噪声） |
| 过拟合风险 | 低（人定阈值，可 walk-forward 标定） | 高（在 ~5 周/个位数命中样本上学权重不可信，见 GATE 3 教训） |
| 探索成本 | 无（确定性） | 有（探索 = 在负 EV 期下注，真金亏损） |
| 落地复杂度 | 低（复用现有 services 指标） | 高（需 reward 归因、特征工程、离线评估闭环） |

**结论**：MVP 用**规则驱动的状态机**。当前样本量（每期个位数命中、forward 仅 1.3 周）下，bandit 的探索成本是真金亏损，且无法在如此稀疏样本上稳定学到权重——这正是 GATE 3「量级不可信」的同类陷阱。**Contextual bandit 列为 Phase 3 远期选项**，仅当累计已结算样本足够（建议 ≥ 500 已结算腿且 ≥ 12 期）、且离线 walk-forward 证明其稳定优于状态机时再考虑，且永远保留风险底线作为硬约束（bandit 只在底线允许的动作子集内探索）。

### 5.2 决策流程（伪代码）

```text
function select_action(db, live_db_path, decision_ts):
    # ---- 0. 硬底线：任一触发 → SKIP ----
    pool = build_pool_snapshot(db, live_db_path, decision_ts)   # 复用 generate_plan 前段
    if select_current_issue(pool.snaps) is None:               # 无可下注期次
        return SKIP, reason="no_issue"

    ok, why = passes_concentration_guard(
        n_qualified_legs=pool.n_qualified_legs,
        concentration_max_pct=pool.concentration_max_pct)       # MIN=13, MAX=60%
    if not ok:
        return SKIP, reason=why                                 # 候选腿不足 / 集中度过高

    legs = collect_settled_legs(db, live_db_path)               # 只含已结算（= decision_ts 之前）
    legs = rolling_window(legs, n=30) and rolling_window(legs, n=60)
    short = _q_stat(window_30); long = _q_stat(window_60)

    if short.n < min_q_n:                                       # 样本不足
        regime = AMBER
    elif short.q < q_skip:                                      # 近期 q 太低
        return SKIP, reason=f"q_recent={short.q:.3f} < {q_skip}"
    elif sp_drift_load(pool) > drift_skip_threshold:            # 漂移负担过重
        return SKIP, reason="drift_load_high"

    # ---- 1. 联赛/选项级降权（喂回 niche_config 黑名单） ----
    dw = select_downweight_leagues(q_buckets(legs).by_league,   # min_n=8, q<0.7
                                   min_n=8, q_threshold=0.7)
    apply_temp_blacklist(db, [lg for lg, _ in dw])              # 写 league_blacklist 配置

    # ---- 2. regime → 动作（状态机） ----
    regime = classify_regime(short, long, pool)                 # GREEN / AMBER / RED
    if regime == RED:
        return SKIP, reason="regime_red"
    if regime == AMBER:
        return LOW_N2N3 or S9_ANCHOR, reason="regime_amber→conservative"
    # GREEN：在 break-even 余量内挑当期最优 preset
    action = pick_best_preset_walk_forward(legs, pool)          # 见 §6 §7
    return action, reason="regime_green"

function classify_regime(short, long, pool):
    if short.q >= q_go and long.q >= q_skip and pool healthy:
        return GREEN
    if short.q < q_skip or long.q < q_skip:
        return RED
    return AMBER     # 含短长窗背离
```

### 5.3 决策状态机（图）

```
                ┌─────────────────────────────┐
                │  decision_ts（每期/每桶触发） │
                └───────────────┬─────────────┘
                                ▼
        ┌──────────────── 硬底线检查 ────────────────┐
        │ no_issue / 候选腿<13 / 集中度>60% /          │
        │ q_recent<q_skip / 漂移负担过重 / 周投上限     │──触发─► [ SKIP ]
        └───────────────────────┬────────────────────┘
                                ▼ 全部通过
                       ┌────────────────┐
                       │ classify_regime│
                       └───┬───────┬────┘
                  RED ◄────┘       └────► GREEN
                   │        AMBER          │
                   ▼          │            ▼
                [ SKIP ]      ▼     pick_best_preset
                       [ LOW_N2N3 /        │ (walk-forward,
                         S9_ANCHOR ]       │  仅当期之前数据)
                                           ▼
                              [ CURRENT_N4 / LOWMID_SP_HIGH_N
                                / S9_ANCHOR ]
```

---

## 6. 风险底线（硬约束，先于收益）

任一触发即**强制空仓或降档**，不可被选择器的「regime 觉得好」覆盖。复用 `src/webui/services.py` 既有常量与函数：

| 底线 | 阈值 | 来源 / 实现 | 触发动作 |
|------|------|-------------|----------|
| 最大 Kelly | 各 preset 自带 per-N kelly（如 S9 = 1/32），全局上限 `KELLY_FRACTION = 1/16` | `services.py` 常量、preset kelly 元组 | 超限拒绝该 preset |
| 周投入上限 | `WEEKLY_STAKE_CAP_FRAC = 0.25`（25% bankroll） | `build_weekly_plan(weekly_stake_cap_frac=...)` | 截断到上限 |
| 单组合上限 | `PER_COMBO_STAKE_CAP_FRAC = 0.005`（0.5%） | `services.py` 常量 | 已在 planner 生效 |
| 候选腿不足 | `MIN_QUALIFIED_LEGS = 13` | `passes_concentration_guard` | SKIP |
| 集中度过高 | `MAX_CONCENTRATION_PCT = 60%` | `passes_concentration_guard` | SKIP |
| 近期 q 过低 | `q_recent < q_skip (0.95)` 且样本达标 | `_q_stat` / `collect_settled_legs` | SKIP |
| 联赛 q 过低 | 分联赛 `q<0.7 over n≥8` | `select_downweight_leagues` | 临时拉黑该联赛 |
| 漂移负担过重 | 候选 `band_haircut_load` 超阈 | `HAIRCUT_MAP` 加权 | SKIP 或降档 |
| 回撤刹车（新增） | 当前 `current_dd ≥ dd_brake (建议 25%)` | `compute_stats().current_dd` | 强制降到 LOW_N2N3，连续两期则 SKIP |

> 周投入上限与单组合上限已在 `build_weekly_plan` 内生效；本选择器**不放松**它们，只可能更保守（在 AMBER/RED 进一步降 Kelly preset 或空仓）。

---

## 7. 避免过拟合（walk-forward）

详细框架见姊妹文档 `walk_forward_strategy_evaluation.md`，本节给出与选择器耦合的关键约束：

1. **时间因果**：`decision_ts` 选策略时，`collect_settled_legs` 天然只返回已结算腿（即过去），不会泄漏未来。任何新增指标必须保持此性质——**禁止用当期或未来比赛结果回选策略**。
2. **不用事后最优参数**：`pick_best_preset_walk_forward` 在每个 `decision_ts` 只对**截至该时刻**的滚动样本评估各 preset 的 what-if 表现（复用 `src/sp_drift/replay.py` / `forward.py` 的 replay 不变量：决策时 SP qualify/sizing，真实 SP 结算），取当期较优者。绝不用全样本回看挑「历史最佳 preset」。
3. **预注册阈值**：`q_go / q_skip / min_q_n / dd_brake / drift_skip_threshold` 在标定期一次性确定后**冻结**，对齐 `sp_drift/forward.py` 的 `MIN_COMBOS=200 / MAX_WEEKS=12 / MARGIN=0.05 / MAXDD_STOP=0.50` 风格，避免事后挑数。
4. **滚动重标定**：阈值每 `K` 期（建议 8 期）才允许重标一次，且重标只能用重标点之前数据；每次重标记录入版本日志（regime_decisions 表，见 §8）。
5. **样本门控**：`min_q_n` 不达标时一律降到 AMBER，宁可保守。GATE 3 的核心教训是「方向可信、量级不可信」——本选择器只在方向（q 符号、漂移符号）上行动，不押注稀疏样本的量级。

---

## 8. 需要新增的数据结构、配置项、Dashboard、周报字段

### 8.1 数据结构 / 表（webui DB）

```
-- 新增表：每次选择器决策的审计记录（可回放“为什么这样选”）
CREATE TABLE regime_decisions (
    decision_ts      TEXT PRIMARY KEY,   -- ISO，对应一次择时
    issue            TEXT,               -- select_current_issue 结果
    regime_label     TEXT,               -- GREEN / AMBER / RED
    action           TEXT,               -- SKIP / S1 / S7 / S9 / ...
    reason           TEXT,               -- 触发的指标/底线（人读）
    q_recent_short   REAL,               -- _q_stat(window_30).q
    q_recent_long    REAL,               -- _q_stat(window_60).q
    q_recent_n       INTEGER,
    sp_drift_load    REAL,
    n_qualified_legs INTEGER,
    concentration_max_pct REAL,
    current_dd       REAL,               -- compute_stats().current_dd
    downweighted_leagues TEXT,           -- JSON 数组
    thresholds_version TEXT              -- 当时生效的阈值版本
);
```

复用对象（无需新建）：`BankrollState`、`q_buckets` 返回结构、`diagnostic_legs` 返回结构。

### 8.2 配置项（`db.set_config` 键）

| 键 | 默认 | 说明 |
|----|------|------|
| `regime_selector_enabled` | `0` | 总开关；MVP 默认 OFF（影子模式） |
| `regime_q_go` | `1.05` | GREEN 门槛 |
| `regime_q_skip` | `0.95` | SKIP 门槛 |
| `regime_min_q_n` | `30` | q_recent 最小腿数 |
| `regime_window_short` | `30` | 短窗腿数 |
| `regime_window_long` | `60` | 长窗腿数 |
| `regime_dd_brake` | `0.25` | 回撤刹车 |
| `regime_drift_skip` | `<待标定>` | 漂移负担空仓阈 |
| `regime_anchor_sid` | `S9` | AMBER 默认锚点策略 |
| `regime_thresholds_version` | `v1` | 阈值版本号 |

> 选择器仍通过既有 `apply_strategy(db, sid)` 落地动作，不引入第二套参数写入路径。

### 8.3 Dashboard 展示

- **当前 regime 卡片**：大字 `GREEN/AMBER/RED` + 本期 action + reason；q_recent（短/长窗）、样本量、当前 dd。
- **regime 时间线**：近 N 期 regime_label 与 action 的色带（绿/黄/红 + SKIP 灰），叠加 equity 曲线（`equity_series`），直观看「坏区是否空仓」。
- **底线灯板**：8 条底线（§6）的当前状态（绿/红），红灯标注触发值。
- **候选池健康**：`n_qualified_legs` / `concentration_max_pct` / `hhi`（复用 `generate_plan` 已算字段）。
- **联赛降权列表**：`select_downweight_leagues` 输出 + 原因串。

### 8.4 周报字段（接 `docs/research/` 周报风格）

```
## 择时选择器 — 本期
- decision_ts / issue：…
- regime：AMBER（短窗 q=1.01，长窗 q=0.97，样本 34 腿）
- action：S9_ANCHOR（reason：regime_amber→conservative）
- 底线：候选腿 18≥13 ✓ / 集中度 41%≤60% ✓ / current_dd 12% < 25% ✓
- 降权联赛：[联赛A (q=0.61, n=11)]
- 阈值版本：v1（冻结于 2026-06-23）
## 复盘
- 上期 action 的已结算 q / PnL vs 当期所选 preset 的 what-if（walk-forward 口径）
```

---

## 9. 实验计划

对齐 GATE 风格，预注册、分阶段、可证伪：

- **GATE-R0（离线回放标定）**：在历史已结算数据上跑 walk-forward（`replay_policy`），对每个 `decision_ts` 比较「选择器动作」vs「固定 S9」vs「固定 custom（实盘旧参数）」vs「always-skip」。**判据**：选择器在 2026-05-22 之后的坏区切片上，ROI ≥ always-skip（即至少没在坏区乱下注），且全期 ROI ≥ 固定 S9。冻结 §3/§5 阈值。
- **GATE-R1（影子模式 / paper）**：`regime_selector_enabled=0`，选择器每期只**记录** `regime_decisions`，不改实盘。并行实盘仍跑 S9。运行 ≥ 8 期或 ≥ 200 已结算腿（对齐 `forward.py` MIN_COMBOS=200）。**判据**：影子决策的 what-if PnL ≥ 实盘 S9，且 SKIP 期确实落在坏区。
- **GATE-R2（小额真钱）**：通过 R1 后，开启 enabled，但动作空间限制在 `{SKIP, LOW_N2N3, S9_ANCHOR}`（不放激进 preset），bankroll 上限折半。运行 ≥ 8 期。**停止规则**：`current_dd > 0.50` 立即停（对齐 MAXDD_STOP）。
- **GATE-R3（全动作空间）**：R2 正且无单底线反复误触发后，纳入 `CURRENT_N4 / LOWMID_SP_HIGH_N`。
- **远期**：满足样本门槛（≥500 腿 / ≥12 期）后评估是否用 contextual bandit 替换状态机（§5.1）。

每个 GATE 产出一份 `docs/research/regime_selector_*.md`，含 ledger、equity 图、verdict（go/no-go/uncertain），不事后改阈值。

---

## 10. 最小可行版本（MVP）拆解

MVP = **影子模式的规则状态机**，纯只读 + 记录，不改实盘下注路径。按依赖顺序：

1. **M1 指标聚合器**（纯函数，复用现有）：`build_regime_features(db, live_db_path, decision_ts)` → 调 `collect_settled_legs` + `_q_stat`（短/长窗）+ `q_buckets` + `select_downweight_leagues` + 池快照（`diagnostic_legs` / `leg_concentration_pct`）+ `compute_q_drift`，输出特征 dict。**无新算法**，只是组装。
2. **M2 regime 分类 + 状态机**：`classify_regime(features)` 与 `select_action(features)`（§5 伪代码），纯函数，阈值读 config。带单测（构造 GREEN/AMBER/RED/各底线触发用例）。
3. **M3 决策记录**：新增 `regime_decisions` 表 + 写入；每期定时器（接现有 sp-forward weekly timer 风格，见 `DEPLOY.md`）触发一次，`enabled=0` 时只记录。
4. **M4 Dashboard 最小卡片**：当前 regime + action + reason + 底线灯板。
5. **M5 周报字段**：把 `regime_decisions` 最新行 + 上期复盘渲染进周报。

MVP 完成判据：连续 4 期影子记录无误，决策可在周报回放，且 SKIP 至少在已知 2026-05-22 后坏区被触发。**M1–M5 全部不调用 place，零真钱风险。**

YAGNI（MVP 不做）：
- 不做 contextual bandit（§5.1，Phase 3）。
- 不新增 preset（动作空间限于现有 REGISTRY）。
- 不改 `build_weekly_plan` / planner 内部（只在其外做选择与底线门控）。
- 不接临近开赛 SP 落地（属 `inplay_sp_timing_filter.md`）。
- 不动 `kickoff_window_hours`（已知任何窗口值都无法两全，保持 0）。

---

## 11. 与姊妹文档的关系

| 文档 | 关系 |
|------|------|
| `low_mid_sp_high_n_experiment.md` | 提供本选择器 `LOWMID_SP_HIGH_N` 动作的 edge 来源（高 N 低 break-even q）；其 preset 一旦验证，注册进 REGISTRY 后纳入动作空间。 |
| `single_match_probability_calibration.md` | 改善 `p_final`，直接抬升 q 信号质量，使 regime 分类阈值更可靠。 |
| `inplay_sp_timing_filter.md` | 处理 SP 漂移的「落地」侧；本选择器只用漂移的方向/负担作降档信号，二者互补不重叠。 |
| `walk_forward_strategy_evaluation.md` | 提供 §6/§7 的 walk-forward 评估骨架；本选择器是其上的「在线决策」消费者。 |
```
