# 推进测试计划：SP 漂移保守分位 haircut（MVP）

**日期**: 2026-06-24
**作者**: Claude（承接对话：盈亏归因 + SP 漂移建模直觉）
**状态**: **第一轮（P1–P4）完成（2026-06-24）**。复盘：`docs/research/sp_drift_quantile_mvp_retro.md`
**关联**: `docs/research/pnl_attribution.md`、`docs/strategy/final_sp_process_model.md`、`docs/research/sp_drift_quantile_mvp_retro.md`、[[sp-drift-study]]、`src/sp_drift/{panel,drift_stats,replay,drift_model,forward}.py`

---

## 第一轮结果与决定（P4，2026-06-24）

四张卡均经独立审核 + push：P1 `drift_model`(7420d98) → P2 `adjusted_sp`(696b295) → P3 QHC arm + 前瞻泄露修复(43daa19+8bcc993) → P4 复盘(a1b5550)。

- **真正交付的价值**：P1 的 (SP档×MTK) 漂移模型表——稳健量化「haircut×决策时机」统一结构（近开赛 SP 稳、远期/高 SP 漂移极端）。
- **OOS（~1.6 周）全是噪声**，不可判任何 arm 有效性（C0 +910% / QHC −100% / N3 +1007% 皆薄样本）。
- **本轮教训**：P3 初版前瞻泄露（完整 panel 训练）被 reviewer 逮住并修复 → 纪律：**所有 forward arm 的模型/参数只用 pre-forward 数据训练/冻结**。
- **决定 = 继续累积（选项 b）**：不加特征、不碰实盘；drift_model/QHC/FAV5/N arm 已接入每周一 forward timer 自动累积。
- **预注册下一轮触发**：当 QHC 累积 ≥ 数十次命中（或 ≥8–12 周）→ 再开一轮复盘正式比较 QHC vs C2 vs C0，届时才考虑 (a) 加特征 或 落地保守分位 haircut（仍需先过 GATE）。

详见复盘文档 `docs/research/sp_drift_quantile_mvp_retro.md`。

## 1. 目标

直击**头号可控亏损来源 = SP 漂移**（盈亏归因实测 drift 因子 0.545，且随 N 乘法放大；selection 反而 +EV）。

把决策时 SP 视为「真实结算 SP」的带噪估计，**按 (SP档 × MTK桶) 建模 `ratio = final_sp/decision_sp` 的均值与离散度**，用一个**保守分位**的预测结算 SP 来算 EV/sizing，而不是乐观的决策 SP。**纸面/OOS 在 forward 框架验证；不通过不改实盘。**

## 2. 已确立的背景（本会话）

- 盈亏归因：选腿在决策价上 +EV(2.08)；亏在 rake(0.65)×drift(0.545)，且 drift 随 N 复利。
- 漂移是均值回归（band: <3.5 +33%、>8 −81%）且强依赖 MTK（残差 46%@18h → 3%@1h）。
- 现成件：`HAIRCUT_MAP` 点估计 + `maybe_haircut_snapshots`（默认关）；`panel.attach_final_and_settlement`（**全腿**、无幸存者偏差）；forward C0/C1/C2 arm。

## 3. 非目标（YAGNI）

- 不改实盘 config。不上花哨 ML。MVP 特征只到 `SP档 × MTK桶`，不加联赛/让球等。
- 不动 GATE-FT（仍只看 C0/C1/C2）；新 arm 为描述性对照。

## 4. 阶段（卡片）

| 卡 | 目标 | 交付 | 验收 |
|----|------|------|------|
| **P1** 拟合漂移模型 | 离线、可复现地估 `ratio` 的 E 和 σ | `src/sp_drift/drift_model.py::fit_drift_model(panel)→DriftModel`：按 (SP档×MTK桶) 在**全腿**上估 mean(ratio)、sd(ratio)、n，小样本格**收缩**到 band/全局先验；确定性 | 确定性表；小 n 格向先验收缩；脚本输出表；单测 |
| **P2** 保守分位调整 | 把模型变成 haircut | `DriftModel.adjusted_sp(sp,mtk,q=0.25)`：返回 `sp×quantile_q(ratio｜band,mtk)`（正态/对数正态近似）；q=0.5 退化为均值点估计 | σ 越大/MTK 越早 → haircut 越狠；q=0.5≈均值；单测 |
| **P3** forward arm | OOS 对照 | `forward.py` 加 `QHC` arm：qualify/size 前用 DriftModel 保守分位调 SP（类比 C2 但用模型+分位）；runner+报告+单测；不进 GATE-FT | ledger 出 QHC 行；报告显示其 ROI/命中/σ；单测；GATE-FT 不受影响 |
| **P4** 复盘 + go/no-go | 读 OOS 对照决定下一步 | 读 C0 vs C2 vs QHC，写复盘；决定 (a)加特征 (b)继续累积 (c)搁置；更新本计划 | 复盘文档；明确决定 |

## 5. 每卡纪律

TDD（红-绿-重构）→ **本地 commit（不 push）** → 交 reviewer 审本地 commit → **审核通过才 push** → **复盘**（评估发现、按需调整后续卡）→ 下一卡。

## 6. 验证

每卡：单测全绿 + reviewer 通过 + 脚本输出可复现（同命令两次一致）。

## 7. 风险

- **数据薄（16 期）+ 高 MTK 覆盖可能少**：MVP 用低维 + 收缩；P1 会暴露可测到什么粒度，据此在 P4 调整。
- **幸存者偏差**：用 panel 全腿（含未命中）测 ratio，不用命中腿。
- **过拟合**：MVP 不调参寻优；保守分位是稳健化手段；forward 是 OOS 闸。
