# SP 漂移优化 — 探究与验证设计稿

**日期**: 2026-06-11
**作者**: brainstorming（多轮澄清 + 实盘数据诊断）
**状态**: 设计稿，待评审 → 转 writing-plans
**关联**: [v2.1 spec](2026-05-03-beijing-lot-v2.1-spec.md)、`src/phase5a/filter.py`（现有漂移防线）、`src/webui/services.py::sp_drift_stats`

---

## 1. 背景与动机

实盘 forward-test（40 批 / 2887 组合 / 84 命中）整体 +1,061（ROI +4.3%），但真实轨迹是「5 月冲到 ~111.4k 峰值 → 5/20 后一路回吐到 ~101k」。

诊断发现**系统性、不利的 SP 漂移**是首要嫌疑：

| 实测漂移（154 条命中腿，计划 SP → 结算 SP） | 值 |
|------|-----|
| 平均计划 SP → 结算 SP | 4.05 → 3.36 |
| 平均漂移 | **−16.5%** |
| 不利 / 稳定 / 有利占比 | **77% / 5% / 18%** |
| 时间趋势 | 前半段 −17.8%，后半段 −17.2%（**未改善**） |

北单 SP 是 parimutuel：识别出的低估 niche，散户临场也往同一边压，把 SP 买下去。N=4 组合赔付是各腿 SP 连乘，每腿 −16.5% → 中奖组合实际只赔模型假设的 **(0.835)⁴ ≈ 48%**，约腰斩——这解释了「回测号称 CAGR 261%、实盘却只 +4%」。

**现有漂移防线已写进代码但效果未显现**：`DriftBlockRule`（4 条手调规则）、`league_blacklist`、`league/drift` 联动、`kickoff_window_hours` 过滤都存在，但 (1) 最直接的 `kickoff_window_hours` 在实盘 config 是 **None（关闭）**；(2) 已生效的 `DriftBlockRule` 只压「特定大跌格子」频率，对全体腿 −16.5% 的系统性漂移没有改变（前后半段一致）。

## 2. 目标（Goal）

判定「SP 漂移感知优化」能否把实盘 N=4 让球胜平负策略的**真实 EV**，从当前的勉强打平抬到**扣除 35% 房费后稳健为正**——通过量化漂移、建模最终 SP、推导并回测具体策略改动。

**终点**：报告 + 代码改动 + 上线前回测（反事实重放）+ go/no-go。**不直接改动正在跑的实盘 default profile。**

**非目标（YAGNI）**：
- 不在本课题内做实盘 A/B forward-test（那是 GATE 3 通过后的下一个独立 spec）。
- 不重构现有 live webui / autoplan / 结算管线（只在 GATE 3 通过后注入推荐参数与新过滤规则）。
- 不挖与漂移无关的新 alpha（如纯模型 vs 欧赔）。

## 3. 验证标准（贯穿所有阶段）

**机制优先 + 多切片一致**：每个结论必须同时满足——

1. **可解释的因果机制**：能说出「为什么会这样」（如 vol% 失衡 → 该侧 SP 继续下跌），而非纯相关。
2. **多切片方向一致**：效果在 ≥3 个独立切片（niche / 联赛 / SP 档）上方向相同，而非只靠一个总体数字或单一格子。

理由：仅 5.5 周轨迹数据，单一 OOS 数字检力低、易过拟合；机制 + 一致性比单点统计显著更可信。每个阶段报告须显式给出机制论证与切片一致性表。

## 4. 数据底座与可行性

**可用数据**（已核实，截至 2026-06-11）：
- Live 快照 `data/beidan_live.db::snapshots`：**742,992 条 / 2,704 场 / 2026-05-02 → 06-11**（~5.5 周），每场中位 **270** 个快照。
- 列：`sp_3/sp_1/sp_0`（三侧 SP 全有）、`vol_pct_3/1/0`（销量比）、`pool_total`、`eu_h/d/a`（欧赔）、`snapshot_ts`。
- `matches.kickoff_ts` → 可对每个快照算**距开赛分钟数（MTK）**。
- 已结算 + ≥3 快照：**1,730 场**（漂移建模可用样本）。
- 历史库 `beidan_history.db`：8 年 38k 场，**仅** final winning_sp + 欧赔，**无时间序列、无输方 SP** → 不能用于漂移建模，仅作最终-SP/赛果上下文参考。

