---
aliases:
  - Issue 190 Sparse Divergence N7 Decision Report
  - 稀疏分歧 N7 决策报告
tags:
  - beijing-lot
  - research
  - n7
  - decision
status: decision-review
updated: 2026-08-05
---

# Issue #190：稀疏独立模型—盘口分歧 N7 决策分析报告

PI synthesis timestamp: **2026-08-05 Asia/Shanghai**

主经济口径：**税前 ROI**。税后结果只作敏感性参考。

范围：历史纸面研究与路线决策；不构成下注、购买、生产或策略推广授权。

## 五分钟执行摘要

#190 验证的不是“基本面模型平均是否比市场好”，而是一个更接近用户原始设想的
稀疏价值框架：让独立模型给出赛果概率或预期线，让市场/盘口代表共识价格，只在两者
出现足够大的赛前分歧时选择场次，并沿分歧方向选择赛果。大部分比赛可以不下注。

本轮最重要的结论有六条：

1. **方向判断比重新选场更有信息。** 在 2,424 个冻结 detector policies 上，
   `D_DIRECTION_ONLY` 的中位税前 ROI 为 `-1.89%`，明显好于 expanded-support B0 的
   `-8.52%`；`D_MATCH_ONLY_FULL` 和 `D_JOINT_SPARSE` 的中位数分别为
   `-22.27%` 和 `-16.24%`。这说明当前信号更像“在既有好场次中选择有利方向”，
   而不是“仅凭分歧重新寻找七场”。
2. **宽筛里确有正向结构，但不能把 475 当成 475 个独立发现。** 475 行同时满足
   绝对税前 ROI 为正和 matched B0 lift 为正；经过 bootstrap、去最大期/年份和
   正收益年份检查后只剩 18 个 policy aliases，再按真实票和逐期贡献折叠为 10 个
   不同 issue-economic identities。
3. **最有信息量的 Z100/K1 簇不是单期彩票尖峰。** 其中 6 个不同经济身份覆盖
   52–85 期，税前 ROI 为 `+8.78%` 到 `+20.48%`，相对 matched B0 的 lift 为
   `+21.19pp` 到 `+28.62pp`；bootstrap lift 下界、去最大期和去最大年份结果均为正。
4. **最终 `NO_PROMOTION` 的直接原因是证据覆盖，而不是正收益被推翻。** 上述 18 个
   aliases 全部只在盘口 `0` 上发生，严格合同要求候选 arm 自身至少覆盖两个盘口
   strata，因此严格候选数为 0。正确表述是“存在 line-0、方向型、稳定性较好的历史
   信号，但没有跨盘口推广证据”，不是“分歧方向没有价值”。
5. **独立模型只在总体概率质量上小幅改善。** `FUNDAMENTAL_INDEPENDENT` 相对
   `HANDICAP_CONSENSUS` 的 LogLoss/Brier/ECE 都更好，但 calibrated market estimator
   的 LogLoss 和 ECE 更优。Edge 若存在，更可能是稀疏局部条件，而不是基本面模型对
   全市场的普遍碾压。
6. **路线决策应从静态全局推广转向赛前 regime-conditioned 激活。** 不应把 line-0
   正向簇直接升级为生产策略，也不应因 cross-line 条件失败而丢弃它。#193 应使用
   赛前可见的概率、SP、盘口和分歧结构，判断何时启用 direction-only sleeve；#192
   再在 #193 完成后研究它与其他 sleeve 的风险归一化组合。

一句话决策：**保留 BEST_FULL 为控制基线，把 line-0 direction-only 视为下一轮动态
策略的重要候选组件；不做全局 promotion，也不把 coverage fail 误写成“无信号”。**

## 1. 原始问题与本轮机制

用户提出的核心判断是：盘口代表资本对比赛结果的共识定价，独立模型代表另一套赛前
估值。真正值得研究的不是把两者平均混合后对所有场次重排，而是寻找少数满足以下条件
的比赛：

```text
独立模型估值 ──┐
                 ├── 差值足够大 ──► 选择该场 ──► 沿偏离方向选赛果
盘口/市场共识 ──┘
                    差值不够大 ──► NO_BET
```

这个框架同时解决两个问题：

- **选场**：哪些比赛的模型—市场分歧值得进入 N7；
- **选赛果**：分歧指向哪一侧，资金应该覆盖哪个结果。

