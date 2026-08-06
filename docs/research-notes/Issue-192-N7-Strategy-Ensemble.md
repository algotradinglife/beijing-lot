# Issue #192：N7 多策略组合与资金分配 Gate B

## 结论

Gate B 的唯一权威交付是
[`bj192_gate_b_minimal_stage4`](../../results/bj192_gate_b_minimal_stage4/README.md)。
它保留了已审计账本，并修正了两类解释错误：实际资金不同的路径不再被称为
matched-FULL lift；资金不可执行仅在 allocator 的缩放或破产约束实际触发时才标记。

结论仍是 **`NO_PROMOTION`**。历史正点估计、终值或回撤改善都不是购买、下注或生产
授权。

## 不可变身份与范围

- Gate-A manifest：`6108defd857bf431bcaf55109df0e195b45aa754e8fd46f1db82d329102ff256`
- Gate-A content identity：`66ce6f86703b31d710ad678b49287de3bc6b2c43a5b36c278e1369bdecd861d5`
- 最终 Gate-B manifest：`3159431d91dda7dfb23ea7dbe4daa42a5411f7e52616e50bb31f04722c17ebe4`
- 最终 Gate-B content identity：`b3ec5764903402b35208bb3ee1ad9d1854274bf19b45fd4f3a89ee943385ed7e`

交付包覆盖 252 条冻结的完整 348 期路径：三个 singleton、三个 pair 和一个
triple，跨既定 mode/fraction/weight/normalization 轴。Gate-A 的三个 ordinal bundle
逐期经济等价，仅 `BUNDLE_ORDINAL_001` 是可执行表示。原始 20,000 次 paired
stationary-block max-T 推断未重新运行；本次修正不扩展研究搜索空间。

## 冻结的未匹配 bootstrap 诊断（税前）

| 原生候选（相对 BEST_FULL_FULL） | 原始配对净额差 | 95% 配对下界 | max-T FWER p | 诊断结论 |
|---|---:|---:|---:|---|
| MODEL + Q | ¥469.58 | -¥157.49 | 0.10019 | `STRICT_MAX_T_NOT_PASSED` |
| Q top-mass M192 | ¥422.38 | -¥194.17 | 0.12559 | `STRICT_MAX_T_NOT_PASSED` |

这些数字是冻结的原始 candidate-vs-FULL 路径差；资金审计已证明两侧实际 funding
不同，因此它们只保留为未匹配 bootstrap 诊断，**不能**确立 candidate lift 或严格的
matched-capital 证据。

## 受限的 matched-capital 复放

为回答“同一笔逐期资本下”的控制问题，包额外进行了两项预先限定、非搜索性的
ticket-prefix 复放：每侧仍使用自己的冻结 ticket prefix，但每期都使用同一整数元、
整张 ¥2 ticket 的最大共同可执行 schedule。两个侧的
`capital_schedule_hash` 完全相同，ticket funding hash 则刻意独立保留。

| 对照 | 共同可执行期数 | 共同 stake | 结果 |
|---|---:|---:|---|
| MODEL+Q vs Q | 180 / 348 | ¥276,480 | MODEL+Q ROI -15.91%，Q -3.64%，matched-capital lift **-¥33,910.53**；其余 168 期因一侧不可执行或原子取整不可共用。 |
| Q vs FULL | 0 / 348 | ¥0 | `NOT_IDENTIFIABLE_NO_COMMON_EXECUTABLE_SCHEDULE`：FULL 的 2,187-ticket 原子前缀与 Q 的可用容量从无共同整数 schedule；全部 348 期逐期记录为 unavailable，不是零 lift。 |

这两项对照没有 bootstrap 重跑，也没有产生新的候选或推广结论；只有 MODEL+Q vs Q
是有效 matched-capital 对照，且结果为负。所有 unavailable 期、共同 support 和原子
取整规则均写入机器可读账本。

## 交付账本与图源

最终包有 36 个 manifest 覆盖 payload（约 39 MiB），包括：

- `issue_ledger.csv.gz`：87,696 条逐期资金路径，按 `first_kickoff_ts` 排序；
- `sleeve_funding_ledger.csv.gz`、`risk_decomposition.csv.gz`、`weight_history.csv.gz`：
  各 150,336 条；
- `capital_summary.csv`（252）与 `baseline_lift.csv`（468）：分别保留 allocator
  不可执行定义及 candidate/control 的独立 support、funding hash；
- `matched_capital_comparisons.csv`、`matched_capital_issue_ledger.csv` 与
  `matched_capital_unavailable_issues.csv`：上表的完整可复放对照；
- `charts/decision_paths.svg`、`.png`、`.pdf`：由同一 `decision_chart_source.csv`
  用仓库固定的 matplotlib 生成，并均由 manifest 覆盖。

税始终以每张命中的 ¥2 ticket tax lot 结算，不跨 ticket 或 issue 汇总。图表、滚动
风险和严格筛选均保留完整 path identity；不得把不同 fraction、bundle 或 selector
support 的点连成一条可比较曲线。

## 边界

交付仅校正资金比较、资金约束语义和决策图表；不回写 selector、M、ticket ordering
或上游概率模型。所有未来的正结论仍需新的预注册、独立验证。
