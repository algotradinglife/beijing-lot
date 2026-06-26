# N=7 主策略 + 1h 冷门尾仓评估报告

**日期:** 2026-06-26
**数据:** `data/derived/beidan_xlsm/beidan_xlsm.sqlite`，当前可评估期号从 2024 年到 `25042`
**目标:** 完成 1-3：滚动选择器防过拟合验证、资金单位落地、最新期候选清单导出。

## 1. 结论

当前不建议再上“滚动自适应选择触发器”作为生产层。滚动选择器只用过去期选择规则，整体 ROI 从主策略的 64.23% 提到 73.94%，但低于固定保守触发器的 77.46%。这说明冷门尾仓方向有增益，但现阶段更该冻结简单、可解释的触发规则。

建议冻结的候选策略是：

- 主策略：`confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2`
- 尾仓：`cold_snapshot=1h`，`N=3`，`odds>=5`，`model_p>=0.16`，`model/market>=1.25`，`rank>=3`，`top2`
- 重叠过滤：`cold_overlap_filter=match`，整场避开主策略已经覆盖的比赛
- 触发器：`n_cold_candidate_matches>=15` 且 `n_q_legs>=180`
- 资金：触发时 `80% main / 20% cold`，否则 `100% main`

`n_q_legs>=100 + cold_pred_hit_prob<=0.10` 的激进版历史表现更好，但 `pred_hit_prob<=0.10` 这个条件不够自然，过拟合风险明显，应放入观察池，不作为当前冻结方案。

## 2. 主策略 vs 尾仓

汇总口径为 `train_issues=8,12,16,20` 四组敏感性结果相加，因此不是单一真实资金曲线，而是参数稳健性横截面。

| 策略 | 触发期数 | budget units | profit units | ROI | maxDD units |
| --- | ---: | ---: | ---: | ---: | ---: |
| `main_only` | 0 / 240 | 18820.0 | 12087.9 | 64.23% | 1120.1 |
| 保守尾仓 `cand15_q180` | 74 / 240 | 18820.0 | 14578.1 | 77.46% | 1084.5 |
| 激进尾仓 `cand15_q100_pmax10` | 81 / 240 | 18820.0 | 15751.3 | 83.69% | 1084.5 |
| 滚动选择器 | 47 / 240 | 18820.0 | 13914.8 | 73.94% | 1084.5 |
| 滚动选择器 trailing=12 | 34 / 240 | 18820.0 | 12550.6 | 66.69% | 1120.1 |

判断：

- 冷门尾仓不是靠“和主策略叠加更多预算”产生收益，而是在同预算下用小比例预算替代主策略预算。
- 固定保守触发器比滚动选择器更好，说明当前没有必要做 meta selector。
- 激进触发器提升最大，但它使用的 `pred_hit_prob<=0.10` 可能是在当前样本里碰巧切掉坏期，必须样本外验证。

## 3. 资金单位落地

脚本用 `unit_yuan=2`、`bankroll_yuan=10000`、历史 maxDD 上限 15%、单期最大亏损上限 3% 做换算。

关键结果：

- 保守/激进方案最坏窗口 maxDD 为 `1084.5 units`。
- 如果 1 unit = 2 RMB，则历史 maxDD 约 `2169 RMB`，占 10000 RMB 本金的 `21.7%`。
- 若坚持 15% 历史 maxDD cap，则 10000 RMB 本金下 unit 上限约 `1.38 RMB`。
- 如果彩票实际最小单位是 2 RMB，则满足 15% maxDD cap 需要本金约 `14,500 RMB` 以上。
- 最坏单期亏损为 `80 units`，即 2 RMB/unit 下 `160 RMB`，只占 10000 RMB 的 1.6%，单期亏损不是主要约束，连续回撤才是主要约束。

实盘建议：

- 纸面跟踪阶段可以用 2 RMB/unit。
- 若实盘本金只有 10000 RMB，需要接受历史级别约 22% maxDD，或降低触发频率。
- 若要严格 15% maxDD，按当前历史轨迹估计至少准备约 1.45 万 RMB 本金。

## 4. 最新期候选清单

`scripts/export_combo_live_candidates.py` 导出了当前 DB 的最后一期 `25042`。注意：这是当前数据文件里的最后一期历史数据，赛程时间在 2025-04-09 到 2025-04-15，不是 2026-06-26 的真实最新期。

导出决策：

| issue | triggered | main_share | cold_share | main_budget_units | cold_ticket_stake_units | cold_pred_hit_prob | cold_pred_ev_per_stake | n_cold_candidate_matches | n_q_legs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 25042 | 1 | 0.80 | 0.20 | 80.0 | 1.0 | 5.93% | 176.19 | 31 | 285 |

