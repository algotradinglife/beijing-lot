---
title: "#137 概率加权 N7 抽样：Gate B 完整结算"
date: 2026-08-02
status: complete
decision: NO_PROMOTION
---

# #137：选场 × 概率加权 N7 抽样完整结算

阶段：Gate B；历史纸面结算已完成，结论为 `NO_PROMOTION`。这不是购买、生产或
投注授权。

## 冻结与结算边界

- 唯一赛前输入：Gate-A v2
  `results/bj137_gate_a_preoutcome_v2`，manifest
  `0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df`；
- 唯一赛后真值：canonical final-SP join，payload
  `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`；
- 早期 Gate-B v2 包保留不改；可复审的税务修订包为
  `results/bj137_gate_b_outcome_settlement_v2r1`，manifest
  `f4848d61b7eab31b97077751fdb2f49ad242e483033c6d29524ba4f7b43445fb`；
- 348 个完整 `(issue, fold)` 实例，10 个 E_SP/GM_E_SP gate、
  `K={1,2,4,8,ALL}`、13 个 `M`、三种随机 seed，以及 FULL、top-mass、
  model/market/blend/q 抽样和两个 hard-delete control；
- 共 5,028,600 条 issue-policy 台账、317,900 条 ALL/YEAR/FOLD/LOYO 汇总。

每张命中序列的毛回报为 `¥2 × 0.65 × Π(final winning SP)`。税务按**单张
中奖彩票**处理：先对这一张票的毛回报判断 `≥¥10,000`，仅该张票才收 20%；不把多张
票、多个 identity、多个 `M` 重复、同一 issue-policy 或任何策略臂的收益相加以跨越门槛。
WR 重复抽到的序列仍是各自 stake、各自判断税线的票。

`ticket_tax_ledger.csv.gz` 逐行保存命中 portfolio/draw 的单张毛回报、独立票数、单张
税额及其乘数；`ticket_tax_reconciliation.csv` 对 14,450 个冻结策略逐一核对该逐票账本
与 issue-policy 账本。全部差额为零，合计税额同为 `¥324,774,233.06`。因此 v2r1 没有
更改任何结算数值：四个原始汇总/增量矩阵的解压内容哈希与 v2 完全一致；它只移除了会让
人误解为税务分桶的字段，并把单票税务证据持久化。

## 主结果

完整抽样矩阵包含大量局部正数：2,929 条 ALL-scope 行有正的税后绝对 ROI，典型地来自
`M=1` 的极低命中次数和很小 stake。这些不是策略晋级证据。

| 检验 | 结果 |
| --- | ---: |
| 三个 seed 的 ALL-scope matched sampler lift（无税和税后均正） | 461 个组合 |
| 同时在所有 YEAR/FOLD/LOYO 切片持续为正 | **0 个组合** |
| ALL-scope 为正的 FULL selector lift | 4 个（均为 NO_GATE 的 K=1/2/4/8） |
| 同时在所有 YEAR/FOLD/LOYO 切片持续为正的 selector | **0 个组合** |

因此，冻结的推广规则没有任何通过者：需要对同一 matched delta 在三个 seed、所有
YEAR/FOLD/LOYO 视图中都保持无税与实际税后正值。单 seed、稀疏 M、原始 ROI 为正、
或仅税后表观改善均不能晋级，也不触发严格独立 EV。

作为尺度参照，`NO_GATE/K_ALL/FULL` 的无税/税后 ROI 是
`-18.54%/-20.38%`；限制为 `NO_GATE/K1/FULL` 后改善为
`-14.71%/-18.33%`，但仍为负，且选择增量没有跨年持续性。一个看似最好的稀疏例子
`NO_GATE/K4/Q_INFORMED_WOR/M=1/seed=137001` 的税后 ROI 为 `+270.42%`，
却只有 `0.394%` issue 覆盖命中率、¥2,032 stake，并在时间切片中失败；它正是该
稳定性规则要排除的情形。

## 归因与后续

报告保留三种不混淆的比较：

1. selector lift：同 gate 的 K 相对 `K_ALL/FULL`；
2. sampler lift：固定同一 selected-K identity 后，抽样器相对该 exact-K FULL；
3. interaction：抽样器相对 `K_ALL/FULL`。

现有证据不支持把选场、K 收缩、概率加权抽样或其组合推广为 N7 策略。负结论不等于
禁止继续研究；它只禁止从该已结算矩阵中事后选择一个稀疏峰值。下游若要继续，应使用
新的、赛前冻结的外部样本或不同的预注册假设。
