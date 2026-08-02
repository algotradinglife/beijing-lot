---
title: "#137 概率加权 N7 抽样：Gate B v3r1 共同支持集结算"
date: 2026-08-02
status: complete
decision: NO_PROMOTION
interpretation_tier: NOT_VALIDATED_AFTER_CONCENTRATION_OR_MULTIPLE_TESTING
---

# #137：选场 × 概率加权 N7 抽样 v3r1 共同支持集终局结算

阶段：Gate B v3r1 已完成终局历史结算，并由 #144 作严格、独立的只读 EV 复验。候选的包
完整性通过，但统计上未能验证为正：它不再是待推广候选，终局决定为 `NO_PROMOTION`，解释
层级为 `NOT_VALIDATED_AFTER_CONCENTRATION_OR_MULTIPLE_TESTING`。本报告不构成购买、生产或
投注授权。

## 冻结、结算与税务边界

- 唯一赛前输入仍是 Gate-A v2：`results/bj137_gate_a_preoutcome_v2`，manifest
  `0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df`；没有读取
  Gate-A v3 或重新选择任何 match、identity、M 或 seed。
- 唯一赛后真值仍是 canonical final-SP join，payload
  `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`。
- 直接父包为已经审计的逐票税务包
  `results/bj137_gate_b_outcome_settlement_v2r1`，manifest
  `f4848d61b7eab31b97077751fdb2f49ad242e483033c6d29524ba4f7b43445fb`；其 14,450
  个策略的逐票税务对账均为零差额。
- 本次不可变派生包为
  `results/bj137_gate_b_outcome_settlement_v3_common_support`，manifest
  `fe55b7bdd8508a2b19bba2a57ecde9c7238feab1000a15a78ac24689cf89fb31`，content identity
  `be2012567f0aa1690be8e50711afe00233f8686fc5baa9423c400637e9a35f5f`。
- 本报告修订包为只读派生
  `results/bj137_gate_b_outcome_settlement_v3r1_reporting_correction`，manifest
  `7453eb917bc4b5422ac13f2d46af540c7c4ebb87a163d8f247b67a9615cd27c0`，content identity
  `17c8ee093c399e0693c139203a5fa2fc34a4d7f743cf50db2cd1f7ca9b23a19d`。它只汇总已冻结的
  v3 矩阵，不读取 Gate-A、重抽票、改变台账、共同支持集或候选规则。

每张命中序列的毛回报是 `¥2 × 0.65 × Π(final winning SP)`。20% 税只按**这一张**
中奖彩票是否达到 `¥10,000` 判断；绝不把多张票、多个 identity、M 重复、期次或策略臂
汇总后再计税。`tax_adjusted_roi` 仍完整报告，但策略排序、比较和候选判定以已含 0.65
因子、尚未扣逐票税的 `no_tax_roi` 为主。

## 为什么需要 v3

父账本把任一 selected identity 的赛果缺失记为整个 issue-policy 不可结算。因此 K 收缩、
FULL、抽样器和硬删码臂可能各自在不同 issue 集合结算。v2 的聚合 ROI 直接相减会混入
可用性和期次构成。v3 对每个候选—基准对只使用两者都 `SETTLED` 的完整期次交集，并在
每一行同时保存候选、基准和匹配支持数。

例如 NO_GATE/K1 FULL 对 NO_GATE/K_ALL FULL：候选独自可结算 271 期、基准 187 期，
交集为 187 期；共同支持集上的 selector 增量为 **税前 +1.02pp、税后 +0.10pp**，而不是
旧的未匹配聚合 +3.84pp/+2.05pp。这个例子不能被解释为稳定 selector edge。

## 完整参数面与对照

`common_support_effects.csv.gz` 有 685,080 行，保留 ALL、YEAR、FOLD、LOYO 四种视图：

| 比较 | 行数 | 目的 |
| --- | ---: | --- |
| selector：FULL K 对同 gate K_ALL FULL | 880 | 单独归因 K 收缩 |
| sampler：抽样器对 exact-K FULL | 316,800 | 单独归因 outcome sampling |
| interaction：抽样器对 K_ALL FULL | 316,800 | 联合效应，不替代 sampler 对照 |
| M=1458 对 p_min hard delete | 25,300 | 补齐 sampler-minus-p 控制 |
| M=1458 对 q_min hard delete | 25,300 | 补齐 sampler-minus-q 控制 |

