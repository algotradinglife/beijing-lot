# Issue #314 — CORE/TAIL Soft-MoE、显式覆盖与动态暴露

## 五分钟结论

本轮终审结论是 `NO_LEARNABLE_INCREMENT`，且 **不可推广**。它没有找到优于冻结
控制的完整 learned MoE：

- 2023 model-unseen 验证中，`RAW_LEARNED_MOE` 的中位期末资金为
  **CNY−57.78**，而 #312 精确 `FIXED_N7_K512_WOR` 控制为
  **CNY87,984.27**；31 个 seed 中 learned 赢 0 个，触发强制 fallback。
- 2024 一次性终局中，未获授权的 raw challenger 期末资金为
  **CNY34,373.99**，portable N7/K512/WOR 控制和 guarded primary 均为
  **CNY81,882.32**；paired median lift 为 **−CNY45,972.61**。
- raw challenger 的 2024 总投入是 CNY270,336，是固定控制 CNY67,584 的四倍；
  它不是因缩小暴露而失败，而是动态 K 学到了错误的放大方向：66/66 期都选
  K2048。
- 选择性保护相对 no-protection 的中位 seed lift 为 **+CNY1,048.49**，31 个
  seed 中 **80.65%** 为正；但对抗性终审发现，它相对同预算随机保护的配对
  中位 lift 为 **−CNY594.31**，仅 **45.16%** seeds 为正。因此只能说明“增加
  一个分支可能有机械收益”，不能证明模型学会了保护哪一腿，不能判为
  `STRUCTURAL_SIGNAL`。
- 场次 selector 和赛果 direction 是主要负贡献。把 selector 重置为简单
  GLOBAL 后，控制终值升至 CNY89,179.26；raw 相对它少 CNY54,361.13。把
  outcome direction 重置为 MARKET 后也改善约 CNY5,494.11。

因此本轮真正的认知不是“MoE 可用”，而是：**软权重解决了硬 argmax 的形式
问题，却没有解决长尾 ROI 标签和动态 exposure 外推的不稳定性；当前 learned
selector、direction、保护定位和 K 映射均应被拒绝。**
#210 继续保持 Blocked，不继承 #314 候选。

## 时间与因果边界

独立统计单位始终是北单“期”。比赛、M×3 cell、物理票、expert 和 seed 都嵌套
在期内，不能扩大样本量。

| 阶段 | 年份 | 用途 |
|---|---|---|
| train | 2019–2021 | expert/action ROI 拟合 |
| screen | 2022 | model family、CORE/TAIL 5/10/15% 筛选 |
| validation | 2023 | model-unseen 验证、决定 learned 或 fallback |
| terminal | 2024 | 冻结后一次性结算与归因 |

Gate A 提交 `d240b01` 在打开 2024 结算前冻结了模型、66 期共同支持、31 个
nuisance seeds、2024 allocations 与 SHA。`freeze_receipt.json` 明确记录
`2024_outcome_columns_opened=[]`。2024 是 model-unseen，不宣称 human-unseen。
终局 18,090 个 feature-side match keys 中 17,933 个具有可信可用赛果与中奖 SP，
覆盖率 99.13%。缺失或不可信结算会使包含该场的票 fail closed，且不进入 d=1/d=2
归因；所有 matched 条件共享
同一数据边界，因此不会单独偏袒 learned arm，但绝对收益仍受该缺口影响。

## 输入与专家

输入来自 10h 因果代理面板，保留两个独立的 M×3 概率通道：

- `q_eu_bjline`：平均欧赔映射到北单让球后的三赛果概率；
- `q_line_only_control`：仅由北单让球线形成的粗市场先验；
- signed/absolute divergence、market/value/entropy、盘口和可用公司数等期级
  分布特征。

这仍不包含一个独立、成熟的球队战力概率，因此不能把本轮结论外推为“基本面
分歧无效”。

初始库有 8 个可解释 expert：4 个 CORE、4 个 TAIL。每张票严格是一个 N 串 1；
learned expert 的每个入选场次 coverage depth 只能为 1 或 2，保护腿数显式记录，
不允许用全包 depth=3 冒充模型能力。#312 的 fixed control 只作为历史控制而保留
原有三分支生成语义，它不进入 learned action 空间。