尾仓票：

- `192259:0@-2`
- `192514:0@-2`
- `192651:0@-2`

这里的预测 EV 非常高，不能按字面当成真实 edge。它更像“模型认为市场严重低估”的排序信号，仍要经过前向纸面验证。

## 5. 复现命令

语法检查：

```bash
python3 -m py_compile scripts/evaluate_combo_main_cold_tail.py scripts/evaluate_combo_trigger_selector.py scripts/plan_combo_bankroll.py scripts/export_combo_live_candidates.py
```

防过拟合选择器：

```bash
python3 scripts/evaluate_combo_trigger_selector.py --output-dir results/combo_trigger_selector_default
python3 scripts/evaluate_combo_trigger_selector.py --output-dir results/combo_trigger_selector_dd025 --dd-penalty 0.25
python3 scripts/evaluate_combo_trigger_selector.py --output-dir results/combo_trigger_selector_trailing12 --trailing-issues 12
```

资金单位换算：

```bash
python3 scripts/plan_combo_bankroll.py --output-dir results/combo_bankroll_plan_default --unit-yuan 2 --bankroll-yuan 10000 --max-dd-pct 0.15 --max-issue-loss-pct 0.03
```

最新期候选导出：

```bash
python3 scripts/export_combo_live_candidates.py --output-dir results/combo_live_candidates_default
```

## 6. 新增文件

- `scripts/evaluate_combo_trigger_selector.py`
- `scripts/plan_combo_bankroll.py`
- `scripts/export_combo_live_candidates.py`
- `docs/research/n7_combo_cold_tail_report_2026-06-26.md`
- `docs/research/n7_combo_cold_tail_handoff_2026-06-26.md`

## 7. 风险与下一步

最大风险是“用 final snapshot 形成主策略”与真实 1h/2-4h 入场口径不完全一致。尾仓已经使用 `cold_snapshot=1h`，但主策略仍需专门跑 `main_snapshot=1h` 或 `10h` 的可落地口径版本。

下一步建议：

1. 用保守触发器做前向纸面跟踪，冻结参数，不再在同一批历史数据上调参。
2. 复跑 `main_snapshot=1h` 和 `main_snapshot=10h`，比较收益是否仍来自可实盘获得的信息。
3. 将 `export_combo_live_candidates.py` 接入真实未结算数据源，确保候选导出完全不依赖 `winning_sp/result_code/hit`。

## 8. 投后验证更新

2026-06-26 复跑 `docs/research/n7_combo_cold_tail_validation_2026-06-26.md` §3 的单窗口口径：`train_issues=12`、62 期、`cold_snapshot=1h`、`cold_overlap_filter=match`、保守触发器 `n_cold_candidate_matches>=15` 且 `n_q_legs>=180`。`main_only` 结果为：

| main_snapshot | ROI | stake units | profit units |
| --- | ---: | ---: | ---: |
| `final` | 43.9% | 4870.0 | 2138.1 |
| `1h` | 10.9% | 4874.0 | 533.6 |
| `10h` | 9.0% | 4883.0 | 438.8 |

留一期检验：去掉最佳单期 `24041` 后，其余 61 期净额为 `-467.6` units，ROI `-9.8%`，9/62 期盈利。上述数字与验证文档一致：基于 `main_snapshot=final` 的 64-84% ROI **不是可实盘落地的 edge**（final 用了≈结算价的信息选腿）。

### §8 补注（v2 修正，2026-06-26，Claude；Codex 因额度限制待复核）

用户反馈纠正了"留一期变负 → 否定"这个判据：**收益集中是正偏态彩票的正常形态，留一期对偏态分布必然变难看，只能说明 62 期太短、无法判定，不能证伪。** 故修正结论为：

- **确凿**：`main_snapshot=final` 的 near-lookahead 把 headline 抬高；实盘入场（1h/10h）单窗口 ~9-11%。**"64-84%"不可落地、不应据此冻结。**
- **未证伪（非已证伪）**：实盘口径 ~9-11% 是正的点估，受 62 期小样本 + 偏态限制无法判真假。**不应据 62 期把冷门尾仓方向判死。**
- **正确下一步**：长周期预注册前向纸面测（实盘可得入场 / 单一资金曲线 / bootstrap CI 接受宽区间 / 真北单 SP 逐期结算 / 数月-数年）。详见 `docs/research/n7_combo_cold_tail_validation_2026-06-26.md`（v2）。
