# Issue #312 — 显式场次、赛果与保护联合动作立方体

## 五分钟结论

本轮没有找到可接受的增量策略，终审结论为 `NO_INCREMENT`。在冻结的
exact-B0 共同支持上，2023 年 48 期每期固定投入 512 注、CNY1,024，开发期
选定的 `JOINT_TAIL` 中位终值为 CNY70,795.72；最强同资金控制
`FIXED_N7_K512_WOR` 为 CNY87,984.27。两个 seed 中位终值之差为
-CNY17,188.55，而先逐 seed 配对再取中位数的 lift 为 -CNY18,163.94。
31 个物理 seed 中只赢 5 个，低于预设的 19 个门槛；同暴露 permutation
百分位只有 13.6%，且 ex-largest P&L 为 -CNY35,974.61。

这不是“联合参数没有价值”，而是对当前建模方式的否定：小型 MLP 直接从
期级特征与完整 action identity 预测高噪声、长尾的 action ROI，再做硬
`argmax`，会把有限的排序误差放大成错误动作。模型对平均 ROI 的 pooled
Spearman 仍有 0.309、期内中位 Spearman 有 0.443，但这些弱排序能力不足以
可靠识别最优尾部动作。下一步应把神经网络降为候选专家，把学习目标下沉到
M×3 cell 的概率、价值与不确定性，再由受约束的组合优化器完成 N、场次、
赛果和保护配置。

## 为什么本轮重做了共同支持

#306 的 post-merge EV 发现其正向 `ACTION_VALUE_SIGNAL` 使用了更宽的 #209
支持集，而非契约要求的 inherited exact-B0 共同支持。将 2023 限制到正确的
48 期后，#306 的开发选择与正向 matched-lift 结论均不能复现。因此 #312：

- 只继承 #306 的票生成接口，不继承其正向科学结论；
- 开发排序限定在 #299 `MATCHED_BASELINE_AND_FEATURES` 支持：2019–2022
  分别 47、30、49、53 期；
- 2023 终评固定为 48 期；
- #306 策略仅作为接口型次要对照，不参与最强控制判定；
- 额外报告 exact B0/BEST_FULL one-bundle 经济结果，但由于其投入规模不同，
  不把它伪装成同资金比较。

### 合并前因果读取修正

PI 终审发现，最初的开发 runner 调用 #209 `build_tensor()` 后才筛选
`issue_year < 2023`。2023 标签没有进入特征、动作或选择逻辑，且冻结提交早于
终评结算提交，但底层进程确实曾先打开 2023 标签，因此原实现不满足严格的
outcome-unexposed 读取边界。

合并前已改为两层物理读取约束：Parquet 对赛果标签执行年份谓词下推，SQLite
只查询该投影中出现的期号；为对齐 #209 未携带 unit key 的旧模型输出，未来
年份只投影 `issue_code/match_idx` 身份列，不打开 `target_outcome` 或 SP。随后用
新入口重建 2019–2023 全部 action×physical-seed 账本，并与既有账本逐项比较。
`results/issue-312/causal_replay_receipt.json` 记录结果；若不完全一致，本报告与
PR 不得合并。

## 冻结设计

### 动作空间

在读取 2023 赛果之前冻结 192 个开发动作，再由 2021/2022 expanding OOF
冻结 48 个终评候选。动作向量显式包含：

- `N=3..10`；
- `K=8/32/128/512`，最终每期通过重复 bundle 固定为 512 注；
- 场次 selector：global value、best value、low entropy、cold excludable、
  divergence、hybrid；
- candidate pool：N、N+2、N+4、全部可用场次；
- 赛果方向：market probability、raw value、signed divergence、hybrid；
- 票生成：TOP、WR、WOR；
- 保护：none、uncertainty、divergence、5%/15% soft re-entry。

每张中奖 N 串 1 的结算为：

```text
gross = CNY2 × 0.65 × product(SP_SETTLE legs)
```

`0.65` 只在整张票上应用一次，不按腿重复折扣。

本轮 `divergence` 的精确定义是
`q_eu_bjline - q_line_only_control`：前者把平均欧赔概率映射到北单让球后的
三赛果空间，后者只是让球线构造的粗先验。它不是北单三项 SP 反推概率，
也不包含独立球队战力概率。因此本轮只能检验“欧赔映射 vs 粗让球线先验”
这一种分歧实现，不能外推为所有基本面/市场分歧均无效。