其关键假设是分歧稀疏，而不是每场都有 edge。#134 的 blend re-rank 对每场都做微调，
容易把局部独立判断稀释成市场概率的小扰动；#190 则把“是否有分歧”和“分歧方向”显式
拆开。

## 2. 四臂设计：把选场贡献与方向贡献分开

| Arm | 固定什么 | 改变什么 | 回答的问题 |
|---|---|---|---|
| `B0_BEST_FULL` | 既有 BEST_FULL identities | 无；每个 N7 全覆盖 | 当前选场基线表现如何？ |
| `D_MATCH_ONLY_FULL` | 分歧 detector 选出的 identities | 仍然 FULL | 分歧只用于选场是否有价值？ |
| `D_DIRECTION_ONLY` | B0 的既有 identities | 仅按分歧方向分配赛果 | 分歧只用于选赛果是否有价值？ |
| `D_JOINT_SPARSE` | 无 | 分歧同时选场和选方向 | 两层合用能否叠加？ |

完整冻结面为 `2,424 policies × 4 arms`。汇总如下：

| Arm | 有 stake 的 policy rows | 中位税前 ROI | 正 native ROI rows | 正 matched lift rows |
|---|---:|---:|---:|---:|
| B0_BEST_FULL | 2,424 | -8.52% | 0 | 0 |
| D_MATCH_ONLY_FULL | 1,884 | -22.27% | 48 | 142 |
| D_DIRECTION_ONLY | 861 | **-1.89%** | 369 | 662 |
| D_JOINT_SPARSE | 1,884 | -16.24% | 128 | 201 |

### 对四臂结果的解释

- **match-only 明显弱于 B0**：当前分歧 detector 尚不适合单独替代既有选场器。
- **direction-only 最接近打平且产生最多正向 cells**：独立信号在“押哪边”上的作用，
  比在“重建哪七场”上的作用更清晰。
- **joint 没有继承 direction-only 的优势**：选场和方向存在负交互，不能把两个看似
  合理的环节默认相加。这与 #170 的 selector × allocator 非可加性结论一致。
- **B0 的 -8.52% 不是新的 accepted baseline**：它来自 #190 扩展到 189 期的
  SHA-bound SQLite 支持，只用于本轮描述；163 期共同支持上的控制性基线仍为 -9.47%。

## 3. 基线阶梯：为什么同时存在 -9.47% 和 -8.52%

| 口径 | 结算期数 | Stake | Gross | 税前 ROI | 决策角色 |
|---|---:|---:|---:|---:|---|
| ACCEPTED_LEGACY_95_OVERLAP | 163 | ¥712,962 | ¥645,459.39 | **-9.47%** | 继承的 BEST_FULL 基线 |
| EXPANDED_HASH_BOUND_SQLITE | 189 | ¥826,686 | ¥756,244.00 | **-8.52%** | #190 扩展支持描述值 |

两者不是同一分母上的策略改进。-8.52% 说明新增可结算支持没有恶化总体描述，但不能
据此宣布基线从 -9.47% 提升了 0.95pp。任何后续 challenger 都应同时报告：

1. native support 的绝对税前 ROI；
2. 与 B0 完全匹配支持上的 lift；
3. 是否替换 accepted baseline，或仅是扩大支持后的描述值。

## 4. 证据漏斗：475 → 18 → 10 → 0 到底表示什么

```text
2,424 个冻结 policies × 四臂
          │
          ▼
475 个描述性阳性 rows
绝对税前 ROI > 0 且 matched B0 lift > 0
          │
          ▼
18 个 performance-stable policy aliases
bootstrap lift 下界 > 0；去最大期/年份 ROI > 0；至少 2 个正收益年份
          │
          ▼
10 个不同 issue-economic identities
按选中期、N7 票身份/倍数和逐期贡献向量去除参数别名
          │
          ▼
0 个 strict-promotion candidates
全部仅覆盖 line stratum {0}，未满足候选 arm 自身的跨盘口覆盖要求
```

### 4.1 为什么 475 不能直接解读为大量 edge

冻结网格包含大量相近阈值和参数别名。若两个 policy 最终选择完全相同的期、生成相同
的票和逐期现金流，它们在经济上是同一个策略，而不是两次独立发现。475 是搜索面上的
描述行数，适合发现结构，不适合充当统计票数。

### 4.2 为什么 18 仍然值得重视

