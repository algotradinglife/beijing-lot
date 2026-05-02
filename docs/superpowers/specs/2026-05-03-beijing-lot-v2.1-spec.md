# 北京单场 量化策略 v2.1 — 正式 Spec

**日期**: 2026-05-03
**作者**: brainstorming + 多轮 agent 验证
**取代**: v1（单关）spec、隐式 v2（7 关）讨论

---

## 1. 项目目标

构建一个**长期 +EV、可控 DD 的量化彩票投注系统**，配套：
- 自买票通过自营/入股彩票站
- 7% 销售佣金返点（暂不算入主策略，作为安全垫）
- 拆票避税以避开 1 万元税务悬崖

**核心定位**：不是"赌赢"——是**统计套利散户群体偏差**。

---

## 2. 关键决策（以下决策已全部基于 8 年真实 3-SP 数据验证）

### 2.1 玩法
- **北单 让球胜平负 (3/1/0)**
- **N=4 关组合**（"N 选 7 关"中实测最优）
- 单关（N=1）数学不可行；N=2 Sharpe 高但 CAGR 太低；N=3 CAGR 高但 Sharpe 差；**N=4 是 Calmar 全网格最高（7.15）**；N≥5 在低 Kelly 下崩溃

### 2.2 概率源
- 不需要 Pinnacle 实时赔率
- **直接用 北单 实测 SP 反推 niche-based 真概率**
- 8 年历史 3-SP 数据已证明 niche q ≈ 1.4 在 OOS 稳定

### 2.3 仓位规则
```
kelly_fraction = 1/16
per_combo_cap_frac = 0.5% bankroll
weekly_stake_cap_frac = 25% bankroll
min_stake_per_ticket = 2 元（北单最低）
```

**为什么 1/16 而不是经典的 1/4？**
- 1/4 Kelly 在 8 年回测下产生 −81% Max DD（实操心理不可承受）
- 1/16 Kelly 把 Max DD 砍到 −37%，CAGR 仍 261%（100k → 1035 万）
- Calmar 从 5.81 升到 7.15（全网格最优）
- 来源：MacLean-Thorp-Ziemba (2010)：边际估计噪声大时，最优 Kelly 系数应 < 1/2

### 2.4 Niche 选择
**Archetype A**（已 OOS 验证 16/16 niche 存活）：
- SP ∈ [5, 8]
- 主要 niches:
  - `option_0 × SP[5,8] × Top5EU`（test q=1.397, +574% 7关 EV）
  - `draw × SP[5,8] × Other league`（q=1.380, +520%）
  - `option_0 × SP[5,8] × |h|=1`（q=1.335, +391%）
- Niche 列表存储在 `src/niche_analysis/sp_native.py`，可定期 OOS 重新验证

**Archetype B**（低 SP × 高 N 假设）：
- 实测发现 11 个 niche 在 SP ∈ [3.5, 4.5] 存活
- 但所有 B 变体 CAGR 接近 0
- **不采用**——高胜率低盈亏比假设没跨过 35% 房费

### 2.5 拆票避税
- 单注奖金 ≥ 10,000 元 → 20% 税（全额）
- v2.1 默认拆票：单票 stake 反推 → 单票奖金 < 9,999 元
- 用户已确认 北单 票非身份绑定 → 不同人领奖

### 2.6 站点佣金（暂不计入主策略）
- 7% 销售返点（按持股比例）
- 当前回测**不算入**——若计入，所有变体 CAGR + 7% × stake_total
- 作为安全垫：实战 PnL 比回测 PnL 多 7%（约 35k/月，10万 bankroll，5% 周仓）

---

## 3. 系统架构

```
┌─ 数据层
│  ├─ Live Collector (src/live_collector/) — 实时抓取 3-SP
│  ├─ Historical DB (data/raw/beidan_full_3sp.csv) — 8 年回测数据
│  └─ Niche definitions (src/niche_analysis/sp_native.py)
│
├─ 模型层
│  ├─ Niche filter (per-leg q ≥ 1.064)
│  └─ EV 计算 (q × SP × 0.65)
│
├─ 决策层
│  ├─ Combo builder (src/combo_optimizer/) — N=4 组合
│  ├─ Kelly sizer (1/16 Kelly + 三层上限)
│  └─ Tax-cap split (奖金 ≤ 9,999)
│
├─ 执行层（Phase 5a 起）
│  ├─ Weekly run pipeline (src/phase5a/) — 输出可买票清单
│  ├─ 人工执行（前往京津粤彩票站购买）
│  └─ PnL tracker (手动录入 + 累计统计)
│
└─ 监控层
   ├─ 周回报、累计 ROI、Sharpe、DD 实时跟踪
   └─ Kill criteria 触发警报
```

---

## 4. 8 年回测核心结果（推荐配置 N=4 Kelly=1/16）

