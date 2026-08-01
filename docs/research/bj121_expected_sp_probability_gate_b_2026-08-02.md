# #121 Gate B：期望 SP × 最低概率阈值前沿的规范结算

日期：2026-08-02（CST）

Issue：[GitHub #121](https://github.com/algotradinglife/beijing-lot/issues/121)

阶段：Gate B，一次性规范赛果结算；历史纸面研究，不构成投注、生产或盈利建议。

## 已授权输入与不可变边界

本次只结算 PI 接受并合并的 Gate A v3；没有新增或删除阈值、策略臂、候选场次或
角色。合并的 Gate-A commit 为 `a311e0272db927c64722fd9b1b43b2419b07118f`，冻结包
`results/bj121_gate_a_preoutcome_v3/` 的 manifest 为
`acef123c062c4deafd637941ea4ebe5cb165078dfdf0bd1998cc2b6e00446eee`。

赛果只来自 `results/bj95_gate_b_outcome_settlement_v2r8/` 的规范 final-SP join：

- outcome package manifest：`fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc`；
- canonical payload：`13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`；
- Gate-B output manifest：`e7dc57ad5451ddcc138f8ed3e451fbc8447b6bae8566e0d2500597ce56ba26c2`。

对每个已冻结组合，只有所有真实赛果仍在该组合的 allowed codes 内才命中：

```text
gross = ¥2 × 0.65 × Π(final winning SP)     （命中时；否则 0）
net   = gross − issue-level tax − frozen stake
```

`0.65` 恰好应用一次；`K` 和 stake 是 Gate A 已冻结的会计输出，绝不作为结算时的
筛选条件。每一个 `(variant, arm, issue)` 都是独立的纸面政策税桶：该 issue 内累计
gross 达 ¥10,000 时，对桶内所有 gross 收取 20% 税。赛果缺失不寻找替代源，也不扣 stake。

## 完整分母与可用性

| Gate-A frontier rows | Gate-A NO_BET | 已规范结算 | canonical outcome unavailable |
| ---: | ---: | ---: | ---: |
| 311,103 | 86,994 | 207,765 | 16,344 |

完整 344 issue / 2,659 pool 分母、9 个 `E_SP / GM_E_SP / p_min` variant 与 13 个
策略臂均被保留。`NO_BET`、可结算和赛果缺失是三个不同分母状态；没有把缺失行静默删除
或计入损失。

`frontier_summary.csv` 是 9 × 13 的完整阈值比较表，且每一行同时给出 eligible/no-bet/
unavailable、K/stake、命中、gross/tax/net、绝对 ROI、按 kickoff 顺序的最大回撤和最长
连败、集中度、剔除最佳 pool 及 issue 的敏感度。`annual_summary.csv`、`fold_summary.csv`
和 `leave_one_year_out_summary.csv` 为同一张矩阵的所有时间切片；这些 CSV 是本文表格的
完整等价“热图”。

## 全矩阵结果

所有 108 个有 stake 的 `ALL` 行均为负税后绝对 ROI；9 个 `NO_BET_CONTROL` 保持
¥0/无交易。这一结果不是失败关闭：它是被冻结完整矩阵的研究结论。

表现最接近零的有交易行是：

| variant | arm | settled / unavailable | stake | hits | gross | tax | net | tax-adjusted ROI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `ESP300_GM305_LOWP30` | `MIXED_N7` | 1,417 / 79 | ¥541,508 | 206 | ¥422,050.048326 | ¥7,407.264391 | −¥126,865.216065 | **−23.4281%** |
| `ESP300_GM305_LOWP30` | `MIXED_DYNAMIC_4_7` | 1,667 / 122 | ¥550,980 | 283 | ¥428,688.780146 | ¥7,407.264391 | −¥129,698.484245 | −23.5396% |
| `ESP300_GM305_LOWP30` | `PRUNE_N7` | 1,417 / 79 | ¥543,012 | 206 | ¥422,050.048326 | ¥7,407.264391 | −¥128,369.216065 | −23.6402% |
| `ESP300_GM305_LOWP30` | `PRUNE_DYNAMIC_4_7` | 1,667 / 122 | ¥552,548 | 283 | ¥428,688.780146 | ¥7,407.264391 | −¥131,266.484245 | −23.7566% |

作为规模参照，最宽松 `UNFILTERED_FULL_DYNAMIC_4_7` 的 2,357 个可结算 pool 使用
¥10,242,126 stake，税后 net 为 −¥3,298,468.566600（ROI −32.2049%）。严格的
`p_min=0.30` 确实显著降低了 K 与 stake，因此使 ROI 从约 −31% 至 −32% 改善至约
−23% 至 −24%；但并没有翻转为正值。

最接近零的 `MIXED_N7` 行在剔除最佳 issue 后 ROI 为 −25.1693%，剔除最高 gross
pool 后为 −25.0225%。因此该相对较好的点并非由单一期次或单次 payout 造成，也仍然
显著低于零。

## 经济解释与决策

高 `E_SP` 门槛和 `p_min=0.30` 的删除/单选机制主要压缩了覆盖组合数，而不是创造足以
抵消结算 SP、65% 因子和 issue-level 税的价值。全包臂总能覆盖、但仍具有负期望的税后
回报；PRUNE/MIXED 节省 stake 的同时减少命中和可实现的 gross，未改善至正绝对 ROI。

`decision.json` 的终态为 `NO_PROMOTION`，正向候选数为 0。严格规则要求某行同时满足：

1. ALL 税后 ROI、剔除最佳 payout ROI、剔除最佳 issue ROI 均为正；
2. 每一个冻结的年度和 LOYO 切片也为正；
3. 即使满足上述条件，也只能提交独立严格 EV，而不是自动晋级。

没有任何行达到第一步，所以本包不触发独立正向 EV，也不产生策略晋级。

## 审计与复现

结算包：`results/bj121_gate_b_outcome_settlement_v1/`

- `portfolio_settlement.csv.gz`：311,103 条冻结行的逐行结算；
- `frontier_summary.csv`：全部 117 policy rows 的主比较矩阵；
- `annual_summary.csv`、`fold_summary.csv`、`leave_one_year_out_summary.csv`：完整时间稳健性矩阵；
- `pool_failure_concentration.csv`：命中失败与收益集中度；
- `canonical_outcome_join.csv`：经过认证的结算 payload 副本；
- `settlement_card.json`、`decision.json`、`settlement_runner.py`、`SHA256SUMS.json`：来源、规则、决策和可重放绑定。

运行 `python3 settlement_runner.py --output <empty-directory>` 可在兼容 checkout 中从两个
已认证输入包重放；输出路径必须为空，以防覆盖不可变研究包。
