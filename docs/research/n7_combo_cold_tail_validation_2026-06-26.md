# 验证：N=7 主策略 + 冷门尾仓 — 64% headline 是 lookahead 抬高；实盘口径未证伪但**需长周期检验**

**日期**: 2026-06-26（v2，2026-06-26 按用户反馈修正"集中度"框定）
**作者**: Claude（应用户「你看看」对 Codex 的 N7 combo 工作做独立验证）
**被验证**: `docs/research/n7_combo_cold_tail_report_2026-06-26.md` + `_handoff_`（Codex，已 merge 到 main 8832f59）
**复现**: 见 §3（即 Codex handoff 的 TODO #2「复跑 main_snapshot=1h/10h」）
**关联**: [[sp-drift-study]]（漂移=决策SP选腿诅咒）、[[n_walkforward]]（A1）、[[track_b_beat_the_close]]、[[moonshot-high-n]]

---

## 0. 结论先行（两点要分开）

Codex 的**工程诚实扎实**（真北单 winning_sp 结算、walk-forward 只用过去期、0.65 房费、特征无赛果泄露，且主动标注了风险）。验证后要把两件事**分开**说：

1. **64-84% 的 headline 被 `main_snapshot=final` 的 near-lookahead 抬高——这点确凿。** 改成实盘可得的 1h/10h 入场，单窗口 main_only ROI 从 43.9% 降到 ~9-11%（headline 还额外把 4 个 train 窗口相加放大）。**所以"64%"不是可落地数字，不应据此冻结/纸面当 edge。**
2. **但实盘口径下 ~9-11% 的 ROI 是"未证伪"，不是"已证伪"。** 它是**正的点估**，只是 62 期太短、无法判定真假。**收益集中（多数利润来自少数大赚）对一个正偏态彩票是正常形态，不是缺陷**——用"留一期变负"去否定它是**用错了判据**（从偏态小样本里抽掉那次大赚，本来就会变难看）。正确表述是：**样本太短，需要更长周期检验**（用户反馈，已采纳）。

## 1. 确凿的问题：`main_snapshot=final` 是 near-lookahead

脚本用某 snapshot 的**博彩赔率**选腿/定 score，但结算付**真北单 winning_sp**。`final`=收盘博彩赔率 ≈ 你被付的结算价 → 决策价≈结算价 → **漂移/赢家诅咒被消掉**（[[sp-drift-study]]：drift_gm final≈1.0 → 1h 0.96 → 10h 0.85 → 19.6h 0.758）。换实盘入场：

| 入场 snapshot | main_only ROI（train_issues=12，单窗口，62 期） |
|---|---|
| `final`（收盘≈结算价，**非实盘可得**） | 43.9% |
| `1h`（开赛前1h） | **10.9%** |
| `10h`（开赛前10h） | **9.0%** |

这点与偏态无关，是口径问题：headline 用了≈结算价的信息选腿。**实盘要用 ≤1h/2-4h 且确认真实可下注时点的 snapshot。**

## 2'. "集中度"该怎么读（修正我先前的过度解读）

之前我用"留一期变负 / best_issue_profit_share 188-233% / 仅 9-10 期盈利"来否定，**这是错的**：

- **正偏态彩票本就该集中**——平时小赚或小亏、偶尔大赚。要是不集中，它就不是彩票了。
- 留一期/去最佳期对偏态分布"必然变难看"，所以它**不能证伪**，只能说明 **62 期不足以估计这种分布的均值**。
- 因此实盘口径的 ~9-11% 点估**既没被证实、也没被证伪**——结论是**信息不足，需长周期**。

**冷门尾仓**：实盘入场 main+cold 仅 +0.5pp，但同理——增益太稀、样本太短，**无法判定**（不是"无增益"的定论）。报告"+13-20pp"确有问题，但问题是 (a) 建立在被 lookahead 抬高的 final 基线上、(b) 多组触发器在同一历史择优，**这两点是真问题**；至于尾仓本身有没有薄 edge，同样要长周期才知道。

## 2. 与既有研究一致

- [[track_b_beat_the_close]]：19 万场，外部因子赢不过收盘线（OOS log-loss Δ≈0）——**但 log-loss 测不到薄尾部 edge**；偏态彩票的微 edge 只在长周期 PnL 上显形，故 Track B 不能完全关闭"冷门尾仓可能有薄 +EV"这条。
- [[sp-drift-study]] / [[n_walkforward]]：决策价→结算价漂移是结构亏损主因。
- 本验证：换实盘入场，headline 从 43.9% 降到 ~9-11%（lookahead 确凿）；但 ~9-11% 本身**未证伪**，受样本太短限制。市场有效是强先验，但这条具体彩票"未关闭"。

## 3. 复现

```bash
for snap in final 1h 10h; do
  PYTHONPATH=".:src" .venv/bin/python scripts/evaluate_combo_main_cold_tail.py \
    --train-issues 12 --main-snapshot $snap --cold-snapshot 1h --cold-overlap-filter match \
    --trigger-min-cold-candidate-matches 15 --trigger-min-q-legs 180 \
    --output-dir results/snaptest_$snap
done
# 看 results/snaptest_*/combo_summary.csv 的 main_only 行：roi / best_issue_profit_share
# 留一期：读 combo_issue_profit.csv 的 main_only，去掉 max(profit) 期重算 ROI
```

## 4. 建议

1. **别把 64-84% 当可落地 edge**（那是 lookahead + 跨窗相加的产物）。但**也别据 62 期就把冷门尾仓方向判死**——它**未证伪**。
2. **核心瓶颈是数据周期，且是硬约束**：要判定一个正偏态彩票，需要足够多的"偶尔大赚"，即长样本。但回测被 historical_matches 的真 winning_sp 覆盖卡在 **2024-2025（~240 期）**；xlsm 有 2014+ 的比赛但**无北单 SP**（O7）。**现有数据无法长周期回测**——唯一诚实路径是**长周期预注册前向纸面测**：
   - 实盘可得入场（先确认北单真实可下注时点，1h 可能都偏乐观，2-4h 更现实）；
   - **单一资金曲线**（不跨窗相加、不在同一历史择优触发器）；
   - 用 **bootstrap CI 判读、并明确接受偏态→区间很宽、需数月到数年**（不是几周）；
   - 用真北单 SP 逐期结算累积。
3. 主仓维持低N纪律不变；登月仓只能 EV-agnostic（[[moonshot-high-n]] Track A）。真钱动作需用户确认。

## 5. 致谢、修正与局限

- Codex 的结算/walk-forward/无泄露做得对，且**主动列出了 main_snapshot=final 的风险**——本验证只是执行了它的 TODO。
- **修正（v2）**：本文 v1 用"留一期变负 / 集中度高"来否定该策略，**这是用错判据**——收益集中是正偏态彩票的正常形态，留一期对偏态分布必然变难看，只能说明**样本太短无法判定**，不能证伪。确凿的只有 `main_snapshot=final` 的 lookahead（kills the 64% headline）；实盘口径的 ~9-11% 是**未证伪**。
- 评估样本受 historical_matches 真 winning_sp 覆盖限制，仅 2024-2025 重叠 ~240 期、单窗口 62 期——**这正是"不能据此下结论"的核心原因，而非"已证伪"的依据**。