**关键可行性结论**：漂移研究只能用这 5.5 周 live 面板。统计上够做分格漂移与预测建模，但**只覆盖一个赛季切片**，跨季泛化性属已知局限（不得宣称）。顺带：当年因「历史不可得」放弃的 vol_pct 信号，在 live 数据里实际是有的，可在 Phase 2 作为特征纳入。

## 5. 架构与代码边界

新增独立研究包 `src/sp_drift/`，与 live webui 解耦，复用现有 `niche_analysis` / `combo_optimizer` / `backtest` 的 niche filter、EV、kelly 模块：

| 模块 | 职责 | 单一目的 |
|------|------|----------|
| `src/sp_drift/panel.py` | 原始快照 → 以 MTK 索引的研究面板（带标签、缓存 parquet） | 数据装配 |
| `src/sp_drift/drift_stats.py` | 描述性漂移统计（分时间 / 分格子 / 去偏） | Phase 1 |
| `src/sp_drift/sp_model.py` | 最终 SP 预测器（基线 + 可解释模型） | Phase 2 |
| `src/sp_drift/policies.py` | 策略杠杆（window / haircut / 过滤 / 时机）的参数化定义 | Phase 3 |
| `src/sp_drift/replay.py` | 反事实重放引擎（按策略重建计划 → 对真实结果结算 → 指标） | Phase 4 |

每个模块在 `tests/sp_drift/` 有 fixture 上的确定性测试（面板装配、重放结算尤其要测）。每阶段产出 `docs/research/sp_drift_phaseN.md` + 图。

接口约定：`panel.build()` 返回 tidy 长表（一行一个 `(match, selection, snapshot)` 或聚合到 `(match, selection)` 的决策视图）；下游模块只消费面板，不直接碰 sqlite。`replay.py` 的策略入参是 `policies.py` 的数据类，便于网格扫描。

## 6. 阶段设计

### Phase 0 — 分析底座

构建可复用面板：对每个 `(match, selection)`，以 MTK 为索引的 SP 轨迹、vol% 轨迹、pool_total、欧赔、最终结算 SP、赛果，以及 niche/联赛/SP档/让球类/赛事类型标签。

- 产出：`src/sp_drift/panel.py` + 缓存 parquet（写到 `data/derived/sp_drift/`）。
- 机制 sanity：池子随时间增长？vol% 三项和≈100%？SP 与隐含概率自洽（1/SP 归一后 ≈ 1/return_rate）？
- 完成判据：面板能复算出诊断里的 −16.5% 命中腿漂移（与 `sp_drift_stats` 对齐，作为正确性锚点）。

### Phase 1 — 量化漂移（描述性，**GATE 1**）

| 子问题 | 方法 | 产出 |
|------|------|------|
| Q1.1 漂移 vs 时间 | `drift(t)=SP(t)/SP_final`，按 MTK 分桶 | 残余漂移曲线（T-6h/3h/1h/15m 还剩多少） |
| Q1.2 分格漂移 | option×让球类×SP档×联赛×赛事类型 的均值/分布 | 漂移热力图 + 最差格子表 |
| Q1.3 可预判性 | 决策时刻可观测量（尤其 vol% 失衡）与后续漂移方向的关系 | 相关/分组证据，桥接 Phase 2 |
| Q1.4 去选择偏差 | 对**所有 qualify 腿**（非仅中奖腿）算漂移 | 无偏 EV 冲击估计 |

**GATE 1 决策**：漂移是否 (a) 大、(b) 系统、(c) 至少部分可预判？
- 大但**决策时刻方向随机**（纯噪声）→ 预测/过滤无效，仅「下单更晚」有用 → 跳过 Phase 2，直奔 Phase 3 的时机 + window 杠杆，并接受降低的 EV。
- 系统且可预判 → 进完整 Phase 2。
- 一致性要求：Q1.2 的方向性须在 ≥3 联赛 / ≥3 SP 档上成立。

### Phase 2 — 建模最终 SP（预测性，**GATE 2**）

预测器 `final_SP_hat = f(SP(t), vol%(t), pool(t), MTK, 联赛, 让球, option, 欧赔)`：
- **基线**：`final_SP ≈ SP(t)`（当前策略隐含假设）。
- **模型**：机制优先 → 先可解释模型（漂移比回归 / 带特征重要性的 GBM），预测漂移比 `final/decision`。
- **评估**：时间外样本（前 N 周训练 / 后段测试）上，f 是否显著优于基线——指标为最终 SP 的 MAE，**以及更关键的隐含概率/EV 误差**；特征重要性须符合「vol% 失衡 + 剩余时间驱动漂移」的因果故事。

