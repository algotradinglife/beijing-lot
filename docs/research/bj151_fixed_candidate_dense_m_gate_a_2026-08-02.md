---
title: "#151 #137 固定候选的密集 M 复现：Gate A"
date: 2026-08-02
status: preregistered
---

# #151：固定 #137 候选的密集 M 与采样机制复现

这是一个 outcome-unexposed Gate-A 冻结，而不是新的候选搜索。唯一候选定义直接来自
#137 已接受 Gate-A v2 的 `NO_GATE / K4` 参与记录：每个完整期次恰好使用其冻结的
`selected_portfolio_ids`，以及同一身份的 `Q_WEIGHT` 七腿向量。

候选的历史描述性参考点为 `Q_INFORMED_WOR_DISTINCT / M=64`，固定 seed 为
`137001/137002/137003`。该参考点不是已验证 edge；本冻结禁止根据赛果选择 identity、
gate、K、M、seed 或候选池。

## 样本与机制

- 348 个 #137 `NO_GATE/K4` 完整 issue/fold 行：339 个 `AVAILABLE`，9 个源端
  `NO_BET`（不足四个 identity）；9 行在每个 arm/M 都保留为零 stake，而非删除。
- 1,356 个固定 N7 identities、9,492 个 role-vector 行；每个可用 issue 都是 4 个 identity。
- M 轴与 #148 对齐：`16..512` 每 16、`576..1024` 每 64、`1088..2112` 每 64，及
  `2187` FULL，合计 58 点。
- 每个非 FULL M 使用 Q 加权 WR（主比较，重复抽样仍是独立 ¥2 ticket）和
  Q 加权 WOR（#137 候选机制敏感性）；FULL 为每个 identity 精确枚举 2,187 票。
- M 为每一 N7 identity 的抽样数，故可用 issue 的总 draws 为 `4×M`，总 stake 为
  `4×M×¥2`；FULL 也按相同 4 个固定 identity 计算。

## 输入绑定与赛果边界

固定候选只读取 `results/bj137_gate_a_preoutcome_v2`，其 manifest 为
`0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df`。
#148 的 Gate-A manifest
`fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6`
仅绑定其 broader-pool dense-M 比较定义；Gate A 不读取 #148 或 #137 的结算、ROI、
final SP、payout、tax 或任何赛果。

Gate B 若获授权，必须在不改变本包 plans 的前提下：先报告 pre-tax `no_tax_roi`，再报告
per-ticket 税后 ROI；报告候选、同 K4 FULL 和 candidate−FULL；将 #148 broader-pool
曲线并列显示；并提供 YEAR/FOLD/LOYO、issue bootstrap、最大 issue 贡献、资金分布、
重复率与 coverage。稳定正结果仍须单独 strict independent EV；研究本身不授权下注或推广。

## 可复现性

包位于 `results/bj151_gate_a_preoutcome_v1`，manifest 为
`3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6`。执行
`python3 results/bj151_gate_a_preoutcome_v1/freeze_runner.py --output <new-dir>` 可重放；
暂存目录位于目标输出旁边，绝不使用 `/tmp`。
