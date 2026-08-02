---
title: "#137 概率加权 N7 抽样：Gate B 共同支持集结算"
date: 2026-08-02
status: in_review
decision: POSITIVE_CONCENTRATED_REQUIRES_STRICT_INDEPENDENT_EV
---

# #137：选场 × 概率加权 N7 抽样共同支持集结算

阶段：Gate B v3 派生结算，等待 PI 复审。它识别出一个**集中型正候选**，必须先经严格、
独立的 EV 复验；本报告不构成购买、生产或投注授权。

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

## 主结论：一个需独立复验的集中型候选

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
去掉候选最大毛回报期次后，三个 seed 的绝对税前 ROI 均转负。尽管配对的 leave-one-issue-
out 税前增量仍全为正（最差约 +5.24pp、+16.67pp、+7.53pp），固定种子的期次 bootstrap
95% 区间均跨越零。因此结论是
`POSITIVE_CONCENTRATED_REQUIRES_STRICT_INDEPENDENT_EV`：可提交独立 EV 复验，不能推广或
交易。

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

下一步只能由独立执行者用冻结合同复验这个集中型候选；不得以这份历史包修改 Gate-A、
选择新的 M/seed，或生成投注包。
