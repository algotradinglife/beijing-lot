# 验证：N=7 主策略 + 冷门尾仓 的 64-84% ROI 不成立（实盘口径 + 留一期检验）

**日期**: 2026-06-26
**作者**: Claude（应用户「你看看」对 Codex 的 N7 combo 工作做独立验证）
**被验证**: `docs/research/n7_combo_cold_tail_report_2026-06-26.md` + `_handoff_`（Codex，已 merge 到 main 8832f59）
**复现**: 见 §3（即 Codex handoff 的 TODO #2「复跑 main_snapshot=1h/10h」）
**关联**: [[sp-drift-study]]（漂移=决策SP选腿诅咒）、[[n_walkforward]]（A1 单期脆弱性）、[[track_b_beat_the_close]]、[[moonshot-high-n]]

---

## 0. 结论先行

Codex 的**工程是诚实、扎实的**（真北单 winning_sp 结算、walk-forward 模型只用过去期、0.65 房费、特征无赛果泄露，且在文档里主动标注了主要风险）。**但报告的结论（主策略 ROI 64%、加尾仓 77-84%、建议冻结→纸面跟踪）不成立**：我执行了 Codex 自己列的 TODO #2（把入场口径从 `final` 改成实盘的 `1h`/`10h`），ROI 崩塌，且残余正收益完全来自单期运气。**不应作为 edge 推进到纸面/实盘。**

## 1. 两个独立的、各自致命的问题

**问题一：`main_snapshot=final` 是 near-lookahead。** 脚本用某 snapshot 的**博彩赔率**选腿/定 score，但结算付**真北单 winning_sp**。`final`=收盘博彩赔率 ≈ 你被付的结算价 → 决策价≈结算价 → **漂移/赢家诅咒被消掉**（[[sp-drift-study]]：drift_gm final≈1.0 → 1h 0.96 → 10h 0.85 → 19.6h 0.758）。把入场改成实盘可得的 1h/10h，ROI 从 43.9% 崩到 ~9-11%（单窗口；报告的 64% 还额外把 4 个 train 窗口**相加**放大）。

| 入场 snapshot | main_only ROI（train_issues=12，单窗口，62 期） |
|---|---|
| `final`（收盘≈结算价） | **43.9%** |
| `1h`（开赛前1h，实盘可得） | **10.9%** |
| `10h`（开赛前10h，实盘可得） | **9.0%** |

**问题二：实盘口径下，正收益全靠单期。** 留一期检验（去掉利润最大的 1 期）：

| 入场 | full ROI | 去掉最佳单期 ROI | 其余 61 期净额 | 盈利期 |
|---|---|---|---|---|
| `final` | 43.9% | +14.2% | +679 units | 12/62 |
| **`1h`** | 10.9% | **−9.8%** | **−468 units** | **9/62** |
| **`10h`** | 9.0% | **−12.2%** | **−584 units** | **10/62** |

`best_issue_profit_share` 在 1h/10h 是 **188% / 233%**——即单期利润 > 全部净利润，**其余 61 期合计亏损**。只有 ~15% 的期盈利。这是 [[n_walkforward]] A1「全靠一周」脆弱性的极端版：62 期小样本上的纯尾部方差，不是稳定 edge。

**冷门尾仓基本无增益**：实盘入场下 main+cold 仅 +0.5pp（11.4% vs 10.9%，本身是一两个冷门命中）。报告里「+13-20pp」是在被 lookahead 抬高的 `final` 基线上、叠加多组触发器配置在同一历史上择优（Codex 自己也标注激进版 `pred_hit_prob<=0.10` 过拟合）。

## 2. 与既有研究一致

- [[track_b_beat_the_close]]：19 万场、2014-2025，外部因子（含线移/排名/亚盘）赢不过收盘线（OOS log-loss Δ≈0）。
- [[sp-drift-study]] / [[n_walkforward]]：决策价→结算价漂移是结构亏损主因；小样本 ROI 被个位数命中主导、bootstrap CI 巨宽。
- 本验证：换实盘入场 + 留一期，64% 直接变 −10%。**市场有效、无可利用选腿 edge——再次坐实。**

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

1. **不要冻结/纸面跟踪此候选当 edge。** 实盘入场（1h/10h）下它是「去掉一个走运期就 −10%」。
2. 若仍想研究**冷门高赔率方向**，纪律必须是：(a) 只用实盘可得 snapshot（≤1h 也要确认 北单实际可下注时点）；(b) 单一资金曲线、不跨窗口相加；(c) 逐期 bootstrap CI + 留一期脆弱性（本验证已显示它过不了）；(d) 触发器不在同一历史上择优。
3. 主仓维持低N纪律不变；登月仓只能 EV-agnostic（[[moonshot-high-n]] Track A）。真钱动作需用户确认。

## 5. 致谢与局限

- Codex 的结算/walk-forward/无泄露做得对，且**主动列出了 main_snapshot=final 的风险**——本验证只是执行了它的 TODO。
- 本验证用 train_issues=12 单窗口；其他窗口量级相近（报告的 64% 是 8/12/16/20 四窗相加）。
- 评估样本受 historical_matches（真 winning_sp）覆盖限制，仅 2024-2025 重叠 ~240 期、单窗口 62 期——小样本本身就是「不能据此下结论」的核心原因。
