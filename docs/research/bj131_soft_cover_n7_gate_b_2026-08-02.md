# #131 Gate B：全局删码 N7 的软覆盖 sleeve 结算

日期：2026-08-02（CST）
Issue：[GitHub #131](https://github.com/algotradinglife/beijing-lot/issues/131)

阶段：Gate B；已接受 Gate A v3 的一次性 canonical outcome settlement。结论为
`NO_PROMOTION`，不构成购买、生产或投注授权。

## 结论

三个预注册 seed、九个已冻结 selector variant、七个 sleeve 的 **189 个 ALL-scope
行，无税及实际税后 ROI 均为负**。因此没有任何正 ROI 行需要严格独立 EV。

中间 sleeve 有时会在同一已结算样本中同时优于 hard prune 与 FULL，但最佳比例随
variant 和 seed 改变，且主 seed 的严格 selector `ESP300_GM305_LOWP20` 以 hard prune
最好。这是样本内随机抽样位置的敏感性，不是可推广的 sleeve 深度或新增 selector edge。

双重归因应明确区分：

1. `MATCHED_FULL_N7` 是 #127 既有七场 selector baseline；
2. sleeve 的 delta 只衡量在同一七场、同一删码、同一结算窗口下，买回 omitted-code
   slab 的 portfolio-layer 增量。

## 输入与边界

- Gate A v3：`results/bj131_gate_a_preoutcome_v3/`，manifest
  `79d722a7919afb03916d0be57dd72c51c5ef2174fbf6b27cea2042ed6a65e53c`；
- canonical outcome join：#95 已验收的
  `results/bj95_gate_b_outcome_settlement_v2r8/`，payload
  `13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89`；
- 没有重新选择七场、删码、阈值、seed、sleeve 或票顺序；
- 每个中码 sequence 的 gross 是 `¥2 × 0.65 × final winning-SP product`。每个
  `issue × variant × seed × sleeve` policy 的 winning gross 达 ¥10,000 时才计 20% tax。

完整逻辑分母为 2,397,066 行：1,894,515 active 与 502,551 Gate-A no-bet。最终状态为：

| 状态 | 行数 |
| --- | ---: |
| `SETTLED` | 1,821,834 |
| `UNAVAILABLE_CANONICAL_OUTCOME` | 72,681 |
| `NO_BET_GATE_A` | 502,551 |

每一个 `seed × sleeve` 都保留相同的 86,754 active settled、3,461 active outcome gap、
23,931 no-bet 分母；缺少 canonical outcome 的行 stake 为零，绝不以别的来源替代。

## 全套 primary 曲线

下表是主 seed `131001` 的实际税后 ROI；列依次为 0%、5%、10%、20%、33%、50%、100%
sleeve。完整的 9×3×7 曲线、以及年度/fold/LOYO 支持，在 package 的
`sleeve_response_curve.csv` 中保存，不能只挑下表的最优点解释。

| variant | 0% | 5% | 10% | 20% | 33% | 50% | 100% | primary 最好 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ESP280_GM290_LOWP20 | -28.49% | -29.24% | -29.10% | -30.62% | -32.18% | -31.24% | -30.20% | 0% |
| ESP280_GM290_LOWP25 | -32.02% | -32.08% | -32.17% | -31.85% | -31.77% | -32.26% | -32.49% | 33% |
| ESP280_GM290_LOWP30 | -31.81% | -31.75% | -31.76% | -31.76% | -31.65% | -31.96% | -32.19% | 33% |
| ESP290_GM300_LOWP20 | -26.74% | -25.63% | -25.92% | -25.20% | -24.05% | -26.77% | -28.59% | 33% |
| ESP290_GM300_LOWP25 | -31.67% | -31.89% | -31.93% | -31.51% | -31.55% | -31.82% | -32.25% | 20% |
| ESP290_GM300_LOWP30 | -31.64% | -31.83% | -32.12% | -32.08% | -31.75% | -31.77% | -32.07% | 0% |
| ESP300_GM305_LOWP20 | -19.91% | -20.65% | -20.11% | -21.23% | -23.57% | -26.96% | -21.75% | 0% |
| ESP300_GM305_LOWP25 | -30.66% | -30.95% | -30.94% | -31.11% | -31.58% | -31.88% | -31.13% | 0% |
| ESP300_GM305_LOWP30 | -30.97% | -30.87% | -31.00% | -31.36% | -31.30% | -31.19% | -31.51% | 5% |

严格 selector 的 primary 结果最能说明不稳定性：hard prune 是 -19.91%，FULL 是
-21.75%，5%/10%/20%/33%/50% 依次为 -20.65%/-20.11%/-21.23%/-23.57%/-26.96%。
10% 虽比 FULL 少损失 1.64pp，却仍比 hard prune 多损失 0.10pp。两个额外 seed 的
同一 strict row 又分别在 5%（-19.55%）与 50%（-15.66%）达到各自最佳；这正是为何
不可以把任意一个 `s` 事后固定为政策。

## matched 增量、支持与风险

`sleeve_response_curve.csv` 对每个 `scope × variant × seed × sleeve` 同时报：

- FULL selector baseline 的 no-tax / tax ROI；
- sleeve−FULL 与 sleeve−hard-prune 的两种 ROI delta；
- stake 与 gross retention、删码实际开出率、coverage；
- 年度、OOS fold、leave-one-year-out support；
- ALL scope 的最大回撤、最长 miss streak、去除最大 payout 与最佳净收益 issue 后 ROI、
  正净收益和 gross 的集中度。

`matched_sleeve_deltas.csv.gz` 是 1,821,834 条 settled portfolio×seed×sleeve 的逐行
配对表，包含同一 portfolio 的 FULL/hard-prune coverage、gross、stake 和税后净额差。
它让任何“软覆盖优于端点”的说法都可回到同场的增量，而不是混合不同 selector 样本。

在主 seed 中，FULL 相对 hard prune 的税后差在九个 selector 中始终更差
0.38–1.85pp；这是 tax/stake 结构下的端点比较，并不让 hard prune 成为正 edge。中间
sleeve 的少数局部改善既不在主 seed 中统一出现，也没有使任一绝对 ROI 过零。

## 可复现性

不可变 package：`results/bj131_gate_b_outcome_settlement_v2/`

- manifest：`aa3244b4182acc7d05b3c3d11ea838277055735b43a7dbac8b1cafc667fa2b7a`；
- portable content identity：`fc5d99234328f0ae8ced6b3624e69a2aedc6e196cb151b699f281beb392deacb`；
- `portfolio_settlement.csv.gz`：完整三 seed × 七 sleeve 结算分母；
- `sleeve_summary.csv`、`robustness_summary.csv`、`sleeve_response_curve.csv`：完整曲线和
  年/折/LOYO 支持；
- `matched_sleeve_deltas.csv.gz`：逐 portfolio matched increment；
- `settlement_runner.py`：可移植的一次性重放器。为避免内存相关的执行漂移，ALL-scope
  path metrics 使用临时磁盘排序；临时数据库在 package 写入前删除，非输入、非输出。v2 将
  scratch 固定在 repository `results/` 而非调用者可能容量不足的输出父目录，因此同一 runner
  可安全重放到 `/tmp` 或其他小型交付目录。

`pytest -q tests/scripts/test_settle_bj131_soft_cover_n7_gate_b.py` 覆盖 manifest、完整
分母、每个 sleeve 的几何、与 #127 accepted endpoint 的精确恒等、全曲线非正性与内容身份。
