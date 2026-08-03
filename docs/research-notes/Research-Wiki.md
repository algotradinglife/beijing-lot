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
7. **放松候选标准会产生候选，但尚未得到跨年可推广优势。** #119 的冻结
   敏感性网格显示 q/p 阈值会强烈改变候选密度；少量正 ROI 全部或几乎全部集中在
   2019 的少数 observation。宽松单选与全覆盖总体为负，严格 #106 控制仍为
   零候选。Gate B v1r3 已按真实 kickoff 时序修正回撤/连败，并将 Gate-A
   `NO_BET` 与 canonical outcome 不可用分别报告；这两项报告修正不改变任何
   stake、gross、tax、net 或 ROI。结果正在等待窄范围独立复验，不能用于购买或生产。详见
   [[Issue-119-Candidate-Sensitivity|Issue #119 候选标准敏感性]]。

## 近期 N7 策略结论（2026-08-02）

这一节记录最近几轮研究的可复用结论，供后续候选生成、选场和组合层研究引用。
统一经济口径是税前 `no_tax_roi`：已包含北单 `0.65` 派彩系数，但不扣逐票税；税后
结果只作次级参考。

### 选场、删码与软覆盖

- **#127：绝对改善主要来自选场，不是硬删码。** 在同一 `p_min<=0.20` 口径下，
  更严格的 `E_SP/GM_E_SP` 使 FULL 基线改善 **+6.79pp**；PRUNE−FULL 的增量
  却没有稳定改善，最严格档反而为 **-1.95pp**。18.66% 的删码开出率与 #101 的
  18.46% 基本一致，更像概率校准正常，而不是删码策略获得了新 edge。
- **#131：软覆盖没有稳定甜区。** 从 hard prune 到 FULL 的 sleeve（0%、5%、10%、
  20%、33%、50%、100%）在 189 个 ALL-scope 行上税前和税后均未出现可推广的正结果；
  不同 seed 的局部最佳比例不一致，因此不能把某个 sleeve 深度固化为策略规则。
- **#132：完整期次的 `q=p×predicted_SP` 没有击败 `p_min`。** 以完整 `(issue, fold)`
  为主单位，p-min、q-min 和 FULL 的冻结比较中，所有非控制 ALL 行均为负；最佳
  `p_min` 仍未达到盈亏平衡，q 排序没有提供稳定增量。早期按 segment 的结果不再作为
  主结论。

这三项共同确立一个强制报告规范：任何“选场 + 剪枝/抽样”实验都必须同时报告
每个选场门槛的 matched FULL 基线，以及同门槛下的 `PRUNE−FULL` 增量、stake retention
和 gross-return retention。不能用 PRUNE 绝对 ROI 代替剪枝增量，也不能把降低税负
解释成税前 edge。

### 概率抽样与独立验证

- **#137：找到描述性最强的候选，但没有得到验证。** `NO_GATE/K4/Q-WOR/M64`
  的三个 seed 税前 ROI 为 `+16.38%/+11.77%/+2.67%`，相对 exact-K FULL 的增量为
  `+32.15pp/+27.54pp/+18.44pp`；21 个 seed×LOYO 配对增量均为正。这个结果来自
  `q=p×predicted_SP` 的无放回抽样，不等于单纯选场或市场概率映射已经产生 edge。
- **#144：完整性通过，统计确认失败。** 独立重放、Gate-A/赛果绑定、逐票税务和
  manifest 均通过；但最大一期贡献最高 **24.23%**，去掉最大期次后两个 seed 的绝对
  税前 ROI 为负，三组 issue-bootstrap 95% 区间均跨零。候选来自 5,300 个冻结参数组，
  因此终局为 `NO_PROMOTION`，解释层级为
  `NOT_VALIDATED_AFTER_CONCENTRATION_OR_MULTIPLE_TESTING`。

结论不是“概率抽样无效”，而是：它显示了值得继续研究的资金效率信号，但目前不能
区分真实 edge 与少数大额期次加上大量参数搜索造成的集中性结果。任何正结果都需要
真正 held-out/forward 数据和严格独立 EV；普通负结果则应给出完整参数面和解释，不应
用 `fail-close` 或“无候选”替代分析。

### #146：分散化的当前结构瓶颈

PR #146 对 Issue #133 冻结了完整期次的 allocator frontier。关键发现不是收益，而是
候选几何：#137 的 N7 identity 大量共享 **6 条 companion legs**，所以主 K4 池中
match cap 1–3、Jaccard `.50` 以及联合严格 cap 均无法形成完整的 4 个 N7；q-delete
cap 1/2 分别仅在 **101/348** 和 **142/348** 个期次可行，cap 4 则基本回到集中结构。

这说明当前瓶颈主要在上游 N7 候选生成，而不是 allocator 本身。#133 Gate B 因此只应
把 q-delete cap 1/2 作为有辨识度的新分散臂，报告集中度、重叠、参与率、资金利用率和
税前 `PRUNE/ALLOCATOR−FULL` 增量；match/Jaccard 严格 cap 的结构性 `NO_BET` 作为诊断，
不能伪装成策略比较。FULL 与 M64/M128 的原始 stake 不同，FULL 只能作为资本归一化 ROI
基线，原始资金量必须单独报告。

### 后续推导的控制规则

1. 主分析单位是完整期次，segment 只能作为诊断标签。
2. 先分离 selector lift、sampler/allocator lift 和 interaction，再讨论总 ROI。
3. 先看税前结果；税后只用于说明税线和资金暴露的影响。
4. 每个候选都要报告集中度、最大期次敏感性、LOYO 和按期 bootstrap。
5. “描述性阳性”不等于推广；必须经过样本外验证。负结果也必须留下参数遍历和可复用的结构结论。

### #133 Gate B：WR 基线下的 12 个主比较（2026-08-02）

本节记录已合并 PR #147 的 v2 结算。主比较是同一完整期次、同一候选身份、同一
seed 下，`Q_DELETE_EXPOSURE_CAP_1/2` 相对于 `CONCENTRATED_TOP_SCORE` 的
`Q_INFORMED_WR_DUPLICATE_STAKE` 基线。WR 中每次抽样都是独立的 ¥2 票，重复代码
不去重；税前 ROI 是主口径，税后 ROI 为辅助口径。

| M | cap | seed | cap ROI | WR ROI | 税前增量 | cap 税后 ROI | WR 税后 ROI | 税后增量 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 | 1 | 133001 | -24.51% | -51.16% | **+26.65pp** | -24.51% | -51.16% | **+26.65pp** |
| 64 | 2 | 133001 | -42.73% | -47.42% | **+4.69pp** | -42.73% | -47.42% | **+4.69pp** |
| 64 | 1 | 133002 | -55.22% | -37.69% | -17.53pp | -55.22% | -37.69% | -17.53pp |
| 64 | 2 | 133002 | -57.22% | -41.67% | -15.55pp | -57.22% | -41.67% | -15.55pp |
| 64 | 1 | 133003 | -61.28% | -50.19% | -11.09pp | -61.28% | -50.19% | -11.09pp |
| 64 | 2 | 133003 | -43.08% | -34.13% | -8.95pp | -43.08% | -34.13% | -8.95pp |
| 128 | 1 | 133001 | -45.12% | -55.56% | **+10.44pp** | -45.12% | -55.56% | **+10.44pp** |
| 128 | 2 | 133001 | -22.64% | -15.28% | -7.36pp | -26.49% | -19.13% | -7.36pp |
| 128 | 1 | 133002 | -47.93% | -40.08% | -7.85pp | -47.93% | -40.08% | -7.85pp |
| 128 | 2 | 133002 | -52.89% | -43.84% | -9.05pp | -52.89% | -43.84% | -9.05pp |
| 128 | 1 | 133003 | -57.50% | -40.80% | -16.70pp | -57.50% | -40.80% | -16.70pp |
| 128 | 2 | 133003 | -29.61% | -26.13% | -3.48pp | -32.71% | -29.23% | -3.48pp |

只有 12 项中的 3 项税前增量为正（M64/cap1、M64/cap2、M128/cap1，均为
seed 133001）；其余 9 项为负。需要注意，PR 文档中的“仅 2/12 为正”与冻结
`matched_effects.csv.gz` 的逐行数据不一致；Wiki 以可审计 CSV 为准，并将该计数
差异作为报告瑕疵记录。修正后的统计卡按预先锁定的 12 比较、24 个
ROI 指标、跨 seed、LOYO、issue bootstrap 和 Bonferroni 规则判断，正向结果没有
稳定证据，因此终局为 **NO_PROMOTION**。

这里的结论不是“重叠一定有害”，而是：在当前候选 identities 共享六条 companion
legs、可用场次池有限的条件下，主动去重没有产生稳定税前增量。集中度应作为风险
诊断，而不是硬性优化目标；若要继续研究 allocator，应先生成真正多样化的 N7 leg
sets，再重复 WR/WOR/overlap-cap 对照。

### #148 Gate B：密集 M 曲线（2026-08-02）

![#148 dense M-grid curve](assets/bj148_dense_m_grid_curve.png)

#148 在固定 common-support identities、三组 seed 和完整 issue 单位上，遍历 58 个
M 点：`16..512` 步长 16，`576..1024` 和 `1088..2112` 步长 64，另加 FULL
`M=2187`。没有单期下注上限；每期所有可用 identities 都参与，资金随候选数量自然
变化。WR 是主基线，WOR 仅作敏感性，FULL 是精确 `3^7` 枚举控制。

Gate B 只在 canonical outcome 完整的 187 个期次上结算（另有 156 个期次因 outcome
不完整而保留为 zero-stake unavailable），因此不能把不可结算期次误当作零收益期次。
FULL 执行资金为 ¥20,964,582，税前 ROI **-18.54%**，税后 ROI **-20.38%**。

| M | 相对 FULL 资金利用率 | 三 seed 平均税前 ROI | 平均重复票比例 | 平均 unique coverage |
|---:|---:|---:|---:|---:|
| 16 | 0.73% | -16.08% | 0.34% | 99.66% |
| 96 | 4.39% | -10.26% | 2.16% | 97.84% |
| 512 | 23.41% | -15.79% | 10.97% | 89.03% |
| 1024 | 46.82% | -16.46% | 20.36% | 79.64% |
| 2112 | 96.57% | -17.11% | 36.15% | 63.85% |

没有任何 M 在三个 WR seed 上同时取得正税前 ROI。跨 seed 平均最好的点是 `M=32`
（-10.04%），但三个 seed 分别为 -18.24%、-28.45% 和 +16.58%，属于 seed-local
maximum；最好的 worst-seed 点是 `M=96`，三个 seed 仍为 -13.98%、-13.86% 和
-2.96%。因此终局为 **DESCRIPTIVE_SURFACE_ONLY / NO_STABLE_SWEET_SPOT**，而
不是把某个 M 点晋级为策略。

解释上，M 增大确实使资金暴露快速上升、重复票增加、unique coverage 下降，但没有
带来稳定的税前回报改善。当前阶段应把 M 视为资金—覆盖率—风险的选择参数，而不是
独立 alpha 来源；后续优先改善候选场次和决策链，再重新评估 M 曲线。

### 从 #137 正收益候选到 #151 固定候选复现（2026-08-02）

此前 #137 曾出现一个值得保留的描述性正收益候选：
`NO_GATE/K4/Q_INFORMED_WOR_DISTINCT/M64`。三个 seed 的税前 ROI 约为
`+16.38%`、`+11.77%` 和 `+2.67%`，相对匹配 FULL 也有较大提升。但这不是已确认
的正 EV，原因包括：候选来自约 5,300 个参数组的筛选、收益集中于少数 issue、issue
bootstrap 区间跨过 0，以及独立验证未通过集中度/多重比较稳定性门槛。

后续研究并没有把该结果简单丢弃，而是分层处理：

```text
#137：发现描述性候选
   ↓ 固定 identities / gate / selection definition
#133：测试 overlap / allocator，发现候选池共享六条 companion legs
   ↓ 固定 common-support，遍历 M=16..2187
#148：没有稳定 M 甜区；M 主要改变资金暴露、重复率和 coverage
   ↓ 不重新挑参、不 outcome re-select
#151：复现 #137 候选，并与 #148 broader-pool 曲线并列
```

因此当前 Wiki 的证据分层是：

- **已知**：#137 有描述性正结果，但没有严格样本外稳定证据；#133 的当前候选池
  不适合通过强制去重创造稳定增量；#148 没有跨 seed 稳定的 M 甜区。
- **仍待验证**：#137 的候选定义本身是否具有可复现结构，或者正收益只是参数筛选、
  seed 波动和 issue concentration 的组合。
- **#151 的约束**：只继承 #137 冻结的 candidate definition，不重新遍历 outcome
  选择；比较 WR、WOR、FULL 和密集 M 曲线，并报告 candidate−FULL 及其相对
  #148 broader-pool 的差异。

这条路线保留了正收益假设的研究价值，同时避免把历史筛选峰值误当作已授权 edge。
若 #151 出现跨 seed、LOYO 和 bootstrap 稳定的阳性结果，再进入严格独立 EV；若阳性
消失，则要明确归因于 M、采样机制、候选池扩展或 issue concentration，而不是简单
以 `NO_PROMOTION` 结束。

### #151/#154：固定候选复现与独立验证结论（2026-08-02）

![#151 WR vs WOR dense M curve](assets/bj151_wr_wor_dense_m_curve.png)

#151 固定 #137 `NO_GATE/K4` identities、Q vectors、seeds 和历史 sampler namespace，
没有重新挑参。原始 `Q_INFORMED_WOR_DISTINCT/M64` 税前 ROI 被精确复现：

| seed | WOR/M64 税前 ROI | 税后 ROI |
|---:|---:|---:|
| 137001 | +16.38% | +5.06% |
| 137002 | +11.77% | +5.95% |
| 137003 | +2.67% | -3.02% |
| 三 seed 平均 | **+10.27%** | — |

邻近 WOR 点的三 seed 平均也为正：M48 `+5.30%`、M80 `+4.29%`、M128
`+0.86%`。但是相同固定候选的 WR/M64 平均税前 ROI 为 **-24.86%**，且整个 WR
M 网格均为负；matched K4 FULL 为 **-15.77%**。因此历史阳性是明显的
**WOR-distinct sampler-specific signal**，不是候选池在任意抽样机制下的普遍正 EV。

#154 从 fresh detached checkout 独立重建 #137 sampler，并对全部 171 个非 FULL WOR
surface rows 得到零差异，确认历史结果是真实可重放的。但严格稳健性仍不成立：

- 三个 seed 的 issue-bootstrap 95% 区间均跨 0；
- 去掉最大贡献 issue 后税前 ROI 为 `-11.47%`、`+0.08%`、`-9.46%`；
- top issue gross share 为 `24.23%`、`10.82%`、`12.16%`；
- 58 个 M × 3 seeds 仍暴露于同一历史样本和多重比较。

最终分级为 **PASS_REPRODUCTION_ONLY**：#137 正收益候选及其附近 WOR 正值簇被独立
复现，值得作为 sampler 设计线索保留；但收益依赖少数期次、bootstrap 不稳定，不能
晋级为已验证正 EV，也不产生购买、生产或投注授权。后续若继续，应使用冻结的 WOR
机制进行真正的 held-out / forward validation，而不是继续在同一历史窗口选 M。

### #145：WR/WOR/残差/封顶重复票分配冻结（Gate A，2026-08-03）

#145 不再重开 #137/#151 的候选选择，而是固定 #151 的 `NO_GATE/K4` candidate，另加
`ESP300_GM290/K8` 作为次级敏感性臂。Gate A 只冻结分配规则，不读取结算结果：696 个
issue-arm 行、3,540 个 N7 identity、24,780 个 role 行和 1,006,416 个分配计划行均为
赛前输入。

同一 identity、同一 issue stake 下保留六个权重源（`MODEL_P_CAL`、`MARKET_WF_CAL`、
`BLEND_A25/A50/A75`、`Q_WEIGHT`），并比较 weighted WR duplicate-stake、WOR-distinct、
deterministic residual/systematic、cap `{1,2,4,8}`、top-mass 与 FULL。低 M 面是
`16..256` 步长 16，`512/1024/1458/2187` 仅作收敛控制；沿用 #137 的三枚 seed
`137001/2/3`。每个重复 `¥2` ticket 单独计数和未来单票税，不按 issue 或 policy 汇总。

Gate B 尚未授权；若获授权，先报税前 `no_tax_roi` 和同 stake 的机制差异，再单独报逐票
税，并保留 seed、LOYO、YEAR/FOLD、issue bootstrap、最大期次剔除、coverage 与重复票
浓度。v8 在 v5 绑定基础上逐字复用 #137 `stable_uniform`、WR/WOR token 顺序，并将
`identity_signature` 固定为 `selected_match_ids`；新增直接对照测试，确保相同权重/seed/identity
产生相同票码倍数，并增加真实 BLEND_A50/M2187 原始单位回归，防止总和缩放再次引入
边界票码偏移。v8 机制契约另行显式记录每个 arm 的 expected-unique formula 与
realized-unique rule，并将 `bj145_allocation_engine.py` 与六个 N7 golden-vector
fingerprints 绑定进 manifest，避免在 Gate B 才首次决定 residual/capped 的票码倍数，也避免
把 WR 的重复票、WOR 的无放回 distinct 和 FULL 控制混为同一指标。该冻结不构成
购买、生产或投注授权。详见 [#145 Gate A](../research/bj145_ticket_allocation_gate_a_2026-08-03.md)。

### #145：Gate B v2 完整结算与分配机制解释（2026-08-03）

v1 包原样保留，但其 coverage/miss 分母和 outcome-code marginal 不再作为终局解释。
权威替代包为 `results/bj145_gate_b_outcome_settlement_v2`；它不改 Gate-A v8 的
identity、权重、机制、M、cap、seed 或逐 issue 结算行，只修正结算后的汇总、完整
2,187-code allocation atlas、机制对照、稳定性分析、图表和报告。全矩阵仍为
1,006,416 个 issue/config 行、2,892 个配置、63,624 个 ALL/YEAR/FOLD/LOYO summary、
63,360 个 matched FULL 差、12,960 个全 M-grid 机制 pair、5,760 个 bootstrap 和
2,880 个 Holm 行；税务 reconciliation 2,892/2,892 PASS。

#### 分母修正与 FULL 控制

coverage、wager miss streak 和 chronological drawdown 只使用 `SETTLED + positive-stake`
行；Gate-A no-bet 与 canonical outcome unavailable 单独计数，不再伪装成 miss。主臂
支持集为 254 issues / 1,016 identities，次臂为 191 / 1,528。FULL 在两个支持集上均为
100% coverage；旧口径把主臂 `Q_WEIGHT/WOR_DISTINCT/M16/137002` 记成 13/348，v2
修正为 13/254 = 5.1181%。

| arm | FULL 税前 ROI | FULL 税后 ROI | settled issues | FULL coverage | tax-net max drawdown |
|---|---:|---:|---:|---:|---:|
| `PRIMARY_NO_GATE_K4` | -15.77% | -18.88% | 254 | 100.00% | ¥865,364.85 |
| `SECONDARY_ESP300_GM290_K8` | -16.12% | -18.30% | 191 | 100.00% | ¥1,246,062.84 |

#### 权重、机制与 cap

六个权重源的非 FULL 历史中位税前 ROI 均为负；`Q_WEIGHT` 产生最高 same-window
峰值，但也有明显 seed/期次集中。以下是主臂中位数；次臂的结论方向相同，完整六权重
×机制×cap×M×seed 数字面保存在包内 `mechanism_weight_surface_summary.csv`。

| 主臂权重 | 中位税前 ROI | 描述性最大值 | 正值 cells |
|---|---:|---:|---:|
| `MODEL_P_CAL` | -17.79% | +67.97% | 26/240 |
| `MARKET_WF_CAL` | -14.38% | +55.01% | 24/240 |
| `BLEND_A25` | -17.49% | +55.01% | 17/240 |
| `BLEND_A50` | -20.79% | +67.97% | 12/240 |
| `BLEND_A75` | -18.62% | +67.97% | 16/240 |
| `Q_WEIGHT` | -15.77% | +84.76% | 61/240 |

但 matched 归因并不支持把 Q 峰值解释成普遍权重优势：固定机制、cap、M、seed、stake
后，`Q_WEIGHT` 相对其余五个权重的主臂中位差为 -2.85pp（500 better / 675 worse /
25 tie，共 1,200 cells），次臂为 -5.52pp（376 / 798 / 26）。因此 Q 的最高 cell 是
尾部峰值，而不是跨配置的一般改善。

WOR 在相同 M 下消除 exact duplicate，主/次臂的中位 coverage 为 30.51%/56.02%，
中位税前 ROI 为 -11.68%/-8.51%；WR 保留自然重复 stake，中位 duplicate ratio
4.42%/4.34%，税前 ROI 为 -18.04%/-18.97%。residual、top-mass 和 cap=1 的
中位 unique ratio 为 100%；cap 从 1 增至 8 时重复集中和 miss streak 显著上升，主臂
中位税前 ROI 从 -18.06% 降至 -30.56%，次臂从 -20.16% 降至 -40.40%。没有一个 cap
在六权重、三 seed、YEAR/FOLD/LOYO 上形成稳定优势。降低 stake 或提高 unique coverage
本身都不是 edge；因此同时报告 capital utilization、gross retention、hit tickets、
winning identities、top-issue share、HHI、drawdown 和 miss streak。

matched 机制归因进一步区分了“机制信号”和“可晋级策略”：固定 arm、weight、M、stake
与 seed 后，WOR−WR 的主/次臂中位税前差为 +5.77pp/+9.69pp，分别有 243/360、
285/360 cells 有利于 WOR；WOR 同时把 duplicate-ratio 中位数降低约 4.42pp/4.34pp。
WR−residual 则方向不一致：主臂 -1.16pp（165/360 有利），次臂 +1.55pp
（205/360 有利）。cap2/cap4/cap8 相对 residual 的主臂中位差为
-0.39pp/-2.74pp/-12.24pp，次臂为 -0.35pp/-4.90pp/-19.20pp；coverage 随 cap
放宽下降而重复集中上升，没有稳定的 cap tradeoff 改善。

#### 稳定性与集中度

WR/WOR 的 matched seed ROI range 并不小：主臂中位 22.51pp/22.01pp，次臂
14.76pp/8.89pp；p95 可达 56.60pp–67.23pp。2,880 个税前 issue-bootstrap 比较中
只有 52 个 lower 95% bound 高于零，2,605 个区间跨零。1,983 个 Holm-significant
sign rows 中，1,898 个是 negative-issue majority，只有 85 个是 positive-issue majority；
这个 per-issue candidate−FULL sign test 主要记录 coverage/miss 方向，不衡量少量大额
派彩的幅度，因此不能把 1,983 解释成有利发现。每个配置另有真实
leave-one-issue-out（保留造成 min/max 的 issue ID）和“剔除本配置最大 gross issue 后
相对 matched FULL”的税前敏感性。历史最高的主臂 Q-WOR/M16/137002 从 +84.76%
降到 ex-largest +48.43%，但其它 seed 与 bootstrap 不稳定；这仍不是独立正 EV。

主臂 Q-WOR/M64 的三个 seed 为 +16.38%/+11.77%/+2.67%，这正是 #151/#154 已复现
的历史簇，不是 #145 新发现；三条 bootstrap CI 全部跨零，剔除各自最大 gross issue 后
为 -11.47%/+0.08%/-9.46%。该簇 YEAR/FOLD 仅 12/21 行为正，LOYO 15/21 为正，
仍是 mixed stability。M16/137002 的 +84.76% 更是 seed outlier：另两个 seed 为
-42.54% 与 -29.30%，跨 seed 中位数 -29.30%。

#### 五个终局问题

1. **概率/价值权重是否有 matched 增益？** 没有；Q 对五类匹配权重的中位差在两臂均负。
2. **WOR 是否改善？** 历史 matched 归因支持 distinct-coverage/WOR，但不构成晋级证据。
3. **WR 或 residual 是否更好？** 两臂方向相反，且 WR 增加约 4.4pp 重复暴露。
4. **repeat cap 是否改善 tradeoff？** cap1 接近 distinct identity control；cap2/4/8 均无稳定改善。
5. **是否存在稳定 sweet spot？** 没有；seed、YEAR/FOLD/LOYO、LOIO、ex-largest、
   bootstrap 与 multiplicity 的联合证据均不支持晋级。

完整 outcome-code atlas 对 2,892 个配置各列 2,187 个代码，共 6,324,804 行：目标概率
质量、实际分配 ticket copies/frequency、两者 delta 与真实赛果 identity/hit 分开记录；
每配置目标与 realized frequency 均守恒为 1，delta 和为 0。M=512/1024/1458/2187
也进入 matched pairwise 收敛控制，不再只看 M≤256。

![#145 税前 ROI 随 M/cap 的完整曲线](../../results/bj145_gate_b_outcome_settlement_v2/roi_vs_m_cap.svg)

![#145 相对 matched FULL 的税前比较](../../results/bj145_gate_b_outcome_settlement_v2/matched_pre_tax_comparison.svg)

![#145 issue-bootstrap 不确定性与稳定性](../../results/bj145_gate_b_outcome_settlement_v2/uncertainty_stability.svg)

终局仍为 **DESCRIPTIVE_SURFACE_ONLY_NO_PROMOTION**。高历史 cell 只能作为后续 strict
independent-EV 与真正 held-out/forward validation 的候选，不能产生购买、生产或投注
授权。v2 不可变清单 `SHA256SUMS.json` 的 SHA-256 为
`10d5a5082a175ddc965b01fb257e8e5c7e91a844d7ee823fd6d2ad5aeff84cc9`。完整表格和
解释见 v2 包内 `report.md`；Gate-A 设计仍见
[#145 Gate A](../research/bj145_ticket_allocation_gate_a_2026-08-03.md)。

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
| 严格候选门槛是否错过了可用信号？ | [[Issue-119-Candidate-Sensitivity#结论与下一步]] |
| 哪条北单让球线仍然薄弱？ | [[Issue-83-Continuous-Market-Model#原生让球线异质性]] |
| 如何按期望 SP 选场，并按最低赛果概率决定全包、双选或单选胆？ | [#121 Gate A 阈值冻结](../research/bj121_expected_sp_probability_gate_a_2026-08-02.md) · [Gate B ROI 对比](../research/bj121_expected_sp_probability_gate_b_2026-08-02.md) |
| 同一 N7 中全局只删一个最低概率代码是否有价值？ | [#127 Gate A 匹配单码删除冻结](../research/bj127_global_single_prune_gate_a_2026-08-02.md) · [Gate B matched settlement](../research/bj127_global_single_prune_gate_b_2026-08-02.md) |
| 同一完整期次中按 `p_min` 或 `q=p×predicted_SP` 删除一个代码是否有价值？ | [#132 完整期次 Gate B 结算](../research/bj132_complete_issue_gate_b_2026-08-02.md) |

## 证据等级

本 Wiki 沿用 [[research_status#2.4 Data quality grading|研究状态中的数据质量分级]]：

- **A级**：严格 as-of、赛前冻结、可审计；
- **B级**：有时间戳，但每次使用仍需核验；
- **C级**：历史快照代理，只能探索；
- **D级**：结算或赛后数据，禁止作为赛前特征。

当前 #82、#83 和本次校准曲线属于 **C级历史 timing proxy**。它们适合缩小
研究方向，不适合直接决定真钱投注。#83 的“晋级”只表示进入 #77 的严格前瞻
比较，不表示生产或投注晋级。

## #121：期望 SP × 最小概率阈值

#121 的完整 9 × 13 参数矩阵已经结算。108 个非空策略行全部为负，最佳为
`ESP300_GM305_LOWP30 / MIXED_N7`，税后绝对 ROI `-23.43%`；剔除最佳
payout/issue 后仍为 `-25.02%/-25.17%`，2020–2025 每个有样本年度均为负。

研究上仍有清楚的结构发现：`p_min=0.30` 将全包 N7 的资金量减少约 91%，并把
ROI 从约 `-31%` 改善至约 `-23%~-24%`；提高 E_SP/GM 门槛再改善不到一个
百分点。说明“高 E_SP 选场 + 删除最低概率赛果”有效压缩了成本，但当前两个
静态指标不足以形成正 edge。下一轮应引入基本面、盘口变化、让球线/联赛条件、
SP 不确定性或税线控制，而不是在已结算阈值附近事后微调。

## #127：匹配全局单码删除

#127 是与 #121 不同的、只删除一个全局最低概率代码的 matched-pair 复查。Gate A v2
将低 `p_min` 删除候选与六个高 `E_SP` companion 明确分离：候选自身不受 match-level
`E_SP` floor 限制，七场组合才受 `GM_E_SP` 检验。Gate B 的 9 个冻结 variant 在绝对
无税及实际税后 ROI 上全部为负；最严格 `.20` PRUNE 为 -10.30% 无税、-19.91% 税后，
同场 FULL 为 -8.35% 无税、-21.75% 税后。PRUNE 固定节省三分之一 stake，删码实际发生约
18%–24%；无税 ROI 相对 FULL 在 7/9 行微升、2/9 行下降，但均未达 breakeven。税后改善
主要来自较低 tax exposure 而非正的无税 edge，所以结论为 `NO_PROMOTION`。

## #131：全局删码的软覆盖 sleeve

#131 以 #127 已冻结的七场与全局删码为 selector baseline，不重新选场。它预注册在 729 张
omitted-code slab 中按固定嵌套顺序加回 0%、5%、10%、20%、33%、50%、100% 的票，并以三个
赛果未知 seed 检查样本顺序敏感性。0% 精确复现 hard prune，100% 精确复现 FULL；中间 sleeve
仅改变 portfolio-layer coverage，不能被解释为新的 selector edge。Gate B 已结算：9 个 selector ×
3 个 seed × 7 个 sleeve 的 189 个 ALL-scope 行，无税和实际税后 ROI 全部为负。主 seed 的
严格 selector 以 hard prune -19.91% 税后最佳，10% sleeve -20.11%、FULL -21.75%；其它 seed
的“最佳”比例又变化，故局部改善不构成稳定、可推广的 sleeve 深度。结论为 `NO_PROMOTION`。
详见 [#131 Gate B 完整结算](../research/bj131_soft_cover_n7_gate_b_2026-08-02.md)。

### 选场与剪枝的分离归因

在同一 `p_min<=0.20` 口径下，`E_SP/GM_E_SP` 门槛越严格，FULL 基线从 -15.14%
改善到 -8.35%，即选场贡献 **+6.79pp**；但 matched PRUNE 相对 FULL 的无税增量没有
随之稳定改善，最严格档反而为 **-1.95pp**。因此 #127 中绝对表现的主要改善来自选场，
不能记在删码策略名下。

| 选场门槛 | FULL 无税 ROI | PRUNE 无税 ROI | PRUNE−FULL | 删码开出率 |
|---|---:|---:|---:|---:|
| `ESP280_GM290_LOWP20` | -15.14% | -15.28% | -0.15pp | 18.23% |
| `ESP290_GM300_LOWP20` | -13.24% | -13.14% | +0.10pp | 18.32% |
| `ESP300_GM305_LOWP20` | -8.35% | -10.30% | -1.95pp | 18.66% |

最严格档的 18.66% 删码开出率也不是新的预测进步：它与 #101 同口径
`p_min<=0.20` 的 18.46% 几乎一致，符合概率校准预期。#121 删除多场赛果，coverage
定义不同，不能把它当成这个 18.46% 的直接对照。按 `E_SP` 分层后的删码开出率也没有
显示稳定单调下降；当前样本只能支持“校准正常”，不能支持“选场使删码更准”。

因此 `NO_PROMOTION` 同时表达两件事，而不是笼统否定整个方向：

1. 当前 `E_SP/GM_E_SP` 选场虽显著改善 FULL 基线，但仍未把无税 ROI 推到正值；
2. 在同一批七场、同一资金口径下，当前 `p_min` 硬删除没有提供稳定的边际增量。

这不等于所有剪枝都不可行。对“删一个代码、stake 保留 2/3”的策略，剪枝无税 ROI
优于 FULL 的必要条件是删码后的 gross return retention 高于 `2/3`。#127 最严格档只有
65.249%，未越过这条 matched 基准线。

### 后续研究的强制双指标报告

以后所有“选场 + 剪枝/抽样”研究必须同时报告以下两组指标，且使用同一批 N7、同一
结算窗口和可比资金口径：

1. **选场基线**：每个选场门槛下的 matched FULL 无税/税后 ROI，用来衡量 selector
   相对历史 FULL 的改善；
2. **剪枝增量**：同门槛下 `PRUNE−FULL` 无税/税后 ROI，并同时报告 stake retention、
   gross return retention 与删码开出率，用来判断删码是否独立贡献 edge。

禁止用 PRUNE 的绝对 ROI 代替剪枝增量，也禁止把税负下降产生的表面改善解释为无税
edge。负结果仍需给出完整参数遍历、分层切片和 Wiki 结论，不能以“无候选”或
fail-close 代替策略分析。

## #132：完整期次 p-min 与 q-min 删码

#132 的主结果不采用早期按 segment 切分的敏感性计算，而以 348 个完整 `(issue, fold)`
实例的赛前冻结为唯一主样本。52,534 个 N7 identity 在 FULL、`p_min` 删码与
`q=p×predicted_SP` 删码三个臂中共享同七场；所有 160,734 个冻结行、3,132 个 no-bet、
期次税桶和 LOYO 单位均被保留。最终 27 条非控制 ALL 行均为负。最佳 `p_min` 行
`ESP300_GM305_LOWP20` 无税/税后 ROI 为 -16.90%/-29.68%，仍没有正 edge；最佳
`q_min` 税后为 -33.34%。因此 q 排名没有成为 `p_min` 的改进，也没有获得推广。

`p_min` 删码虽固定把 stake 降至 matched FULL 的 2/3，却未将收益保留到盈亏平衡。
YEAR、FOLD 与 leave-one-year-out 切片均作为诊断保留；此处的 `NO_PROMOTION` 只表示
当前完整期次历史证据不支持推广，并非购买建议。详见
[#132 完整期次 Gate B](../research/bj132_complete_issue_gate_b_2026-08-02.md)。

## #137：选场 × 概率加权 N7 抽样

#137 把完整期次的选场、`K={1,2,4,8,ALL}` identity 参与数和每个 N7 的抽样数
`M` 分开冻结；随后结算 10 个 gate、13 个 M、多个概率向量和三种随机 seed 的全矩阵。
税务以一张实际中奖票为唯一阈值单位：先逐张票判断 `¥2×0.65×Π(SP)≥¥10,000`，再累加
已逐票确定的税额；绝不汇总多张票来跨越税线。v2r1 的逐票账本对 14,450 个策略与
issue-policy 汇总账本全部零差额对账。

v3 将所有 selector、sampler、interaction 和 M=1458 hard-control 比较改为候选与基准
共同 `SETTLED` 完整期次的配对计算：685,080 行参数面同时报告双方支持数、税前主 ROI/
增量和税后敏感性。NO_GATE/K1 对 K_ALL 的例子从旧的未匹配 +3.84pp/+2.05pp 降为共同
187 期上的税前 +1.02pp、税后 +0.10pp，不能再解释为 selector 改善。

主尺度为 `no_tax_roi`（已含北单 0.65 因子，不扣逐票税）；随机策略需要三 seed 的 ALL
和全部 LOYO 配对增量为正，YEAR/FOLD 只保留为离散度诊断。唯一绝对税前正候选是
`NO_GATE/K4/Q_INFORMED_WOR_DISTINCT/M64`：三个 seed 税前 ROI 为 +16.38%/+11.77%/
+2.67%，相对 exact-K FULL 增量为 +32.15pp/+27.54pp/+18.44pp。但其最大单一期次份额
最高 24.23%，去掉最大期次后绝对 ROI 为 -11.47%/+0.08%/-9.46%（两负、一条近盈亏平衡
正值）。#144 已完成独立只读 EV：包哈希、Gate-A/赛果绑定、逐票税务和重放均通过，但三组
seed 的 20,000 次配对 issue-bootstrap matched-lift 95% 区间都跨零，且该候选来自 5,300 个
冻结 gate×K×sampler/vector×M 选择组。保守的家族错误率控制不能把普通区间已跨零的候选
转为已验证正 edge；终局决定为 `NO_PROMOTION`，解释层级
`NOT_VALIDATED_AFTER_CONCENTRATION_OR_MULTIPLE_TESTING`。这区分了**完整性通过**与
**统计未验证**，并不授权推广、购买或生产部署。

v3r1 报告派生包补齐完整解释：同族 Q-WOR/K4 曲线在 M32/64/128/256 中仅 M64 同时通过
三 seed 绝对 ROI 和 LOYO；ESP300/GM*/K8/Q/M128 是次级近盈亏平衡信号（ROI
+4.46%/-2.23%/+4.46%，增量 +20.58pp/+13.89pp/+20.58pp，最差 LOYO +5.90pp），不能替代
主候选。机制面中 q-WOR 为 111 个 ALL 正增量、29 个 LOYO 稳定、1 个绝对 edge；model
WOR 为 98/19/0，model WR 为 57/1/0，market WOR 为 53/0/0；raw M1 峰值不通过 controlling
rule。上述数值保留为描述性历史证据，不能据此回写选择规则或创建投注包。详见
[#137 Gate B v3r1 共同支持集终局结算](../research/bj137_probability_weighted_sampling_gate_b_2026-08-02.md)。

## #159：selected-baseline WOR 跨 N reporting recovery（2026-08-03）

#159 的 Gate-B v2 结算账本保持不可变；本节只记录从已认证账本派生的 v2r1
reporting recovery。v2r1 不重新打开 canonical outcomes，不改变 identity、issue、
winning-ticket、stake、payout、tax、net 或 ROI 行。

- source v2 manifest：`ad724693f7fbee8a120030cb4ace852a4cf69011bf98b39b41ae427bcfbd0917`
- source v2 content identity：`42f8960c9754efb3033cb6da54f38b759da3cb64d7272f195845aeabb51b1b08`
- v2r1 manifest：`546d2a0aa026ea8f8bdaccad0cb9b7079d3e690e8db83c09675d62f0eb6077ef`
- v2r1 content identity：`a33c802d98b00172a2cd84d32b7085a4900508f3b9c420afb30ecea6168b92ea`

完整 81 个 N×M×seed 主表（税前主指标、税后次指标、实际 stake/ticket、coverage、
YEAR/FOLD/LOYO、bootstrap、matched/common-support N7、overlap、最大 issue/year 排除、
双 drawdown 和双 miss streak）在不可变包的 `report.md`、`surface_summary.csv`、
`issue_bootstrap.csv` 与 `matched_n7_deltas.csv` 中。图表包括 `roi_surface_pre_tax.svg`、
`matched_n7_pre_tax_delta.svg`、`stability_exclusions_M64.svg` 和 `uncertainty_M64.svg`。可读结论和 M64 摘要见
[#159 v2r1 reporting recovery](../research/bj159_selected_wor_cross_n_gate_b_v2r1_2026-08-03.md)。

M64 seed-mean 的关键读回如下：N=9 原始税前 ROI `+71.97%`，去掉每个 seed 的最大
signed-issue 贡献后为 `-76.05%`，去掉最大 signed-year 贡献后为 `-93.12%`；其余 N
的原始曲线均为负。81 个 ALL 行中原始正值 8 行、最大 issue 排除后仅 1 行、最大 year
排除后 0 行。因此 N=9 是极端集中度信号，不是稳定的 N 甜点，也不构成 strict EV、
样本外验证、购买、生产或推广授权。

本次修正把最大贡献定义为**正 stake 行中 signed pre-tax net 的最大值**，排除时分别
扣除实际 stake、pre-tax net 和 tax-adjusted net；税仍按单张中奖 ¥2 ticket 独立判断，
绝不跨票、跨 issue 或跨 policy 汇总计税。执行 miss streak 明确跳过 no-bet 和 zero-stake
unavailable rows；drawdown 同时提供税前主值和税后次值。

## 相关笔记

- [[beidan_vs_euro_divergence|北单与欧赔偏差研究]]
- [[track_b_beat_the_close|Track B：超越市场基线]]
- [[single_match_probability_calibration|单场概率校准设计]]
- [[Issue-119-Candidate-Sensitivity|Issue #119 候选标准敏感性]]
- [[roadmap|研究路线图]]
- [Issue #82](https://github.com/algotradinglife/beijing-lot/issues/82)
- [Issue #83](https://github.com/algotradinglife/beijing-lot/issues/83)
- [Issue #77](https://github.com/algotradinglife/beijing-lot/issues/77)
- [Issue #101：按期冷门赛果剪枝](https://github.com/algotradinglife/beijing-lot/issues/101)
- [Issue #121：期望 SP × 最小赛果概率阈值](https://github.com/algotradinglife/beijing-lot/issues/121)
- [Issue #127：匹配全局单码删除](https://github.com/algotradinglife/beijing-lot/issues/127)
- [Issue #132：p-min vs q-min 全局删码](https://github.com/algotradinglife/beijing-lot/issues/132)
