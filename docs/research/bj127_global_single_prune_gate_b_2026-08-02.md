# #127 Gate B：同场 N7 全包与全局单码删除结算

日期：2026-08-02（CST）

Issue：[GitHub #127](https://github.com/algotradinglife/beijing-lot/issues/127)

阶段：Gate B；历史纸面结算，结论 `NO_PROMOTION`，等待轻量 PI 复核。

## 结论先行

九个冻结 `p_min × E_SP / GM_E_SP` variant 的每个可结算 FULL/PRUNE matched pair
均为负税后 ROI。最小损失是严格的 `ESP300_GM305_LOWP20 / PRUNE_ONE_GLOBAL_N7`：

- 359 个同场配对完成结算（12 个 canonical outcome gap 未下注）；
- 固定 `K=1,458`、stake ¥2,916 的组合总 stake 为 ¥1,046,844；
- 292 个覆盖命中，覆盖率 81.34%；全局删码发生 67 次（18.66%）；
- 无税 ROI 为 -10.30%，实际 issue-tax ROI 为 **-19.91%**；
- 剔除最佳 payout / issue 后实际 ROI 为 -21.35% / -22.83%；
- 最大回撤 ¥210,016.94，最长连续未命中 2。

它优于同一七场的 FULL 税后 -21.75%，但 FULL 的无税 ROI 为 -8.35%，比 PRUNE
更好。这说明税后约 1.84 个百分点的改善主要来自较小的返奖及税线暴露，而不是删掉
全局低概率码创造了正的无税价值。因此没有策略晋级或购买结论。

## 冻结与结算边界

只读取已合并且 PI 验收的 Gate A v2：

- Gate A merge：`665b96183f0369b28d8bed88434c01e9dd84217e`；
- Gate A manifest：`a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da`；
- canonical outcome/final-SP package manifest：
  `fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc`；
- canonical payload：`canonical_outcome_join.csv`
  `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`。

对每一个冻结 pair，FULL 与 PRUNE 都使用相同七场、相同 canonical result 和未封顶
final winning SP：

```text
gross = 2 × 0.65 × Π(final winning SP)   # 命中时，0.65 只用一次
FULL  K/stake = 2,187 / ¥4,374
PRUNE K/stake = 1,458 / ¥2,916
```

FULL 的 21 个码全覆盖；PRUNE 仅缺冻结时决定的一个全局最小概率码。每个
`variant × arm` 是独立的纸面 policy：同一个 native issue 内先汇总 gross，达到
¥10,000 后对该 policy 的 winning gross 征收 20% tax。没有 canonical outcome 的冻结
组合记为 `UNAVAILABLE_CANONICAL_OUTCOME`、stake 为零，不能用其他来源替代。

## 完整分母和阈值曲线

| 状态 | rows |
| --- | ---: |
| Gate-A `NO_BET_CONTROL` | 23,931 |
| canonical settled（两 arm） | 173,508 |
| canonical outcome unavailable（两 arm） | 6,922 |
| 合计 | 204,361 |

`threshold_curves.csv` 是全部 9 个 variant 的 matched FULL-minus-PRUNE 曲线。以下为
ALL scope 的税后比较：

| E_SP / GM / p_min | FULL ROI | PRUNE ROI | PRUNE−FULL | stake saved |
| --- | ---: | ---: | ---: | ---: |
| 2.80 / 2.90 / .20 | -30.20% | -28.49% | +1.71 pp | ¥1,535,274 |
| 2.80 / 2.90 / .25 | -32.49% | -32.02% | +0.47 pp | ¥14,817,654 |
| 2.80 / 2.90 / .30 | -32.19% | -31.81% | +0.38 pp | ¥29,380,158 |
| 2.90 / 3.00 / .20 | -28.59% | -26.74% | +1.85 pp | ¥1,392,390 |
| 2.90 / 3.00 / .25 | -32.25% | -31.67% | +0.58 pp | ¥14,587,290 |
| 2.90 / 3.00 / .30 | -32.07% | -31.64% | +0.43 pp | ¥29,149,794 |
| 3.00 / 3.05 / .20 | -21.75% | **-19.91%** | +1.84 pp | ¥523,422 |
| 3.00 / 3.05 / .25 | -31.13% | -30.66% | +0.48 pp | ¥10,564,668 |
| 3.00 / 3.05 / .30 | -31.51% | -30.97% | +0.54 pp | ¥24,536,682 |

PRUNE 覆盖率随低概率阈值从 .20 到 .30 下降约 81.3% 到 76.3%，对应删码发生率
18.3%–23.7%。也就是说，固定的一票数压缩不是免费：被删的结果约每五个同场组合出现一次。

## 年度、LOYO 和异常值

最优严格 PRUNE variant 在六个有结算年度全部负：2020 -28.37%、2021 -26.46%、
2022 -35.61%、2023 -33.00%、2024 -28.60%、2025 -42.08%。其 LOYO 范围为
-29.60% 至 -32.56%，没有移除某一年后转正。2019 没有该严格组合，不被解释为零收益年度。

同一策略在剔除最佳 payout 或最佳 signed-net issue 后分别从 -19.91% 变为 -21.35% 和
-22.83%；结论并非由一个未触及的高额返奖或单一期次决定。`matched_pair_deltas.csv`
保留 86,754 个完成结算的同场 pair，能够逐条复核：FULL 总是覆盖，PRUNE 未命中当且仅当
冻结的删码实际发生。

## 经济解释

全局删一个最低概率码稳定地把成本减少 33.33%，并降低 gross，从而减少 issue-level
tax。它对绝对税后 ROI 有小幅改善，但不能使预税期望为正；在最严格样本中 PRUNE 的无税
ROI 甚至比 FULL 差 1.95 个百分点。当前证据支持“成本/税风险压缩”的描述，不支持把
删码当作独立价值 edge。继续研究应引入未用于 `p_min` 的赛前信息或更可靠的赔率价值模型，
而不是在已结算的九个阈值附近继续调参。

## 复现与审计

不可变 package：`results/bj127_gate_b_outcome_settlement_v1/`

- manifest：`77712e25965faa6a13d6783032026eca146a3eba9b67462d9af3439c34cd8965`；
- `portfolio_settlement.csv.gz`：204,361 条完整结算分母；
- `matched_pair_deltas.csv`：逐 pair 的 FULL/PRUNE 经济差；
- `arm_comparison.csv`、`robustness_summary.csv`、`threshold_curves.csv`：ALL、年度、fold、LOYO 和阈值曲线；
- `settlement_card.json`、`decision.json`、`CONTENT_IDENTITY.json`、`settlement_runner.py`：口径与可移植重放。

`pytest -q tests/scripts/test_settle_bj127_global_prune_gate_b.py` 覆盖 manifest、完整
分母、同场 K/stake、删码命中、一次 0.65、issue-level tax、所有负 ROI 和稳健性文件。