**GATE 2 决策**：预测器是否把最终 SP 误差降到足以**改变 qualify/EV 判断**？
- 若靠近开赛时基线已近最优（如 T-30m 几无残余漂移）→ Phase 2 价值坍缩为「直接用晚期 SP」（=开窗），则**不建模**，明确记录此权衡并把重心交给 Phase 3-P1。
- 一致性要求：模型增益须在多切片上正向，不靠个别联赛拉动。

### Phase 3 — 推导策略（处方性）

每个杠杆独立测量、带机制论证、可参数化：

- **P1 `kickoff_window_hours`**：扫 T∈{不限,6h,3h,2h,1h,30m}，画「残余漂移 × qualify 数 × EV」权衡曲线，选 T\*。
- **P2 EV haircut**：把预期漂移注入 EV，用**漂移调整后 SP**（按格子固定 haircut，或 Phase 2 模型驱动）qualify，而非观测 SP。
- **P3 漂移感知过滤**：用 Phase 1 全格子图**数据驱动地**扩展/替换现有手调的 4 条 `DriftBlockRule`（保持现有 JSON 加载机制与 league/drift 联动）。
- **P4 下单时机**：给出「在 MTK=? 下单」的操作建议，可能加约束（计划只在窗口内定稿）。

### Phase 4 — 回测重估 EV（**GATE 3**，终点）

**反事实重放**：对每个候选策略组合，用面板的决策时刻数据重建「本应生成的计划」，对真实最终 SP + 赛果结算，算真实 EV/ROI/漂移/qualify 数/MaxDD/Calmar。
- 对比：基线（当前无窗 config）vs 各单项策略 vs 最优组合。
- **多切片**：按周 / 联赛 / SP 档，要求改善方向一致。
- 诚实计量：报告面板覆盖率（仅 collector 见过的比赛）与跨季局限。

**GATE 3 / go-no-go**：最优组合的**漂移调整后 EV** 是否跨过 35% 房费、且多切片一致为正？
- **是** → 输出推荐配置 + 落地代码改动（`kickoff_window` 默认值、haircut、更新的 `DriftBlockRule`），交付下一个 spec 做上线前实盘验证。
- **否** → 结论「SP 漂移结构性侵蚀该 edge，N=4 让球当前不可行」——合法且省钱的负结果，触发对玩法/N/SP 区间的重新评估。

## 7. 指标字典

- `drift_ratio = final_SP / decision_SP`：下注腿上 <1 即不利。
- `residual_drift(T) = E[|1 − drift_ratio|]`，限定 MTK=T 做决策。
- `qualify_count`：给定策略下通过 niche 的腿/组合数。
- `drift_adjusted_EV`：用 final_SP（或预测 final_SP）替代 decision_SP 算的 EV。
- 重放指标：realized ROI、周 ROI 分布、MaxDD、Calmar。

## 8. 风险与局限

| 风险 | 处理 |
|------|------|
| 5.5 周 = 单赛季切片，跨季泛化未验证 | 明确标注；结论只声称样本期内成立 |
| 覆盖偏差：仅含 collector 见过的比赛 | Phase 4 报告覆盖率；不外推到未观测比赛 |
| 中奖腿选择偏差（−16.5% 偏高估计） | Phase 1 Q1.4 用全 qualify 腿重算 |
| Parimutuel 反身性（自身下注移动 SP） | 当前注额下可忽略，注明；未来注额放大需复核 |
| GATE 2 过拟合（薄数据 + 灵活模型） | 机制优先 + 时间外样本 + 多切片一致 |

## 9. 阶段依赖与早停

```
Phase 0 ──> Phase 1 ──[GATE 1]──> Phase 2 ──[GATE 2]──> Phase 3 ──> Phase 4 ──[GATE 3]──> 推荐配置 / 负结果
                          │（方向随机）                    ↑
                          └────────────────────────────────┘（跳过建模，直接 window+时机）
```

每个 GATE 都是潜在早停点：GATE 1 可在最便宜阶段否决整个课题（若漂移不可战胜）；GATE 2 可省掉建模；GATE 3 给最终 go/no-go。

## 10. 交付物清单

- `src/sp_drift/` 五模块 + `tests/sp_drift/` 测试
- `docs/research/sp_drift_phase{0..4}.md` + 图
- 最终报告：漂移量化结论、预测器价值、策略权衡曲线、重放 EV 对比、推荐配置（或负结果）
- （GATE 3 通过时）落地代码改动：`kickoff_window_hours` 默认值、EV haircut、更新的 `DriftBlockRule` 集