| 指标 | 值 |
|---|---|
| 入场资金 | 100,000 元 |
| 8 年终值 | 10,348,426 元 |
| CAGR | 260.8% |
| Sharpe | 0.48 |
| Sortino | 1.39 |
| Max DD | **−36.5%** |
| Calmar | **7.15**（全网格最高）|
| Time Underwater | 64% |
| 周均 stake | 约 5% bankroll |
| 周胜率 | ~30%（多数周亏损）|

---

## 5. 阶段计划

### Phase 5a — 小金额 forward test（2026-06 起，2 月）
- bankroll: 2,000–5,000 元
- 配置: N=4, Kelly=1/16
- 目标: 验证执行流程（实时抓 SP → 算 EV → 买票 → 对账）
- 累计 ≥ 50 注
- Kill: ROI < −30%（在 50 注后）

### Phase 5b — 中量 forward test（2026-08 起，4 月）
- bankroll: 10,000–20,000 元
- 累计 ≥ 200 注
- Kill: ROI < −20% 或 DD > −60%

### Phase 6 — 真验证（2026-11 / 累计样本足够后）
- bankroll: 30,000–50,000 元
- **决策点**: Sharpe > 0.3 且累计 ROI 显著 > 0 → Phase 7
- 否则停止

### Phase 7 — Production（2027 起）
- bankroll: 100k+
- 入股彩票站（如条件成熟）
- 算入 7% 佣金返点
- 长期持续运营

---

## 6. 待验证 / 待执行

| 项 | 影响 | 谁 |
|---|---|---|
| 单注 vs 单期 计税规则 | τ ∈ [0.8, 1.0] | 用户线下 |
| 站点入股可行性 | 决定 7% 佣金是否真能拿到 | 用户 |
| Live Collector 24×7 部署 | 持续数据积累 | 自动 |
| Phase 5a 执行流程 | 第一次实盘 | 用户 + 系统 |

---

## 7. Kill Criteria（重要）

任何阶段触发以下任一条件 → **暂停下注，复盘，再决定继续/退出**：

1. 累计 ROI 在 ≥ 50 注后仍 < −25%
2. 单批次 DD > −50%
3. 单期权益跌至初始 bankroll 的 50% 以下
4. Niche q 跨季度回退（用 Live Collector 数据滚动重验）
5. 北单官方规则变更（如返奖率调整、最低注金提升）

---

## 8. 已完成的代码资产

| 模块 | 状态 | 描述 |
|---|---|---|
| `src/live_collector/` | ✅ 18/18 测试 | 实时 3-SP 抓取 |
| `src/backfill/` | ✅ 7/7 测试 | 历史数据爬虫 |
| `src/niche_analysis/sp_native.py` | ✅ 部分测试 | OOS-validated niche 表 |
| `src/combo_optimizer/` | ✅ 36/36 测试 | 组合 + Kelly + 拆票 |
| `src/sweep/` | ✅ | N×SP sweep |
| `src/dual_sweep/` | ✅ | 双 archetype 评估 |
| `src/backtest_combo/` | ✅ 10/10 测试 | 真组合回测 |
| `notebooks/kelly_n_grid.py` | ✅ | Kelly × N 全网格 |
| `notebooks/barbell_direct.py` | ✅ | barbell 实测分析 |
| `src/phase5a/` | ⏳ agent 进行中 | 实战 weekly run |
| `src/drawdown/` | ⏳ agent 进行中 | DD 解构 + stop-loss |
| `src/niche_corr/` | ⏳ agent 进行中 | 相关性 + Markowitz |

---

## 9. 报告与数据

- `KELLY_N_REPORT.html` — 推荐配置说明
- `ANALYSIS_REPORT.html` — 完整研究报告
- `docs/research/dual_archetype_report.html` — 双 archetype 完整对比
- `docs/research/niche_analysis_real_sp.html` — niche 分析（真 3-SP）
- `docs/research/combo_sweep_report.html` — N=2-8 sweep
- `data/raw/beidan_full_3sp.csv` — 8 年 135k 历史数据
- `data/raw/kelly_n_grid.csv` — Kelly×N 网格结果

---

## 10. 哲学

这个项目从最初"理论 7 关 + 理论 EV 数学"演进到"实测 4 关 + 实测 niche q + 实测 Kelly=1/16"。每一次 pivot 都是**数据反驳了直觉**：

- v1: 单关数学上不可行 → pivot 到组合
- v2: 7 关理论甜蜜点 → 实测变量太大 → pivot 到 N=3-4
- v2.1: Kelly=1/4 经典 → 实测 DD 不可承受 → pivot 到 Kelly=1/16

**最终建议**：在数据指向的方向走，不在直觉里固守。每个 Phase 之间用 Live Collector 新数据复验 niche，发现退化就重新选。

---

*本 spec 是当前状态的最终版本。后续若有新数据、新洞察、新约束，应通过 `superpowers:brainstorming` 重新触发 v2.2 / v3 设计。*