这 18 个 aliases 已经通过本轮冻结的收益稳定性检查。它们不是只依赖最大一期或最大
年份才为正，也不是 bootstrap 点估计偶然大于零。它们折叠为 10 个不同经济身份后，
仍说明 line-0 方向信号在多个支持宽度下重复出现。

### 4.3 为什么最终仍必须是 0

严格晋级合同还要求候选 arm 自身至少覆盖两个联赛和两个盘口 strata。#195 发现旧口径
曾错误继承 match-only 的盘口覆盖；纠正后，18 个 direction-only aliases 的实际 line
集合都只有 `{0}`。因此它们无法证明同一机制能跨让球线工作。

这是一项**外推边界失败**，不是一项**收益稳定性失败**。若报告只写
`NO_PROMOTION_FROM_GATE_B` 而不保留这一区别，会丢失本轮最重要的科学信息。

## 5. Z100/K1 正向簇：本轮最值得讨论的数据

Z100/K1 簇包含 12 个参数 aliases，折叠为 6 个不同经济身份：

| 经济身份 | 规则 | 期数 | 税前 ROI | matched lift | bootstrap lift 下界 | 去最大期 ROI | 去最大年份 ROI | line strata |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `ad7ab0b665324240` | DP050_Z100 / K1 | 52 | +14.89% | +27.92pp | +0.37pp | +7.28% | +20.60% | 1 |
| `177ac7f82fe65a8b` | Z_100 / K1 | 60 | +19.83% | +27.97pp | +1.19pp | +8.48% | +31.66% | 1 |
| `db2a66f423b3b694` | DP050_Z100 / K1 | 60 | +20.48% | +28.62pp | +1.79pp | +9.14% | +32.62% | 1 |
| `4c468ed3f19f632e` | DP050_Z100 / K1 | 75 | +14.83% | +26.96pp | +4.27pp | +5.71% | +25.92% | 1 |
| `7fe30c9f6b63326b` | DP050_Z100 / K1 | 75 | +15.35% | +27.48pp | +4.67pp | +6.24% | +26.67% | 1 |
| `047f1906e3624153` | DP050_Z100 / K1 | 85 | +8.78% | +21.19pp | +0.13pp | +0.67% | +16.39% | 1 |

### 这组数据支持什么

- 支持“方向分歧可能包含局部价值”的研究假设；
- 支持把这一簇作为 #193 的候选 action/sleeve，而不是从候选目录中删除；
- 支持重点研究为什么它只在 line 0 和特定赛前结构中出现；
- 支持用 prior-only regime policy 判断何时激活，而不是每期强制使用。

### 这组数据不支持什么

- 不支持把 +8.78% 到 +20.48% 当成未来可实现收益；
- 不支持跨盘口、跨规则的全局推广；
- 不支持从 2,424 个 policy 中事后挑一个最优点直接部署；
- 不支持把 12 个 aliases 当成 12 次独立重复验证；
- 不支持在本批 outcomes 上继续微调阈值来“救成”严格阳性。

## 6. 概率模型表现：独立模型有改善，但不是普遍优势

在 100,906 个 trusted outcomes 上：

| Probability source | LogLoss | Brier | ECE | 相对 handicap consensus |
|---|---:|---:|---:|---|
| HANDICAP_CONSENSUS | 1.126232 | 0.683754 | 0.081892 | 对照 |
| FUNDAMENTAL_INDEPENDENT | 1.116766 | 0.677073 | 0.073369 | 三项均改善 |
| CALIBRATED_MARKET_ESTIMATOR | **1.114387** | 0.677845 | **0.067176** | LogLoss/ECE 最好 |

基本面独立模型确实比 handicap consensus 更接近真实结果，但 calibrated market
estimator 仍有更好的 LogLoss 和 ECE。这与“市场在大部分场次定价正确、可利用分歧只
稀疏存在”的假设一致：平均预测质量的小幅提升，不会自动转化为均匀下注 edge。

因此下一轮不应追求把独立模型全面替换市场模型，而应回答：

- 哪些赛前 regime 下独立模型的偏离更可信？
- 偏离方向是否在不同盘口/联赛/年份保持一致？
- 偏离强度、概率熵、SP 结构与可执行 N7 资金效率如何共同决定是否下注？

## 7. 风险、稳定性与多重比较

### 已经降低的风险

- Z100/K1 经济身份覆盖 52–85 期，不是 1–2 期的极窄尖峰；
- paired issue bootstrap 的 lift 下界为正；
- 删除最大正贡献 issue 后税前 ROI 仍为正；
- 删除最大 payout year 后税前 ROI 仍为正；
- 至少两个年份为正；
- 参数 aliases 已折叠为真实 issue-economic identities。