K 锚点为 64/192/512/1024/2048；512 不是上限。模型先输出每个 expert×K 的
预测 ROI，再在 CORE/TAIL sleeve 内做 softmax 权重，最后按 CNY2 粒度整数化。
Ridge、HGB 和 MLP 都由 scikit-learn 提供，没有自写估计器。

## 2022 筛选与 2023 失效方式

2022 筛选选择了 `RIDGE + TAIL 5%`。它在 53 期只投入 CNY6,784（即每期 K64），
中位期末资金 CNY99,256.97、周转 ROI −10.95%。但是用 2019–2022 重拟合后，
模型在 2023/2024 的 114 个预测期全部选到 K2048。这是一个明确的 distribution
shift：开发面认为低 K 较好，重拟合的线性 K 系数却把所有新期推到最大锚点。

2023 结果如下：

| 条件 | 中位期末资金 | 周转 ROI | 最大回撤 | ex-largest P&L | 正收益期率 |
|---|---:|---:|---:|---:|---:|
| #312 exact fixed N7/K512/WOR | 87,984.27 | −24.45% | 16,746.00 | −19,141.39 | 20.83% |
| portable N7/K512/WOR | 87,894.61 | −24.63% | 18,824.71 | −19,785.46 | 20.83% |
| equal CORE mixture | 71,820.21 | −57.33% | 28,179.79 | −30,896.25 | 14.58% |
| fixed CORE/TAIL 90/10 | 71,355.95 | −58.28% | 28,761.79 | −30,843.69 | 14.58% |
| raw learned MoE | −57.78 | −50.89% | 100,057.78 | −107,294.51 | 20.83% |

portable control 与 #312 原始控制只差约 CNY90 的中位终值，说明 N7/K512/WOR
延伸在数值上接近；但两者没有相同的 fitted value/ticket identity，报告仍将它们
严格分名。#312 精确路径只用于 2023 accepted-ladder 锚定；2024 portable 控制
不伪装成 byte-identical continuation。

## 2024 终局与 matched factor attribution

| 条件 | 中位期末资金 | 总投入 | 周转 ROI | 最大回撤 | ex-largest P&L |
|---|---:|---:|---:|---:|---:|
| portable N7/K512/WOR / guarded | 81,882.32 | 67,584 | −26.81% | 27,301.51 | −27,609.38 |
| equal CORE mixture | 74,402.89 | 67,584 | −37.87% | 28,842.22 | −33,981.62 |
| fixed CORE/TAIL 90/10 | 71,321.24 | 67,584 | −42.43% | 31,122.70 | −36,150.16 |
| random protection control | 33,640.95 | 270,336 | −24.55% | 87,657.38 | −102,243.89 |
| raw learned MoE | 34,373.99 | 270,336 | −24.28% | 86,134.19 | −101,679.39 |

raw 的 turnover ROI 看似略优于固定控制，但这是不同暴露规模下的比率，不能
覆盖资金路径：它多投入 CNY202,752，却少留下约 CNY47,508 资金，最大回撤也放大
三倍以上。按用户要求，主判断以 CNY100,000 资金曲线和 matched lift 为准。
将同一 raw expert 比例确定性缩到每期 K512 后，固定暴露诊断终值改善到
CNY83,304.85、最大回撤降到 CNY21,893.67；这进一步确认主要失败来自 K2048
暴露放大，而不是“少下注产生的 alpha”。该诊断不能替换同资金 factor reset。

可持有性也没有通过：raw 的 66 个终局期全部处于水下，样本结束仍连续 66 期
未恢复；guarded control 有 65 期处于水下，末端仍连续 61 期未恢复。两者都不是
可运营候选。

factor reset 的 lift 定义为 `RAW_LEARNED_MOE − RESET`；正值表示 learned factor
相对该单因子重置有贡献：

