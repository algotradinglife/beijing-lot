# 8 小时自主探索总结 — 北单 让球胜平负 (3/1/0) 量化策略

**日期**: 2026-05-02
**已完成**: 设计稿草案（v1）、5 项实证分析、3 篇研究报告、25 份历史数据集、北单数据源实测

---

## TL;DR — 核心结论

1. **方法学可行**：用国际盘口（Pinnacle）反推真实概率的方法（Approach A）经实证校准良好。在 5 联赛 × 5 季 × 8903 场上：
   - Pinnacle 1X2 校准误差 < 2pp，favourite ROI = −1.4%（市场高效）
   - Pinnacle AH 校准误差 < 1.5pp
   - 模型重建 Pinnacle 自家 1X2 平均偏差 ~1.1pp（与原书价无统计差异）

2. **发现一个必须修复的系统性偏差**：Skellam 转换器在 8903 场实测中 **系统性低估让球后平局 (p1) 约 2.8pp**（实际 27.5% vs 预测 24.8%），高估让后主胜 ~2.2pp。这是 Dixon-Coles τ 效应。**未修正前每注 "1" 选项被低估 EV ~6%，会拒绝大量真正盈利的下注。** v1 必须加经验校正。

3. **N ≥ 50 才能控制最坏损失**（你的核心诉求）：Monte Carlo（2 万批次每点）显示在 5% 真实 edge 下：
   - N=10：5% 分位 ROI = −45%（不可接受）
   - **N=50：5% 分位 ROI = −18%**（推荐）
   - N=100：5% 分位 ROI = −11%

   北单 一期 5–10 场，要凑 50 候选 → **批次必须是周聚合**（不是单期）。

4. **EV 阈值 T = 0.05 默认**（最坏损失目标）；T = 0.10–0.15 适合最大化长期增长（但批次方差更大）。最终 T 需 Phase 4 实测 σ_p 后调。

5. **仓位规则定型**：1/4 Kelly + 三层上限（per-match 5% 资金，pool 0.5%，batch 25%）。Kelly 公式与文献一致（MacLean–Thorp–Ziemba 2010 + Whelan 2025）。

6. **Edge 来源仅一种站得住脚**：散户群体 SP 偏好（draw aversion + popularity bias）vs 国际市场。**v1 必须用真实北单数据验证此偏差存在**（Phase 4 Go/No-Go 决策点）；如果偏差不存在或太小覆盖不了 35% 房费，**整个项目无 edge，应停止**。

---

## 已交付的可见产出

### 设计稿（核心交付物）
- **`docs/superpowers/specs/2026-05-02-beijing-lot-310-design.md`** — 完整设计文档，包含：
  - 系统架构（4 层）
  - 8 个核心决策（每个带数据/文献支撑）
  - 5 个开发阶段计划
  - 6 类风险与必须实证回答的关键问题

### 研究报告
- `docs/research/sp-bias-and-kelly.md` — 25+ 篇文献综述（Snyder, HZR, Thaler-Ziemba, MacLean-Thorp-Ziemba, Whelan 等），最终给出具体仓位规则
- `docs/research/ah-to-1x2-methodology.md` — Skellam 方法学详细推导
- `docs/research/data-sources-beidan.md` — 北单数据源实测（500.com 全量可爬；销量比 + 输方 SP 历史不存）

### 实证分析（Python，全部跑通）
- `notebooks/portfolio_sim.py` — 批次方差网格扫描（决定 N ≥ 50）
- `notebooks/winners_curse.py` + `_v2.py` — EV 阈值 + 噪声敏感性分析
- `notebooks/pinnacle_calibration.py` — 校准 Pinnacle 1X2（验证 A 路线基础）
- `notebooks/ah_calibration.py` — 校准 Pinnacle AH（边际 2.3%；25% 比赛是整数线）
- `notebooks/ah_to_1x2.py` — Skellam 转换器（6/6 单元测试通过）
- `notebooks/integer_line_test.py` — 整数线实测（**发现关键的 +2.8pp 平局校正需求**）

### 数据集
- `data/raw/football-data/` — 5 联赛 × 5 季原始 CSV（共 9498 场 × 100+ 字段）
- `data/raw/big5_pinnacle.csv` — 清洗后的 8993 场 × 关键字段
- `data/raw/big5_int_line_predictions.csv` — 整数线预测 + 实际结果（8903 场）
- `data/raw/portfolio_sweep.csv` — Monte Carlo 全网格结果（60 行 × 13 字段）

### 持久化记忆（自动 memory）
- `project_beijing_lot_strategy.md` — 项目目标、关键决策、开放问题（跨 session 持久化）
- `feedback_design_collaboration.md` — 你的协作风格偏好
- `MEMORY.md` — 索引

---

## 我等你回来要决定的事

设计稿基本写完，但有几个项目需要你确认或选择：

