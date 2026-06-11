# SP 漂移 Phase 0 — 面板体检

- 面板行数（pre-kickoff）: 974,423
- match 数: 1,757
- pre-kickoff 快照/腿: 中位 164, 均值 193.8, 最大 700
- 基线决策 MTK（plan 实际生成时刻中位）: 1078 分钟 (~18.0h before kickoff)
- MTK 分布: P10=243 中位=1298 P90=3077 分钟

## 锚点（final_sp = 收盘前快照 SP，vs 结算 winning_sp，仅中奖腿）
- n = 1,623
- **中位比 winning_sp/final_sp = 1.003**（≈1 表示无系统性偏差）
- **Spearman 相关 = 0.841**（单调一致性）
- 相对差占比: <5% 34% / <10% 55% / <20% 80%
- 判定：✅ 通过（标准：中位比∈[0.95,1.05] 且 Spearman≥0.80）

> 注：北单 SP 为 parimutuel，末段仍在移动，且 winning_sp 是结算后官方值，故收盘快照与之有逐场噪声（<5% 仅 ~34%）但**无系统性偏差**。因此 `drift_bias`（有符号）可靠；`residual_drift`（幅度）会含此代理噪声、偏大。