### 时间与资金边界

- 2019–2022：开发；2021/2022 为 expanding OOF 选择窗口；
- 2023：一次性终评；2024+ 未读取；
- 每个条件在完全相同的 48 期上，每期 512 注 / CNY1,024；
- 开发 11 个物理 seed，终评 31 个物理 seed；
- action registry、候选表与 2023 allocation 分别在赛果读取前提交并绑定 SHA。

## 主要结果

| 条件 | 2023 中位终值 | 本金增长 | 周转 ROI | 最大回撤 | 正收益期率 | 任意返奖率 | ex-largest P&L |
|---|---:|---:|---:|---:|---:|---:|---:|
| IDENTITY_SHUFFLED | 95,807.81 | -4.19% | -8.53% | 15.24% | 20.83% | 41.67% | -17,838.96 |
| #306 interface comparator | 88,557.97 | -11.44% | -23.28% | 16.97% | 18.75% | 54.17% | -17,283.99 |
| FIXED_N7_K512_WOR | 87,984.27 | -12.02% | -24.45% | 16.13% | 20.83% | 29.17% | -19,141.39 |
| ABLATE_OUTCOME | 75,231.50 | -24.77% | -50.39% | 27.32% | 10.42% | 14.58% | -33,119.29 |
| JOINT_MEAN | 73,961.63 | -26.04% | -52.98% | 26.04% | 10.42% | 47.92% | -30,070.28 |
| JOINT_PRIMARY / TAIL | 70,795.72 | -29.20% | -59.42% | 30.18% | 10.42% | 12.50% | -35,974.61 |
| ABLATE_SELECTOR | 68,261.35 | -31.74% | -64.57% | 31.74% | 10.42% | 10.42% | -37,463.17 |
| ABLATE_PROTECTION | 68,163.07 | -31.84% | -64.77% | 33.16% | 8.33% | 10.42% | -39,934.51 |
| BEST_STATIC_ACTION | 50,848.00 | -49.15% | -100.00% | 49.15% | 0.00% | 0.00% | -48,128.00 |

exact B0/BEST_FULL one-bundle 在相同 48 期总投入 CNY153,090，P&L 为
-CNY20,751.04，周转 ROI -13.55%，终值 CNY79,248.96。它不是每期 CNY1,024
的 matched control，不能与上表直接比较绝对终值优劣。

## 风险路径

`JOINT_PRIMARY` 的中位最长连续亏损期为 18，最长无返奖为 15；最差滚动
5/10/20 期 P&L 分别为 -CNY5,120、-CNY10,240、-CNY19,096.91。31 个 seed
没有一个终值超过初始 CNY100,000，且中位路径直到样本末端仍处于水下。
因此，即使忽略相对基线，它也不具备用户要求的可持有性。

固定 N7/WOR 的中位最长亏损期为 9、最长无返奖为 7，路径风险明显较小；
但其终值仍为负。它继续是安全控制，不是可投产正 Edge。

## MLP 到底学到了什么

模型不是完全随机：

| 目标 | pooled Spearman | 期内中位 Spearman | 期内相关为正比例 |
|---|---:|---:|---:|
| mean ROI | 0.309 | 0.443 | 72.92% |
| positive probability | 0.413 | 0.546 | 89.58% |
| 5x tail probability | 0.347 | 0.402 | 93.75% |

但“平均排序有信息”不等于“最顶部 action 可选”。硬 `argmax` 专门选择预测
误差最大的尾部，形成 winner's curse。55 个同时存在于开发与终评的静态动作，
开发—2023 排名 Spearman 只有 0.167，证明 action 排名的跨期迁移很弱。

最典型的是开发期最佳静态动作 `N10/K8/GLOBAL_VALUE/RAW_VALUE/WR/NONE`：
31 个终评 seed 中 30 个终值都是 CNY50,848，只有 1 个 seed 命中特大回报，
最大终值 CNY5,136,275.62。其 seed 中位数是全损、均值却为 CNY214,894.05。
这正是不能用均值 ROI 直接训练并 argmax 的原因。

`IDENTITY_SHUFFLED` 的中位终值较好也不能当策略：它是负对照，不是可部署
规则；其均值同样被单一大奖 seed 拉到 CNY266,752.73，ex-largest 仍为负。
它只能说明当前 learned identity mapping 不优于一个偶然的、较分散的动作映射。

## 各因素的可解释信号

