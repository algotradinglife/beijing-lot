# Issue #192：N7 多策略组合与资金分配 Gate B

## 结论

本次 Gate B 从已结算、hash-bound 的最小 Stage-4 checkpoint 重建了完整的
组合层交付包；没有再次回放任何 ticket，也没有新增 M 曲线或事后搜索。虽然若干
历史路径有正的点估计，两个达到“材料性正值”门槛的原生控制候选都没有通过预先
规定的 20,000 次配对 stationary-block max-T 推断。因此终局是 **`NO_PROMOTION`**：
不得把任何路径用作生产、购买或下注授权。

## 不可变身份与范围

- Gate-A manifest：`6108defd857bf431bcaf55109df0e195b45aa754e8fd46f1db82d329102ff256`
- Gate-A content identity：`66ce6f86703b31d710ad678b49287de3bc6b2c43a5b36c278e1369bdecd861d5`
- Gate-B manifest：`e028c54d7826e6c48eff2090538ac404f6b250f2c9f334e74bcc6acb4f6cf421`
- Gate-B content identity：`cad3fc655d06e1fbb94128652d083c5b8dee729b0c10b1736548473a13ccd585`
- checkpoint：`.scratch/bj192_minimal_stage4_checkpoint.json`，payload
  `4e531ef6d2897321ff493442b769e18f94ec59e3a39068ae7b9f84668f0bfd50`

冻结的 sleeve 是 `BEST_FULL_FULL`、`MODEL_SOURCE_MODEL_CAP1_M512` 和
`Q_SOURCE_Q_TOP_MASS_M192`。交付覆盖 3 个 singleton、3 个 pair 和 1 个 triple，
以及 36 个已冻结的 mode/fraction/weight/normalization 轴：共 252 条
完整 348-期资金路径。三个 Gate-A ordinal bundle 已逐期验证经济等价，仅保留
`BUNDLE_ORDINAL_001` 作为唯一可执行表示。`NATIVE_REQUEST_CONTROL` 仅为 1.0；FIXED 与 COMPOUNDING
分别保留 0.10/0.25/0.50/1.00；权重仅为 EQUAL_WEIGHT 与 PRIOR_MINIMUM_VARIANCE，
资金规范化仅为 UNIT_CAPITAL 与 UNIT_EX_ANTE_VOL_CAPPED_5PCT。

## 严格推断（税前主口径）

| 原生候选（相对 BEST_FULL_FULL） | 配对平均净额增量 | 95% 配对下界 | max-T FWER p | 结论 |
|---|---:|---:|---:|---|
| MODEL + Q | ¥469.58 | -¥157.49 | 0.10019 | `STRICT_MAX_T_NOT_PASSED` |
| Q top-mass M192 | ¥422.38 | -¥194.17 | 0.12559 | `STRICT_MAX_T_NOT_PASSED` |

两个比较共享相同的 348 期完整日历、¥100,000 native control、EQUAL_WEIGHT、
UNIT_CAPITAL、BUNDLE_ORDINAL_001、seed `19220001` 和平均 block length
`18.65475810617763`。显著性判断使用两比较共同的 resample，故不能把单路径的正
ROI、正 bankroll 终值或较低 drawdown 当作独立发现。

## 交付账本与图源

[`bj192_gate_b_minimal_stage4_v2`](../../results/bj192_gate_b_minimal_stage4_v2/README.md)
是唯一 Gate-B 数据包（约 100 MiB）。其 manifest 覆盖 26 个 payload：

- `issue_ledger`：87,696 条按 `first_kickoff_ts` 排序的逐期资金路径；
- `sleeve_funding_ledger`、`risk_decomposition`、`weight_history`：各 150,336 条；
- `stage_attribution`：601,344 条，不把上游不可识别步骤伪装成 splice attribution；
- `rolling_window_metrics`：259,560 条；
- `capital_summary`、`holding_metrics`、`portfolio_k_saturation`：各 252 条；`baseline_lift`：324 条；
- `all_pairs_risk_return_surface`：108 条；`bootstrap_stability`、`terminal_decision`：各 2 条。

图表应直接由包内的 `issue_ledger.csv.gz`（权益与回撤）、
`rolling_window_metrics.csv.gz`（滚动风险）、`capital_summary.csv`/
`all_pairs_risk_return_surface.csv`（资本与风险前沿）、`dependence*.csv.gz`（真实
资金流依赖）和 `bootstrap_stability.csv`（严格筛选）生成。每个来源均保留完整的
path identity；不要把不同 fraction、bundle 或 selector support 的点连成同一条曲线。

## 边界

税务按已冻结的每张 ¥2 ticket tax lot 结算，绝不跨 ticket/issue 汇总计税。包内
`standalone_m_curve` 刻意为空：最小收尾合约禁止重新运行 M 曲线。上述结果是历史
组合与资金层诊断，不能反向改写 selector、M、ticket ordering 或上游概率模型；任何
未来正结果都需要新的预注册独立验证。