### 仍未解决的风险

- **盘口覆盖**：所有稳定身份只有 line 0；
- **回顾性搜索**：2,424 个 policies 仍构成较大的冻结搜索面；
- **历史复用**：正向簇已在本批 outcomes 中被识别，不能再把同批数据当独立确认；
- **regime 可识别性**：尚未证明只用赛前特征就能在未知结果前选中这些有利期；
- **策略交互**：joint arm 的总体表现显示，方向优势与重新选场不一定可加；
- **资金路径**：即使 aggregate ROI 为正，后续仍需检查逐期权益、回撤、尾部共亏和
  与其他策略的相关性。

因此本轮最合理的状态不是“promote”或“discard”二选一，而是
`EXPLORATORY_DIRECTION_SLEEVE / COVERAGE_LIMITED / PRIOR_ONLY_ACTIVATION_REQUIRED`。

## 8. 对后续路线的决策建议

### 8.1 #193：先解决“什么时候启用”

截至 2026-08-05 的 live Issue Graph 中，[#193](https://github.com/algotradinglife/beijing-lot/issues/193)
为 `Ready`，且 #190 是其已关闭上游之一。#193 应把 #190 的结果纳入，但要严格分成
两个证据层：

1. **Oracle diagnostic**：允许用事后结果估计“若每期知道最佳 action，理论上最多能
   改善多少”，只测上限和 regret，禁止晋级；
2. **Causal pre-event policy**：只用当期截止时可见信息，通过 expanding-window、
   nested-LOYO 或等价时序隔离，选择是否启用 direction-only 及其参数。

建议 #193 将以下 #190 特征放入冻结特征集：

- 独立模型与盘口/市场概率的分歧强度、方向和分位数；
- line 组成，特别是 line 0 占比与候选数；
- 每期 eligible matches、候选 identity 数和 K1 可行性；
- 概率熵、最小概率、E_SP、GM_E_SP、SP 离散度；
- 基本面与 calibrated-market 两类估计的一致/冲突模式；
- 明确 missingness/coverage 标志。

核心比较不应只是“动态策略 vs B0”，还应包含：

- 静态 B0；
- 静态 line-0 direction sleeve；
- 仅动态 M；
- 仅动态 selector；
- 仅动态 allocator/direction；
- 完整 regime-conditioned tuple；
- oracle ceiling。

若 causal policy 不能选中正向期，也要区分：没有 oracle opportunity、赛前特征无法
识别、action 噪声过大、支持不足，还是模型真的无效。

### 8.2 #192：后解决“如何组合”

[#192](https://github.com/algotradinglife/beijing-lot/issues/192) 当前被 #193 原生
`blockedBy`，Project 状态为 `Blocked`。这一顺序是正确的：只有 #193 先定义可在赛前
选择的 sleeve 和 M，#192 才能研究它们与 BEST_FULL、既有 allocator sleeves 的资金
归一化组合。

#192 对 #190 direction sleeve 至少应检查：

- 与 BEST_FULL 和其他 sleeves 的逐期收益相关、秩相关；
- 下行相关、共同亏损率和 worst-decile overlap；
- line-0 regime 是否与其他策略共振或形成对冲；
- 各自最优 M 后的等资本、逆波动、equal-risk-contribution；
- ROI 改善来自独立收益，还是仅来自 covariance reduction；
- 去最大期/年份、LOYO 和 rolling regime 下的组合稳定性。

### 8.3 是否立即补做跨盘口实验

不建议为了满足形式要求，把 line-0 规则机械外推到数据稀疏的其他盘口。更合理的顺序是：

1. 先用 #193 判断 line-0 正向簇能否被赛前识别；
2. 同时统计其他 line strata 的可用支持、分歧含义和赛果映射是否同构；
3. 只有当跨盘口有足够样本且足球语义一致时，再建立单独的 outcome-unexposed 合同；
4. 若不同盘口机制不同，应分层建模，不应只为得到“2 strata”而混池。

## 9. 供决策讨论的关键问题

1. **研究资产定位**：是否同意将 Z100/K1 定义为
   `coverage-limited exploratory direction sleeve`，进入 #193 action catalog，但不晋级？
2. **主攻方向**：下一步资源是否优先用于“赛前识别何时启用”，而非继续扩大静态阈值
   网格？
3. **盘口边界**：line 0 是否可以作为独立可研究市场机制，还是必须等待跨盘口复制后
   才保留任何候选资格？
4. **成功标准**：#193 是否以改善 matched B0 的绝对税前 ROI、regret 和回撤为共同
   目标，而不是只要求一次性达到正 EV？
5. **组合顺序**：是否确认 #192 继续等待 #193，避免用事后挑选的 sleeve 权重做伪对冲？
6. **验证强度**：若 #193 只有负结果，采用常规复现与详细归因；只有出现 materially
   positive、可晋级 causal candidate 时才启动严格独立 EV。

## 10. PI 结论

#190 没有给出可推广策略，但它把路线从“基本面平均混合重排”推进到了更有解释力的
“独立估值—市场定价稀疏分歧”框架。这个进步主要体现在：

- 四臂归因确认信号更偏向方向层，而不是全量重选场；
- 经济身份折叠后仍存在多个较宽支持的正向历史簇；
- 稳定性与 coverage 被正确拆开，避免把外推限制误当成信号消失；
- 下一步问题已从“静态阈值是否正收益”收敛为“赛前 regime 能否识别何时使用”。

所以本轮的决策不是推广，也不是收掉，而是：**保持 B0 控制线，冻结 line-0
direction-only 研究资产，交给 #193 做严格赛前动态激活检验；在 #193 给出可执行 sleeve
前，#192 不启动结果驱动的组合权重优化。**

## 术语速查

| 术语 | 含义 |
|---|---|
| `native support` | 某策略按自身规则实际可执行且有可信结算的期/身份集合 |
| `matched B0 lift` | 候选与 B0 限制到相同可比较支持后，候选 ROI 减 B0 ROI |
| `policy alias` | 参数名不同，但可能生成相同经济行为的冻结规则行 |
| `issue-economic identity` | 由选中期、N7 票身份/倍数和逐期贡献向量定义的真实经济策略 |
| `line stratum` | 北单让球线分层；本轮稳定正向身份只有 line `0` |
| `K1` | 每期最多保留一个合格 N7 identity；不是每期只买一张票 |
| `bootstrap low` | 以完整 issue 为块重采样得到的 paired lift 95% 区间下界 |
| `ex-largest` | 删除最大正贡献 issue 或 payout year 后重算 ROI |
| `direction-only` | 保持 B0 选场身份，只让分歧决定赛果方向/票分配 |
| `joint sparse` | 分歧同时决定选场和赛果方向 |
| `NO_PROMOTION` | 未达到冻结晋级条件；不等于所有中间信号都为零 |

## 证据与追溯入口

- [Issue #190](https://github.com/algotradinglife/beijing-lot/issues/190)：研究合同与终局讨论；
- [Issue #195](https://github.com/algotradinglife/beijing-lot/issues/195)：独立复验与 coverage 纠正；
- [PR #194](https://github.com/algotradinglife/beijing-lot/pull/194)：Gate B 终局合并；
- [#190 研究摘要](Issue-190-Sparse-Divergence-N7.md)；
- [#190 Gate B 完整报告](../../results/bj190_gate_b_sparse_divergence_v1/REPORT.md)；
- [四臂归因表](../../results/bj190_gate_b_sparse_divergence_v1/four_arm_attribution.csv.gz)；
- [完整 frontier](../../results/bj190_gate_b_sparse_divergence_v1/full_frontier.csv.gz)；
- [概率质量表](../../results/bj190_gate_b_sparse_divergence_v1/full_population_probability_metrics.csv)；
- [coverage—ROI frontier 图](../../results/bj190_gate_b_sparse_divergence_v1/coverage_roi_frontier.svg)；
- [matched lift frontier 图](../../results/bj190_gate_b_sparse_divergence_v1/matched_lift_frontier.svg)；
- [threshold × top-K heatmap](../../results/bj190_gate_b_sparse_divergence_v1/threshold_topk_heatmap.svg)；
- [Gate B package README](../../results/bj190_gate_b_sparse_divergence_v1/README.md)。

不可变终局绑定：

- package manifest：`5685f25d9ce70a66b38b283f668d258d97dfe2e356c5bd45d9666400c6ab4554`；
- content identity：`5112dc652277a234fcb36687d59e2bd96bf8daeaaa1c9ddd06481923de909ce6`；
- manifest payload：`43 / 43` 通过复算。