配对 ablation 给出的窄结论是：

- protection 相对完全去保护，中位 seed lift +CNY4,359.35，80.65% seeds
  为正；但 ex-largest lift 为 -CNY1,308.88，且联合策略整体仍显著落后控制。
  因此它是值得保留的参数，不是独立 Edge。
- selector 相对 global reset，中位 lift +CNY583.51，54.84% seeds 为正，
  但 ex-largest lift -CNY3,337.81，证据很弱。
- outcome direction 相对 raw-value reset，中位 lift -CNY807.66，只有 38.71%
  seeds 为正；当前 divergence/hybrid outcome 学习是负贡献。

结果暴露后的全动作边际表中，WR 的平均 ROI 好于 WOR，TOP 最差；N7/N8
比 N3–N6 稳定，N10 均值则完全由极少大奖驱动。这些边际不是随机化的 matched
因果比较，只能用于提出下一轮假设，不能直接挑参数。

## 对抗性解释

如果挑战本轮结论，最强反驳是：训练期数仍少、2023 可能发生 regime shift，
而 pooled/within-issue 相关为正，说明换损失或决策层可能挽救信号。这个反驳
成立，因此本轮不能证明“神经网络永远无效”。

但它不能挽救当前策略：预注册的 primary 在 31/31 seeds 都没有正终值；其
中位终值比最强控制低 CNY17,188.55，paired-seed median lift 为
-CNY18,163.94，permutation 位于 13.6th percentile，且路径与
ex-largest 同时恶化。继续围绕该 MLP 调层数或学习率属于错误层级的优化。

## Post-merge EV 解释边界

异步 EV 对 merge commit `c7d09b8` 的独立复算不改变 `NO_INCREMENT`，但修正
并收窄了三处解释：

- 上述 CNY17,188.55 是两个 seed 中位数之差，不是 paired-seed median lift；
  后者是 -CNY18,163.94。配对胜场严格针对已命名的最强控制，不再使用逐 seed
  从多个控制中取最大值的复合门槛。
- 冻结的 matched 单因子 reset 只覆盖 selector、outcome direction 和
  protection。N/K、generator、candidate pool 的表格是 outcome-exposed
  描述性边际，不能据此断言这些因素没有增量，也不能用于 retain/delete 决策。
- 2023 ledger 的 `temporal_role=calibration` 是继承自 #209 的来源角色，而在
  #312 实验中 2023 是 terminal evaluation。当前计算按年份执行，不影响本轮
  结论；下游必须拆分 source role 与 experiment role，避免接口误读。

fresh checkout 缺少外置的原始 Parquet/SQLite 与 ticket-leg primitives，因此
EV 没有从原始源独立重建每张票的 gross。已确认的边界包括 47 个 manifest
payload、共同支持、聚合账本、因果重拟合和代码中整票仅乘一次 0.65。原始数据
不提交 Git；下一轮必须提供可定位的 source manifest 与 ticket-level replay
receipt。这是 exploration 可接受的可移植性边界，不是已完成的独立源复算。

## 下一步模型架构

1. **先做纯 MoE soft mixture。** 把可解释的 N7/WOR、value-WR、保护型与
   少量长尾生成器作为 experts；gate 每期把 512 注按连续权重分给多个专家，
   而不是硬选唯一 action。第一版使用正则化线性 stacking/softmax gate，
   同时保留等权与固定权重混合作为简单控制。
2. **显式拆成 CORE 与 TAIL 两类专家。** CORE 占大部分资金，目标是打平或
   微赢，必须通过中位/截尾收益、ex-largest、亏损连段和滚动窗口门槛；
   TAIL 只占小 sleeve，允许一两年才出现一次大奖，但要求长期贡献可解释、
   最大持续拖累有界，并与 CORE 及其他 tail 路径低相关。第一版冻结
   CORE 85%–95%、TAIL 5%–15% 的小网格，禁止一次尾部预测接管全部资金。
3. **分歧拆成独立专家通道。** 至少分开检验欧赔映射概率与北单让球隐含
   概率的偏离、球队战力概率与北单让球隐含概率的偏离；未来有可靠多时点
   数据后再加入赔率变化/消息面分歧。不能继续把不同来源压成一个分数。
