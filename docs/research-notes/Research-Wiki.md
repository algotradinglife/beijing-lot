---
aliases:
  - Beijing-lot Research Wiki
  - 研究 Wiki
tags:
  - beijing-lot
  - research
  - moc
status: active
updated: 2026-08-02
---

# Beijing-lot Research Wiki

> [!summary]
> 这是研究结论的入口，不是盈利承诺。概率、覆盖率和模拟收益必须分别阅读；
> 历史代理结果不得冒充严格赛前结果。

## 当前结论

1. **EURO 市场信息是目前最稳定的概率基线之一。** 但北单结算目标是带让球的
   3/1/0，不能把无让球 EURO 概率直接当作北单概率。正确入口见
   [[EURO-BJLINE-Baseline|EURO + 北单让球基线]]。
2. **基线在主体概率区间内校准良好，高概率尾部偏乐观。** 1h 样本中，
   Top1 的 40%–60% 区间和 Top2 的 70%–85% 区间最稳定；Top2 ≥85%
   的预测均值为 88.15%，实际覆盖为 84.22%。详见
   [[Top1-Top2-Calibration|Top1 / Top2 校准曲线]]。
3. **加入亚盘让球与水位只有极小的平均改善，尚不足以晋级。** #82 的
   1h 融合相对基线仅改善 log loss `0.000243`，Top1 反而略降；
   初盘快照上 log loss 还略有恶化。详见
   [[Issue-82-Market-Fusion|Issue #82 市场融合实验]]。
4. **连续 EURO 表达已经晋级为唯一历史候选。** #83 不再把 EURO 最大概率
   切成粗桶，而是直接使用去水后的连续对数概率，并结合北单原生让球线。
   相对离散基线，三个快照的 log loss 和 Brier 均改善，且每个快照都是
   10/10 个样本外年份同方向。详见
   [[Issue-83-Continuous-Market-Model|Issue #83 连续市场概率模型]]。
5. **亚洲盘和盘口移动没有获得独立晋级。** 完整 movement arm 的总体指标
   略好，但 93%–99% 的改善已经由连续 EURO 实现；其额外增量很小且逐年
   反转。因此 #77 只接收 `CONTINUOUS_EURO_BJLINE`。
6. **Top2 比 Top1 更贴近 N7 双选问题。** Top2 的覆盖率可以用来估计双选腿，
   但多腿之间并不独立，不能直接把单腿覆盖率连乘后当成真实票命中率。

## 知识图谱

```mermaid
flowchart LR
    A["EURO 原始 1X2"] --> B["比例去水"]
    C["北单原生让球线"] --> D["EURO + BJLINE 基线"]
    B --> D
    B --> M["连续 EURO 对数概率"]
    C --> N["CONTINUOUS_EURO_BJLINE"]
    M --> N
    E["亚盘让球与香港盘水位"] --> F["EURO + Asian + BJLINE 融合"]
    D --> G["Top1 校准"]
    D --> H["Top2 覆盖校准"]
    D --> F
    N --> G
    N --> H
    G --> I["单选腿筛选"]
    H --> J["双选腿 / N7 压缩"]
    F --> K["#82：未晋级"]
    N --> L["#83：唯一历史候选"]
    E --> O["静态 Asian / movement 增量"]
    O --> P["#83：未晋级"]
    L --> Q["#77：严格前瞻验证"]
```

## 阅读路径

| 想回答的问题 | 入口 |
| --- | --- |
| EURO 概率怎样映射到北单让球 3/1/0？ | [[EURO-BJLINE-Baseline]] |
| Top1 各概率段实际命中率是多少？ | [[Top1-Top2-Calibration#Top1 校准曲线]] |
| Top2 各概率段实际覆盖率是多少？ | [[Top1-Top2-Calibration#Top2 校准曲线]] |
| 胜、平、负作为 Top1 时是否一样可靠？ | [[Top1-Top2-Calibration#按 Top1 结果类别分层]] |
| 哪种双选组合更可靠？ | [[Top1-Top2-Calibration#按 Top2 组合分层]] |
| 加入亚盘信息改善了多少？ | [[Issue-82-Market-Fusion#结果]] |
| 为什么融合暂时不能晋级？ | [[Issue-82-Market-Fusion#PI 结论]] |
| 连续 EURO 比离散分桶改善了多少？ | [[Issue-83-Continuous-Market-Model#核心结果]] |
| 改善来自 EURO、亚盘还是盘口移动？ | [[Issue-83-Continuous-Market-Model#改善归因]] |
| 为什么最终只把简单模型交给 #77？ | [[Issue-83-Continuous-Market-Model#PI 决策]] |
| 哪条北单让球线仍然薄弱？ | [[Issue-83-Continuous-Market-Model#原生让球线异质性]] |
| 如何按期望 SP 选场，并按最低赛果概率决定全包、双选或单选胆？ | [#121 Gate A 阈值冻结](../research/bj121_expected_sp_probability_gate_a_2026-08-02.md) |

## 证据等级

本 Wiki 沿用 [[research_status#2.4 Data quality grading|研究状态中的数据质量分级]]：

- **A级**：严格 as-of、赛前冻结、可审计；
- **B级**：有时间戳，但每次使用仍需核验；
- **C级**：历史快照代理，只能探索；
- **D级**：结算或赛后数据，禁止作为赛前特征。

当前 #82、#83 和本次校准曲线属于 **C级历史 timing proxy**。它们适合缩小
研究方向，不适合直接决定真钱投注。#83 的“晋级”只表示进入 #77 的严格前瞻
比较，不表示生产或投注晋级。

## 相关笔记

- [[beidan_vs_euro_divergence|北单与欧赔偏差研究]]
- [[track_b_beat_the_close|Track B：超越市场基线]]
- [[single_match_probability_calibration|单场概率校准设计]]
- [[roadmap|研究路线图]]
- [Issue #82](https://github.com/algotradinglife/beijing-lot/issues/82)
- [Issue #83](https://github.com/algotradinglife/beijing-lot/issues/83)
- [Issue #77](https://github.com/algotradinglife/beijing-lot/issues/77)
- [Issue #121：期望 SP × 最小赛果概率阈值](https://github.com/algotradinglife/beijing-lot/issues/121)
