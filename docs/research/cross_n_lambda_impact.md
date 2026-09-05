# cross_n_lambda 回测影响分析

**日期**: 2026-05-24  
**参数**: `cross_n_lambda` — 控制多 N 层之间场次重叠的跨层惩罚系数  
**修复**: 方案 A — 频次截断（`_CROSS_N_TOP_LEGS = 5`，仅传递 top-5 高频腿）

---

## 回测对比结果（修复后）

| 指标 | S1 稳健 (../../doc/λ=0) | S9 跨N多样化 (../../doc/λ=0.5) | Delta |
|------|--------------|---------------------|-------|
| 总盈利 | -1,079,597 元 | -1,059,027 元 | **+20,571 元** |
| 总下注额 | 3,671,456 元 | 3,671,364 元 | -92 元 |
| ROI | -29.41% | -28.85% | **+0.56%** |
| 命中率 | 7.83% | 7.88% | +0.04% |
| 周 Sharpe（年化） | -2.063 | -1.998 | **+0.065** |
| 最大回撤 | -1,100,517 元 | -1,092,795 元 | **+7,721 元（改善）** |
| 期数 | 相同 | 相同 | 0 |

8 年历史数据，S9 在所有指标上均略优于 S1：ROI +0.56%，回撤收窄 7,721 元，Sharpe 改善 0.065。

---

## 早期问题：top_k 池饱和（已修复）

### 原始问题

修复前，每期 N=2 运行完毕后将**所有** `match_id:selection` 加入 `cross_n_used`：

```python
# 修复前（每一张票的每一条腿都加入）
for plan in sub_plans:
    for leg in plan.combo.legs:
        cross_n_used.add(../../doc/f"{leg.match_id}:{leg.selection}")
```

每期 top_k=14 候选，N=2 生成 60 张票（每张 2 腿），60 张票覆盖全部 14 个场次。
→ `cross_n_used` 立即饱和到 14/14
→ N=3/N=4 所有 combo 受到完全相同的跨层惩罚
→ 排名不变，选择完全相同，Delta = 0

### 修复（方案 A）

只传递 N=2 中**出现最频繁的 top-5 个 `match_id:selection`**：

```python
# 修复后（只传频次最高的 5 个）
cross_n_used.update(_top_freq_leg_ids(sub_plans, _CROSS_N_TOP_LEGS))  # _CROSS_N_TOP_LEGS=5
```

`_top_freq_leg_ids` 用 `Counter.most_common(../../doc/top_k)` 实现，零歧义：

```python
def _top_freq_leg_ids(sub_plans: List[TicketPlan], top_k: int) -> set:
    freq: Counter = Counter(
        f"{leg.match_id}:{leg.selection}"
        for plan in sub_plans
        for leg in plan.combo.legs
    )
    return {lid for lid, _ in freq.most_common(../../doc/top_k)}
```

修复后，N=3/N=4 只有使用了那 5 个"核心"场次的 combo 受到惩罚，其余 9 个场次无惩罚，排名出现差异，选择结果不同。

---

## 参数调节建议

| `_CROSS_N_TOP_LEGS` | 含义 | 适用场景 |
|---------------------|------|---------|
| 3 | 只惩罚最核心 3 场 | 池小（≤8 场），保留更多分散空间 |
| **5（默认）** | 惩罚次核心 5 场 | 回测（14 场池）的均衡选择 |
| 7 | 更激进分散 | 大池，对高频腿容忍度低 |

目前 `_CROSS_N_TOP_LEGS = 5` 在两个文件中以常量定义，修改一处即生效。

---

## 结论

| 建议 | 说明 |
|------|------|
| **S9 + cross_n_lambda=0.5** | 小幅提升 ROI、Sharpe、回撤，无副作用，建议作为默认配置 |
| **`_CROSS_N_TOP_LEGS = 5`** | 当前最佳截断值；如果实盘池很小（<8 场），可调低到 3 |
| **不推荐 cross_n_lambda > 1.0** | 惩罚过强会排斥高-EV 场次，降低整体 EV |

---

## 附：代码变更说明

**修复涉及两处**：

- `src/backtest_combo/simulator.py`
  - 新增 `from collections import Counter`
  - 新增常量 `_CROSS_N_TOP_LEGS = 5`
  - 新增函数 `_top_freq_leg_ids(sub_plans, top_k) -> set`
  - `simulate_issue()` 内用 `cross_n_used.update(_top_freq_leg_ids(../../doc/...))` 替换原循环

- `src/webui/services.py`
  - 新增 `from collections import Counter`
  - 新增常量 `_CROSS_N_TOP_LEGS = 5`
  - 新增函数 `_top_freq_leg_ids_dict(tickets, top_k) -> set`（dict 版本）
  - mix 循环内同样替换为频次截断版本