4. **先优化保守价值而非长尾。** CORE 主目标使用 shrinkage 后期望净收益
   或 log-capital growth，并以正收益期率、最坏窗口和下行风险为约束。
   不能只最大化命中率，因为低赔率高命中仍可能稳定亏损；TAIL 另用长期
   贡献、尾部命中间隔和组合分散价值评价，不能套用 CORE 的中位收益门槛。
5. **学习对象下沉到 M×3 cell。** 分别估计校准胜率、条件返奖、市场—模型
   divergence 与不确定性，避免直接拿极稀疏的整套 action ROI 当主标签。
6. **模型并列而非 MLP 独占。** 用 regularized linear、成熟树模型和 MLP
   作为专家；神经网络只有在时序 OOS 明确优于简单模型时才获得权重。
7. **组合层采用受约束优化。** 输入 cell 分布和协方差，联合决定 N、场次
   子集、赛果、WR/WOR、选择性保护与资金暴露；禁止无保护的硬 argmax。
8. **先寻找真正的 CORE frontier。** 当前 exact-support N7/WOR 本金增长仍为
   -12.02%，只能作为风险控制，尚不能称为打平 CORE。应先从专家库与简单
   混合中找到接近 0 的稳定前沿，再优化 tail sleeve 占比。
9. **回退约束。** 任一 learned policy 在开发 OOS 不满足 matched baseline
   与路径门槛时，必须回退到 frozen control；#312 不打开 #210 或 2024+。

### 下一轮新增的显式动作参数

本轮每张票在每场只有一个赛果，跨票覆盖深度主要由赛果权重和 WR/WOR 抽样
自然产生，没有独立的“每场覆盖几个赛果”参数。下一轮必须把结构决策和随机
抽样拆开：

- `coverage_depth[j] ∈ {1,2}`：第 j 场只允许单选或双选，暂不允许三赛果全包；
- `protected_leg_count = Σ(coverage_depth[j]-1)`：显式控制一张票组中需要保护
  的场次数；模型同时选择主赛果与保护赛果；
- `K/exposure` 不固定为 512。512 仅保留为 matched control；模型可以在边际
  价值、回撤与集中度约束下提高或降低注数和资金暴露，不设人为的单期硬上限；
- WR/WOR 只负责在上述结构支持上生成具体彩票，不能再代替覆盖深度决策。

因此下一轮先用空间填充/分层筛选覆盖 N、单/双选保护、WR/WOR、K 与 exposure
的交互，再对有效区域做连续权重 MoE；不做不可执行的全笛卡尔网格。

### 2023–2024 逐期近失票归因

冻结下一轮模型后，2023 validation 与 2024 terminal 都必须提供逐期诊断。
重点抽取“只差 1 场”和“只差 2 场”的票，并把漏选原因互斥或分层归因为：

- 场次 selector 没有纳入该场；
- 赛果方向模型选择错误或低估冷门；
- 单/双选保护没有覆盖正确分支；
- 正确分支在抽样支持内但有限 K 没有抽到；
- 正确票已进入候选但资金分配不足；
- SP/价值门槛排除了正确分支。

输出包括每期 gap-count 分布、原因占比、冷门概率/SP/分歧分层，以及“若增加
一层选择性保护或边际 K，收益是否改善”的反事实。只有能转化为新参数、特征
或约束的稳定模式才进入算法；禁止依据 2024 个案回调已冻结参数。

### 下一轮时间切分

#312 不能在已经观察 2023 后临时追加 2024，否则会破坏本轮冻结边界。下一轮
MoE 应把 2019–2021 用于训练、2022 用于 gate 与 CORE/TAIL 约束调参、已暴露
的 2023 用于 validation 和归因诊断；所有 experts、权重规则、目标函数与回退
门槛提交冻结后，2024 才做一次性 terminal held-out。主要报告并列展示 2023
validation 与 2024 held-out，但任何 promotion 只以 2024 为准。2025+ 继续保留。

在开启 2024 前，必须先构建与历史面板相同字段的 2024 共同支持 receipt；不能
直接套用止于 2023 的 #299 exact-B0 receipt。#210 可作为这一 held-out 接口，
但需要按新的 CORE/TAIL MoE 契约重构后再激活。

## 交付索引

- Notebook: `notebooks/research/issue-312/bj312_explicit_joint_action_cube.ipynb`
- 冻结收据与结果：`results/issue-312/`
- 核心代码：`src/issue312/`
- 可重建入口：`scripts/build_bj312_action_registry.py` 至
  `scripts/run_bj312_experiment.py`
