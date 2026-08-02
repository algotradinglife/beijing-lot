# #132 legacy segment sensitivity — `p_min` 与 `q=p×predicted_SP` 全局删码结算

> 此包只结算已 supersede 的 segment-compatible Gate-A v1，分类为
> `LEGACY_SEGMENT_SENSITIVITY / NON_CONTROLLING`。以下 `NO_PROMOTION` 只适用于该
> legacy comparator；#132 的 complete-issue primary result 为 `NOT_RUN`，必须等待
> replacement Gate A 被 PI 接受后才可进行新的 Gate B。

## 绑定与可复现性

- Gate A：`results/bj132_gate_a_preoutcome_v1/`，manifest
  `5b41fef30543647eef1dec5cfd65e4a12343c898ebd929d13393a2d6f1371937`；
- canonical final-SP outcome join：#95 Gate B v2r8，manifest
  `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc`；
- Gate B v1 的本地同文件系统计算结果保留不改；v2 使用相同冻结和算法，补上跨文件系统
  clean-replay 的原子交付恢复。经 scope reclassification 后的最终包为
  `results/bj132_legacy_segment_sensitivity_outcome_settlement_v2/`；其数值 payload 保持不变，
  仅更新 decision/card/README/runner 的 legacy attribution。

结算只打开通过 manifest 验证后的赛果源。每个 ¥2 序列仅在命中时支付
`¥2×0.65×七场最终中奖 SP 乘积`；按 issue × variant × arm 汇总 gross 达 ¥10,000
才扣 20% 税。没有重选场次、重算 `q`、重排删码或改变 stake。

## 完整冻结矩阵

保留 23,931 条 Gate-A no-bet 行；90,215 个已冻结组合各有 FULL、`p_min`、`q_min`
三臂，合计 294,576 条。其中 260,262 条已结算、10,383 条缺少 canonical outcome
而 fail closed。76,501 个已结算组合同时是赛前 `p_min/q_min` 分歧组合，直接配对比较已
写入 `q_minus_p_disagreement_deltas.csv.gz`。

三臂保持同一七场。FULL 为 ¥4,374，两个删码臂均为 ¥2,916，固定保留 2/3 stake；因此
ROI 差异是删除评分的边际差异，而非选场或资金规模差异。

| ALL-scope 最佳 absolute 税后 ROI | variant | 税后 ROI | 相对 FULL | 无税相对 FULL |
|---|---|---:|---:|---:|
| `p_min` | ESP300_GM305_LOWP20 | -19.91% | +1.84pp | -1.95pp |
| `q_min` | ESP300_GM305_LOWP20 | -20.17% | +1.58pp | -0.25pp |

全部 18 条 non-FULL ALL-scope 行的无税与实际税后 ROI 都为负；因而此处的税后改善来自
较低的 tax exposure，不能解释为正的 payout edge。`q_min` 在 8/9 个 variant 的无税 ROI
相对 FULL 更高（`p_min` 为 7/9），但没有一条达到 breakeven；也没有证据表明它稳定地优于
`p_min`。legacy 结论：`NO_PROMOTION`（非 controlling；不代表 complete-issue primary）。

## 分层与风险

`deletion_strata.csv` 逐臂保留 outcome type、deleted-code probability、predicted SP、
deleted-match E_SP 与 portfolio GM_E_SP 的预期删码率、实际删码率和两类 ROI。年度、fold、
LOYO 的完整摘要在 `robustness_summary.csv`；每个 arm 的 drawdown、最长 miss streak、
最大 event 敏感性和 issue concentration 在 `arm_summary.csv`。FULL、删码臂和直接
`q_min−p_min` 配对差异分别在 `matched_full_deltas.csv.gz` 与
`q_minus_p_disagreement_deltas.csv.gz`。

运行 `python3 scripts/settle_bj132_delete_score_n7_gate_b.py` 可在干净输出目录重放包；
`tests/scripts/test_settle_bj132_delete_score_n7_gate_b.py` 覆盖 manifest、#127 FULL endpoint、
三臂几何、factor/tax、全矩阵、分层与稳健性输出。
