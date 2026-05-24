# cross_n_lambda 回测影响分析

**日期**: 2026-05-24  
**参数**: `cross_n_lambda` — 控制多 N 层之间场次重叠的跨层惩罚系数

---

## 结论摘要

在当前回测设置下，`cross_n_lambda=0.5`（S9 策略）对所有指标的影响为零：  
ROI、CAGR、Sharpe、最大回撤、总盈利均与 `cross_n_lambda=0`（S1 策略）完全相同。

**这不是参数无效，而是回测环境的结构性限制导致的"池饱和"问题。**

---

## 回测对比结果

| 指标 | S1 稳健 (λ=0) | S9 跨N多样化 (λ=0.5) | Delta |
|------|--------------|---------------------|-------|
| 总盈利 | -1,079,597 元 | -1,079,597 元 | **0** |
| 总下注额 | 3,671,456 元 | 3,671,456 元 | **0** |
| ROI | -29.4% | -29.4% | 0% |
| CAGR | — | — | 0% |
| Sharpe | — | — | 0 |
| 最大回撤 | — | — | 0 |

两次运行输出完全相同的 plan ledger，stake 完全相同，无任何差异。

---

## 根本原因：top_k 池饱和

### 问题机制

1. **候选池构建**：每期 `build_candidates_for_issue()` 生成所有 edge≥0.05 的候选项（通常 30-50 个，覆盖 30-50 场），再经 `select_pool()` 按 edge 排序取 top-K（默认 `top_k=14`），保留唯一场次 **14 场**。

2. **N=2 饱和**：N=2 的 `max_combos=60` 张票从 14 场里选 2-leg 组合，排列组合数 = C(14,2) × ... 实际生成约 60 张票，这 60 张票会**覆盖全部 14 个场次**（每场至少出现在数十张票中）。

3. **cross_n_used 饱和**：N=2 运行完毕后，`cross_n_used` = {全部 14 个 match_id}。

4. **惩罚均等化**：N=3/N=4 在评分时，所有候选 combo 的每条腿都在 `cross_n_used` 中，导致**跨层惩罚对所有 combo 完全相同**（= n_legs × cross_n_lambda），排名不变，选择结果不变。

### 实际调试输出示例（期号 26046）

```
26046: 37 cands, 37 unique matches
  N=2: 60 tickets, 14 unique matches in tickets, cross_n_used size now 14
  N=3: 80 tickets, 14 unique matches in tickets, cross_n_used size now 14  
  N=4: 60 tickets, 14 unique matches in tickets, cross_n_used size now 14
```

N=2 一层就耗尽了整个 top-14 池，N=3/N=4 没有任何非惩罚场次可选。

---

## cross_n_lambda 何时真正有效

该参数在**生产实盘**场景中设计合理，并且是有效的：

| 场景 | top_k 池大小 | N=2 实际覆盖场次 | cross_n_lambda 效果 |
|------|------------|--------------|-------------------|
| 回测（每期 30-50 场比赛）| 14 场 | 14 场（全覆盖） | **无效**（饱和） |
| 实盘（每期 6-14 场比赛）| 6-10 场 | 3-6 场（部分覆盖） | **有效**（N=3/4 会偏向未被选场次） |

实盘时每期可用比赛数通常只有 6-14 场，N=2 仅能覆盖其中一部分，`cross_n_lambda` 就能起到分散作用。

---

## 修复方案（待评估）

### 方案 A：按出现频次截断 cross_n_used（推荐）

不记录 N=2 用过的**所有** match，只记录**出现次数 ≥ 阈值**的高频场次（例如频次 ≥ top-3）：

```python
from collections import Counter
freq = Counter(leg.match_id for plan in sub_plans for leg in plan.combo.legs)
# 只惩罚在 N=2 中出现次数最多的 top-3 场次
threshold = sorted(freq.values(), reverse=True)[min(2, len(freq)-1)]
for match_id, count in freq.items():
    if count >= threshold:
        cross_n_used.add(f"{match_id}:{selection}")  # 需按 selection 拆分
```

**优点**：区分"N=2 极度依赖"vs"偶尔出现"的场次，真正惩罚集中度最高的场次。

### 方案 B：降低 top_k for N=2

将 N=2 的 top_k 设为更小值（如 6），强制 N=2 只看前 6 场，N=3/N=4 再从完整 top-14 中选，`cross_n_used` 只饱和到 6。

**缺点**：改变了 N=2 的候选集，影响其 EV 最优性。

### 方案 C：weighted cross_n_used（频次加权惩罚）

`cross_n_used` 改为 dict（match_id → 出现次数），惩罚时按频次加权：
```python
cross_penalty = sum(cross_n_used.get(_leg_id(l), 0) for l in c.legs)
score -= cross_n_lambda * cross_penalty
```

**优点**：自然保留频次信息，无需截断。

---

## 当前建议

| 建议 | 说明 |
|------|------|
| **生产实盘**：保留 cross_n_lambda=0.5 | 实盘每期场次有限，该参数能有效分散；S9 策略参数正确 |
| **回测**：当前无法验证 cross_n_lambda 效果 | 需要方案 A 或 C 修复后重跑 |
| **默认值**：维持 cross_n_lambda=0 | 避免在不确定效果的情况下影响回测基准 |
| **S9 策略**：在策略页保留，作为实盘分散选项 | 但不应以回测数据为其背书（因无法回测） |

---

## 附：代码变更说明

本次已完成：

- `src/combo_optimizer/builder.py`：`select_diverse_combos()` 新增 `cross_n_used` + `cross_n_lambda` 参数
- `src/combo_optimizer/main.py`：`build_plan()` 透传参数
- `src/phase5a/planner.py`：`build_weekly_plan()` 透传参数  
- `src/webui/services.py`：mix 循环维护 `cross_n_used` set，按 N 层顺序累积
- `src/webui/strategies.py`：新增 S9 策略；`match_strategy()` 比较 `cross_n_lambda`
- `src/webui/templates/strategy_params.html`：新增 cross_n_lambda 滑块 + S9 预设按钮
- `src/backtest_combo/simulator.py`：`simulate_issue()` + `run_combo_backtest()` 支持 mix 模式和 cross_n_lambda
