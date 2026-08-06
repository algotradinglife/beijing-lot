---
aliases:
  - Issue 190 Sparse Divergence N7
tags:
  - beijing-lot
  - research
  - n7
status: gate-b-complete
updated: 2026-08-05
---

# Issue #190：稀疏独立模型—盘口分歧 N7

## 结论

完整冻结的 2,424 个 detector policies × 4 个 attribution arms 已一次性结算。
Gate B 得到 `475` 个“绝对税前 ROI > 0 且相对 matched B0 lift > 0”的描述性
screen rows。经 #195 独立复验纠正 coverage 口径后，严格候选数为 `0`，结论为
`NO_PROMOTION_FROM_GATE_B`。性能条件是正 bootstrap 下界、去最大期/年份 ROI 为正且
正收益年份至少 2 个；coverage 条件则独立要求候选 arm 自身至少覆盖 2 个联赛和 2 个
盘口 strata。两者不再混写。

为避免丢失有效的科学信息，另冻结一层 `performance-stable but coverage-limited`
screen：`18` 个 policy aliases 在 bootstrap、去最大期/年份和正收益年份条件上通过，
但因只覆盖 line `0` 而不能晋级；它们折叠为 `10` 个不同的 344 期 issue-economic
identities。最有信息量的是 Z100/K1 的 52/60/75/85 期簇（12 aliases、6 个经济身份）。

接受的 BEST_FULL baseline ladder 保持不变。在 #95 的 163 期共同支持上，税前 ROI
仍为 `-9.47%`；扩大到 #190 的 189 期 SHA-bound SQLite 支持后，描述性 ROI 为
`-8.52%`。新增支持不替代或降级旧 baseline。

## 结算来源和 fail-closed 边界

- Gate-A eligible matches：`101,970`；
- SQLite `match_features` trusted settlements：`100,906`；
- unavailable：`1,064`，对应身份执行 0 张票、0 stake，不计为亏损；
- fully settled N7 identities：`2,946 / 3,181`；
- 与 #95 canonical ledger 重叠 `46,802` 行，result code/SP 差异 `0`。

控制源是 Gate A 已绑定的 SQLite，SHA-256 为
`7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f`。
#95 只作为重叠一致性 oracle，不作为结算分母。

## 四臂 attribution

| Arm | 有 stake 的 policy rows | 中位 native ROI | 正 native ROI rows | 正 matched lift rows |
|---|---:|---:|---:|---:|
| B0_BEST_FULL | 2,424 | -8.52% | 0 | 0 |
| D_MATCH_ONLY_FULL | 1,884 | -22.27% | 48 | 142 |
| D_DIRECTION_ONLY | 861 | -1.89% | 369 | 662 |
| D_JOINT_SPARSE | 1,884 | -16.24% | 128 | 201 |

整体上，match-only 与 joint sparse 没有形成可直接晋级的稳定方案；较强信号主要出现在
direction-only。原先标作严格候选的 18 个 `D_DIRECTION_ONLY` cells，在各自冻结身份上
都只覆盖盘口 `0` 这一层，而不是误继承自 `D_MATCH_ONLY_FULL` 的 6 层。它们仍保留为
描述性正 ROI/bootstrap 证据，但不能支持跨盘口稳定性，也不具备晋级资格。

| Z100/K1 distinct economic support | Native ROI | Matched lift | Bootstrap low | Line strata |
|---:|---:|---:|---:|---:|
| 52 issues | +14.89% | +27.92% | +0.37% | 1 |
| 60 issues (identity A) | +19.83% | +27.97% | +1.19% | 1 |
| 60 issues (identity B) | +20.48% | +28.62% | +1.79% | 1 |
| 75 issues (identity A) | +14.83% | +26.96% | +4.27% | 1 |
| 75 issues (identity B) | +15.35% | +27.48% | +4.67% | 1 |
| 85 issues | +8.78% | +21.19% | +0.13% | 1 |

## 概率诊断

在 100,906 个 trusted outcomes 上：

| Probability source | Log loss | Brier | ECE |
|---|---:|---:|---:|
| HANDICAP_CONSENSUS | 1.126232 | 0.683754 | 0.081892 |
| FUNDAMENTAL_INDEPENDENT | 1.116766 | 0.677073 | 0.073369 |
| CALIBRATED_MARKET_ESTIMATOR | 1.114387 | 0.677845 | 0.067176 |

因此独立基本面概率相对 handicap consensus 有小幅总体改善，但 calibrated market
estimator 的 log loss 更低；不能把少数 direction-only 正收益 cells 解释成独立模型已
普遍优于市场。

## 账务和耐久性

税前 ROI 是主口径。税只按每一张命中的 ¥2 票分别计算，不跨票、跨期或跨人汇总。
arm-specific correction 后完整包含 43 个 manifest payload；canonical ledger、四臂
issue-level settlement、bootstrap contributions/results 和所有其他 economics payload
逐字节不变：

- corrected package manifest：`5685f25d9ce70a66b38b283f668d258d97dfe2e356c5bd45d9666400c6ab4554`；
- corrected content identity：`5112dc652277a234fcb36687d59e2bd96bf8daeaaa1c9ddd06481923de909ce6`；
- canonical ledger：`c939b7825ba9e720624e56812000fec692213ea48d5cc5934095c59ec286c818`。

不可变包：`results/bj190_gate_b_sparse_divergence_v1`。其中包含完整四臂 settlement、
20,000 次 paired bootstrap、YEAR/FOLD/LOYO、风险与集中度、failure attribution、
chart-source tables、SVG 图和 exact candidate freeze。