### 决定 1：T 阈值与目标函数
你最初说"减少每批购买的最大损失"——我据此选了 T = 0.05（控制最坏损失）。但实证显示：
- T = 0.05：批次最坏损失更小，但长期增长率较低
- T = 0.10–0.15：长期增长率高 ~25%，但单批次最坏损失更大（−25% vs −18%）

**问题**：你更看重哪个目标？还是你接受 T = 0.05 默认 + Phase 4 后再调？

### 决定 2：北单数据源（agent 已回，结果如下，需要你确认应对方案）

**实测结论**（详见 `docs/research/data-sources-beidan.md`）：
- ✅ 500.com 全量可爬：~2,115 期 / ~170k 场（自 2007-05），单脚本约 70 分钟跑完
- ✅ 历史结果、让球数、中奖侧 SP、平均欧赔 都保留
- ❌ **历史只保留中奖选项 SP**，输的两个选项 SP 已被擦除
- ❌ **销量比例（投注分布）历史不留档** — 这是验证群体偏差最关键的信号
- ✅ 实时数据（开赛前的 3-SP + 销量比）完整可获取，但需 Live Collector 持续抓取

**这是落到了 B/C 之间的混合情景**。我已据此修订设计稿（§5、§6.1）：

- 必须立即启动 Live Collector（~2 人天工作量），开始积累真实数据
- Limited Backtest（用历史 170k 场 + 平均欧赔代理）可在 1-2 周内出报告，但**不能验证群体偏差量级**（关键 edge 假设）
- 真正的 Go/No-Go 决策推迟 ~6 个月（需要 Live Collector 积累足够数据）

**问题**：你接受这个延长的时间表，还是希望换一种 edge 来源（不依赖群体偏差）？我能想到的替代 edge 都比较薄弱（如纯模型 alpha 对比平均欧赔），未必能 cover 35% 房费。

老实说：如果群体偏差 edge 不存在或太小，**整个项目大概率没有正期望**——这个风险无法在不收集真实数据下消除。

### 决定 3：第一阶段的 bankroll 与执行模式
我没问过你打算用多少钱启动。这影响：
- 5% per-match cap 的绝对额（500 元 bankroll 下 25 元/注；5 万下 2500 元/注）
- 是否需要 pool size filter（小 bankroll 下不会触发）
- forward test 阶段的速度

**问题**：你的初始 bankroll 计划是多少？是否在京津粤三地（北单只在这三地销售）？

### 决定 4：开发体力与时间预算
当前设计预计 8–12 周到 v1 上线（Phase 1–4）。Phase 4 的实证验证可能耗时最久（需 ≥1 年回看数据 + 200 注 forward test 才能有统计意义）。

**问题**：你能投入多少周/月开发时间？实际工作机会上是否要继续推进 v1 开发，还是先停在设计阶段？

---

## 最重要的发现 / 警告

### 警告 1：北单不是和庄对赌，而是和散户对赌
- 返奖率 65%，房费 35%（高于普通博彩）
- 这意味着任何"知识缺乏的盲注策略"长期 ROI ≈ −35%。**不可能靠运气或感觉盈利**。
- 唯一可行的 edge：散户群体定价错误 vs 国际市场。这是个有限的 edge（文献显示 5–10pp 量级），需用 35% 房费 cover 后才有正期望。

### 警告 2：真正的 Go/No-Go 决策推迟 ~6 个月
这是 8 小时探索期间最重要的发现：北单不archive 销量比 + 不archive 输方 SP，意味着：
- 历史回测能告诉我们的最多是"模型预测多准 vs 平均欧赔"
- 历史回测**不能**告诉我们"北单散户偏差是否真存在 + 大到能 cover 35% 房费"
- 学术上 draw aversion 在西方 1X2 市场已确认（高信心），但**北单 SP 池下的实际量级是未知数**
- 必须 Live Collector 跑 3+ 月 + 200+ 注 forward test 才能有统计意义的答案
- 在此之前 **任何投入都是基于假设的探索性投入，不能靠它盈利**

### 警告 3：合规
中国大陆体育彩票为国家专营。本系统**只用于个人决策辅助**，不做代购、不托管、不收费咨询。生成的投注清单只在本地保留。

---

## 已抵达边界

我自主能做的研究/设计工作基本到了边界——再做就涉及生产代码 scaffolding 了，按 brainstorming skill 的硬约束在你审完设计稿前不应继续。

**等你回来后我建议的下一步顺序**：
1. 你审阅 `docs/superpowers/specs/2026-05-02-beijing-lot-310-design.md`（已更新到 §5 Phase 7 + §6.1 数据风险）
2. 确认或修订 §"我等你回来要决定的事" 列出的 4 个决定（特别是延长时间表 + 群体偏差风险）
3. 同意后转入 superpowers:writing-plans 写实施计划（Phase 1 是关键路径，重点是 Live Collector）
4. **如果决定继续**：第一步可以是搭 Live Collector（最早开始有用数据，最高优先级）

— 工作于 2026-05-02 00:30 (GMT+8) 至本次写完