| 因子重置 | median paired lift | 正 lift seed 比例 | 解读 |
|---|---:|---:|---|
| coverage/protection → none | +1,048.49 | 80.65% | 多加一个分支相对不保护有收益 |
| learned protection → random | −594.31 | 45.16% | 保护位置没有学出优于随机的增量 |
| K unique structure → 512 | +1,980.15 | 58.06% | 未达到 60% 稳定门槛 |
| generator → WOR | 0.00 | 45.16% | 无可辨增量 |
| N → 7 | −668.20 | 32.26% | 动态 N 没有证明价值 |
| outcome direction → MARKET | −5,494.11 | 0% | learned direction 明显伤害 |
| selector → GLOBAL | −54,361.13 | 0% | learned selector 是最大失败源 |

因而没有因子同时满足信息性对照和稳定性门槛，终审降为
`NO_LEARNABLE_INCREMENT`。尤其不能把“优于不保护”误读成“学会了保护位置”。

## Near-miss 的正确读法

2024 逐票记录 d=1/d=2，并区分 realized outcome 在冻结 support 外，还是已在
support 内但有限抽样没有形成中奖 identity。portable control 的 d=1/d=2 分别
为 7,891 / 45,375；raw learned 为 255,095 / 728,431，主要因为它投入四倍。

“再加一个保护结果”的 payout 是 outcome-exposed oracle 上界：它使用真实漏掉
的赛果，目的是量化可挽回规模，不是可执行收益。报告给出真实新增 CNY2 stake，
但其 gross 不能当成策略 ROI；下一轮若使用这一线索，必须先用赛前特征学习
`P(该腿是唯一错误 | issue, ticket, support)`，再做独立年份验证。

## 对抗性审查

如果我是挑战者，会提出以下反驳：

1. **保护 lift 可能只是增加分支的机械效果。** 相对随机保护为负已经推翻
   “当前规则学会保护位置”的解释；31 seeds 也只是抽样噪声，不能把 66 期变成
   2046 个独立样本。
2. **reset 不是完整重训练。** 它回答的是冻结 allocation 下改变一个构造因子的
   局部反事实，不证明重新训练后的全局最优策略会得到相同 lift。
3. **raw exposure 失败可能来自 K 外推，而非 MoE 权重本身。** 这正是本轮发现：
   下一步应把 K 作为带单调/风险约束的独立模型，不再与 expert ROI 共享一个
   无约束预测目标。
4. **portable 控制不是 #312 原票身份。** 所以只将 2023 #312 路径视为 accepted
   ladder；2024 比较的名字和限制均单列。
5. **分歧仍是粗代理。** 当前 `q_eu_bjline − q_line_only_control` 不等于独立战力
   模型与资本均线的完整分歧。

这些反驳把结论进一步收紧为 `NO_LEARNABLE_INCREMENT / NO_PROMOTION`。可以
保留“保护腿值得重新建模”这一研究问题，但不能保留当前保护规则为有效结构。

## 后续方向

不应继续扩大当前 soft-MoE 的 expert 数或神经网络容量。更有价值的下一步是：

1. 以 portable N7/K512/WOR 为安全回退，单独学习“哪一腿值得保护”，目标使用
   d=1 的赛前可预测概率，并显式扣除保护新增 stake；
2. 把 exposure/K 拆成独立模块，使用受约束 marginal-K 曲线或 ordinal model，
   禁止开发期 K64 到验证期全 K2048 的边界塌缩；
3. selector 先退回 GLOBAL/简单市场控制，再逐项加入独立战力分歧，任何改进都
   同时报告绝对资金路径和 matched lift；
4. 只有新的赛前保护模型同时击败 no-protection 和 random-protection，才可称为
   保护增量；在此之前不解锁 #210。

## 可复核入口

- 执行 notebook：`notebooks/research/issue-314/bj314_core_tail_moe.ipynb`
- 冻结收据：`results/issue-314/freeze_receipt.json`
- 终局决策：`results/issue-314/decision.json`
- 资金曲线：`results/issue-314/capital_paths_2024.png`
- 风险前沿：`results/issue-314/risk_return_frontier_2024.png`
- matched attribution：`results/issue-314/matched_factor_attribution_2024.csv`
- near-miss：`results/issue-314/terminal_near_miss_2024.parquet`
- 来源与 replay：`results/issue-314/terminal_source_receipt.json`、
  `results/issue-314/ticket_replay_receipt.json`