每行都给出 gate、K、M、概率向量、WR/WOR/去重机制、双方绝对 ROI、共同支持数，以及先
`no_tax_roi_delta`、后 `tax_adjusted_roi_delta`。`stability_diagnostics.csv` 再对所有
YEAR/FOLD 单元给出正增量占比、最差/最佳/平均增量和标准差；这些是高方差 N7 的离散度
诊断，不作为“每年都必须为正”的否决规则。

另外，M=1458 的 q 对 p 硬删码对照被保留。例如 ESP300_GM305/K_ALL 的共同支持集上，
q 的税后 ROI 约 -11.87%，而 p 约 -16.37%；这是有限样本下的相对效率信号，不是跨年
稳定 edge，也不能替代 #132 的删码结论。

## 主结论：描述性集中信号，但未通过独立统计验证

新的主规则为：随机抽样臂须在三个冻结 seed 的 ALL 共同支持集 `no_tax_roi_delta` 都为正，
且每个 LOYO 年份省略、每个 seed 都为正。YEAR/FOLD 只作诊断。若三 seed 的**绝对**
`no_tax_roi` 也为正，则为正候选，触发严格独立 EV；逐票税后表现不得推翻税前结论。

结果：464 个随机臂通过 ALL 三 seed 的税前增量，50 个通过 LOYO；但只有一个同时满足
三 seed 绝对税前 ROI 为正：

`NO_GATE / K4 / Q_INFORMED_WOR_DISTINCT / M=64`

| seed | 匹配期次 | 税前 ROI | 对 exact-K FULL 税前增量 | 税后 ROI | 对 FULL 税后增量 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 137001 | 254 | +16.38% | +32.15pp | +5.06% | +23.93pp |
| 137002 | 254 | +11.77% | +27.54pp | +5.95% | +24.83pp |
| 137003 | 254 | +2.67% | +18.44pp | -3.02% | +15.85pp |

该候选不是稳健推广结论：其最大单一期次毛回报份额分别为 24.23%、10.82%、12.16%；
去掉候选最大毛回报期次后，137001 与 137003 的绝对税前 ROI 为 -11.47% 与 -9.46%，
137002 为接近盈亏平衡的 **+0.08%**，而不是负值。尽管配对的 leave-one-issue-
out 税前增量仍全为正（最差约 +5.24pp、+16.67pp、+7.53pp），#144 用独立预登记 seed
执行 20,000 次配对 issue bootstrap 后，三个 matched-lift 95% 区间均跨越零：
`[-23.011,+106.721]pp`、`[-13.313,+74.394]pp`、`[-22.447,+65.426]pp`。

#144 同时独立复核了完整逐票台账、税务、Gate-A/outcome 绑定及重放，完整性均通过；但该候选
来自 5,300 个冻结 gate × K × sampler/vector × M 选择组。即使不声称不具尾部精度的
bootstrap-max p 值，普通 bootstrap 下界已全部为负，保守的家族错误率控制不可能把它转为
已验证的正 edge。因此终局结论是 `NO_PROMOTION` /
`NOT_VALIDATED_AFTER_CONCENTRATION_OR_MULTIPLE_TESTING`：保留税前三 seed 绝对 ROI、21 个
LOYO 正增量和 M 曲线作为**描述性研究证据**，但不把它解释为可推广、可购买或可生产部署的
正策略。税后结果仍是次级执行/税务敏感性，不决定此科学结论。

### 同族 M 曲线与 FULL 归因

下表是同一 `NO_GATE/K4/Q_INFORMED_WOR_DISTINCT`、同一 exact-K FULL 基准的税前曲线。
数值为“候选绝对 ROI / sampler-minus-FULL 增量”，三个 seed 依次为 137001/2/3；并非选取
局部最大值。只有 M64 在三个 seed 同时有正绝对 ROI 和正 LOYO 增量。

| M | seed 137001 | seed 137002 | seed 137003 | 最差 LOYO 增量 |
| ---: | --- | --- | --- | ---: |
| 32 | -21.24% / -5.47pp | +35.61% / +51.38pp | -24.15% / -8.38pp | -26.42pp |
| 64 | +16.38% / +32.15pp | +11.77% / +27.54pp | +2.67% / +18.44pp | +8.08pp |
| 128 | -4.12% / +11.65pp | +4.47% / +20.24pp | +2.23% / +18.00pp | +5.40pp |
| 256 | -1.51% / +14.26pp | -8.53% / +7.24pp | -30.25% / -14.48pp | -22.60pp |

`NO_GATE/K1/FULL` 对 `K_ALL/FULL` 的共同支持 selector 归因为 271/187/187 个期次、
税前 +1.02pp、税后 +0.10pp；全部 selector 中虽有 4 个 ALL 税前正增量，但没有一个
LOYO 稳定。因此这里的 M64 信号是 sampler 相对同一 K4 FULL 的归因，不能偷换成
selection edge。

### 次级 ESP300/GM*/K8/Q/M128 信号

三个 ESP300/GM 门在冻结数据上拥有同一组 191 个匹配期次/seed。它们是较低集中度的
近盈亏平衡敏感性，不取代主候选；v3 的 `candidate_fragility.csv` 按合同只为绝对正候选
生成，所以该次级臂没有额外 concentration 行。

| gate | 税前 ROI（137001/2/3） | 对 exact-K FULL 税前增量（137001/2/3） | 最差 LOYO |
| --- | --- | --- | ---: |
| ESP300_GM290 | +4.46% / -2.23% / +4.46% | +20.58pp / +13.89pp / +20.58pp | +5.90pp |
| ESP300_GM300 | +4.46% / -2.23% / +4.46% | +20.58pp / +13.89pp / +20.58pp | +5.90pp |
| ESP300_GM305 | +4.46% / -2.23% / +4.46% | +20.58pp / +13.89pp / +20.58pp | +5.90pp |

### 概率向量与 WR/WOR 紧凑面

v3r1 的 `mechanism_summary.csv` 以 gate×K×sampler×M 计数：model WOR 有 98 个 ALL
正增量组、19 个 LOYO 稳定、0 个绝对 edge；model WR 有 57/1/0；market WOR 有 53/0/0；
blend A25/A50/A75 WOR 为 43/0/0、51/0/0、51/1/0；q WOR 为 111/29/**1**。deterministic
top-mass 是 102/13/0，p/q global single-code delete 分别为 40/16/0 与 50/13/0。

原始 ALL 单 seed 最大值为 `ESP280_GM305/K1/MODEL_P_CAL_WR/M1/137001` 的 +790.06pp，
但它不通过 all-seed、LOYO 或绝对 edge 规则，故只是极稀疏峰值而非候选。

top-mass 也按无随机 seed 的单独规则评估：102 个 ALL 税前正增量、13 个 LOYO 稳定，
但没有绝对税前 ROI 为正的候选。selector 有 4 个 ALL 正增量、0 个 LOYO 稳定；所以本次
不能把 K 收缩或 selector 本身归因为正 edge。

## 诊断修复与限制

- `largest_event_tax_sensitivity.csv` 现在删除同一最大期次的**毛回报和该期税额**，并同时
  报告税前结果；不再只减 gross 留下全部税。
- `calibration_diagnostics_corrected.csv` 对缺少 canonical outcome 的行同时排除 Brier
  分子和分母，仍报告缺口数与覆盖率。
- `candidate_fragility.csv` 对每个候选 seed 保存最大期次份额、同一期次剔除后的配对
  税前 delta、254 个 leave-one-issue-out 结果，以及 5,000 次固定种子 issue bootstrap。

终局边界：不得以这份历史包修改 Gate-A、选择新的 M/seed，或生成投注包。任何新的假设
必须由新的、赛前定义的研究合同检验，而不能把本次 5,300 组历史选择面中的局部峰值回写成
策略规则。
